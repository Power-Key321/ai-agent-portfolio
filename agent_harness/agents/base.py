"""
SubAgentBase — 子智能体抽象基类 + AgentMessage 通信协议。

核心设计: AgentMessage 包裹 Envelope，子智能体解包后调 ModuleBase.process()，
不改任何现有模块。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class AgentMessage:
    """智能体间通信消息。包裹 Envelope，不替代它。

    Attributes:
        message_id: 唯一消息 ID
        sender_id: 发送方智能体 ID
        recipient_id: 接收方智能体 ID ("*" = 广播)
        envelope: 核心数据载体 (与现有模块完全兼容)
        message_type: task | result | query | heartbeat | cancel
        priority: 0=低, 5=普通, 10=紧急
        correlation_id: 链接请求-响应对
        ttl: 最大跳数，防止死循环
        payload: 可选额外数据
    """

    sender_id: str
    recipient_id: str
    envelope: "Envelope"  # noqa: F821
    message_type: str = "task"
    priority: int = 5
    ttl: int = 10

    message_id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    correlation_id: Optional[str] = None
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())

    def is_expired(self) -> bool:
        return self.ttl <= 0

    def decrement_ttl(self) -> None:
        self.ttl -= 1

    def create_reply(self, envelope: "Envelope", message_type: str = "result") -> "AgentMessage":  # noqa: F821
        """创建此消息的回复。交换收发方，设置关联 ID。"""
        return AgentMessage(
            sender_id=self.recipient_id,
            recipient_id=self.sender_id,
            envelope=envelope,
            message_type=message_type,
            priority=self.priority,
            correlation_id=self.message_id,
            payload={"reply_to": self.message_id},
        )


@dataclass
class AgentResult:
    """子智能体处理结果。"""
    agent_id: str
    message: AgentMessage
    success: bool = True
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class SubAgentBase(ABC):
    """子智能体抽象基类。

    任何智能体只需实现 handle_message() 即可接入乐高城市。

    用法:
        class MyAgent(SubAgentBase):
            spec = AgentSpec(agent_id="my_agent", capabilities=[...], backend="inline")

            def handle_message(self, message: AgentMessage) -> AgentMessage:
                # 解包 Envelope，调用 ModuleBase.process()
                result = my_module.process(message.envelope)
                return message.create_reply(result.envelope)

            def health_check(self) -> bool:
                return True
    """

    spec: "AgentSpec"  # noqa: F821

    @abstractmethod
    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """处理一条消息并返回响应。

        Args:
            message: 入站消息 (包含 Envelope)

        Returns:
            响应消息 (包含处理后的 Envelope)
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """健康检查。返回 False 将被 AgentBus 标记为 ERROR。"""
        ...

    @property
    def agent_id(self) -> str:
        return self.spec.agent_id

    @property
    def status(self) -> AgentStatus:
        return self.spec.status

    @status.setter
    def status(self, value: AgentStatus) -> None:
        self.spec.status = value

    def can_handle(self, module_type: str, variant: str | None = None) -> bool:
        """检查此智能体是否能处理指定的模块类型+变体。"""
        for cap in self.spec.capabilities:
            if cap.module_type != module_type:
                continue
            if variant is None:
                return True
            if variant in cap.variants:
                return True
        return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.agent_id}, {self.status.value})"
