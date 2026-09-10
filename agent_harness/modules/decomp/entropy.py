"""
DecompEntropy — 熵减链分解模块。

沿碳基大脑演绎法的熵减链（信息源→过滤层→处理层→产出层→验证层）拆解任务，
每个子任务自动补全8维规格（目标/成功标准/动作/量化指标/产出物/输入依赖/停止条件/风险预判）。
"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.core.deduction_engine import get_deduction_engine


class DecompEntropy(ModuleBase):
    """熵减链分解 — 沿5阶段熵减链拆解，每子任务8维补全。

    替代 DecompLinear 的固定 explore→design→implement→verify 模板，
    根据任务类型选择合适的熵减链。
    """

    name = "decomp"
    variant = "entropy"

    def __init__(self):
        self._engine = get_deduction_engine()

    def process(self, envelope: Envelope) -> ModuleResult:
        intent = envelope.intent_class or ""
        user_input = (envelope.task.get("normalized_intent") or
                       envelope.task.get("original_input", ""))
        entities = envelope.task.get("entities", {})
        complexity = envelope.task.get("complexity_score", 0.5)
        five_elements = envelope.task.get("five_elements", {})

        # 沿熵减链拆解
        specs = self._engine.build_entropy_subtasks(
            intent_class=intent,
            user_input=user_input,
            entities=entities,
            complexity=complexity,
        )

        # 转换 SubtaskSpec → envelope subtask dict（兼容下游模块）
        subtasks = []
        for spec in specs:
            st = {
                "id": spec.id,
                "description": spec.name,
                "type": self._map_entropy_to_type(spec.entropy_stage),
                "entropy_stage": spec.entropy_stage,
                "estimated_tokens": self._estimate_tokens(spec.entropy_stage, complexity),
                "dependencies": self._resolve_dep_ids(spec.input_dependencies, specs),
                # 8维补全
                "goal": spec.goal,
                "success_criteria": spec.success_criteria,
                "actions": spec.actions,
                "quant_metric": {
                    "name": spec.quant_metric_name,
                    "unit": spec.quant_metric_unit,
                    "target": spec.quant_metric_target,
                },
                "stop_conditions": spec.stop_conditions,
                "risk_prediction": spec.risk_prediction,
                "fallback_strategy": spec.fallback_strategy,
            }
            subtasks.append(st)

        # 构建 DAG 边
        edges = []
        for st in subtasks:
            for dep in st["dependencies"]:
                edges.append({"from": dep, "to": st["id"]})

        # 写入 envelope
        envelope.task["subtasks"] = subtasks
        envelope.task["dag_edges"] = edges
        envelope.task["decomp_strategy"] = "entropy_chain"
        envelope.task["entropy_chain"] = [s.entropy_stage for s in specs]
        envelope.task["five_elements_applied"] = bool(five_elements)

        # 记录分解质量
        dep_completeness = sum(
            1 for st in subtasks if st["dependencies"] or st["entropy_stage"] == "信息源"
        ) / max(1, len(subtasks))
        envelope.task["decomp_quality"] = {
            "total_stages": len(subtasks),
            "dependency_completeness": dep_completeness,
            "fallback_coverage": sum(
                1 for st in subtasks if st.get("fallback_strategy")
            ) / max(1, len(subtasks)),
        }

        return ModuleResult(envelope=envelope)

    @staticmethod
    def _map_entropy_to_type(entropy_stage: str) -> str:
        mapping = {
            "信息源": "explore",
            "过滤层": "filter",
            "处理层": "code_gen",
            "产出层": "assemble",
            "验证层": "verify",
        }
        return mapping.get(entropy_stage, "execute")

    @staticmethod
    def _estimate_tokens(entropy_stage: str, complexity: float) -> int:
        bases = {"信息源": 4000, "过滤层": 3000, "处理层": 12000,
                  "产出层": 5000, "验证层": 6000}
        base = bases.get(entropy_stage, 5000)
        return int(base * (0.5 + complexity))

    @staticmethod
    def _resolve_dep_ids(dep_names: list[str],
                          specs: list) -> list[str]:
        """将阶段名称解析为子任务 ID。"""
        name_to_id = {s.entropy_stage: s.id for s in specs}
        return [name_to_id[n] for n in dep_names if n in name_to_id]
