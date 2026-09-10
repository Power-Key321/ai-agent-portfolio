"""单步拆解 — 不拆子任务，整个任务作为一个执行单元。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class DecompSingle(ModuleBase):
    """不拆解，适用于简单查询和 bug 修复。"""

    name = "decomp"
    variant = "single"

    def process(self, envelope: Envelope) -> ModuleResult:
        envelope.task["subtasks"] = [{
            "id": "s1",
            "description": envelope.task.get("normalized_intent") or envelope.task.get("original_input", ""),
            "type": "execute",
            "estimated_tokens": 5000,
            "dependencies": [],
        }]
        envelope.task["dag_edges"] = []
        envelope.task["decomp_strategy"] = "single"
        return ModuleResult(envelope=envelope)
