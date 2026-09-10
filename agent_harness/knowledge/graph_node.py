"""
GraphNode — 知识图谱节点数据模型。

每个节点像一个 Obsidian 笔记: markdown 内容 + [[wikilinks]] + 元数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


NODE_TYPES = ("concept", "entity", "preference", "pattern", "session", "artifact")
LAYERS = ("canon", "chronicle", "draft")


@dataclass
class GraphNode:
    """知识图谱中的一个节点。

    Attributes:
        node_id: 唯一标识 (slugified title, 如 "concept_fastapi_auth")
        title: 人类可读标题
        node_type: concept | entity | preference | pattern | session | artifact
        layer: canon (不可变) | chronicle (编年) | draft (草稿)
        content: markdown 内容，支持 [[wikilinks]] 语法
        summary: 一句话摘要，用于低成本检索和注入提示
        tags: 标签列表，快速过滤
        aliases: 別名列表，歧义消解时匹配
        importance: 0-1 计算的重要性分数
        confidence: 0-1 知识确信度 (用户确认过=高置信)
        access_count: 被查询次数 (LRU 裁剪用)
        created_at / updated_at: ISO 时间戳
        source_session_id: 创建此节点的会话 ID
        last_verified_at: 用户最后一次确认此知识的时间
    """

    node_id: str
    title: str
    node_type: str = "concept"
    layer: str = "chronicle"

    content: str = ""
    summary: str = ""

    importance: float = 0.5
    confidence: float = 0.5
    access_count: int = 0

    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_session_id: Optional[str] = None
    last_verified_at: Optional[str] = None

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {NODE_TYPES}, got '{self.node_type}'")
        if self.layer not in LAYERS:
            raise ValueError(f"layer must be one of {LAYERS}, got '{self.layer}'")

    def touch(self) -> None:
        """记录一次访问。"""
        self.access_count += 1
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_verified(self) -> None:
        """标记为用户已确认。"""
        self.confidence = min(1.0, self.confidence + 0.15)
        self.last_verified_at = datetime.now(timezone.utc).isoformat()
        self.touch()

    def boost_importance(self, delta: float = 0.05) -> None:
        """提升重要性。"""
        self.importance = min(1.0, self.importance + delta)
        self.touch()

    def decay_importance(self, factor: float = 0.95) -> None:
        """衰减重要性 (未访问时)。"""
        self.importance = max(0.05, self.importance * factor)
        self.touch()

    def extract_wikilinks(self) -> list[str]:
        """从 content 中提取所有 [[wikilinks]] 目标。"""
        import re
        matches = re.findall(r'\[\[([^\]]+)\]\]', self.content)
        return [m.strip() for m in matches]

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "node_type": self.node_type,
            "layer": self.layer,
            "content": self.content,
            "summary": self.summary,
            "importance": self.importance,
            "confidence": self.confidence,
            "access_count": self.access_count,
            "tags": self.tags,
            "aliases": self.aliases,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_session_id": self.source_session_id,
            "last_verified_at": self.last_verified_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        return cls(
            node_id=data["node_id"],
            title=data["title"],
            node_type=data.get("node_type", "concept"),
            layer=data.get("layer", "chronicle"),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            importance=data.get("importance", 0.5),
            confidence=data.get("confidence", 0.5),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
            aliases=data.get("aliases", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            source_session_id=data.get("source_session_id"),
            last_verified_at=data.get("last_verified_at"),
        )

    def __repr__(self) -> str:
        return f"GraphNode({self.node_id!r}, type={self.node_type}, layer={self.layer}, imp={self.importance:.2f})"
