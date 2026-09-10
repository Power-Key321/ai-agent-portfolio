"""
收敛度量模块 — 收敛半径计算 + 收敛速度跟踪。

收敛公式（冷启动版本）:
    r_new = r_prev × (1 - α × c_added / C_max) × (1 - β × clarity)

    α = 约束权重系数 (默认 0.4)
    β = 反馈清晰度系数 (默认 0.3)
    c_added = 本轮新增约束数
    C_max = 该策略最大可能约束数
    clarity = 0 (无反馈) / 0.5 (隐式) / 1.0 (显式确认)

收敛速度:
    c = (r_initial - r_final) / N_spiral_iterations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 每种意图策略的最大约束数估计
STRATEGY_MAX_CONSTRAINTS = {
    "code_feature": 10,
    "code_fix": 6,
    "data_analysis": 8,
    "research": 6,
    "simple_query": 2,
    "refactor": 8,
}


def compute_convergence_radius(
    r_prev: float,
    constraints_added: int,
    strategy_id: str,
    user_feedback_clarity: float = 0.0,
    alpha: float = 0.4,
    beta: float = 0.3,
) -> float:
    """计算本轮收敛半径。

    Args:
        r_prev: 上一轮收敛半径
        constraints_added: 本轮新增约束数
        strategy_id: 策略ID，用于查最大约束数
        user_feedback_clarity: 0=无反馈, 0.5=隐式, 1.0=显式确认
        alpha: 约束权重系数
        beta: 反馈清晰度系数

    Returns:
        新的收敛半径 (0.0 ~ 1.0)
    """
    C_max = STRATEGY_MAX_CONSTRAINTS.get(strategy_id, 8)

    constraint_factor = 1.0 - alpha * (constraints_added / C_max)
    constraint_factor = max(0.05, constraint_factor)

    feedback_factor = 1.0 - beta * user_feedback_clarity
    feedback_factor = max(0.1, feedback_factor)

    r_new = r_prev * constraint_factor * feedback_factor
    return max(0.0, min(1.0, r_new))


def compute_convergence_speed(
    r_initial: float,
    r_final: float,
    spiral_iterations: int,
) -> float:
    """计算收敛速度 c。

    c = (r_initial - r_final) / spiral_iterations

    c 越大 → 少轮次达到高收敛 → 框架效果越好。
    理想情况: c > 0.3 (3轮内从1.0收敛到0.1以下)
    """
    if spiral_iterations <= 0:
        return 0.0
    return (r_initial - r_final) / spiral_iterations


def compute_convergence_radius_from_profile(
    r_prev: float,
    constraints_added: int,
    profile: "ProblemProfile",  # noqa: F821
    user_feedback_clarity: float = 0.0,
    alpha: float = 0.4,
    beta: float = 0.3,
) -> float:
    """从 ProblemProfile 计算收敛半径 (v4 自适应版)。

    与 compute_convergence_radius 的区别: C_max 从 profile 动态派生，
    而非查 STRATEGY_MAX_CONSTRAINTS 硬编码表。
    """
    from agent_harness.core.capability_assembler import CapabilityAssembler
    assembler = CapabilityAssembler()
    C_max = assembler.derive_max_constraints(profile)
    constraint_factor = max(0.05, 1.0 - alpha * constraints_added / max(1, C_max))
    feedback_factor = max(0.1, 1.0 - beta * user_feedback_clarity)
    r_new = r_prev * constraint_factor * feedback_factor
    return max(0.0, min(1.0, r_new))


@dataclass
class ConvergenceTracker:
    """跟踪单次任务的螺旋收敛过程。"""

    trace_id: str = ""
    strategy_id: str = ""
    r_initial: float = 1.0
    r_current: float = 1.0
    iterations: int = 0
    history: list[dict] = field(default_factory=list)
    final_convergence_speed: Optional[float] = None

    def record_iteration(
        self,
        constraints_added: int,
        user_feedback_clarity: float = 0.0,
        alpha: float = 0.4,
        beta: float = 0.3,
    ) -> float:
        """记录一轮螺旋，返回新的收敛半径。"""
        r_new = compute_convergence_radius(
            r_prev=self.r_current,
            constraints_added=constraints_added,
            strategy_id=self.strategy_id,
            user_feedback_clarity=user_feedback_clarity,
            alpha=alpha,
            beta=beta,
        )
        self.history.append({
            "iteration": self.iterations,
            "r_before": self.r_current,
            "r_after": r_new,
            "constraints_added": constraints_added,
            "feedback_clarity": user_feedback_clarity,
        })
        self.r_current = r_new
        self.iterations += 1
        return r_new

    def finalize(self) -> float:
        """标记收敛完成，返回收敛速度。"""
        c = compute_convergence_speed(
            self.r_initial, self.r_current, self.iterations
        )
        self.final_convergence_speed = c
        return c

    @property
    def converged(self, target: float = 0.05) -> bool:
        return self.r_current < target

    def summary(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "strategy_id": self.strategy_id,
            "r_initial": self.r_initial,
            "r_final": self.r_current,
            "iterations": self.iterations,
            "convergence_speed": self.final_convergence_speed,
            "history": self.history,
        }
