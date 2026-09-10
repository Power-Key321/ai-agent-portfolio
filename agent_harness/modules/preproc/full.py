"""完整预处理 — 领域感知的实体提取 + 歧义检测 + 复杂度估算。"""

import re
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.modules.preproc.code import PreprocCode


# 领域感知的实体提取模式
DOMAIN_ENTITIES = {
    "market": {
        "patterns": [
            r"\b[A-Z]{2,6}\s*[/-]\s*[A-Z]{3,6}\b",   # 交易对写法(如 AAA/BBB)
            r"(大盘|指数|个股|板块|标的|品种)",
        ],
        "entity_key": "assets",
    },
    "time_range": {
        "patterns": [
            r"近\s*\d+\s*(?:天|日|周|月|年|小时)",
            r"(\d+)\s*(?:天|日|周|月|年|小时)",
            r"(最近|近期|过去|今年|本月|本周|今天)",
            r"\d{4}[-/]\d{1,2}",
        ],
        "entity_key": "time_range",
    },
    "metrics": {
        "patterns": [
            r"(涨跌幅|波动率|均值|标准差|成交量|价格|市值|换手率|夏普|回撤|相关系数|RSI|MACD|MA\d*)",
            r"(趋势|走势|支撑|阻力|突破|回调)",
            r"(open|close|high|low|volume|volatility|sharpe)",
        ],
        "entity_key": "metrics",
    },
    "general_tech": {
        "patterns": [
            r"(API|SDK|CLI|REST|GraphQL|gRPC|HTTP|HTTPS|JSON|YAML|TOML)",
            r"(数据库|缓存|队列|网关|负载|容器|k8s|docker|nginx|redis|mysql|postgres)",
        ],
        "entity_key": "tech_terms",
    },
}


class PreprocFull(ModuleBase):
    """完整预处理 — 领域感知 + 歧义检测 + 复杂度估算。

    根据意图类别选择不同的实体提取策略:
    - code_feature/refactor → 代码实体 (PreprocCode)
    - data_analysis → 数据领域实体 (币种/时间/指标)
    - research → 通用实体 + 技术术语
    """

    name = "preproc"
    variant = "full"

    def __init__(self):
        self._code_preproc = PreprocCode()

    def process(self, envelope: Envelope) -> ModuleResult:
        text = (envelope.task.get("normalized_intent") or
                envelope.task.get("original_input", ""))

        entities = envelope.task.setdefault("entities", {})

        # 根据意图选择实体提取策略
        intent = envelope.intent_class or ""
        if intent in ("code_feature", "code_fix", "refactor"):
            # 代码实体
            result = self._code_preproc.process(envelope)
            entities.update(result.envelope.task.get("entities", {}))

        # 所有非 simple_query 类型都做通用实体提取
        if intent != "simple_query":
            entities.update(self._extract_domain_entities(text))
            # 歧义检测
            ambiguity_flags = self._detect_ambiguity(text, entities, intent)
            if ambiguity_flags:
                envelope.task.setdefault("ambiguity_flags", []).extend(ambiguity_flags)

        # 重新估算复杂度（考虑领域实体）
        envelope.task["complexity_score"] = self._estimate_complexity(text, entities, intent)
        envelope.task.setdefault("constraints", {})
        envelope.task.setdefault("ambiguity_flags", [])

        return ModuleResult(envelope=envelope)

    def _extract_domain_entities(self, text: str) -> dict:
        """跨领域实体提取。"""
        entities = {}
        text_upper = text.upper()
        for domain, config in DOMAIN_ENTITIES.items():
            matches = []
            for pattern in config["patterns"]:
                found = re.findall(pattern, text, re.IGNORECASE)
                if found:
                    if isinstance(found[0], tuple):
                        matches.extend([f[0] if isinstance(f, tuple) else f for f in found])
                    else:
                        matches.extend(found)
            if matches:
                entities[config["entity_key"]] = list(set(matches))[:5]

        # 提取具体的数字/百分比（说明需求有量化指标）
        numbers = re.findall(r'\d+\.?\d*\s*%', text)
        if numbers:
            entities["quantitative_targets"] = numbers

        return entities

    def _detect_ambiguity(self, text: str, entities: dict, intent: str) -> list[str]:
        """检测输入中的歧义点。"""
        flags = []
        text_lower = text.lower()

        if intent in ("code_feature", "code_fix", "refactor"):
            if not entities.get("language") and not entities.get("framework"):
                flags.append("no_lang_or_framework")
            if not entities.get("files_mentioned") and intent == "code_fix":
                flags.append("no_file_specified_for_fix")
            if len(text) < 20:
                flags.append("very_short_input")

        if intent in ("data_analysis",):
            if not entities.get("assets") and not entities.get("time_range"):
                flags.append("no_assets_or_time_range")
            elif not entities.get("assets"):
                flags.append("no_assets_specified")
            elif not entities.get("time_range"):
                flags.append("no_time_range_specified")
            if not entities.get("metrics"):
                flags.append("no_metrics_specified")
            if len(text) < 25:
                flags.append("very_short_for_analysis")

        if intent == "research":
            if len(text) < 30:
                flags.append("broad_search_scope")

        return flags

    def _estimate_complexity(self, text: str, entities: dict, intent: str) -> float:
        """领域感知的复杂度估算。

        0.0 = 非常明确的简单任务（不需要螺旋）
        1.0 = 极度模糊的复杂任务（需要完整螺旋）
        """
        score = 0.50  # 中性起点

        # ── 共性因子 ──
        entity_count = sum(len(v) if isinstance(v, list) else 1 for v in entities.values())
        if entity_count == 0:
            score += 0.20
        elif entity_count <= 2:
            score += 0.05
        elif entity_count <= 5:
            score -= 0.15
        else:
            score -= 0.30

        input_len = len(text)
        if input_len < 15:
            score += 0.20
        elif input_len < 30:
            score += 0.10
        elif input_len > 100:
            score -= 0.15
        elif input_len > 60:
            score -= 0.05

        # ── 代码特定因子 ──
        if intent in ("code_feature", "code_fix", "refactor"):
            if entities.get("framework"):
                score -= 0.10
            if entities.get("files_mentioned"):
                score -= 0.20
            if entities.get("language"):
                score -= 0.05

        # ── 数据分析特定因子 ──
        if intent in ("data_analysis",):
            if entities.get("assets"):
                score -= 0.10
            if entities.get("time_range"):
                score -= 0.10
            if entities.get("metrics"):
                score -= 0.10
            if entities.get("quantitative_targets"):
                score -= 0.15

        # ── 研究特定因子 ──
        if intent == "research":
            if entities.get("tech_terms"):
                score -= 0.10

        return max(0.10, min(score, 0.90))
