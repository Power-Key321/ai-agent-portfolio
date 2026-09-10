"""
GraphStorage — 知识图谱 JSON 文件存储层。

原子写入、索引维护、节点文件管理。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_harness.knowledge.graph_node import GraphNode, LAYERS
from agent_harness.knowledge.graph_edge import GraphEdge


def _atomic_write_json(path: Path, data: dict | list) -> None:
    """原子写入 JSON 文件 (先写临时文件再替换)。带 Windows 重试。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # Windows: 目标文件可能被其他进程锁定，重试 3 次
        for attempt in range(3):
            try:
                tmp.replace(path)
                return
            except (PermissionError, OSError):
                if attempt < 2:
                    time.sleep(0.05 * (attempt + 1))
                    # 尝试先删除目标文件
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:
                        pass
                else:
                    raise
    finally:
        tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict | list | None:
    """读取 JSON 文件，不存在则返回 None。"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@dataclass
class GraphStorage:
    """知识图谱持久化存储层。

    文件结构:
        vault_root/
        ├── graph_meta.json
        ├── edge_index.json      # {source_id: [{"target": id, "type": t, "weight": w}, ...]}
        ├── tag_index.json       # {tag: [node_id, ...]}
        ├── alias_index.json     # {alias: canonical_node_id}
        └── nodes/
            ├── canon/           # 不可变层
            ├── chronicle/       # 编年层
            └── draft/           # 草稿层
    """

    vault_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "knowledge_graph")

    # 内存缓存
    _edge_index: dict[str, list[dict]] = field(default_factory=dict, init=False)
    _tag_index: dict[str, list[str]] = field(default_factory=dict, init=False)
    _alias_index: dict[str, str] = field(default_factory=dict, init=False)
    _loaded: bool = False

    def __post_init__(self):
        self.vault_root.mkdir(parents=True, exist_ok=True)
        for layer in LAYERS:
            (self.vault_root / "nodes" / layer).mkdir(parents=True, exist_ok=True)

    def _ensure_loaded(self) -> None:
        """懒加载索引到内存。"""
        if self._loaded:
            return
        self._edge_index = _read_json(self.vault_root / "edge_index.json") or {}
        self._tag_index = _read_json(self.vault_root / "tag_index.json") or {}
        self._alias_index = _read_json(self.vault_root / "alias_index.json") or {}
        self._loaded = True

    # ── 节点 I/O ──

    def _node_path(self, node_id: str, layer: str = "chronicle") -> Path:
        return self.vault_root / "nodes" / layer / f"{node_id}.json"

    def save_node(self, node: GraphNode) -> None:
        """保存（创建或更新）一个节点。"""
        self._ensure_loaded()
        path = self._node_path(node.node_id, node.layer)
        _atomic_write_json(path, node.to_dict())

        # 更新别名索引
        for alias in node.aliases:
            self._alias_index[alias] = node.node_id

        # 更新标签索引
        for tag in node.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if node.node_id not in self._tag_index[tag]:
                self._tag_index[tag].append(node.node_id)

        self._save_indexes()
        self._save_meta()

    def load_node(self, node_id: str, layer: str | None = None) -> GraphNode | None:
        """加载单个节点。如果未指定 layer，在所有层中搜索。"""
        self._ensure_loaded()
        if layer:
            path = self._node_path(node_id, layer)
            data = _read_json(path)
            return GraphNode.from_dict(data) if data else None

        for lyr in LAYERS:
            path = self._node_path(node_id, lyr)
            data = _read_json(path)
            if data:
                return GraphNode.from_dict(data)
        return None

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有引用。"""
        self._ensure_loaded()
        deleted = False
        for lyr in LAYERS:
            path = self._node_path(node_id, lyr)
            if path.exists():
                path.unlink()
                deleted = True
                break
        if not deleted:
            return False

        # 清理边索引
        self._edge_index.pop(node_id, None)
        for src, edges in list(self._edge_index.items()):
            self._edge_index[src] = [e for e in edges if e.get("target") != node_id]

        # 清理标签索引
        for tag, ids in list(self._tag_index.items()):
            self._tag_index[tag] = [i for i in ids if i != node_id]

        # 清理别名索引
        self._alias_index = {k: v for k, v in self._alias_index.items() if v != node_id}

        self._save_indexes()
        self._save_meta()
        return True

    def get_all_node_ids(self, layer: str | None = None) -> list[str]:
        """获取所有节点 ID。"""
        self._ensure_loaded()
        ids = []
        layers = [layer] if layer else list(LAYERS)
        for lyr in layers:
            nodes_dir = self.vault_root / "nodes" / lyr
            if nodes_dir.exists():
                for f in nodes_dir.glob("*.json"):
                    ids.append(f.stem)
        return ids

    def get_node_count(self) -> int:
        return len(self.get_all_node_ids())

    def find_node_by_alias(self, alias: str) -> str | None:
        """通过别名查找规范化 node_id。"""
        self._ensure_loaded()
        return self._alias_index.get(alias)

    # ── 边 I/O ──

    def save_edge(self, edge: GraphEdge) -> None:
        """保存一条边到索引。"""
        self._ensure_loaded()
        if edge.source_id not in self._edge_index:
            self._edge_index[edge.source_id] = []

        # 替换已有同类型边，或追加
        replaced = False
        for i, existing in enumerate(self._edge_index[edge.source_id]):
            if existing.get("target") == edge.target_id and existing.get("edge_type") == edge.edge_type:
                self._edge_index[edge.source_id][i] = {
                    "target": edge.target_id,
                    "edge_type": edge.edge_type,
                    "weight": edge.weight,
                    "bidirectional": edge.bidirectional,
                    "evidence": edge.evidence,
                }
                replaced = True
                break
        if not replaced:
            self._edge_index[edge.source_id].append({
                "target": edge.target_id,
                "edge_type": edge.edge_type,
                "weight": edge.weight,
                "bidirectional": edge.bidirectional,
                "evidence": edge.evidence,
            })

        self._save_indexes()

    def get_edges(self, node_id: str, direction: str = "both") -> list[dict]:
        """获取与节点相关的所有边。

        Args:
            node_id: 节点 ID
            direction: "outgoing" | "incoming" | "both"
        """
        self._ensure_loaded()
        result = []

        if direction in ("outgoing", "both"):
            result.extend(self._edge_index.get(node_id, []))

        if direction in ("incoming", "both"):
            for src, edges in self._edge_index.items():
                for e in edges:
                    if e.get("target") == node_id:
                        result.append({
                            "target": node_id,
                            "source": src,
                            "edge_type": e["edge_type"],
                            "weight": e.get("weight", 0.5),
                            "bidirectional": e.get("bidirectional", False),
                            "evidence": e.get("evidence", ""),
                            "direction": "incoming",
                        })

        return result

    def delete_edge(self, source_id: str, target_id: str, edge_type: str | None = None) -> bool:
        """删除一条边。"""
        self._ensure_loaded()
        if source_id not in self._edge_index:
            return False
        before = len(self._edge_index[source_id])
        if edge_type:
            self._edge_index[source_id] = [
                e for e in self._edge_index[source_id]
                if not (e.get("target") == target_id and e.get("edge_type") == edge_type)
            ]
        else:
            self._edge_index[source_id] = [
                e for e in self._edge_index[source_id] if e.get("target") != target_id
            ]
        self._save_indexes()
        return len(self._edge_index[source_id]) < before

    # ── 索引持久化 ──

    def _save_indexes(self) -> None:
        _atomic_write_json(self.vault_root / "edge_index.json", self._edge_index)
        _atomic_write_json(self.vault_root / "tag_index.json", self._tag_index)
        _atomic_write_json(self.vault_root / "alias_index.json", self._alias_index)

    def _save_meta(self) -> None:
        """写入全局元数据。"""
        meta = {
            "node_count": self.get_node_count(),
            "edge_count": sum(len(v) for v in self._edge_index.values()),
            "canon_count": len(self.get_all_node_ids("canon")),
            "chronicle_count": len(self.get_all_node_ids("chronicle")),
            "draft_count": len(self.get_all_node_ids("draft")),
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _atomic_write_json(self.vault_root / "graph_meta.json", meta)

    def get_meta(self) -> dict:
        self._ensure_loaded()
        return _read_json(self.vault_root / "graph_meta.json") or {
            "node_count": 0, "edge_count": 0,
            "canon_count": 0, "chronicle_count": 0, "draft_count": 0,
        }

    def reload(self) -> None:
        """强制重新加载所有索引。"""
        self._loaded = False
        self._ensure_loaded()
