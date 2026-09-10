"""
子智能体实现。

- InlineSubAgent: 包裹现有 ModuleBase，进程内执行
- ClaudeCodeSubAgent: 每个子任务独立 CC 子智能体
- ApiSubAgent: 封装外部 API (DeepSeek 等)
- LocalFnSubAgent: 纯 Python 函数，无需 LLM
"""

from agent_harness.agents.sub_agents.inline_agent import InlineSubAgent
from agent_harness.agents.sub_agents.cc_sub_agent import ClaudeCodeSubAgent
from agent_harness.agents.sub_agents.api_agent import ApiSubAgent
from agent_harness.agents.sub_agents.local_fn_agent import LocalFnSubAgent

__all__ = [
    "InlineSubAgent",
    "ClaudeCodeSubAgent",
    "ApiSubAgent",
    "LocalFnSubAgent",
]
