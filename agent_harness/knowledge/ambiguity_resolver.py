"""
AmbiguityResolver — 歧义消解引擎。

核心价值: "模糊概念 → 精确意图"

输入: 用户的模糊表达 (如 "搞个认证")
输出: 消歧后的精确意图 + 置信度 + 证据链

算法:
  1. 搜索匹配 (title + aliases + tags) → 候选节点
  2. 沿边遍历 (≤2 hop): follows resolves_to / prefers / instance_of
  3. 打分: match_score × edge_weight_product × importance × confidence
  4. best_score > 0.6: 消歧成功
  5. best_score < 0.3: needs_clarification = True
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent_harness.knowledge.graph_node import GraphNode


@dataclass
class ResolvedMeaning:
    """一个消歧候选。"""
    node: GraphNode
    confidence: float           # 匹配置信度 (0-1)
    evidence_path: list[str]    # 图遍历路径
    explanation: str            # 人类可读解释


@dataclass
class AmbiguityResolution:
    """消歧结果。"""
    original_query: str
    candidates: list[ResolvedMeaning]
    best_match: Optional[ResolvedMeaning] = None
    needs_clarification: bool = False

    def __post_init__(self):
        if self.candidates and not self.best_match:
            self.best_match = self.candidates[0]


@dataclass
class AmbiguityResolver:
    """歧义消解器。

    用法:
        resolver = AmbiguityResolver(kg)
        result = resolver.resolve("搞个认证")
        if result.needs_clarification:
            print(f"需要澄清: {result.original_query}")
        else:
            print(f"消歧结果: {result.best_match.explanation}")
    """

    graph: "KnowledgeGraph"  # noqa: F821
    max_depth: int = 2
    min_confidence: float = 0.6
    clarify_threshold: float = 0.3

    def resolve(self, query: str) -> AmbiguityResolution:
        """消解模糊查询的歧义。"""
        # 步骤 1: 搜索候选节点
        candidates = self._find_candidates(query)
        if not candidates:
            return AmbiguityResolution(
                original_query=query,
                candidates=[],
                needs_clarification=True,
            )

        # 步骤 2: 直接匹配 + 图遍历扩展
        resolved: list[ResolvedMeaning] = []
        for node, base_score in candidates:
            # 始终保留直接匹配候选
            resolved.append(ResolvedMeaning(
                node=node,
                confidence=base_score,
                evidence_path=[node.node_id],
                explanation=self._build_explanation(node, base_score),
            ))
            # 追加扩展候选 (更具体的节点, 即使置信度因路径衰减而降低)
            meaning = self._expand_candidate(node, base_score)
            if meaning and meaning.node.node_id != node.node_id:
                resolved.append(meaning)

        # 步骤 3: 排序
        resolved.sort(key=lambda r: r.confidence, reverse=True)

        # 步骤 4: 判決
        result = AmbiguityResolution(
            original_query=query,
            candidates=resolved[:5],
        )

        if not resolved:
            result.needs_clarification = True
        elif resolved[0].confidence < self.clarify_threshold:
            result.needs_clarification = True
        elif resolved[0].confidence >= self.min_confidence:
            result.best_match = resolved[0]
            result.needs_clarification = False
        else:
            result.best_match = resolved[0]
            result.needs_clarification = len(resolved) > 1 and (
                resolved[0].confidence - resolved[1].confidence < 0.15
            )

        return result

    def _find_candidates(self, query: str) -> list[tuple[GraphNode, float]]:
        """搜索候选节点。支持正向匹配(query在节点中)和反向匹配(节点在query中)。"""
        scored: list[tuple[GraphNode, float]] = []
        query_lower = query.lower()

        for node in self.graph.get_all_nodes():
            score = 0.0

            if query_lower == node.node_id.lower():
                score = 2.0
            elif query_lower in node.title.lower():
                score = 1.0
            elif any(query_lower in a.lower() for a in node.aliases):
                score = 0.8
            elif any(query_lower in t.lower() for t in node.tags):
                score = 0.5
            elif query_lower in node.summary.lower():
                score = 0.3
            # 反向匹配: 节点标题/别名是查询的子串 (如 "认证功能" 匹配 "认证")
            elif node.title.lower() in query_lower:
                score = 0.6
            elif any(a.lower() in query_lower for a in node.aliases):
                score = 0.5
            elif query_lower in node.content.lower():
                score = 0.4

            if score > 0:
                score *= node.importance * node.confidence
                scored.append((node, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:10]

    def _expand_candidate(self, node: GraphNode, base_score: float, depth: int = 0) -> Optional[ResolvedMeaning]:
        """沿边遍历扩展候选节点。

        Follows: resolves_to → 找具体实现
                 prefers → 找用户偏好
                 instance_of → 找具体示例
                 uses → 找使用的工具
        """
        if depth >= self.max_depth:
            return ResolvedMeaning(
                node=node,
                confidence=base_score,
                evidence_path=[node.node_id],
                explanation=f"{node.title}: {node.summary or node.content[:100]}",
            )

        best_extension: Optional[ResolvedMeaning] = None
        best_ext_score = 0.0

        # 扩展优先级: resolves_to > prefers > instance_of > uses
        priority_order = ["resolves_to", "prefers", "instance_of", "uses"]

        for edge_type in priority_order:
            edges = self.graph.storage.get_edges(node.node_id, "outgoing")
            for edge in edges:
                if edge.get("edge_type") != edge_type:
                    continue
                target_id = edge.get("target", "")
                target = self.graph.get_node(target_id)
                if target is None:
                    continue

                edge_weight = edge.get("weight", 0.5)
                ext_score = base_score * edge_weight * target.importance * target.confidence

                # 递归扩展
                deeper = self._expand_candidate(target, ext_score, depth + 1)
                if deeper and deeper.confidence > best_ext_score:
                    best_extension = deeper
                    best_extension.evidence_path = [node.node_id] + deeper.evidence_path
                    best_extension.confidence = ext_score
                    best_ext_score = deeper.confidence

        if best_extension:
            return best_extension

        # 无扩展，返回当前节点
        return ResolvedMeaning(
            node=node,
            confidence=base_score,
            evidence_path=[node.node_id],
            explanation=self._build_explanation(node, base_score),
        )

    @staticmethod
    def _build_explanation(node: GraphNode, confidence: float) -> str:
        """构建人类可读的解释。"""
        parts = [node.title]
        if node.summary:
            parts.append(f"— {node.summary}")
        if node.tags:
            parts.append(f"[标签: {', '.join(node.tags[:3])}]")
        if confidence >= 0.8:
            parts.append("(高置信)")
        return " ".join(parts)
