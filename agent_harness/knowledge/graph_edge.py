"""
GraphEdge — 知识图谱边数据模型。

有向加权边，类型化关系。支持自动双向检测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


EDGE_TYPES = (
    "related_to",       # 一般关联
    "instance_of",      # A 是 B 的实例
    "prefers",          # 用户偏好 A 优于 B
    "uses",             # A 使用 B
    "resolves_to",      # A 消歧后指向 B
    "contradicts",      # A 与 B 矛盾
    "created_in",       # A 创建于会话 B
    "depends_on",       # A 依赖 B
    "similar_to",       # A 类似于 B
)


@dataclass
class GraphEdge:
    """知识图谱中的一条有向边。

    Attributes:
        edge_id: 唯一标识 (通常是 "{source_id}--{edge_type}--{target_id}")
        source_id: 源节点 ID
        target_id: 目标节点 ID
        edge_type: 关系类型
        weight: 0-1 连接强度
        bidirectional: True 如果关系是对称的
        evidence: 此边存在的原因 (如 "用户在对话中明确表示偏好")
        access_count: 被使用次数
        created_at / updated_at: ISO 时间戳
        source_session_id: 创建此边的会话 ID
    """

    source_id: str
    target_id: str
    edge_type: str = "related_to"
    weight: float = 0.5
    bidirectional: bool = False

    edge_id: str = ""
    evidence: str = ""
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_session_id: Optional[str] = None

    def __post_init__(self):
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(f"edge_type must be one of {EDGE_TYPES}, got '{self.edge_type}'")
        if not self.edge_id:
            self.edge_id = f"{self.source_id}--{self.edge_type}--{self.target_id}"

    def touch(self) -> None:
        """记录一次访问。"""
        self.access_count += 1
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def strengthen(self, delta: float = 0.1) -> float:
        """强化连接权重。返回新权重。"""
        self.weight = min(1.0, self.weight + delta)
        self.touch()
        return self.weight

    def weaken(self, factor: float = 0.9) -> float:
        """衰减连接权重。返回新权重。"""
        self.weight = max(0.01, self.weight * factor)
        self.touch()
        return self.weight

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "bidirectional": self.bidirectional,
            "evidence": self.evidence,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_session_id": self.source_session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=data.get("edge_type", "related_to"),
            weight=data.get("weight", 0.5),
            bidirectional=data.get("bidirectional", False),
            edge_id=data.get("edge_id", ""),
            evidence=data.get("evidence", ""),
            access_count=data.get("access_count", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            source_session_id=data.get("source_session_id"),
        )

    def __repr__(self) -> str:
        arrow = "↔" if self.bidirectional else "→"
        return f"GraphEdge({self.source_id} {arrow} {self.target_id}, type={self.edge_type}, w={self.weight:.2f})"
