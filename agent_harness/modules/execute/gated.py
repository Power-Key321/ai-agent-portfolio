"""
ExecutorGated — 量化门检执行器。

在 Executor 基础上增加：
- 每子任务执行后运行4道量化门检
- 退化检测（degradation_streak 追踪）
- 自动降级策略（退化达上限 → 触发降级而非阻塞）
- 门检日志写入 envelope
"""

from __future__ import annotations

import copy
import time as time_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.core.deduction_engine import get_deduction_engine, GateResult
from agent_harness.modules.execute.executor import (
    Executor, CircuitBreaker, FAILURE_SELF_HEAL_MAP,
)
from agent_harness.core.logging_setup import get_logger, get_trace_id
from agent_harness.core.observability import get_collector


@dataclass
class ExecutorGated(ModuleBase):
    """门检执行器 — 每子任务执行后量化检测，自动降级。

    与 Executor 的区别：
    - 执行每个子任务后，强制运行4道门检
    - 门检失败累计到 degradation_streak
    - streak 达上限 → 触发降级策略（不阻塞后续子任务）
    - 降级后的子任务标记 DEGRADED 而非 FAILED
    """

    name = "execute"
    variant = "gated"

    on_execute: Optional[callable] = field(default=None, repr=False)
    timeout_ms: int = 60000
    retry_same_max: int = 3
    max_degradation_streak: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: float = 60.0

    _breaker: CircuitBreaker | None = field(default=None, init=False, repr=False)
    _engine: object = field(default=None, init=False, repr=False)
    _logger: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._breaker = CircuitBreaker(
            failure_threshold=self.circuit_breaker_threshold,
            reset_seconds=self.circuit_breaker_reset_seconds,
        )
        self._engine = get_deduction_engine()
        self._logger = get_logger("executor_gated")

    def __repr__(self) -> str:
        return f"{self.name}.{self.variant}"

    def process(self, envelope: Envelope) -> ModuleResult:
        subtasks = envelope.task.get("subtasks", [])
        if not subtasks:
            return ModuleResult(
                envelope=envelope,
                success=False,
                error="无子任务可执行",
                failure_class="ambiguous_intent",
                self_heal_strategy="retry_refined",
            )

        if self._breaker.is_open:
            return ModuleResult(
                envelope=envelope,
                success=False,
                error="断路器已熔断",
                failure_class="tool_error",
                self_heal_strategy="escalate_to_user",
            )

        execution_plan = envelope.task.get("execution_plan", {})
        batches = execution_plan.get("batches", [])
        max_parallel = envelope.task.get("max_parallel_subtasks", 4)
        collector = get_collector()

        all_results = []
        degradation_streak = 0
        gate_log = []

        for batch in batches:
            subtask_ids = batch["subtask_ids"]
            is_parallel = batch.get("parallel", False) and len(subtask_ids) > 1

            # ── 执行阶段 ──
            if is_parallel:
                batch_exec_results = self._execute_parallel_batch(
                    envelope, batch, subtasks, max_parallel,
                )
            else:
                batch_exec_results = []
                for st_id in subtask_ids:
                    st = self._find_subtask(subtasks, st_id)
                    if st is None:
                        continue
                    envelope.task["_current_subtask"] = st
                    t0 = time_mod.time()
                    result = self._execute_single(envelope, st, batch.get("timeout_ms"))
                    elapsed_ms = int((time_mod.time() - t0) * 1000)
                    batch_exec_results.append((st_id, result, elapsed_ms))

            # ── 门检阶段（串行：保持 degradation streak 语义）──
            for item in batch_exec_results:
                if len(item) == 3:
                    st_id, result, elapsed_ms = item
                else:
                    st_id, result = item
                    elapsed_ms = 0

                st = self._find_subtask(subtasks, st_id)
                if st is None:
                    continue

                # 4道门检
                gates = self._engine.run_gate_checks(
                    st,
                    self._extract_result_data(result, st),
                    round_num=envelope.spiral_iteration,
                )

                for g in gates:
                    collector.record_gate(st_id, g.gate_name, g.passed, g.details)

                # 退化检测
                should_degrade, degrade_reason = self._engine.detect_degradation(
                    gates, degradation_streak, self.max_degradation_streak,
                )

                if should_degrade:
                    degradation_streak += 1
                    fallback = st.get("fallback_strategy", "跳过此子任务")
                    gate_log.append({
                        "subtask_id": st_id,
                        "status": "DEGRADED",
                        "reason": degrade_reason,
                        "fallback": fallback,
                        "gates": [{"name": g.gate_name, "passed": g.passed,
                                    "detail": g.details} for g in gates],
                        "degradation_streak": degradation_streak,
                        "elapsed_ms": elapsed_ms,
                    })
                    collector.record_degradation(st_id, degrade_reason,
                                                 degradation_streak, fallback)
                    self._logger.warning(
                        "subtask_degraded",
                        subtask=st_id,
                        reason=degrade_reason,
                        fallback=fallback,
                        streak=degradation_streak,
                    )

                    if degradation_streak >= self.max_degradation_streak * 2:
                        self._logger.warning(
                            "severe_degradation_skip_remaining",
                            skipped_count=len(subtasks) - len(all_results) - 1,
                        )
                        all_results.append({
                            "subtask_id": st_id,
                            "status": "degraded",
                            "fallback_applied": fallback,
                        })
                        envelope.task["execution_results"] = all_results
                        envelope.task["gate_log"] = gate_log
                        envelope.task["degradation_total"] = degradation_streak
                        return ModuleResult(
                            envelope=envelope,
                            success=False,
                            error=f"严重退化: {degrade_reason}",
                            failure_class="tool_error",
                            self_heal_strategy="escalate_to_user",
                        )

                    all_results.append({
                        "subtask_id": st_id,
                        "status": "degraded",
                        "fallback_applied": fallback,
                    })
                    continue

                # 正常
                degradation_streak = max(0, degradation_streak - 1)
                gate_log.append({
                    "subtask_id": st_id,
                    "status": "success",
                    "gates": [{"name": g.gate_name, "passed": g.passed,
                                "detail": g.details} for g in gates],
                    "elapsed_ms": elapsed_ms,
                })
                all_results.append({
                    "subtask_id": st_id,
                    "status": "success",
                    "artifacts": result.envelope.task.get("_artifacts", []),
                })
                self._breaker.success()

        envelope.task["execution_results"] = all_results
        envelope.task["gate_log"] = gate_log
        envelope.task["degradation_total"] = degradation_streak
        envelope.task.pop("_current_subtask", None)
        return ModuleResult(envelope=envelope)

    def _execute_parallel_batch(
        self, envelope: Envelope, batch: dict,
        subtasks: list, max_workers: int,
    ) -> list[tuple]:
        """并发执行同一批次内的子任务，返回 (st_id, result, elapsed_ms) 列表。"""
        subtask_ids = batch["subtask_ids"]
        timeout_ms = batch.get("timeout_ms", self.timeout_ms)
        actual_workers = min(max_workers, len(subtask_ids))

        self._logger.info(
            "gated_parallel_batch_start",
            subtask_ids=subtask_ids,
            workers=actual_workers,
        )

        results: list[tuple] = []
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            future_map = {}
            for st_id in subtask_ids:
                st = self._find_subtask(subtasks, st_id)
                if st is None:
                    continue
                child_env = Executor._spawn_isolated(envelope, f"execute.gated.parallel.{st_id}")
                child_env.task["_current_subtask"] = st

                def _timed_execute(env, subtask, tmo):
                    t0 = time_mod.time()
                    r = self._execute_single(env, subtask, tmo)
                    elapsed = int((time_mod.time() - t0) * 1000)
                    return r, elapsed

                future = pool.submit(_timed_execute, child_env, st, timeout_ms)
                future_map[future] = st_id

            for future in as_completed(future_map):
                st_id = future_map[future]
                try:
                    result, elapsed_ms = future.result()
                except Exception as e:
                    result = ModuleResult(
                        envelope=envelope,
                        success=False,
                        error=f"并行执行异常: {e}",
                        failure_class="tool_error",
                    )
                    elapsed_ms = 0
                results.append((st_id, result, elapsed_ms))

        self._logger.info(
            "gated_parallel_batch_done",
            count=len(results),
        )
        return results

    def _execute_single(self, envelope: Envelope, subtask: dict,
                         timeout_ms: int | None = None) -> ModuleResult:
        """执行单个子任务（带重试）。"""
        timeout = timeout_ms or self.timeout_ms

        for attempt in range(self.retry_same_max):
            try:
                if self.on_execute is not None:
                    result = self.on_execute(envelope, subtask)
                else:
                    result = self._default_gated_execute(envelope, subtask)

                if result.success:
                    return result

                fc = result.failure_class or "tool_error"
                if fc != "tool_error":
                    return result

                if attempt < self.retry_same_max - 1:
                    time_mod.sleep(2 ** attempt)
            except Exception as e:
                if attempt == self.retry_same_max - 1:
                    return ModuleResult(
                        envelope=envelope, success=False,
                        error=str(e), failure_class="tool_error",
                    )
                time_mod.sleep(2 ** attempt)

        return ModuleResult(envelope=envelope, success=False,
                             error="max retries exceeded")

    def _default_gated_execute(self, envelope: Envelope,
                                subtask: dict) -> ModuleResult:
        """带门检感知的默认执行 — 产出结构化结果供门检。"""
        entities = envelope.task.get("entities", {})
        intent = envelope.task.get("original_input", "")

        quant_metric = subtask.get("quant_metric", {})
        execution_prompt = {
            "subtask_id": subtask["id"],
            "type": subtask.get("type", "execute"),
            "entropy_stage": subtask.get("entropy_stage", ""),
            "intent": intent,
            "context": {
                "language": entities.get("language"),
                "framework": entities.get("framework"),
                "files": entities.get("files_mentioned", []),
            },
            "action": subtask["description"],
            "quant_target": quant_metric,
            "fallback": subtask.get("fallback_strategy", ""),
            "expected_output": self._expected_output_for(subtask),
        }

        envelope.task.setdefault("_artifacts", []).append({
            "type": "gated_execution",
            "subtask": subtask["id"],
            "entropy_stage": subtask.get("entropy_stage", ""),
            "description": subtask["description"],
            "execution_prompt": execution_prompt,
            "gate_metrics": {
                quant_metric.get("name", "items_found"): 1,  # 占位，实际执行时替换
            },
        })
        return ModuleResult(envelope=envelope)

    def _extract_result_data(self, result: ModuleResult,
                              subtask: dict) -> dict:
        """从 ModuleResult 中提取门检所需的数据。"""
        data = {}
        # 从 artifacts 中提取量化数据
        artifacts = result.envelope.task.get("_artifacts", [])
        for a in artifacts:
            if a.get("subtask") == subtask["id"]:
                metrics = a.get("gate_metrics", {})
                data.update(metrics)

        # 估算产出数量
        matching = [a for a in artifacts if a.get("subtask") == subtask["id"]]
        data.setdefault("items_found", len(matching))
        data.setdefault("count", len(matching))

        return data

    @staticmethod
    def _find_subtask(subtasks: list, st_id: str) -> Optional[dict]:
        for st in subtasks:
            if st["id"] == st_id:
                return st
        return None

    @staticmethod
    def _expected_output_for(subtask: dict) -> str:
        stage = subtask.get("entropy_stage", "")
        outputs = {
            "信息源": "检索结果列表（含来源和相关性）",
            "过滤层": "筛选后的候选条目（含筛选理由）",
            "处理层": "处理/分析/编码结果",
            "产出层": "组装好的交付物",
            "验证层": "验证报告（含通过/失败项）",
        }
        return outputs.get(stage, "执行结果")
