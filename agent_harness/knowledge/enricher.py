"""
GraphEnricher — 知识图谱自动丰富管线。

每次交互后自动:
  1. 从 task entities 中提取概念 → 创建/更新节点
  2. 记录会话节点
  3. 学习用户偏好 (从反馈信号)
  4. 强化活跃边
  5. 解析内容中的 [[wikilinks]]
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_harness.knowledge.graph_node import GraphNode
from agent_harness.knowledge.graph_edge import GraphEdge


@dataclass
class GraphEnricher:
    """从交互中自动丰富知识图谱。

    用法:
        enricher = GraphEnricher(kg)
        # 在一次交互后:
        new_nodes = enricher.enrich_from_interaction(
            session_id="abc123",
            task_entities={"framework": "FastAPI", "language": "Python"},
            strategy_id="code_feature",
            signal_type="accepted",
            user_input="帮我写一个JWT认证中间件",
        )
    """

    graph: "KnowledgeGraph"  # noqa: F821
    session_id: Optional[str] = None

    _entity_to_node_type: dict = field(default_factory=lambda: {
        "framework": "concept",
        "language": "concept",
        "library": "concept",
        "tool": "concept",
        "pattern": "pattern",
        "concept": "concept",
    })

    def enrich_from_interaction(
        self,
        session_id: str,
        task_entities: dict | None = None,
        strategy_id: str = "unknown",
        signal_type: str = "accepted",
        user_input: str = "",
    ) -> list[GraphNode]:
        """从一次完整的任务交互中丰富图谱。"""
        self.session_id = session_id
        new_nodes: list[GraphNode] = []

        # 1. 提取实体创建概念节点
        if task_entities:
            new_nodes.extend(self._enrich_entities(task_entities))

        # 2. 确保策略节点存在
        strategy_node = self._ensure_strategy_node(strategy_id)
        if strategy_node:
            new_nodes.append(strategy_node)

        # 3. 从用户输入中提取概念
        if user_input:
            new_nodes.extend(self._enrich_from_input(user_input, strategy_id))

        # 4. 学习用户偏好
        self._learn_from_feedback(strategy_id, signal_type)

        # 5. 创建会话节点
        session_node = self._create_session_node(session_id, user_input, strategy_id, signal_type)
        if session_node:
            new_nodes.append(session_node)

        return new_nodes

    def _enrich_entities(self, entities: dict) -> list[GraphNode]:
        """从任务实体创建概念节点。"""
        nodes = []
        for entity_type, entity_value in entities.items():
            if isinstance(entity_value, list):
                for item in entity_value:
                    node = self._ensure_concept_node(str(item), entity_type)
                    if node:
                        nodes.append(node)
            elif isinstance(entity_value, str):
                node = self._ensure_concept_node(entity_value, entity_type)
                if node:
                    nodes.append(node)
        return nodes

    def _ensure_concept_node(self, name: str, entity_type: str = "concept") -> Optional[GraphNode]:
        """确保概念节点存在，不存在则创建。"""
        node_id = f"concept_{name.lower().replace(' ', '_').replace('-', '_')}"
        existing = self.graph.get_node(node_id)
        if existing:
            existing.boost_importance(0.05)
            if entity_type not in existing.tags:
                existing.tags.append(entity_type)
            self.graph.upsert_node(existing)
            return existing

        node = GraphNode(
            node_id=node_id,
            title=name,
            node_type=self._entity_to_node_type.get(entity_type, "concept"),
            layer="chronicle",
            content=f"## {name}\n\n{entity_type}: {name}\n",
            summary=f"{entity_type}: {name}",
            tags=[entity_type],
            aliases=[name.lower()],
            confidence=0.3,
            importance=0.3,
            source_session_id=self.session_id,
        )
        self.graph.upsert_node(node)
        return node

    def _ensure_strategy_node(self, strategy_id: str) -> Optional[GraphNode]:
        """确保策略节点存在。"""
        if strategy_id == "unknown":
            return None
        node_id = f"pattern_strategy_{strategy_id}"
        existing = self.graph.get_node(node_id)
        if existing:
            existing.boost_importance(0.02)
            self.graph.upsert_node(existing)
            return existing

        node = GraphNode(
            node_id=node_id,
            title=f"策略: {strategy_id}",
            node_type="pattern",
            layer="chronicle",
            summary=f"Harness 策略 {strategy_id} — 被用户使用过",
            tags=["strategy", strategy_id],
            confidence=0.4,
            importance=0.3,
            source_session_id=self.session_id,
        )
        self.graph.upsert_node(node)
        return node

    def _enrich_from_input(self, user_input: str, strategy_id: str) -> list[GraphNode]:
        """从用户输入中提取关键词并创建节点。"""
        nodes = []
        # 提取技术关键词 (简单启发式)
        keywords = {
            "jwt": "concept", "auth": "concept", "认证": "concept",
            "api": "concept", "middleware": "pattern", "中间件": "pattern",
            "token": "concept", "refresh": "concept", "oauth": "concept",
            "fastapi": "concept", "flask": "concept", "django": "concept",
            "sqlalchemy": "concept", "pydantic": "concept",
            "react": "concept", "vue": "concept", "typescript": "concept",
            "docker": "concept", "k8s": "concept", "redis": "concept",
            "postgres": "concept", "mongodb": "concept",
        }
        input_lower = user_input.lower()
        for keyword, kw_type in keywords.items():
            if keyword in input_lower:
                node = self._ensure_concept_node(keyword.upper() if keyword.isupper() or len(keyword) <= 5 else keyword.title(), kw_type)
                if node:
                    nodes.append(node)
                    # 连接策略节点
                    strategy_node_id = f"pattern_strategy_{strategy_id}"
                    if strategy_id != "unknown":
                        self.graph.add_edge(
                            strategy_node_id, node.node_id,
                            edge_type="uses", weight=0.3, bidirectional=True,
                            evidence=f"用户在 {strategy_id} 任务中提到了 {keyword}",
                        )
        return nodes

    def _learn_from_feedback(self, strategy_id: str, signal_type: str) -> None:
        """从用户反馈中学习偏好。"""
        strategy_node_id = f"pattern_strategy_{strategy_id}"
        strategy_node = self.graph.get_node(strategy_node_id)
        if strategy_node is None:
            return

        if signal_type == "accepted":
            strategy_node.confidence = min(1.0, strategy_node.confidence + 0.1)
            strategy_node.importance = min(1.0, strategy_node.importance + 0.05)
        elif signal_type == "modified":
            strategy_node.confidence = max(0.1, strategy_node.confidence - 0.05)
        elif signal_type == "retried":
            strategy_node.confidence = max(0.1, strategy_node.confidence - 0.1)

        strategy_node.last_verified_at = datetime.now(timezone.utc).isoformat()
        self.graph.upsert_node(strategy_node)

    def _create_session_node(
        self, session_id: str, user_input: str, strategy_id: str, signal_type: str
    ) -> Optional[GraphNode]:
        """记录一次会话。"""
        node_id = f"session_{session_id[:8]}"
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        node = GraphNode(
            node_id=node_id,
            title=f"会话 {session_id[:8]} ({day})",
            node_type="session",
            layer="draft",
            content=f"## 会话记录\n\n- 日期: {day}\n- 策略: {strategy_id}\n- 反馈: {signal_type}\n- 输入: {user_input[:200]}\n",
            summary=f"会话: {user_input[:80]}",
            confidence=0.9,
            importance=0.2,
            source_session_id=session_id,
        )
        self.graph.upsert_node(node)

        # 连接到策略节点
        if strategy_id != "unknown":
            self.graph.add_edge(
                node_id, f"pattern_strategy_{strategy_id}",
                edge_type="created_in", weight=0.5, bidirectional=False,
            )

        return node
