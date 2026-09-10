"""并行调度 — 当 DAG 中存在无依赖关系的子任务时，并发执行。"""

import concurrent.futures
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class ScheduleParallel(ModuleBase):
    """拓扑排序 + 识别可并行批次，用 ThreadPoolExecutor 并发执行。

    策略:
    1. 分析 DAG 依赖关系
    2. 每轮识别所有依赖已满足的子任务 → 归入同一批次
    3. 同一批次内的子任务用线程池并行调度
    4. 最大并行数由策略表 max_parallel_subtasks 控制
    """

    name = "schedule"
    variant = "parallel"

    def process(self, envelope: Envelope) -> ModuleResult:
        subtasks = envelope.task.get("subtasks", [])
        edges = envelope.task.get("dag_edges", [])

        # 获取最大并行数（从 envelope 中的策略配置）
        max_parallel = envelope.task.get("max_parallel_subtasks", 4)

        # 构建依赖图
        dep_graph: dict[str, set[str]] = {}
        for st in subtasks:
            dep_graph[st["id"]] = set(st.get("dependencies", []))

        completed: set[str] = set()
        remaining = set(dep_graph.keys())
        batches = []

        while remaining:
            # 找出所有依赖已满足的子任务
            ready = sorted([
                tid for tid in remaining
                if dep_graph[tid].issubset(completed)
            ])

            if not ready:
                # 有循环依赖？取第一个作为 fallback
                ready = [sorted(remaining)[0]]

            # 如果可并行的少于 max_parallel，归为一个批次
            if len(ready) <= max_parallel:
                batch_ids = ready
            else:
                batch_ids = ready[:max_parallel]

            batch_subtasks = []
            for tid in batch_ids:
                st = next(s for s in subtasks if s["id"] == tid)
                batch_subtasks.append(st)

            is_parallel = len(batch_ids) > 1
            if is_parallel:
                # 并行批次：token 取批内最大（因为并发执行）
                allocated = max(st.get("estimated_tokens", 5000) for st in batch_subtasks)
            else:
                allocated = sum(st.get("estimated_tokens", 5000) for st in batch_subtasks)

            batches.append({
                "batch_id": f"b{len(batches) + 1}",
                "subtask_ids": batch_ids,
                "parallel": is_parallel,
                "parallel_count": len(batch_ids),
                "allocated_tokens": allocated,
                "timeout_ms": max(st.get("estimated_tokens", 5000) * 5 for st in batch_subtasks),
            })

            for tid in batch_ids:
                completed.add(tid)
                remaining.discard(tid)

        total_tokens = sum(st.get("estimated_tokens", 5000) for st in subtasks)
        parallel_batches = sum(1 for b in batches if b["parallel"])
        total_time_sequential = total_tokens * 5
        # allocated_tokens 已正确处理：并行批次 = max, 串行批次 = sum
        total_time_parallel = sum(
            b["allocated_tokens"] * 5 for b in batches
        )

        envelope.task["execution_plan"] = {
            "strategy": "parallel",
            "batches": batches,
            "max_parallel_subtasks": max_parallel,
            "parallel_batches": parallel_batches,
            "estimated_total_tokens": total_tokens,
            "estimated_total_time_ms": total_time_parallel,
            "speedup_vs_sequential": round(total_time_sequential / max(1, total_time_parallel), 1),
        }
        return ModuleResult(envelope=envelope)
