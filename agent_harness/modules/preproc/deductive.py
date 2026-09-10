"""
PreprocDeductive — 碳基演绎法预处理模块。

以5要素压缩为核心，输出：
- 本质压缩（主体/动作/对象/价值链/可持续性）
- 概率意图分布（不审问，列概率）
- 传统实体提取（兼容下游模块）
- 歧义标记 + 缺失维度建议
- 领域感知的复杂度估算
"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.core.deduction_engine import get_deduction_engine
from agent_harness.modules.preproc.code import PreprocCode


class PreprocDeductive(ModuleBase):
    """演绎法预处理 — 5要素压缩 + 概率推断 + 实体提取。

    替代 PreprocSimple/PreprocCode/PreprocFull 的统一入口。
    根据意图类型自动选择实体提取策略。
    """

    name = "preproc"
    variant = "deductive"

    def __init__(self):
        self._engine = get_deduction_engine()
        self._code_preproc = PreprocCode()

    def process(self, envelope: Envelope) -> ModuleResult:
        text = (envelope.task.get("normalized_intent") or
                envelope.task.get("original_input", ""))
        intent = envelope.intent_class or ""

        # 1. 5要素本质压缩
        five_elements = self._engine.compress_to_five_elements(
            text, intent_class=intent,
            entities=envelope.task.get("entities", {}),
        )
        envelope.task["five_elements"] = {
            "subject": five_elements.subject,
            "action": five_elements.action,
            "object": five_elements.object,
            "value_chain": five_elements.value_chain,
            "sustainability": five_elements.sustainability,
            "completeness": five_elements.completeness,
        }

        # 2. 概率意图分布
        intent_probs = self._engine.infer_intent_probabilities(
            text, entities=envelope.task.get("entities", {}),
        )
        envelope.task["intent_probabilities"] = intent_probs

        # 如果概率分布与当前分类不一致，记录偏差
        top_prob = intent_probs[0] if intent_probs else None
        if top_prob and top_prob["intent"] != intent and top_prob["probability"] > 0.6:
            envelope.task.setdefault("ambiguity_flags", []).append(
                f"演绎引擎建议意图 '{top_prob['intent']}' (概率{top_prob['probability']}) "
                f"与当前分类 '{intent}' 不一致"
            )

        # 3. 实体提取（兼容现有模块）
        entities = envelope.task.setdefault("entities", {})
        if intent in ("code_feature", "code_fix", "refactor"):
            result = self._code_preproc.process(envelope)
            entities.update(result.envelope.task.get("entities", {}))

        # 通用实体提取
        entities.update(self._extract_broad_entities(text, intent))

        # 4. 歧义检测 + 缺失维度
        ambiguity_flags = envelope.task.setdefault("ambiguity_flags", [])
        self._check_element_gaps(five_elements, ambiguity_flags)
        self._check_entity_gaps(entities, intent, ambiguity_flags)

        # 5. 复杂度估算（5要素+实体双维度）
        envelope.task["complexity_score"] = self._estimate_complexity(
            five_elements, entities, intent, text,
        )

        envelope.task.setdefault("constraints", {})
        if five_elements.completeness >= 0.6:
            envelope.task["constraints"]["five_elements_available"] = True

        return ModuleResult(envelope=envelope)

    def _extract_broad_entities(self, text: str, intent: str) -> dict:
        """跨领域实体提取。"""
        import re
        entities = {}

        # 时间范围
        time_patterns = [
            r"近\s*\d+\s*(?:天|日|周|月|年|小时)",
            r"(最近|近期|过去|今年|本月|本周|今天)",
        ]
        for p in time_patterns:
            m = re.findall(p, text)
            if m:
                entities.setdefault("time_range", []).extend(m)

        # 数字/百分比（量化指标）
        numbers = re.findall(r'\d+\.?\d*\s*%', text)
        if numbers:
            entities["quantitative_targets"] = numbers

        # 文件路径
        files = re.findall(
            r'[\w/\\\-]+\.(?:py|js|ts|go|rs|java|rb|php|html|css|json|yaml|toml)',
            text,
        )
        if files:
            entities["files_mentioned"] = files

        # 技术术语
        tech = re.findall(
            r'\b(API|SDK|CLI|REST|GraphQL|gRPC|HTTP|JWT|OAuth|SQL|NoSQL)\b',
            text, re.IGNORECASE,
        )
        if tech:
            entities["tech_terms"] = list(set(tech))

        return entities

    def _check_element_gaps(self, fe, flags: list) -> None:
        if not fe.subject:
            flags.append("missing_subject")
        if not fe.object:
            flags.append("missing_object")
        if fe.completeness < 0.4:
            flags.append(f"five_elements_incomplete({fe.completeness:.0%})")

    def _check_entity_gaps(self, entities: dict, intent: str, flags: list) -> None:
        if intent in ("code_feature", "code_fix", "refactor"):
            if not entities.get("language") and not entities.get("framework"):
                flags.append("no_lang_or_framework")
        if intent in ("data_analysis",):
            if not entities.get("time_range"):
                flags.append("no_time_range")

    def _estimate_complexity(self, fe, entities: dict, intent: str,
                              text: str) -> float:
        """双维度复杂度估算：5要素完整度 + 实体丰富度。"""
        score = 0.50

        # 5要素维度: 越完整 → 越明确 → 复杂度越低
        score -= fe.completeness * 0.30

        # 实体维度
        entity_count = sum(
            len(v) if isinstance(v, list) else 1 for v in entities.values()
        )
        if entity_count == 0:
            score += 0.20
        elif entity_count <= 2:
            score += 0.05
        elif entity_count <= 5:
            score -= 0.15
        else:
            score -= 0.30

        # 输入长度
        input_len = len(text)
        if input_len < 15:
            score += 0.20
        elif input_len < 30:
            score += 0.10
        elif input_len > 100:
            score -= 0.15

        # 意图特定因子
        if intent in ("code_feature", "code_fix", "refactor"):
            if entities.get("files_mentioned"):
                score -= 0.20
            if entities.get("framework"):
                score -= 0.10
        if intent in ("data_analysis",):
            if entities.get("time_range"):
                score -= 0.10
            if entities.get("quantitative_targets"):
                score -= 0.15

        return max(0.10, min(score, 0.90))
