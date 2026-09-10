"""
InlineSubAgent — 内联子智能体。

包裹现有 ModuleBase 实例，进程内同步执行。
这是"零改动兼容"的关键: 所有现有模块不经修改即可成为子智能体。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from agent_harness.agents.base import SubAgentBase, AgentMessage, AgentResult
from agent_harness.agents.spec import AgentSpec


@dataclass
class InlineSubAgent(SubAgentBase):
    """包裹现有 ModuleBase 的内联子智能体。

    用法:
        from agent_harness.modules.preproc.deductive import PreprocDeductive
        module = PreprocDeductive()
        agent = InlineSubAgent(spec=spec, module=module)
    """

    spec: AgentSpec = field(default_factory=lambda: AgentSpec(agent_id="inline_default"))
    module: Optional[object] = None  # 实际是 ModuleBase 实例

    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """处理消息: 解包 Envelope → module.process() → 打包回复。"""
        if self.module is None:
            return message.create_reply(message.envelope, message_type="error")

        start = time.time()
        try:
            result = self.module.process(message.envelope)
            elapsed_ms = (time.time() - start) * 1000

            if not result.success:
                return AgentMessage(
                    sender_id=self.agent_id,
                    recipient_id=message.sender_id,
                    envelope=result.envelope,
                    message_type="error",
                    correlation_id=message.message_id,
                    payload={
                        "error": result.error,
                        "failure_class": result.failure_class,
                        "self_heal_strategy": result.self_heal_strategy,
                        "elapsed_ms": elapsed_ms,
                    },
                )

            return message.create_reply(result.envelope, message_type="result")

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            return AgentMessage(
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                envelope=message.envelope,
                message_type="error",
                correlation_id=message.message_id,
                payload={"error": str(e), "elapsed_ms": elapsed_ms},
            )

    def health_check(self) -> bool:
        """检查包裹的模块是否可用。"""
        return self.module is not None
