"""
调度引擎 — 按装配指令串联模块，管理单轮螺旋内的执行生命周期。

与 SpiralRefiner 的关系:
- SpiralRefiner 控制"要不要再来一轮"（跨轮次）
- Orchestrator 控制"这一轮里面模块怎么跑"（轮次内）

运行流程 (单轮):
    1. 接收装配指令列表
    2. 按 position 排序
    3. 依次执行模块 process()
    4. 收集结果，处理失败/自愈
    5. 返回下一环节的 Envelope
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from agent_harness.core.envelope import Envelope
from agent_harness.core.convergence import ConvergenceTracker
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.observability import get_collector


@dataclass
class Orchestrator:
    """调度引擎 — 装配模块并执行单轮螺旋。

    Args:
        router: 意图路由器（Router 或 ModelRouter，鸭子类型）— 需实现 match() 和 assemble()
        module_registry: 模块注册表 { "preproc.code": ModuleBase实例, ... }
        on_before_module: 模块执行前回调(用于日志/监控)
        on_after_module: 模块执行后回调
    """

    router: object = field(default_factory=lambda: __import__("agent_harness.core.router", fromlist=["Router"]).Router())
    module_registry: dict[str, ModuleBase] = field(default_factory=dict)

    on_before_module: Optional[callable] = None
    on_after_module: Optional[callable] = None

    # 运行时状态
    _execution_log: list[dict] = field(default_factory=list, init=False)

    def register_module(self, module: ModuleBase) -> None:
        """注册一个模块变体到注册表。"""
        key = f"{module.name}.{module.variant}"
        self.module_registry[key] = module

    def register_modules(self, modules: list[ModuleBase]) -> None:
        for m in modules:
            self.register_module(m)

    def execute(self, envelope: Envelope) -> Envelope:
        """执行单轮螺旋：Router 匹配 → 装配 → 串行执行模块链。

        这是注入到 SpiralRefiner.on_spiral_complete 的回调。

        v4: 若启用自适应模式且存在 ProblemProfile，使用动态装配。
        """
        self._execution_log = []

        # v4 自适应路径: 根据 ProblemProfile 动态选择模块
        if getattr(self.router, 'is_adaptive', False) and envelope.problem_profile is not None:
            instructions = self.router.assemble_from_profile(envelope.problem_profile)
        else:
            strategy = self.router.match(envelope)
            instructions = self.router.assemble(strategy)
        instructions.sort(key=lambda x: x.position)

        for inst in instructions:
            key = f"{inst.module}.{inst.variant}"
            module = self.module_registry.get(key)
            if module is None:
                self._log(inst, "skipped", f"模块未注册: {key}")
                continue

            result = self._run_module(module, envelope)
            if result is None:
                continue

            envelope = result.envelope

            if not result.success:
                healed = self._apply_self_heal(result, envelope)
                if healed is not None:
                    envelope = healed
                else:
                    break

        return envelope

    def _run_module(self, module: ModuleBase, envelope: Envelope) -> Optional[ModuleResult]:
        env = envelope.spawn(f"{module.name}.{module.variant}")

        if self.on_before_module:
            self.on_before_module(module, env)

        t0 = time.time()
        try:
            result = module.process(env)
        except Exception as e:
            result = ModuleResult(
                envelope=env,
                success=False,
                error=str(e),
                failure_class="tool_error",
                self_heal_strategy="retry_same",
            )

        elapsed_ms = int((time.time() - t0) * 1000)
        self._log(module, result.success, result.error, elapsed_ms)

        # 记录到可观测性系统
        collector = get_collector()
        collector.record_module(
            f"{module.name}.{module.variant}",
            elapsed_ms, result.success, result.error,
        )

        if self.on_after_module:
            self.on_after_module(module, result, elapsed_ms)

        return result

    def _apply_self_heal(self, result: ModuleResult, envelope: Envelope) -> Optional[Envelope]:
        """应用自愈策略。返回 healed Envelope 或 None(不可自愈)。"""
        strategy = result.self_heal_strategy
        if strategy is None:
            return None

        fb = envelope.feedback
        fb["failure_class"] = result.failure_class
        fb["self_heal_applied"] = strategy

        if strategy == "retry_same":
            retry_count = fb.get("retry_count", 0)
            if retry_count < 3:
                fb["retry_count"] = retry_count + 1
                fb["retry_triggered"] = True
                return envelope
            return None

        if strategy == "retry_refined":
            envelope.add_constraint("_self_heal_refined", True)
            fb["retry_triggered"] = True
            return envelope

        if strategy == "re_decompose":
            fb["retry_triggered"] = True
            fb["self_heal_applied"] = "re_decompose"
            return envelope

        if strategy == "escalate_to_user":
            fb["self_heal_applied"] = "escalate_to_user"
            return None

        return None

    def _log(self, module, success: bool, error: Optional[str], elapsed_ms: int = 0) -> None:
        if hasattr(module, "name"):
            key = f"{module.name}.{module.variant}" if hasattr(module, "variant") else module.name
        else:
            key = f"{getattr(module, 'module', '?')}.{getattr(module, 'variant', '?')}"
        self._execution_log.append({
            "module": key,
            "success": success,
            "error": error,
            "elapsed_ms": elapsed_ms,
        })

    def get_execution_log(self) -> list[dict]:
        return self._execution_log
