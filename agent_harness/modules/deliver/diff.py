"""Diff 交付 — 代码变更以 diff/patch 形式输出。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class DeliverDiff(ModuleBase):
    """代码变更交付 — 汇总所有子任务结果，组装为 diff 格式。"""

    name = "deliver"
    variant = "diff"

    def process(self, envelope: Envelope) -> ModuleResult:
        results = envelope.task.get("execution_results", [])
        artifacts = []
        for r in results:
            for a in r.get("artifacts", []):
                artifacts.append(a)

        envelope.task["final_deliverable"] = {
            "format": "diff_patch",
            "summary": f"执行了 {len(results)} 个子任务，产出 {len(artifacts)} 个变更",
            "artifacts": artifacts,
            "quality_self_assessment": {
                "completeness": 1.0 if all(r.get("status") == "success" for r in results) else 0.5,
                "known_gaps": [],
            },
        }
        return ModuleResult(envelope=envelope)
