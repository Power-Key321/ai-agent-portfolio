"""
ProblemProfile — 多维连续问题画像，替代硬编码意图分类。

所有维度均为连续值 [0.0, 1.0]，领域向量归一化到和为 1.0。
不从"类别"推导，全部从可观测信号计算。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProblemProfile:
    """多维连续问题画像。

    替代旧的单一 intent_class 分类。每个维度由 ProblemAnalyzer
    从 envelope.task 中的 preproc 产物计算得出。
    """

    # 领域向量 (4维, 归一化到和为1.0)
    domain_code: float = 0.0
    domain_data: float = 0.0
    domain_concept: float = 0.0
    domain_system: float = 0.0

    # 任务特征 (0.0-1.0 连续)
    complexity: float = 0.5
    ambiguity: float = 0.0
    scope: float = 0.5
    risk: float = 0.0
    context_dependency: float = 0.0

    # decomp 后填充
    expected_subtask_count: int = 1

    # 原始信号 (审计/调试)
    signals: dict = field(default_factory=dict)

    @property
    def dominant_domain(self) -> str:
        """返回主导领域名称。"""
        domains = {
            "code": self.domain_code,
            "data": self.domain_data,
            "concept": self.domain_concept,
            "system": self.domain_system,
        }
        return max(domains, key=domains.get)

    @property
    def is_trivial(self) -> bool:
        """极简单问题: 低复杂度 + 低歧义 + 概念为主。"""
        return (
            self.complexity < 0.2
            and self.ambiguity < 0.15
            and self.domain_concept > 0.6
        )

    @property
    def is_complex_code(self) -> bool:
        """复杂代码任务。"""
        return (
            self.domain_code > 0.4
            and self.complexity >= 0.5
        )

    @property
    def is_destructive(self) -> bool:
        """有破坏性风险。"""
        return self.risk >= 0.5
