"""
GraphPruner — 知识图谱裁剪与维护。

硬上限:
  - 总节点 ≤ 500
  - canon ≤ 50, chronicle ≤ 350, draft ≤ 100
  - 每节点最多 20 条出边

策略:
  1. Draft 层: 删除 7 天前且 access_count = 0 的节点
  2. Chronicle 层: 按 importance × access_count × recency 排序，裁剪底部
  3. Canon 层: 永不自动删除
  4. 边: 删除 weight < 0.1 且 access_count = 0 的边
  5. 衰减: 未访问边每周 × 0.95
  6. 合并: Jaccard 相似度 > 0.7 的重复节点自动合并
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from agent_harness.knowledge.graph_node import GraphNode

MAX_TOTAL_NODES = 500
MAX_NODES_PER_LAYER = {"canon": 50, "chronicle": 350, "draft": 100}
MAX_EDGES_PER_NODE = 20
EDGE_WEIGHT_DECAY = 0.95          # 每周衰减因子
DRAFT_MAX_AGE_DAYS = 7
MIN_IMPORTANCE_TO_KEEP = 0.15
MIN_EDGE_WEIGHT = 0.1
MERGE_JACCARD_THRESHOLD = 0.7


@dataclass
class PruneReport:
    """裁剪报告。"""
    nodes_deleted: int = 0
    edges_deleted: int = 0
    nodes_merged: int = 0
    edges_decayed: int = 0
    details: list[str] = field(default_factory=list)


@dataclass
class GraphPruner:
    """知识图谱裁剪器。"""

    graph: "KnowledgeGraph"  # noqa: F821
    max_total_nodes: int = MAX_TOTAL_NODES
    max_per_layer: dict = field(default_factory=lambda: dict(MAX_NODES_PER_LAYER))

    def prune(self) -> PruneReport:
        """执行一次完整裁剪。"""
        report = PruneReport()

        # 1. 清理过期草稿
        report.nodes_deleted += self._prune_stale_drafts()

        # 2. 裁剪各层超额节点
        for layer in ["draft", "chronicle"]:
            deleted = self._prune_layer(layer, self.max_per_layer.get(layer, 100))
            report.nodes_deleted += deleted

        # 3. 裁剪弱边
        report.edges_deleted += self._prune_weak_edges()

        # 4. 限制每节点边数
        report.edges_deleted += self._limit_edges_per_node()

        # 5. 边权重衰减
        report.edges_decayed += self._decay_stale_edges()

        # 6. 合并重复节点
        merged = self._merge_duplicates()
        report.nodes_merged += merged

        return report

    def _prune_stale_drafts(self) -> int:
        """删除过期的草稿节点。"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=DRAFT_MAX_AGE_DAYS)
        deleted = 0
        for node in self.graph.get_all_nodes("draft"):
            try:
                created = datetime.fromisoformat(node.created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created = datetime.now(timezone.utc) - timedelta(days=DRAFT_MAX_AGE_DAYS + 1)
            if created < cutoff and node.access_count == 0 and node.node_type != "preference":
                self.graph.delete_node(node.node_id)
                deleted += 1
        return deleted

    def _prune_layer(self, layer: str, max_nodes: int) -> int:
        """裁剪指定层到最大节点数。"""
        nodes = self.graph.get_all_nodes(layer)
        if len(nodes) <= max_nodes:
            return 0

        # 按 (importance × access_count × recency_factor) 排序
        now = time.time()

        def score(node: GraphNode) -> float:
            try:
                updated = datetime.fromisoformat(node.updated_at.replace("Z", "+00:00"))
                age_days = max(1, (now - updated.timestamp()) / 86400)
                recency = 1.0 / age_days
            except (ValueError, AttributeError):
                recency = 0.1
            return node.importance * (1 + node.access_count * 0.1) * recency

        nodes.sort(key=score)
        to_delete = nodes[:len(nodes) - max_nodes]
        deleted = 0
        for node in to_delete:
            if node.layer == "canon":
                continue  # 永不删除 canon
            self.graph.delete_node(node.node_id)
            deleted += 1
        return deleted

    def _prune_weak_edges(self) -> int:
        """删除权重过低且未被使用的边。保留强边（即使新创建无访问记录）和活跃边。"""
        deleted = 0
        edge_index = self.graph.storage._edge_index
        for source_id, edges in list(edge_index.items()):
            before = len(edges)
            edge_index[source_id] = [
                e for e in edges
                if e.get("weight", 0) >= MIN_EDGE_WEIGHT or e.get("access_count", 0) > 0
            ]
            deleted += before - len(edge_index[source_id])
        return deleted

    def _limit_edges_per_node(self) -> int:
        """限制每节点最多 MAX_EDGES_PER_NODE 条出边。"""
        deleted = 0
        edge_index = self.graph.storage._edge_index
        for source_id, edges in list(edge_index.items()):
            if len(edges) <= MAX_EDGES_PER_NODE:
                continue
            edges.sort(key=lambda e: e.get("weight", 0))
            edge_index[source_id] = edges[-MAX_EDGES_PER_NODE:]
            deleted += len(edges) - MAX_EDGES_PER_NODE
        return deleted

    def _decay_stale_edges(self) -> int:
        """衰减 7 天以上未访问的边。"""
        decayed = 0
        now = time.time()
        week_ago = now - 7 * 86400

        edge_index = self.graph.storage._edge_index
        for source_id, edges in edge_index.items():
            for edge in edges:
                try:
                    edge_time = datetime.fromisoformat(
                        edge.get("updated_at", "").replace("Z", "+00:00")
                    ).timestamp()
                except (ValueError, AttributeError):
                    edge_time = 0
                if edge_time < week_ago and edge.get("access_count", 0) == 0:
                    old_weight = edge.get("weight", 0.5)
                    edge["weight"] = round(old_weight * EDGE_WEIGHT_DECAY, 4)
                    decayed += 1
        return decayed

    def _merge_duplicates(self) -> int:
        """合并 Jaccard 相似度高的重复节点。"""
        merged = 0
        nodes = self.graph.get_all_nodes()
        if len(nodes) < 2:
            return 0

        # 简单合并: 相同 node_type + 相同 layer + 标签 Jaccard > 阈值
        processed = set()
        for i, node_a in enumerate(nodes):
            if node_a.node_id in processed:
                continue
            for node_b in nodes[i + 1:]:
                if node_b.node_id in processed:
                    continue
                if node_a.node_type != node_b.node_type:
                    continue
                if node_a.layer != node_b.layer:
                    continue
                jaccard = self._jaccard(set(node_a.tags), set(node_b.tags))
                if jaccard >= MERGE_JACCARD_THRESHOLD:
                    # 合并: 保留 importance 更高的，转移边
                    if node_a.importance >= node_b.importance:
                        keeper, victim = node_a, node_b
                    else:
                        keeper, victim = node_b, node_a

                    # 合并内容
                    if victim.summary and victim.summary not in keeper.summary:
                        keeper.summary += "; " + victim.summary
                    keeper.tags = list(set(keeper.tags + victim.tags))
                    keeper.aliases = list(set(keeper.aliases + victim.aliases))
                    keeper.access_count += victim.access_count
                    keeper.confidence = max(keeper.confidence, victim.confidence)

                    self.graph.upsert_node(keeper)
                    self.graph.delete_node(victim.node_id)
                    processed.add(victim.node_id)
                    merged += 1
                    break

            processed.add(node_a.node_id)

        return merged

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)
