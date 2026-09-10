"""
ProblemAnalyzer — 多维问题分析器。

纯 Python 启发式，无模型调用，亚毫秒级。
从 envelope.task 中已由 preproc 计算的数据提取信号，
生成连续维度的 ProblemProfile。

用法:
    analyzer = ProblemAnalyzer()
    profile = analyzer.analyze(envelope)
"""

from __future__ import annotations

from agent_harness.core.envelope import Envelope
from agent_harness.core.problem_profile import ProblemProfile


class ProblemAnalyzer:
    """多维问题分析器 — 输入 Envelope，输出 ProblemProfile。"""

    # 领域信号关键词 (复用 DeductionEngine 的检测逻辑)
    _CREATION_KW = ["实现", "开发", "写", "创建", "添加", "做", "搞", "build",
                    "implement", "create", "make"]
    _FIX_KW = ["修复", "fix", "bug", "报错", "错误", "修", "不工作", "坏了",
               "error", "exception", "crash"]
    _ANALYSIS_KW = ["分析", "统计", "数据", "走势", "图表", "可视化", "报表",
                    "analy", "chart", "plot", "report"]
    _RESEARCH_KW = ["搜索", "查找", "找", "调研", "搜", "research", "search", "find"]
    _REFACTOR_KW = ["重构", "整理", "优化结构", "重写", "refactor", "restructure",
                    "clean up", "清理"]
    _QUERY_KW = ["什么是", "怎么", "解释", "what is", "how to", "explain"]

    _DESTRUCTIVE_KW = ["删除", "delete", "remove", "删", "drop", "清空", "销毁"]

    def analyze(self, envelope: Envelope) -> ProblemProfile:
        """从 envelope.task 提取信号，生成 ProblemProfile。"""
        entities = envelope.task.get("entities", {})
        ambiguity_flags = envelope.task.get("ambiguity_flags", [])
        five_elements = envelope.task.get("five_elements", {})
        subtasks = envelope.task.get("subtasks", [])
        original_input = envelope.task.get("original_input", "")
        constraints = envelope.task.get("constraints", {})
        text = original_input

        # 1. 领域向量
        domain = self._compute_domain(text, entities)

        # 2. 复杂度 — 直接从 preproc 读取
        complexity = envelope.task.get("complexity_score", 0.5)

        # 3. 歧义度 — 从 ambiguity_flags + 5要素完整性 + 输入长度
        ambiguity = self._compute_ambiguity(
            ambiguity_flags, five_elements, len(text)
        )

        # 4. 范围 — 从实体丰富度 + 子任务数
        scope = self._compute_scope(entities, subtasks)

        # 5. 风险 — 从动作关键词
        risk = self._compute_risk(text, domain)

        # 6. 上下文依赖
        context_dep = self._compute_context_dependency(domain, constraints)

        return ProblemProfile(
            domain_code=round(domain["code"], 4),
            domain_data=round(domain["data"], 4),
            domain_concept=round(domain["concept"], 4),
            domain_system=round(domain["system"], 4),
            complexity=round(complexity, 4),
            ambiguity=round(ambiguity, 4),
            scope=round(scope, 4),
            risk=round(risk, 4),
            context_dependency=round(context_dep, 4),
            expected_subtask_count=len(subtasks),
            signals={
                "entities_keys": list(entities.keys()),
                "ambiguity_flags": list(ambiguity_flags),
                "input_len": len(text),
                "five_elements_completeness": five_elements.get("completeness", 0.0),
                "subtask_count": len(subtasks),
            },
        )

    # ── 领域向量 ──

    def _compute_domain(self, text: str, entities: dict) -> dict[str, float]:
        """计算四维领域信号并归一化。"""
        text_lower = text.lower()

        # 代码信号: 创建 + 修复 + 重构
        code_raw = 0.0
        code_raw += sum(1.0 for w in self._CREATION_KW if w in text_lower)
        code_raw += sum(1.0 for w in self._FIX_KW if w in text_lower)
        code_raw += sum(0.8 for w in self._REFACTOR_KW if w in text_lower)
        if entities.get("language") or entities.get("framework") or entities.get("files_mentioned"):
            code_raw += 1.5

        # 数据信号
        data_raw = sum(0.8 for w in self._ANALYSIS_KW if w in text_lower)
        if entities.get("assets"):
            data_raw += 1.5
        if entities.get("metrics"):
            data_raw += 1.0
        if entities.get("time_range"):
            data_raw += 0.5

        # 概念信号
        concept_raw = 0.0
        if len(text) < 30 and ("?" in text or "？" in text or any(kw in text_lower for kw in self._QUERY_KW)):
            concept_raw += 2.0
        concept_raw += sum(0.8 for w in self._QUERY_KW if w in text_lower)

        # 系统信号
        system_raw = sum(1.0 for w in self._RESEARCH_KW if w in text_lower)

        # 归一化: softmax 风格 (加 0.5 平滑避免全零)
        raw = {
            "code": code_raw + 0.1,
            "data": data_raw + 0.1,
            "concept": concept_raw + 0.1,
            "system": system_raw + 0.1,
        }
        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}

    # ── 歧义度 ──

    def _compute_ambiguity(self, flags: list[str], five_elements: dict,
                           input_len: int) -> float:
        """从多个信号推断歧义度。"""
        score = 0.0

        # 歧义标志计数
        score += min(len(flags) * 0.12, 0.5)

        # 5要素完整性反向
        completeness = five_elements.get("completeness", 1.0)
        score += (1.0 - completeness) * 0.3

        # 输入极短 = 高歧义
        if input_len < 10:
            score += 0.3
        elif input_len < 20:
            score += 0.1

        return min(1.0, score)

    # ── 范围 ──

    def _compute_scope(self, entities: dict, subtasks: list) -> float:
        """从实体丰富度和子任务数推断范围。"""
        score = 0.2  # 基础

        files = entities.get("files_mentioned", [])
        if isinstance(files, list) and len(files) > 2:
            score += 0.25
        elif isinstance(files, list) and len(files) > 0:
            score += 0.1

        if entities.get("framework"):
            score += 0.15

        entity_count = sum(1 for v in entities.values() if v)
        if entity_count >= 4:
            score += 0.2
        elif entity_count >= 2:
            score += 0.1

        if len(subtasks) >= 4:
            score += 0.2
        elif len(subtasks) >= 2:
            score += 0.1

        return min(1.0, score)

    # ── 风险 ──

    def _compute_risk(self, text: str, domain: dict) -> float:
        """从动作词推断操作风险。"""
        text_lower = text.lower()

        if any(kw in text_lower for kw in self._DESTRUCTIVE_KW):
            return 0.8

        # 创建/写入 = 中等风险
        if domain["code"] > 0.3:
            create_score = sum(0.15 for w in self._CREATION_KW if w in text_lower)
            if create_score > 0.2:
                return min(0.4, create_score)

        # 修复 = 低风险（修改现有）
        if any(w in text_lower for w in self._FIX_KW):
            return 0.15

        return 0.0  # 只读

    # ── 上下文依赖 ──

    def _compute_context_dependency(self, domain: dict,
                                    constraints: dict) -> float:
        """从领域和约束推断上下文依赖度。"""
        score = domain["code"] * 0.5
        if constraints.get("existing_codebase"):
            score += 0.35
        if constraints.get("five_elements_available"):
            score += 0.1
        return min(1.0, score)
