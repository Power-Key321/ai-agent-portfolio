"""
KnowledgeGraph — 知识图谱主引擎。

提供:
- CRUD 操作 (节点 + 边)
- [[wikilinks]] 解析与自动边创建
- 搜索 (标题/标签/别名/全文)
- 图遍历 (邻居查询、路径查找)
- 与现有 LayeredContext (canon/chronicle/draft) 对齐
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_harness.knowledge.graph_node import GraphNode, LAYERS
from agent_harness.knowledge.graph_edge import GraphEdge, EDGE_TYPES
from agent_harness.knowledge.storage import GraphStorage


WIKILINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')


@dataclass
class KnowledgeGraph:
    """知识图谱主引擎。

    用法:
        kg = KnowledgeGraph()
        kg.open()  # 加载索引

        # 创建节点
        node = GraphNode(
            node_id="concept_fastapi",
            title="FastAPI",
            node_type="concept",
            content="用户偏好 [[FastAPI]] 进行后端开发。常用 [[JWT]] 认证。",
            tags=["python", "framework", "backend"],
            aliases=["fastapi", "fast-api"],
        )
        kg.upsert_node(node)

        # 搜索
        results = kg.search("认证")
        # → [GraphNode("concept_jwt_auth"), GraphNode("pattern_auth_middleware"), ...]

        # 获取上下文 (用于注入提示)
        ctx = kg.get_context_for_prompt("认证", max_items=3)
        # → ["JWT 认证中间件 — 用户偏好 FastAPI + python-jose", ...]
    """

    vault_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "knowledge_graph")
    auto_sync_wikilinks: bool = True

    storage: GraphStorage = field(init=False)
    _opened: bool = False

    def __post_init__(self):
        self.storage = GraphStorage(vault_root=self.vault_root)

    def open(self) -> "KnowledgeGraph":
        """加载索引。"""
        self.storage._ensure_loaded()
        self._opened = True
        return self

    @property
    def is_open(self) -> bool:
        return self._opened

    # ═══════════════════════════════════════════════════════════
    # 节点 CRUD
    # ═══════════════════════════════════════════════════════════

    def upsert_node(self, node: GraphNode) -> GraphNode:
        """创建或更新节点。自动解析 [[wikilinks]] 并创建边。"""
        if not node.node_id:
            raise ValueError("node_id is required")

        # 检查是否更新已有节点
        existing = self.storage.load_node(node.node_id)
        if existing:
            node.access_count = existing.access_count + 1
            if node.summary == "" and existing.summary:
                node.summary = existing.summary

        self.storage.save_node(node)

        if self.auto_sync_wikilinks:
            self._sync_wikilinks(node)

        return node

    def get_node(self, node_id: str) -> GraphNode | None:
        node = self.storage.load_node(node_id)
        if node:
            node.touch()
            self.storage.save_node(node)
        return node

    def get_node_by_alias(self, alias: str) -> GraphNode | None:
        canonical = self.storage.find_node_by_alias(alias)
        if canonical:
            return self.get_node(canonical)
        # 在所有节点的别名中搜索
        for node_id in self.storage.get_all_node_ids():
            node = self.storage.load_node(node_id)
            if node and alias in node.aliases:
                return node
        return None

    def delete_node(self, node_id: str) -> bool:
        return self.storage.delete_node(node_id)

    # ═══════════════════════════════════════════════════════════
    # 边管理
    # ═══════════════════════════════════════════════════════════

    def add_edge(
        self, source_id: str, target_id: str, edge_type: str = "related_to",
        weight: float = 0.5, bidirectional: bool = False, evidence: str = ""
    ) -> GraphEdge:
        """创建一条边。"""
        edge = GraphEdge(
            source_id=source_id, target_id=target_id,
            edge_type=edge_type, weight=weight,
            bidirectional=bidirectional, evidence=evidence,
        )
        self.storage.save_edge(edge)
        if bidirectional:
            rev = GraphEdge(
                source_id=target_id, target_id=source_id,
                edge_type=edge_type, weight=weight,
                bidirectional=True, evidence=evidence,
            )
            self.storage.save_edge(rev)
        return edge

    def get_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        """获取节点的所有边。"""
        edges = self.storage.get_edges(node_id, direction)
        for e in edges:
            e["access_count"] = e.get("access_count", 0) + 1
        return edges

    def get_neighbors(self, node_id: str, max_hops: int = 1) -> list[GraphNode]:
        """获取节点的邻居节点。"""
        visited = {node_id}
        current = {node_id}

        for _ in range(max_hops):
            next_layer = set()
            for nid in current:
                for edge in self.storage.get_edges(nid, "outgoing"):
                    target = edge.get("target", "")
                    if target and target not in visited:
                        next_layer.add(target)
                        visited.add(target)
            current = next_layer

        nodes = []
        for nid in visited:
            if nid != node_id:
                node = self.get_node(nid)
                if node:
                    nodes.append(node)
        return nodes

    # ═══════════════════════════════════════════════════════════
    # 搜索
    # ═══════════════════════════════════════════════════════════

    def search(self, query: str, top_k: int = 5, layer: str | None = None) -> list[GraphNode]:
        """全文搜索图谱。

        匹配优先级: node_id 精确匹配 > 标题包含 > 别名匹配 > 标签匹配 > 内容包含
        """
        scored: list[tuple[GraphNode, float]] = []
        query_lower = query.lower()

        ids = self.storage.get_all_node_ids(layer)
        for nid in ids:
            node = self.storage.load_node(nid)
            if node is None:
                continue

            score = 0.0

            # 精确匹配
            if query_lower == node.node_id.lower():
                score = 2.0
            elif query_lower in node.title.lower():
                score = 1.0
            elif any(query_lower in a.lower() for a in node.aliases):
                score = 0.8
            elif any(query_lower in t.lower() for t in node.tags):
                score = 0.6
            elif query_lower in node.content.lower():
                score = 0.4
            elif query_lower in node.summary.lower():
                score = 0.3

            if score > 0:
                score *= node.importance * node.confidence
                scored.append((node, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in scored[:top_k]]

    def search_by_tag(self, tag: str) -> list[GraphNode]:
        """按标签查找所有节点。"""
        node_ids = self.storage._tag_index.get(tag, [])
        return [n for nid in node_ids if (n := self.storage.load_node(nid))]

    # ═══════════════════════════════════════════════════════════
    # 提示上下文生成
    # ═══════════════════════════════════════════════════════════

    def get_context_for_prompt(self, query: str, max_items: int = 3) -> list[str]:
        """获取最相关的知识上下文，用于注入 LLM 提示。

        返回摘要列表，每个 ~50 tokens，总计 <200 tokens。
        """
        nodes = self.search(query, top_k=max_items)
        contexts = []
        for node in nodes:
            summary = node.summary or node.title
            ctx = f"[{node.node_type}] {summary}"
            if node.confidence >= 0.8:
                ctx += " (已确认)"
            contexts.append(ctx)
            node.touch()
            self.storage.save_node(node)
        return contexts

    # ═══════════════════════════════════════════════════════════
    # Wikilink 同步
    # ═══════════════════════════════════════════════════════════

    def _sync_wikilinks(self, node: GraphNode) -> None:
        """解析节点的 [[wikilinks]]，自动创建/更新边和目标节点。"""
        links = node.extract_wikilinks()
        for link in links:
            target = self.get_node(link) or self.get_node_by_alias(link)
            if target is None:
                target = GraphNode(
                    node_id=link,
                    title=link.replace("_", " ").title(),
                    node_type="concept",
                    layer="chronicle",
                    summary=f"从 [[{node.node_id}]] 自动创建的节点",
                    confidence=0.3,
                    importance=0.3,
                )
                self.storage.save_node(target)

            existing_edges = self.storage.get_edges(node.node_id, "outgoing")
            exists = any(e.get("target") == link for e in existing_edges)
            if not exists:
                self.add_edge(node.node_id, link, "related_to", weight=0.5, bidirectional=True,
                              evidence=f"[[wikilink]] from {node.node_id}")

    # ═══════════════════════════════════════════════════════════
    # 批量操作
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        return self.storage.get_meta()

    def get_all_nodes(self, layer: str | None = None) -> list[GraphNode]:
        ids = self.storage.get_all_node_ids(layer)
        return [n for nid in ids if (n := self.storage.load_node(nid))]

    def get_nodes_by_type(self, node_type: str) -> list[GraphNode]:
        return [n for n in self.get_all_nodes() if n.node_type == node_type]
