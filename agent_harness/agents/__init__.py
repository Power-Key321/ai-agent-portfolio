"""
Multi-Agent Orchestration — 乐高城市。

将单 Agent 六模块流水线升级为多 Agent 协作系统:
- SubAgentBase: 子智能体抽象基类
- AgentMessage: 智能体间通信消息（包裹 Envelope）
- AgentBus: 智能体注册/路由/分发总线
- MasterAgent: 总协调器，DAG 感知并行调度
- InlineSubAgent: 内联执行（包裹现有 ModuleBase，零开销）
- ClaudeCodeSubAgent: 每个子任务独立 CC 子智能体
"""

from agent_harness.agents.base import SubAgentBase, AgentMessage, AgentStatus
from agent_harness.agents.spec import AgentSpec, AgentCapability, AgentStats
from agent_harness.agents.bus import AgentBus

__all__ = [
    "SubAgentBase",
    "AgentMessage",
    "AgentStatus",
    "AgentSpec",
    "AgentCapability",
    "AgentStats",
    "AgentBus",
]
