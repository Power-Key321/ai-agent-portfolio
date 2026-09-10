"""顺序调度 — 严格按依赖关系串行执行子任务。MVP 只实现此模式。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class ScheduleSequential(ModuleBase):
    """将 DAG 中的子任务按依赖顺序排列为串行批次。"""

    name = "schedule"
    variant = "sequential"

    def process(self, envelope: Envelope) -> ModuleResult:
        subtasks = envelope.task.get("subtasks", [])
        edges = envelope.task.get("dag_edges", [])

        dep_graph = {st["id"]: set(st.get("dependencies", [])) for st in subtasks}
        completed = set()
        remaining = set(dep_graph.keys())
        batches = []

        while remaining:
            ready = sorted([
                tid for tid in remaining
                if dep_graph[tid].issubset(completed)
            ])
            if not ready:
                break
            for tid in ready:
                st = next(s for s in subtasks if s["id"] == tid)
                batches.append({
                    "batch_id": f"b{len(batches) + 1}",
                    "subtask_ids": [tid],
                    "parallel": False,
                    "allocated_tokens": st.get("estimated_tokens", 5000),
                    "timeout_ms": 60000,
                })
                completed.add(tid)
                remaining.discard(tid)

        total_tokens = sum(st.get("estimated_tokens", 5000) for st in subtasks)
        envelope.task["execution_plan"] = {
            "strategy": "sequential",
            "batches": batches,
            "estimated_total_tokens": total_tokens,
            "estimated_total_time_ms": total_tokens * 5,  # rough estimate
        }
        return ModuleResult(envelope=envelope)
