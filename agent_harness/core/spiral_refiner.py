"""
螺旋收敛控制器 — v2 核心模块。

职责:
1. 管理每轮螺旋的 Envelope 生命周期
2. 计算收敛半径、判断是否继续螺旋
3. 协调 Router 在多轮间重新装配模块
4. 接收用户反馈并精炼约束

运行模型:
    while not envelope.converged and not envelope.exhausted:
        envelope = refiner.execute_spiral(envelope)
        feedback = observe_user_behavior()
        envelope = refiner.refine(envelope, feedback)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .envelope import Envelope
from .convergence import ConvergenceTracker, compute_convergence_radius


@dataclass
class SpiralRefiner:
    """螺旋收敛控制器。

    Args:
        convergence_threshold: 收敛阈值 ε，r < ε 时交付
        max_iterations: 最大螺旋轮次
        alpha: 约束权重系数
        beta: 反馈清晰度系数
        on_spiral_complete: 每轮螺旋完成后的回调(由Orchestrator注入)
        on_refine: 精炼意图的回调(由Router注入)
    """

    convergence_threshold: float = 0.05
    max_iterations: int = 5
    alpha: float = 0.4
    beta: float = 0.3

    # 注入回调
    on_spiral_complete: Callable[[Envelope], Envelope] | None = None
    on_refine: Callable[[Envelope, dict], Envelope] | None = None

    # 内部状态
    _tracker: ConvergenceTracker | None = field(default=None, init=False)

    def start(self, envelope: Envelope) -> Envelope:
        """初始化螺旋，用于新任务的第一轮。

        v4: 若存在 ProblemProfile，从中派生收敛参数覆盖默认值。
        """
        envelope.spiral_iteration = 0
        envelope.spiral_max_iterations = self.max_iterations
        envelope.convergence_radius = 1.0
        envelope.convergence_target = self.convergence_threshold

        # v4: Profile-derived convergence params
        if envelope.problem_profile is not None:
            from agent_harness.core.capability_assembler import CapabilityAssembler
            assembler = CapabilityAssembler()
            spiral_cfg = assembler.derive_spiral_config(envelope.problem_profile)
            envelope.spiral_max_iterations = spiral_cfg["max_iterations"]
            envelope.convergence_target = spiral_cfg["convergence_threshold"]

        self._tracker = ConvergenceTracker(
            trace_id=envelope.trace_id,
            strategy_id=envelope.strategy_id or "unknown",
        )
        return envelope

    def execute_spiral(self, envelope: Envelope) -> Envelope:
        """执行一轮螺旋。调用注入的 on_spiral_complete。"""
        if self.on_spiral_complete is None:
            raise RuntimeError("on_spiral_complete 未注入，无法执行螺旋")

        envelope.spiral_iteration = self._tracker.iterations if self._tracker else 0
        result = self.on_spiral_complete(envelope)

        if self._tracker:
            constraints_added = len(
                result.task.get("constraints_added_this_round", [])
            )
            clarity = self._infer_feedback_clarity(result)
            self._tracker.record_iteration(
                constraints_added=constraints_added,
                user_feedback_clarity=clarity,
                alpha=self.alpha,
                beta=self.beta,
            )
            result.convergence_radius = self._tracker.r_current

        return result

    def refine(self, envelope: Envelope, user_feedback: dict) -> Envelope:
        """根据用户反馈精炼 Envelope，准备下一轮螺旋。

        user_feedback 格式:
            {"signal": "accepted|modified|retried", "note": "...", "explicit_constraints": {...}}
        """
        if envelope.converged:
            return envelope

        if self.on_refine is not None:
            envelope = self.on_refine(envelope, user_feedback)

        clarity = self._infer_feedback_clarity(envelope)
        r_new = compute_convergence_radius(
            r_prev=self._tracker.r_current if self._tracker else envelope.convergence_radius,
            constraints_added=len(envelope.task.get("constraints_added_this_round", [])),
            strategy_id=envelope.strategy_id or "unknown",
            user_feedback_clarity=clarity,
            alpha=self.alpha,
            beta=self.beta,
        )
        envelope.convergence_radius = r_new

        return envelope.spawn_next_spiral() if envelope.should_continue_spiral else envelope

    def finalize(self, envelope: Envelope) -> dict:
        """完成所有螺旋，返回收敛摘要。"""
        if self._tracker:
            c = self._tracker.finalize()
            envelope.feedback["convergence_score"] = c
            envelope.feedback["steps_to_converge"] = self._tracker.iterations
            return self._tracker.summary()
        return {}

    def should_continue(self, envelope: Envelope) -> bool:
        return envelope.should_continue_spiral

    @staticmethod
    def _infer_feedback_clarity(envelope: Envelope) -> float:
        """从 Envelope 推断用户反馈清晰度。"""
        fb = envelope.feedback
        if fb.get("accepted") is True:
            return 1.0
        if fb.get("modified") is True:
            return 0.7
        if fb.get("retry_triggered") is True:
            return 0.3
        return 0.0
