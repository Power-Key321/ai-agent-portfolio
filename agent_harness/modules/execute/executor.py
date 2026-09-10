"""
执行器 — 调用模型/工具执行子任务，含完整的失败分类、自愈策略、超时控制和断路器。

v2 新增:
- 超时控制: on_execute 执行超过 timeout_ms 自动中断
- 断路器: 连续 N 次失败自动熔断，冷却期后自动恢复
- 指数退避: retry_same 重试间隔指数增长
- 结构化日志: 所有执行事件带 trace_id
"""

from __future__ import annotations

import copy
import threading
import time as time_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.core.logging_setup import get_logger, get_trace_id
from agent_harness.core.observability import get_collector


# 失败类型 → 自愈策略映射表
FAILURE_SELF_HEAL_MAP = {
    "ambiguous_intent": "retry_refined",
    "tool_error": "retry_same",
    "context_overflow": "re_decompose",
    "model_hallucination": "re_decompose",
    "timeout": "re_decompose",
    "dependency_fail": "escalate_to_user",
}

# 自愈策略最大重试次数
SELF_HEAL_MAX_RETRIES = {
    "retry_same": 3,
    "retry_refined": 2,
    "re_decompose": 2,
}


class CircuitBreaker:
    """断路器 — 连续失败N次后熔断，冷却期内拒绝执行。

    状态机: CLOSED → (failures >= threshold) → OPEN → (cooldown expired) → HALF_OPEN → (success) → CLOSED
    """

    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 60.0):
        self.threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"
        self._logger = get_logger("circuit_breaker")

    @property
    def state(self) -> str:
        self._check_transition()
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    def success(self) -> None:
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._failures = 0
            self._logger.info("circuit_closed", state="CLOSED")
        elif self._state == "CLOSED":
            self._failures = 0

    def failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time_mod.time()
        if self._failures >= self.threshold:
            self._state = "OPEN"
            self._logger.warning(
                "circuit_opened",
                failures=self._failures,
                threshold=self.threshold,
                reset_seconds=self.reset_seconds,
            )

    def _check_transition(self) -> None:
        if self._state == "OPEN":
            elapsed = time_mod.time() - self._last_failure_time
            if elapsed >= self.reset_seconds:
                self._state = "HALF_OPEN"
                self._logger.info("circuit_half_open")


@dataclass
class Executor(ModuleBase):
    """执行器 — 执行单个子任务，产出结果或分类失败。

    Args:
        on_execute: 实际执行回调 (envelope, subtask) → ModuleResult
        timeout_ms: 单次执行超时（毫秒），0=不限制
        retry_same_max: retry_same 最大重试次数
        retry_refined_max: retry_refined 最大重试次数
        circuit_breaker_threshold: 断路器触发阈值
        circuit_breaker_reset_seconds: 断路器冷却时间（秒）
    """

    name = "execute"
    variant = "default"

    on_execute: Optional[callable] = field(default=None, repr=False)
    timeout_ms: int = 60000
    retry_same_max: int = 3
    retry_refined_max: int = 2
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: float = 60.0

    _breaker: CircuitBreaker | None = field(default=None, init=False, repr=False)
    _logger: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._breaker = CircuitBreaker(
            failure_threshold=self.circuit_breaker_threshold,
            reset_seconds=self.circuit_breaker_reset_seconds,
        )
        self._logger = get_logger("executor")

    def __repr__(self) -> str:
        return f"{self.name}.{self.variant}"

    @staticmethod
    def _spawn_isolated(envelope: Envelope, module_to: str) -> Envelope:
        """为并行执行创建隔离的 envelope（deep copy task 避免竞态）。"""
        child = envelope.spawn(module_to)
        child.task = copy.deepcopy(envelope.task)
        return child

    def process(self, envelope: Envelope) -> ModuleResult:
        subtasks = envelope.task.get("subtasks", [])
        if not subtasks:
            return ModuleResult(
                envelope=envelope,
                success=False,
                failure_class="ambiguous_intent",
                self_heal_strategy="retry_refined",
            )

        if self._breaker.is_open:
            self._logger.warning(
                "circuit_open_rejected",
                trace_id=get_trace_id(),
                breaker_state=self._breaker.state,
            )
            return ModuleResult(
                envelope=envelope,
                success=False,
                error="断路器已熔断，拒绝执行",
                failure_class="tool_error",
                self_heal_strategy="escalate_to_user",
            )

        execution_plan = envelope.task.get("execution_plan", {})
        batches = execution_plan.get("batches", [])
        max_parallel = envelope.task.get("max_parallel_subtasks", 4)

        all_results = []
        for batch in batches:
            subtask_ids = batch["subtask_ids"]
            is_parallel = batch.get("parallel", False) and len(subtask_ids) > 1

            if is_parallel:
                batch_results = self._execute_parallel_batch(
                    envelope, batch, subtasks, max_parallel,
                )
            else:
                batch_results = []
                for st_id in subtask_ids:
                    st = self._find_subtask(subtasks, st_id)
                    if st is None:
                        continue
                    envelope.task["_current_subtask"] = st
                    result = self._execute_with_retry(envelope, st, batch.get("timeout_ms"))
                    batch_results.append((st["id"], result))

            # 统一处理结果
            for st_id, result in batch_results:
                if not result.success:
                    result.failure_class = self._classify_failure(result)
                    result.self_heal_strategy = FAILURE_SELF_HEAL_MAP.get(
                        result.failure_class or ""
                    )
                    envelope.feedback.update({
                        "failure_class": result.failure_class,
                        "self_heal_applied": result.self_heal_strategy,
                    })
                    self._breaker.failure()
                    return result

                self._breaker.success()
                all_results.append({
                    "subtask_id": st_id,
                    "status": "success",
                    "artifacts": result.envelope.task.get("_artifacts", []),
                })

        envelope.task["execution_results"] = all_results
        envelope.task.pop("_current_subtask", None)
        envelope.task.pop("_artifacts", None)

        return ModuleResult(envelope=envelope)

    def _execute_parallel_batch(
        self, envelope: Envelope, batch: dict,
        subtasks: list, max_workers: int,
    ) -> list[tuple[str, ModuleResult]]:
        """使用 ThreadPoolExecutor 并发执行同一批次内的子任务。

        每个子任务获得隔离的 envelope 副本，互不干扰。
        """
        subtask_ids = batch["subtask_ids"]
        timeout_ms = batch.get("timeout_ms", self.timeout_ms)
        actual_workers = min(max_workers, len(subtask_ids))

        self._logger.info(
            "parallel_batch_start",
            subtask_ids=subtask_ids,
            workers=actual_workers,
        )

        results: list[tuple[str, ModuleResult]] = []
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            future_map = {}
            for st_id in subtask_ids:
                st = self._find_subtask(subtasks, st_id)
                if st is None:
                    continue
                child_env = self._spawn_isolated(envelope, f"execute.parallel.{st_id}")
                child_env.task["_current_subtask"] = st
                future = pool.submit(self._execute_with_retry, child_env, st, timeout_ms)
                future_map[future] = st_id

            for future in as_completed(future_map):
                st_id = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = ModuleResult(
                        envelope=envelope,
                        success=False,
                        error=f"并行执行异常: {e}",
                        failure_class="tool_error",
                    )
                results.append((st_id, result))

        self._logger.info(
            "parallel_batch_done",
            count=len(results),
        )
        return results

    def _execute_with_retry(
        self, envelope: Envelope, subtask: dict, timeout_ms: int | None = None
    ) -> ModuleResult:
        """带超时和指数退避的执行。"""
        timeout = timeout_ms or self.timeout_ms
        last_error = None

        for attempt in range(self.retry_same_max):
            result = self._execute_with_timeout(envelope, subtask, timeout)
            if result.success:
                return result
            last_error = result

            # 非 tool_error 不重试
            fc = self._classify_failure(result)
            if fc != "tool_error":
                return result

            if attempt < self.retry_same_max - 1:
                # 指数退避: 1s, 2s, 4s...
                backoff = 2 ** attempt
                self._logger.info(
                    "retry_with_backoff",
                    subtask=subtask.get("id"),
                    attempt=attempt + 1,
                    backoff_seconds=backoff,
                    error=result.error,
                )
                time_mod.sleep(backoff)

        return last_error or ModuleResult(envelope=envelope, success=False, error="max retries exceeded")

    def _execute_with_timeout(
        self, envelope: Envelope, subtask: dict, timeout_ms: int
    ) -> ModuleResult:
        """在独立线程中执行，超时则中断。"""
        if timeout_ms <= 0:
            return self._do_execute(envelope, subtask)

        result_holder: list[ModuleResult] = []
        error_holder: list[Exception] = []

        def target():
            try:
                result_holder.append(self._do_execute(envelope, subtask))
            except Exception as e:
                error_holder.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout_ms / 1000.0)

        if thread.is_alive():
            self._logger.warning(
                "execution_timeout",
                subtask=subtask.get("id"),
                timeout_ms=timeout_ms,
            )
            return ModuleResult(
                envelope=envelope,
                success=False,
                error=f"执行超时 ({timeout_ms}ms)",
                failure_class="timeout",
                self_heal_strategy="re_decompose",
            )

        if error_holder:
            return ModuleResult(
                envelope=envelope,
                success=False,
                error=str(error_holder[0]),
            )

        return result_holder[0] if result_holder else ModuleResult(
            envelope=envelope, success=False, error="no result produced",
        )

    def _do_execute(self, envelope: Envelope, subtask: dict) -> ModuleResult:
        if self.on_execute is not None:
            return self.on_execute(envelope, subtask)
        return self._default_execute(envelope, subtask)

    def _find_subtask(self, subtasks: list, st_id: str) -> Optional[dict]:
        for st in subtasks:
            if st["id"] == st_id:
                return st
        return None

    def _default_execute(self, envelope: Envelope, subtask: dict) -> ModuleResult:
        """无外部回调时的执行逻辑 — 生成结构化执行计划而非空占位。"""
        entities = envelope.task.get("entities", {})
        constraints = envelope.task.get("constraints", {})
        intent = envelope.task.get("original_input", "")

        execution_prompt = {
            "subtask_id": subtask["id"],
            "type": subtask.get("type", "execute"),
            "intent": intent,
            "context": {
                "language": entities.get("language"),
                "framework": entities.get("framework"),
                "files": entities.get("files_mentioned", []),
            },
            "constraints": constraints,
            "action": subtask["description"],
            "expected_output": self._expected_output_for(subtask),
        }

        envelope.task.setdefault("_artifacts", []).append({
            "type": "execution_plan",
            "subtask": subtask["id"],
            "description": subtask["description"],
            "execution_prompt": execution_prompt,
        })
        return ModuleResult(envelope=envelope)

    @staticmethod
    def _expected_output_for(subtask: dict) -> str:
        task_type = subtask.get("type", "")
        if task_type == "explore":
            return "项目结构分析和相关代码列表"
        elif task_type == "design":
            return "实现方案设计文档（含技术选型理由）"
        elif task_type == "code_gen":
            return "可直接运行的代码实现"
        elif task_type == "verify":
            return "验证报告（含测试结果和发现的问题）"
        else:
            return "执行结果"

    @staticmethod
    def _classify_failure(result: ModuleResult) -> str:
        """从错误信息推断失败类型。"""
        error = (result.error or "").lower()
        if any(kw in error for kw in ["not found", "no such file", "undefined", "不存在"]):
            return "model_hallucination"
        if any(kw in error for kw in ["timeout", "timed out", "超时"]):
            return "timeout"
        if any(kw in error for kw in ["context", "token", "length", "window"]):
            return "context_overflow"
        if any(kw in error for kw in ["permission", "denied", "权限", "access"]):
            return "dependency_fail"
        return "tool_error"


def classify_failure(error_message: str) -> str:
    """静态方法版本：从错误消息分类失败类型。"""
    msg = error_message.lower()
    if any(kw in msg for kw in ["not found", "no such file", "undefined", "不存在", "hallucin"]):
        return "model_hallucination"
    if any(kw in msg for kw in ["timeout", "timed out", "超时"]):
        return "timeout"
    if any(kw in msg for kw in ["context", "token", "length", "window", "overflow"]):
        return "context_overflow"
    if any(kw in msg for kw in ["permission", "denied", "权限", "access"]):
        return "dependency_fail"
    if any(kw in msg for kw in ["ambiguous", "unclear", "模糊", "不清楚"]):
        return "ambiguous_intent"
    return "tool_error"


def get_self_heal_strategy(failure_class: str) -> Optional[str]:
    return FAILURE_SELF_HEAL_MAP.get(failure_class)
