"""代码任务预处理 — 提取语言/框架/文件路径等实体。"""

import re
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


LANG_PATTERNS = {
    "python": [r"python", r"fastapi", r"django", r"flask", r"pytest"],
    "javascript": [r"javascript", r"js", r"node", r"express", r"react", r"vue", r"next"],
    "typescript": [r"typescript", r"ts", r"angular", r"nest"],
    "go": [r"\bgolang\b", r"\bgo\b.*\bmod\b", r"\bgin\b"],
    "rust": [r"\brust\b", r"cargo", r"actix", r"tokio"],
    "java": [r"\bjava\b", r"spring", r"maven", r"gradle"],
}

FRAMEWORK_PATTERNS = {
    "fastapi": [r"fastapi"],
    "django": [r"django"],
    "flask": [r"flask"],
    "express": [r"express"],
    "react": [r"react"],
    "vue": [r"vue"],
}


class PreprocCode(ModuleBase):
    """代码任务预处理 — 提取编程语言、框架、文件路径等。"""

    name = "preproc"
    variant = "code"

    def process(self, envelope: Envelope) -> ModuleResult:
        text = envelope.task.get("normalized_intent") or envelope.task.get("original_input", "")

        entities = envelope.task.setdefault("entities", {})
        entities.update(self._extract_entities(text))

        constraints = envelope.task.setdefault("constraints", {})
        constraints["existing_codebase"] = True

        envelope.task["complexity_score"] = self._estimate_complexity(entities)

        return ModuleResult(envelope=envelope)

    def _extract_entities(self, text: str) -> dict:
        text_lower = text.lower()
        entities = {}

        detected_langs = []
        for lang, patterns in LANG_PATTERNS.items():
            for p in patterns:
                if re.search(p, text_lower):
                    detected_langs.append(lang)
                    break
        if detected_langs:
            entities["language"] = detected_langs[0]

        detected_fw = []
        for fw, patterns in FRAMEWORK_PATTERNS.items():
            for p in patterns:
                if re.search(p, text_lower):
                    detected_fw.append(fw)
                    break
        if detected_fw:
            entities["framework"] = detected_fw[0]

        file_paths = re.findall(r'[\w/\\\-]+\.(?:py|js|ts|go|rs|java|rb|php|html|css|json|yaml|toml)', text)
        if file_paths:
            entities["files_mentioned"] = file_paths

        return entities

    def _estimate_complexity(self, entities: dict) -> float:
        """根据输入质量估算复杂度。

        核心逻辑:
        - 输入短 + 无实体 + 无框架 → 高复杂度(0.6+) → 需要更多螺旋
        - 输入长 + 实体多 + 明确框架 → 低复杂度(0.3-) → 可以快速收敛
        """
        score = 0.5  # 中性起点

        # 实体越多 → 越具体 → 复杂度越低
        entity_count = len(entities)
        if entity_count == 0:
            score += 0.20  # 没有实体，很模糊
        elif entity_count <= 1:
            score += 0.05
        elif entity_count <= 3:
            score -= 0.15
        else:
            score -= 0.30  # 实体丰富，需求明确

        # 有框架 → 技术栈明确 → 复杂度降低
        if entities.get("framework"):
            score -= 0.10

        # 有文件路径 → 定位精确 → 复杂度降低
        if entities.get("files_mentioned"):
            score -= 0.15

        # 有语言 → 比没有明确一些
        if entities.get("language"):
            score -= 0.05

        return max(0.10, min(score, 0.90))
