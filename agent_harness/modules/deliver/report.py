"""报告交付 — 分析/调研结果以报告格式输出。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class DeliverReport(ModuleBase):
    """报告交付 — 汇总分析/调研结果为结构化报告。"""

    name = "deliver"
    variant = "report"

    def process(self, envelope: Envelope) -> ModuleResult:
        results = envelope.task.get("execution_results", [])
        subtasks = envelope.task.get("subtasks", [])

        sections = []
        for r in results:
            st = next((s for s in subtasks if s["id"] == r.get("subtask_id")), None)
            sections.append({
                "title": st["description"] if st else r.get("subtask_id", ""),
                "status": r.get("status", "unknown"),
                "findings": r.get("artifacts", []),
            })

        envelope.task["final_deliverable"] = {
            "format": "report",
            "summary": f"完成 {len(results)} 个子任务的分析",
            "sections": sections,
            "quality_self_assessment": {
                "completeness": 1.0 if all(r.get("status") == "success" for r in results) else 0.5,
                "known_gaps": [],
            },
        }
        return ModuleResult(envelope=envelope)
