"""
AgentBus — 智能体消息总线。

职责:
  1. 注册表: 所有子智能体在此注册
  2. 路由: 按 module_type.variant 匹配找到合适的智能体
  3. 分发: 发送消息并等待响应
  4. 健康监控: 定期检查智能体状态
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable

from agent_harness.agents.base import SubAgentBase, AgentMessage, AgentResult, AgentStatus


@dataclass
class AgentBus:
    """智能体消息总线。

    用法:
        bus = AgentBus()
        bus.register(PreprocAgent(spec=...))
        bus.register(ExecuteAgent(spec=...))

        # 路由到合适的智能体
        agent_ids = bus.route("preproc", "deductive")
        # → ["preproc_deductive_01"]

        # 发送消息
        message = AgentMessage(sender_id="master", recipient_id=agent_ids[0], envelope=env)
        reply = bus.send(message)
    """

    _registry: dict[str, SubAgentBase] = field(default_factory=dict)
    _capability_index: dict[str, list[str]] = field(default_factory=dict)  # "preproc.code" → [agent_id, ...]
    _message_log: list[dict] = field(default_factory=list)
    _max_log_size: int = 200

    on_message_logged: Optional[Callable[[dict], None]] = None

    # ── 注册 ──

    def register(self, agent: SubAgentBase) -> None:
        """注册一个子智能体并索引其能力。"""
        self._registry[agent.agent_id] = agent

        for key in agent.spec.get_module_keys():
            if key not in self._capability_index:
                self._capability_index[key] = []
            if agent.agent_id not in self._capability_index[key]:
                self._capability_index[key].append(agent.agent_id)

    def unregister(self, agent_id: str) -> bool:
        """注销一个智能体。"""
        if agent_id not in self._registry:
            return False
        del self._registry[agent_id]
        for key, ids in list(self._capability_index.items()):
            self._capability_index[key] = [i for i in ids if i != agent_id]
        return True

    # ── 路由 ──

    def route(self, module_type: str, variant: str = "default") -> list[str]:
        """查找能处理指定 module_type.variant 的智能体 ID 列表。"""
        key = f"{module_type}.{variant}"
        # 精确匹配
        if key in self._capability_index:
            return self._get_available(self._capability_index[key])
        # 回退: 只匹配 module_type
        candidates = []
        for k, ids in self._capability_index.items():
            if k.startswith(f"{module_type}."):
                candidates.extend(ids)
        if candidates:
            return self._get_available(list(set(candidates)))
        return []

    def route_any(self, module_type: str) -> list[str]:
        """查找能处理 module_type 任意变体的智能体。"""
        candidates = []
        for k, ids in self._capability_index.items():
            if k.startswith(f"{module_type}."):
                candidates.extend(ids)
        return self._get_available(list(set(candidates)))

    def _get_available(self, agent_ids: list[str]) -> list[str]:
        """过滤出空闲的智能体。"""
        available = []
        for aid in agent_ids:
            agent = self._registry.get(aid)
            if agent and agent.status in (AgentStatus.IDLE, AgentStatus.BUSY):
                available.append(aid)
        return available

    # ── 分发 ──

    def send(self, message: AgentMessage, timeout_ms: int = 60000) -> AgentMessage:
        """发送消息给指定智能体并等待响应。

        如果 recipient_id 是 "*"，广播给所有匹配的智能体并返回第一个结果。
        """
        if message.recipient_id == "*":
            return self._broadcast(message, timeout_ms)

        agent = self._registry.get(message.recipient_id)
        if agent is None:
            return message.create_reply(
                message.envelope,
                message_type="error",
            )

        return self._dispatch(agent, message)

    def broadcast(self, message: AgentMessage, timeout_ms: int = 60000) -> list[AgentMessage]:
        """广播给所有注册的智能体。"""
        replies = []
        for agent in self._registry.values():
            if agent.status == AgentStatus.OFFLINE:
                continue
            reply = self._dispatch(agent, message)
            replies.append(reply)
        return replies

    def _broadcast(self, message: AgentMessage, timeout_ms: int) -> AgentMessage:
        """内部广播: 发送给所有匹配的智能体。"""
        replies = self.broadcast(message, timeout_ms)
        if replies:
            return replies[0]
        return message.create_reply(message.envelope, message_type="error")

    def _dispatch(self, agent: SubAgentBase, message: AgentMessage) -> AgentMessage:
        """执行单次分发。"""
        start = time.time()
        prev_status = agent.status
        agent.status = AgentStatus.BUSY

        try:
            reply = agent.handle_message(message)
            elapsed_ms = (time.time() - start) * 1000
            agent.spec.stats.tasks_processed += 1
            agent.spec.stats.tasks_succeeded += 1
            agent.spec.stats.total_elapsed_ms += elapsed_ms
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            agent.spec.stats.tasks_processed += 1
            agent.spec.stats.tasks_failed += 1
            agent.status = prev_status
            return message.create_reply(message.envelope, message_type="error")

        agent.status = prev_status
        self._log(message, reply, elapsed_ms)
        return reply

    # ── 健康检查 ──

    def health_check_all(self) -> dict[str, bool]:
        """对所有注册的智能体运行健康检查。"""
        results = {}
        for agent_id, agent in self._registry.items():
            try:
                ok = agent.health_check()
                agent.status = AgentStatus.IDLE if ok else AgentStatus.ERROR
                results[agent_id] = ok
            except Exception:
                agent.status = AgentStatus.ERROR
                results[agent_id] = False
        return results

    # ── 查询 ──

    def get_agent(self, agent_id: str) -> Optional[SubAgentBase]:
        return self._registry.get(agent_id)

    def list_agents(self) -> list[dict]:
        """列出所有已注册智能体的摘要。"""
        return [
            {
                "agent_id": a.agent_id,
                "backend": a.spec.backend,
                "status": a.status.value,
                "capabilities": a.spec.get_module_keys(),
                "success_rate": round(a.spec.stats.success_rate, 2),
            }
            for a in self._registry.values()
        ]

    def list_capabilities(self) -> dict[str, int]:
        """列出所有已注册能力及可用智能体数量。"""
        return {k: len(self._get_available(v)) for k, v in self._capability_index.items()}

    # ── 内部 ──

    def _log(self, message: AgentMessage, reply: AgentMessage, elapsed_ms: float) -> None:
        entry = {
            "message_id": message.message_id,
            "sender": message.sender_id,
            "recipient": message.recipient_id,
            "type": message.message_type,
            "elapsed_ms": round(elapsed_ms, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._message_log.append(entry)
        if len(self._message_log) > self._max_log_size:
            self._message_log = self._message_log[-self._max_log_size:]

        if self.on_message_logged:
            self.on_message_logged(entry)
