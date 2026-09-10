"""
DAG Executor — 拓扑排序并行执行器。

将装配指令转成 DAG，按拓扑层级并行派发给子智能体。
复用现有 Orchestrator 的 AssemblyInstruction 结构。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from agent_harness.core.envelope import Envelope


@dataclass
class DAGNode:
    """执行 DAG 中的一个节点。

    Attributes:
        node_id: 唯一标识 (如 "preproc.code")
        module_type: 模块类型
        variant: 变体名
        depends_on: 此节点依赖的 node_id 列表
        batch_id: 拓扑层级 (同层可并行)
    """

    node_id: str
    module_type: str
    variant: str
    depends_on: list[str] = field(default_factory=list)
    batch_id: int = 0
    envelope: Optional[Envelope] = None
    result: Optional[Envelope] = None
    error: Optional[str] = None
    done: bool = False
    elapsed_ms: float = 0.0


@dataclass
class ExecutionDAG:
    """模块执行的有向无环图。"""

    nodes: dict[str, DAGNode] = field(default_factory=dict)
    batches: list[list[str]] = field(default_factory=list)  # 每个批次的 node_id 列表
    total_nodes: int = 0

    def add_node(self, node: DAGNode) -> None:
        self.nodes[node.node_id] = node
        self.total_nodes += 1

    def get_ready_nodes(self, batch_id: int) -> list[DAGNode]:
        """获取指定批次的所有就绪节点。"""
        return [self.nodes[nid] for nid in self.batches[batch_id] if nid in self.nodes]


@dataclass
class DAGExecutor:
    """DAG 感知的并行执行器。

    用法:
        executor = DAGExecutor(bus=agent_bus)
        dag = executor.build_dag(assembly_instructions)
        envelope = executor.execute_dag(dag, envelope)
    """

    bus: "AgentBus"  # noqa: F821
    on_execute_node: Optional[callable] = None  # 可选自定义执行回调
    max_workers: int = 6
    timeout_ms_per_node: int = 60000

    def build_dag(self, instructions: list) -> ExecutionDAG:
        """从装配指令列表构建执行 DAG。

        Args:
            instructions: AssemblyInstruction 对象列表，每个有 module/variant/position

        Returns:
            ExecutionDAG: 拓扑排序后的 DAG
        """
        dag = ExecutionDAG()

        # 按 position 分组为批次
        position_groups: dict[int, list] = defaultdict(list)
        for instr in instructions:
            pos = getattr(instr, "position", 0)
            position_groups[pos].append(instr)

        for pos in sorted(position_groups.keys()):
            batch_instructions = position_groups[pos]
            batch_ids = []

            for instr in batch_instructions:
                node_id = f"{instr.module}.{instr.variant}"
                # 依赖前一批次的所有节点
                depends_on = []
                if pos > 0 and (pos - 1) in dag.batches:
                    depends_on = list(dag.batches[pos - 1])

                node = DAGNode(
                    node_id=node_id,
                    module_type=instr.module,
                    variant=instr.variant,
                    depends_on=depends_on,
                    batch_id=len(dag.batches),
                )
                dag.add_node(node)
                batch_ids.append(node_id)

            dag.batches.append(batch_ids)

        return dag

    def execute_dag(self, dag: ExecutionDAG, envelope: Envelope) -> Envelope:
        """按拓扑顺序并行执行 DAG。

        Args:
            dag: 执行 DAG
            envelope: 初始 Envelope

        Returns:
            处理后的 Envelope
        """
        current_envelope = envelope

        for batch_id, batch_node_ids in enumerate(dag.batches):
            batch_nodes = dag.get_ready_nodes(batch_id)

            if len(batch_nodes) == 1:
                # 单节点顺序执行
                node = batch_nodes[0]
                result_env = self._execute_single_node(node, current_envelope)
                if result_env:
                    current_envelope = result_env
                    node.result = result_env
                    node.done = True
            else:
                # 多节点并行执行
                results = self._execute_parallel(batch_nodes, current_envelope)
                for node, result_env in results.items():
                    node.result = result_env
                    node.done = True
                # 合并结果到第一个成功的节点
                for node in batch_nodes:
                    if node.result and not node.error:
                        current_envelope = node.result
                        break

        return current_envelope

    def _execute_single_node(self, node: DAGNode, envelope: Envelope) -> Optional[Envelope]:
        """执行单个 DAG 节点。"""
        start = time.time()

        if self.on_execute_node:
            try:
                result = self.on_execute_node(node, envelope)
                node.elapsed_ms = (time.time() - start) * 1000
                return result
            except Exception as e:
                node.error = str(e)
                node.elapsed_ms = (time.time() - start) * 1000
                return None

        # 通过 AgentBus 分发
        agent_ids = self.bus.route(node.module_type, node.variant)
        if not agent_ids:
            node.error = f"无可用智能体: {node.module_type}.{node.variant}"
            return None

        from agent_harness.agents.base import AgentMessage
        message = AgentMessage(
            sender_id="dag_executor",
            recipient_id=agent_ids[0],
            envelope=envelope,
            message_type="task",
        )
        reply = self.bus.send(message, timeout_ms=self.timeout_ms_per_node)
        node.elapsed_ms = (time.time() - start) * 1000
        return reply.envelope

    def _execute_parallel(self, nodes: list[DAGNode], envelope: Envelope) -> dict[DAGNode, Optional[Envelope]]:
        """并行执行多个节点。"""
        results: dict[DAGNode, Optional[Envelope]] = {}

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(nodes))) as executor:
            futures = {
                executor.submit(self._execute_single_node, node, envelope): node
                for node in nodes
            }
            for future in as_completed(futures):
                node = futures[future]
                try:
                    results[node] = future.result()
                except Exception as e:
                    node.error = str(e)
                    results[node] = None

        return results
