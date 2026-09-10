"""
AgentSpec — 智能体规格定义。

描述每个子智能体的能力、成本和状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent_harness.agents.base import AgentStatus


@dataclass
class AgentCapability:
    """声明子智能体的专业领域。

    Attributes:
        module_type: preproc | decomp | schedule | context | execute | deliver | recovery
        variants: 可处理的变体列表 (如 ["deductive", "code", "full"])
        cost_profile: cheap | normal | expensive
        max_parallel: 同时处理的最大任务数
        requires_model: 是否需要 LLM 访问
    """

    module_type: str
    variants: list[str] = field(default_factory=lambda: ["default"])
    cost_profile: str = "normal"       # cheap | normal | expensive
    max_parallel: int = 1
    requires_model: bool = False

    def __post_init__(self):
        valid_costs = ("cheap", "normal", "expensive")
        if self.cost_profile not in valid_costs:
            raise ValueError(f"cost_profile must be one of {valid_costs}")


@dataclass
class AgentStats:
    """智能体运行统计。"""
    tasks_processed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    total_elapsed_ms: float = 0.0
    last_active_at: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if self.tasks_processed == 0:
            return 1.0
        return self.tasks_succeeded / self.tasks_processed

    @property
    def avg_elapsed_ms(self) -> float:
        if self.tasks_processed == 0:
            return 0.0
        return self.total_elapsed_ms / self.tasks_processed


@dataclass
class AgentSpec:
    """子智能体规格。

    Attributes:
        agent_id: 唯一标识 (如 "preproc_deductive_01")
        capabilities: 此智能体能处理的模块
        backend: inline | claude_subagent | api | local_fn
        status: 当前状态
        stats: 运行统计
        metadata: 额外元数据
    """

    agent_id: str
    capabilities: list[AgentCapability] = field(default_factory=list)
    backend: str = "inline"            # inline | claude_subagent | api | local_fn
    status: AgentStatus = AgentStatus.IDLE
    stats: AgentStats = field(default_factory=AgentStats)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        valid_backends = ("inline", "claude_subagent", "api", "local_fn")
        if self.backend not in valid_backends:
            raise ValueError(f"backend must be one of {valid_backends}")

    def get_module_keys(self) -> list[str]:
        """返回此智能体能处理的 module_type.variant 列表。"""
        keys = []
        for cap in self.capabilities:
            for variant in cap.variants:
                keys.append(f"{cap.module_type}.{variant}")
        return keys
