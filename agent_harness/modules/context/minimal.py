"""最小上下文 — 只做用户记忆检索，适合简单任务。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class ContextMinimal(ModuleBase):
    """最小上下文检索 — 仅检索用户记忆相关的指针。"""

    name = "context"
    variant = "minimal"

    def process(self, envelope: Envelope) -> ModuleResult:
        refs = envelope.context.get("refs", [])
        memory_refs = [r for r in refs if r.startswith("memory://user")]
        envelope.context["refs"] = memory_refs
        return ModuleResult(envelope=envelope)
