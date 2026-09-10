"""
ApiSubAgent — 外部 API 子智能体。

封装对外部 API (如 DeepSeek) 的调用，使其作为子智能体接入乐高城市。
复用现有 DeepSeekAdapter 的接口。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Callable

from agent_harness.agents.base import SubAgentBase, AgentMessage
from agent_harness.agents.spec import AgentSpec


@dataclass
class ApiSubAgent(SubAgentBase):
    """通过外部 API 调用执行任务的子智能体。

    用法:
        spec = AgentSpec(
            agent_id="api_deepseek_01",
            capabilities=[AgentCapability(module_type="decomp", variants=["entropy"])],
            backend="api",
        )
        agent = ApiSubAgent(spec=spec)
        agent.on_api_call = my_api_client.call  # 注入 API 调用
    """

    spec: AgentSpec = field(default_factory=lambda: AgentSpec(agent_id="api_default", backend="api"))

    on_api_call: Optional[Callable[[str, str], str]] = None  # (prompt, model) -> response_text
    default_model: str = "deepseek-chat"
    timeout_ms: int = 30000

    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """处理消息: 构建提示 → 调用 API → 解析结果。"""
        if self.on_api_call is None:
            return message.create_reply(message.envelope, message_type="error")

        envelope = message.envelope
        task = envelope.task

        prompt = self._build_prompt(task, message.payload)
        start = time.time()

        try:
            response_text = self.on_api_call(prompt, self.default_model)
            elapsed_ms = (time.time() - start) * 1000

            # 将响应写回 envelope
            task["api_response"] = response_text
            task["api_elapsed_ms"] = elapsed_ms

            return message.create_reply(envelope, message_type="result")

        except Exception as e:
            return message.create_reply(envelope, message_type="error")

    def health_check(self) -> bool:
        return self.on_api_call is not None

    @staticmethod
    def _build_prompt(task: dict, payload: dict) -> str:
        """构建发送给 API 的提示。"""
        parts = []
        intent = task.get("normalized_intent", "")
        if intent:
            parts.append(f"任务: {intent}")
        subtasks = task.get("subtasks", [])
        if subtasks:
            parts.append(f"子任务: {subtasks[0].get('goal', '执行')}")
        entities = task.get("entities", {})
        if entities:
            parts.append(f"上下文: {entities}")
        constraints = task.get("constraints", {})
        if constraints:
            parts.append(f"约束: {constraints}")
        return "\n".join(parts)
