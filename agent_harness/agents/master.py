"""
MasterAgent — 总协调器。

乐高城市的核心调度员:
- inline 模式: 直接委托 Orchestrator.execute()（零改动，原路径）
- distributed 模式: 将装配指令转成 DAG，通过 AgentBus 并行派发给子智能体
- 螺旋收敛: 每轮结束后检查收敛，未收敛则重新派发
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_harness.core.envelope import Envelope
from agent_harness.agents.bus import AgentBus
from agent_harness.agents.dag_executor import DAGExecutor, ExecutionDAG


@dataclass
class MasterAgent:
    """总协调器 — 管理子智能体并执行分布式流水线。

    用法:
        master = MasterAgent(bus=bus, orchestrator=orchestrator, refiner=refiner, router=router)

        # 内联模式 (原路径)
        env = master.execute(envelope, mode="inline")

        # 分布式模式
        env = master.execute(envelope, mode="distributed")
    """

    bus: AgentBus = field(default_factory=AgentBus)
    orchestrator: Optional["Orchestrator"] = None  # noqa: F821
    refiner: Optional["SpiralRefiner"] = None      # noqa: F821
    router: Optional["ModelRouter"] = None         # noqa: F821

    knowledge_graph: Optional["KnowledgeGraph"] = None  # noqa: F821
    graph_context: Optional["GraphContext"] = None      # noqa: F821

    mode: str = "inline"       # "inline" | "distributed"
    max_workers: int = 6
    dag_executor: Optional[DAGExecutor] = None

    # 统计
    _execution_count: int = 0
    _distributed_count: int = 0
    _total_spiral_rounds: int = 0

    def __post_init__(self):
        if self.dag_executor is None:
            self.dag_executor = DAGExecutor(
                bus=self.bus,
                max_workers=self.max_workers,
            )

    def execute(self, envelope: Envelope, mode: str | None = None) -> Envelope:
        """执行任务。

        Args:
            envelope: 初始 Envelope (已包含 intent_class + strategy_id)
            mode: "inline" | "distributed" (默认使用 self.mode)

        Returns:
            处理后的 Envelope
        """
        mode = mode or self.mode
        self._execution_count += 1

        if mode == "inline":
            return self._execute_inline(envelope)
        else:
            return self._execute_distributed(envelope)

    # ── 内联模式 (原路径，零改动) ──

    def _execute_inline(self, envelope: Envelope) -> Envelope:
        """内联模式: 直接委托现有 Orchestrator。"""
        if self.orchestrator is None:
            raise RuntimeError("orchestrator is required for inline mode")

        # 图谱上下文注入 (如果可用)
        if self.graph_context:
            self.graph_context.inject_to_envelope(envelope)

        return self.orchestrator.execute(envelope)

    # ── 分布式模式 ──

    def _execute_distributed(self, envelope: Envelope) -> Envelope:
        """分布式模式: DAG 感知并行派发。"""
        self._distributed_count += 1
        spiral_round = 0

        while envelope.should_continue_spiral:
            spiral_round += 1
            self._total_spiral_rounds += 1

            # 图谱上下文注入 (每轮更新)
            if self.graph_context:
                self.graph_context.inject_to_envelope(envelope)

            # 1. 获取策略和装配指令
            if self.router:
                strategy = self.router.match(envelope)
                instructions = self.router.assemble(strategy)
            else:
                raise RuntimeError("router is required for distributed mode")

            # 2. 构建 DAG
            dag = self.dag_executor.build_dag(instructions)

            # 3. 执行 DAG
            envelope = self.dag_executor.execute_dag(dag, envelope)

            # 4. 螺旋收敛检查
            if self.refiner and envelope.converged:
                break

            if self.refiner:
                envelope = self.refiner.refine(envelope, {"signal": "accepted"})

        return envelope

    # ── 设置 ──

    def set_mode(self, mode: str) -> None:
        """切换执行模式。"""
        if mode not in ("inline", "distributed"):
            raise ValueError(f"mode must be 'inline' or 'distributed', got '{mode}'")
        self.mode = mode

    def set_graph(self, kg: "KnowledgeGraph") -> None:  # noqa: F821
        """挂载知识图谱。"""
        from agent_harness.knowledge.graph_context import GraphContext
        self.knowledge_graph = kg
        self.graph_context = GraphContext(kg)
        kg.open()

    def register_module_agents(self, modules: list) -> None:
        """将现有 ModuleBase 实例包装为 InlineSubAgent 并注册。

        Args:
            modules: ModuleBase 实例列表 (来自 AdapterBase._register_modules())
        """
        from agent_harness.agents.sub_agents.inline_agent import InlineSubAgent
        from agent_harness.agents.spec import AgentSpec, AgentCapability

        for module in modules:
            spec = AgentSpec(
                agent_id=f"inline_{module.name}_{module.variant}",
                capabilities=[
                    AgentCapability(
                        module_type=module.name,
                        variants=[module.variant],
                        cost_profile="cheap",
                        max_parallel=1,
                        requires_model=False,
                    )
                ],
                backend="inline",
            )
            agent = InlineSubAgent(spec=spec, module=module)
            self.bus.register(agent)

    # ── 查询 ──

    def get_status(self) -> dict:
        return {
            "mode": self.mode,
            "agents_registered": len(self.bus.list_agents()),
            "capabilities": self.bus.list_capabilities(),
            "execution_count": self._execution_count,
            "distributed_count": self._distributed_count,
            "total_spiral_rounds": self._total_spiral_rounds,
            "graph_node_count": self.knowledge_graph.storage.get_node_count() if self.knowledge_graph else 0,
        }
