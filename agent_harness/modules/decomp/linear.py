"""线性拆解 — 将任务按阶段拆为串行子任务链。"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


class DecompLinear(ModuleBase):
    """按 explore → design → code_gen → verify 阶段线性拆解。"""

    name = "decomp"
    variant = "linear"

    def process(self, envelope: Envelope) -> ModuleResult:
        intent = envelope.task.get("normalized_intent") or envelope.task.get("original_input", "")
        entities = envelope.task.get("entities", {})
        complexity = envelope.task.get("complexity_score", 0.5)

        subtasks = []
        sid = 0

        # Phase 1: Explore (if existing codebase)
        if entities.get("existing_codebase") or envelope.task.get("constraints", {}).get("existing_codebase"):
            sid += 1
            subtasks.append({
                "id": f"s{sid}",
                "description": f"读取现有项目结构，收集与 '{intent}' 相关的代码",
                "type": "explore",
                "estimated_tokens": 5000,
                "dependencies": [],
            })

        # Phase 2: Design
        sid += 1
        subtasks.append({
            "id": f"s{sid}",
            "description": f"设计 '{intent}' 的实现方案",
            "type": "design",
            "estimated_tokens": 8000,
            "dependencies": [f"s{sid - 1}"] if sid > 1 else [],
        })

        # Phase 3: Implement
        sid += 1
        subtasks.append({
            "id": f"s{sid}",
            "description": f"实现 '{intent}'",
            "type": "code_gen",
            "estimated_tokens": int(15000 * complexity),
            "dependencies": [f"s{sid - 1}"],
        })

        # Phase 4: Verify (for medium+ complexity)
        if complexity > 0.3:
            sid += 1
            subtasks.append({
                "id": f"s{sid}",
                "description": f"验证 '{intent}' 的实现正确性",
                "type": "verify",
                "estimated_tokens": 8000,
                "dependencies": [f"s{sid - 1}"],
            })

        edges = []
        for st in subtasks:
            for dep in st["dependencies"]:
                edges.append({"from": dep, "to": st["id"]})

        envelope.task["subtasks"] = subtasks
        envelope.task["dag_edges"] = edges
        envelope.task["decomp_strategy"] = "linear"
        return ModuleResult(envelope=envelope)
