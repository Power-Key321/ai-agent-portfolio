"""
GraphContext — 知识图谱与 Harness 流水线集成层。

职责:
  1. 将 KnowledgeGraph 连接到 FeedbackEngine 的 on_event_recorded 钩子
  2. 将 KnowledgeGraph 连接到 LayeredContext，注入图谱上下文
  3. 在每次螺旋轮次前查询图谱获取相关用户知识
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable


@dataclass
class GraphContext:
    """知识图谱与流水线的集成桥接。

    用法:
        ctx = GraphContext(kg)
        # 注册到反馈引擎
        feedback_engine.on_event_recorded.append(ctx.on_feedback_event)
        # 在螺旋前查询
        hints = ctx.get_spiral_hints(envelope.task.get("normalized_intent", ""))
        envelope.graph_context = {"hints": hints, "resolved_intent": hints[0] if hints else None}
    """

    graph: "KnowledgeGraph"  # noqa: F821
    enricher: Optional["GraphEnricher"] = None  # noqa: F821
    session_id: Optional[str] = None

    _enrichment_count: int = 0

    def __post_init__(self):
        from agent_harness.knowledge.enricher import GraphEnricher
        if self.enricher is None:
            self.enricher = GraphEnricher(self.graph)

    # ── 反馈钩子 ──

    def on_feedback_event(self, event: dict) -> None:
        """FeedbackEngine 的 on_event_recorded 回调。

        每次交互完成后自动丰富图谱。
        """
        session_id = event.get("session_id", "unknown")
        self.session_id = session_id

        # 从事件中提取可用的丰富信息
        task_entities = event.get("entities", {})
        strategy_id = event.get("strategy_id", "unknown")
        signal_type = event.get("signal_type", "accepted")
        user_input = event.get("original_input", "")

        self.enricher.enrich_from_interaction(
            session_id=session_id,
            task_entities=task_entities,
            strategy_id=strategy_id,
            signal_type=signal_type,
            user_input=user_input,
        )
        self._enrichment_count += 1

        # 每 20 次丰富后裁剪一次
        if self._enrichment_count % 20 == 0:
            from agent_harness.knowledge.pruner import GraphPruner
            pruner = GraphPruner(self.graph)
            pruner.prune()

    # ── 螺旋轮次钩子 ──

    def get_spiral_hints(self, intent: str, user_input: str = "") -> list[str]:
        """在螺旋轮次前获取图谱上下文提示。

        Args:
            intent: 标准化意图 (如 "搞个认证")
            user_input: 原始用户输入

        Returns:
            最多 3 条知识摘要，用于注入 Envelope.graph_context
        """
        if not intent or not self.graph.is_open:
            return []

        # 尝试歧义消解
        from agent_harness.knowledge.ambiguity_resolver import AmbiguityResolver
        resolver = AmbiguityResolver(self.graph)
        resolution = resolver.resolve(intent)

        hints = []

        if resolution.best_match and not resolution.needs_clarification:
            hints.append(f"已消歧: {resolution.best_match.explanation}")

        # 补充图谱搜索
        graph_hints = self.graph.get_context_for_prompt(intent, max_items=2)
        hints.extend(graph_hints)

        return hints[:3]

    def inject_to_envelope(self, envelope: "Envelope") -> None:  # noqa: F821
        """将图谱上下文注入 Envelope。"""
        if not self.graph.is_open:
            return

        intent = envelope.task.get("normalized_intent", "")
        user_input = envelope.task.get("original_input", "")
        hints = self.get_spiral_hints(intent, user_input)

        envelope.graph_context = {
            "hints": hints,
            "node_count": self.graph.storage.get_node_count(),
            "edge_count": self.graph.get_stats().get("edge_count", 0),
        }

    # ── 用户画像查询 ──

    def get_user_profile(self) -> dict:
        """聚合所有 canon 层节点，构建用户画像。"""
        canon_nodes = self.graph.get_all_nodes("canon")
        profile = {}
        for node in canon_nodes:
            profile[node.node_id] = {
                "title": node.title,
                "summary": node.summary,
                "confidence": node.confidence,
            }
        return profile
