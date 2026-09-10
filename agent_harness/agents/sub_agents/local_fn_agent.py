"""
LocalFnSubAgent — 纯函数子智能体。

执行纯 Python 函数，无需 LLM 访问。用于工具类任务:
  - 文件读写
  - 数据转换
  - 格式校验
  - 正则匹配
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent_harness.agents.base import SubAgentBase, AgentMessage
from agent_harness.agents.spec import AgentSpec


@dataclass
class LocalFnSubAgent(SubAgentBase):
    """纯 Python 函数子智能体。零 token 开销。

    用法:
        spec = AgentSpec(
            agent_id="fn_validator_01",
            capabilities=[AgentCapability(module_type="deliver", variants=["diff"])],
            backend="local_fn",
        )
        agent = LocalFnSubAgent(spec=spec)

        @agent.register("validate_diff")
        def validate_diff(envelope):
            # 校验 diff 格式
            return {"valid": True}
    """

    spec: AgentSpec = field(default_factory=lambda: AgentSpec(agent_id="local_fn_default", backend="local_fn"))

    _functions: dict[str, Callable] = field(default_factory=dict)

    def register(self, name: str) -> Callable:
        """装饰器: 注册一个函数到这个子智能体。

        Usage:
            @agent.register("validate")
            def validate(envelope):
                return {"ok": True}
        """
        def decorator(fn: Callable) -> Callable:
            self._functions[name] = fn
            return fn
        return decorator

    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """处理消息: 根据 payload 中的函数名调用对应函数。"""
        fn_name = message.payload.get("fn_name", "")
        if not fn_name or fn_name not in self._functions:
            return message.create_reply(message.envelope, message_type="error")

        start = time.time()
        try:
            fn = self._functions[fn_name]
            result = fn(message.envelope)
            elapsed_ms = (time.time() - start) * 1000

            # 将结果写回 envelope
            message.envelope.task["fn_result"] = result
            message.envelope.task["fn_elapsed_ms"] = elapsed_ms

            return message.create_reply(message.envelope, message_type="result")

        except Exception as e:
            return message.create_reply(message.envelope, message_type="error")

    def health_check(self) -> bool:
        return True  # 纯函数始终可用
