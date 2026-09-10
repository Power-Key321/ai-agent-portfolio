"""
ClaudeCodeSubAgent — Claude Code 子智能体。

每个子任务作为一个独立的 CC 子智能体运行，拥有自己的系统提示和工具访问权限。
这是"乐高城市"的核心用例: ExecuteAgent 将每个子任务委托给独立的 CC 子智能体。

实际执行依赖外部 CC 适配器的 start_cc() / continue_cc() 协议。
此文件定义子智能体的规格和行为模板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Callable

from agent_harness.agents.base import SubAgentBase, AgentMessage
from agent_harness.agents.spec import AgentSpec


@dataclass
class ClaudeCodeSubAgent(SubAgentBase):
    """每个子任务独立运行的 CC 子智能体。

    用法:
        # 创建一个专精于"代码执行"的 CC 子智能体
        spec = AgentSpec(
            agent_id="cc_executor_01",
            capabilities=[AgentCapability(
                module_type="execute",
                variants=["default", "gated"],
                cost_profile="expensive",
                requires_model=True,
            )],
            backend="claude_subagent",
        )
        agent = ClaudeCodeSubAgent(spec=spec)
        agent.on_dispatch = my_cc_adapter.dispatch_subtask  # 注入 CC 分发回调

    dispatch 协议:
        on_dispatch(task_prompt: str, context: dict) -> dict
        接收任务提示和上下文，返回执行结果。
    """

    spec: AgentSpec = field(default_factory=lambda: AgentSpec(agent_id="cc_default", backend="claude_subagent"))

    # 外部注入的 CC 分发回调
    on_dispatch: Optional[Callable[[str, dict], dict]] = None

    # 子智能体系统提示模板
    system_prompt_template: str = (
        "你是一个专业化子智能体，负责执行以下子任务。\n"
        "任务类型: {module_type}.{variant}\n"
        "专注领域: {focus}\n"
        "请仅处理分配给你的子任务，不要超出范围。"
    )

    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """处理消息: 构建任务提示 → 调用 CC 分发 → 返回结果。"""
        if self.on_dispatch is None:
            return message.create_reply(message.envelope, message_type="error")

        envelope = message.envelope
        task = envelope.task

        # 构建专业化系统提示
        module_type = message.payload.get("module_type", "execute")
        variant = message.payload.get("variant", "default")
        focus = message.payload.get("focus", "代码执行")

        system_prompt = self.system_prompt_template.format(
            module_type=module_type,
            variant=variant,
            focus=focus,
        )

        # 构建任务上下文
        context = {
            "system_prompt": system_prompt,
            "subtask": task.get("subtasks", [{}])[0] if task.get("subtasks") else {},
            "entities": task.get("entities", {}),
            "constraints": task.get("constraints", {}),
            "graph_context": envelope.graph_context if hasattr(envelope, "graph_context") else {},
        }

        try:
            result = self.on_dispatch(
                task.get("normalized_intent", "执行子任务"),
                context,
            )

            # 将结果写回 envelope
            if "execution_results" not in task:
                task["execution_results"] = []
            task["execution_results"].append(result)

            return message.create_reply(envelope, message_type="result")

        except Exception as e:
            return message.create_reply(envelope, message_type="error")

    def health_check(self) -> bool:
        return self.on_dispatch is not None
