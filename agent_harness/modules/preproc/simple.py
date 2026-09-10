from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class PreprocSimple(ModuleBase):
    """简单透传 — 用于 simple_query 等无需复杂预处理的场景。"""

    name = "preproc"
    variant = "simple"

    def process(self, envelope: Envelope) -> ModuleResult:
        envelope.task.setdefault("entities", {})
        envelope.task.setdefault("constraints", {})
        envelope.task["complexity_score"] = 0.1
        return ModuleResult(envelope=envelope)
