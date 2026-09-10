"""
Claude Code Adapter — 将 Agent Harness 对接到 Claude Code CLI。

v3: 继承 AdapterBase 协议，与 Codex/Cursor 适配器共享接口。

用法（在 Claude Code 中通过 skill 调用）:
    /harness "帮我实现一个JWT认证中间件"

实际流程:
    skill.md → 触发 → claude_code.py → Harness.start(task)
    → 螺旋收敛 → 交付结果
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

from agent_harness.adapters.base import AdapterBase
from agent_harness.core.envelope import Envelope, LazyCache
from agent_harness.core.model_router import ModelRouter
from agent_harness.modules.base import ModuleBase, ModuleResult

# 模块导入
from agent_harness.modules.preproc.simple import PreprocSimple
from agent_harness.modules.preproc.code import PreprocCode
from agent_harness.modules.preproc.full import PreprocFull
from agent_harness.modules.preproc.deductive import PreprocDeductive
from agent_harness.modules.decomp.single import DecompSingle
from agent_harness.modules.decomp.linear import DecompLinear
from agent_harness.modules.decomp.entropy import DecompEntropy
from agent_harness.modules.schedule.sequential import ScheduleSequential
from agent_harness.modules.schedule.parallel import ScheduleParallel
from agent_harness.modules.context.full import ContextFull
from agent_harness.modules.context.minimal import ContextMinimal
from agent_harness.modules.execute.executor import Executor
from agent_harness.modules.execute.gated import ExecutorGated
from agent_harness.modules.deliver.diff import DeliverDiff
from agent_harness.modules.deliver.report import DeliverReport
from agent_harness.core.state_manager import StateManager
from agent_harness.core.memory_guard import MemoryGuard
from agent_harness.modules.deliver.gated import DeliverGated
from agent_harness.modules.deliver.neg_verify import NegVerifyModule


@dataclass
class ClaudeCodeAdapter(AdapterBase):
    """Claude Code 适配器 — 继承 AdapterBase 协议。

    v3: 使用 AdapterBase 模板方法，只需实现 _register_modules 和模型回调。
    """

    adapter_name: str = "claude_code"
    agent_mode: str = "inline"  # v3: "inline" | "distributed"
    on_model_call: Optional[Callable[[str, str], str]] = None
    on_tool_call: Optional[Callable] = None

    def __post_init__(self):
        # 父类核心：确保 AdapterBase 的属性已初始化
        if not hasattr(self, 'memory_guard'):
            self.state_manager = StateManager(
                workspace_dir=str(_HARNESS_ROOT.parent / ".claude" / "harness_states")
            )
            self.memory_guard = MemoryGuard()
            self._cc_envelope = None
        # 如果不从外部注入 ModelRouter，构造一个
        if not hasattr(self, 'model_router') or self.model_router is None:
            self.model_router = ModelRouter()
        if self.on_model_call is not None:
            self.model_router.on_model_call = self.on_model_call
        if not hasattr(self, 'harness_root') or self.harness_root is None:
            self.harness_root = _HARNESS_ROOT
        # v3: 确保 agent_mode 已设置
        if not hasattr(self, 'agent_mode'):
            self.agent_mode = "inline"
        if not hasattr(self, 'master_agent'):
            self.master_agent = None
        if not hasattr(self, 'orchestrator') or self.orchestrator is None:
            self._build_orchestrator()
        if not hasattr(self, 'refiner') or self.refiner is None:
            self._build_refiner()

    def _register_modules(self) -> list[ModuleBase]:
        executor = Executor(on_execute=self._execute_subtask)
        gated_executor = ExecutorGated(on_execute=self._execute_subtask)
        return [
            PreprocSimple(), PreprocCode(), PreprocFull(), PreprocDeductive(),
            DecompSingle(), DecompLinear(), DecompEntropy(),
            ScheduleSequential(), ScheduleParallel(),
            ContextFull(), ContextMinimal(),
            executor, gated_executor,
            DeliverDiff(), DeliverReport(), DeliverGated(),
            NegVerifyModule(),  # neg_verify 自动检测否定结论 → 触发外部对照
        ]

    def _resolve_model_call(self, prompt: str, skeleton_hash: str) -> str:
        if self.on_model_call is not None:
            return self.on_model_call(prompt, skeleton_hash)
        return "simple_query"

    def _execute_subtask(self, envelope: Envelope, subtask: dict) -> ModuleResult:
        """执行单个子任务。"""
        if self.on_model_call is not None:
            try:
                output = self.on_model_call(subtask["description"], "")
                envelope.task.setdefault("_artifacts", []).append({
                    "type": "model_output",
                    "subtask": subtask["id"],
                    "content": str(output)[:5000],
                })
                return ModuleResult(envelope=envelope)
            except Exception as e:
                return ModuleResult(envelope=envelope, success=False, error=str(e))

        envelope.task.setdefault("_artifacts", []).append({
            "type": "placeholder",
            "subtask": subtask["id"],
            "description": subtask["description"],
        })
        return ModuleResult(envelope=envelope)

    def run_standalone(self, user_input: str, intent_override: str | None = None) -> str:
        result = self.start(user_input, intent_override=intent_override)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)


# ── 模块级便捷函数 ──

_adapter: Optional[ClaudeCodeAdapter] = None


def get_adapter() -> ClaudeCodeAdapter:
    global _adapter
    if _adapter is None:
        _adapter = ClaudeCodeAdapter()
    return _adapter


def run_task(user_input: str, intent_override: str | None = None) -> str:
    return get_adapter().run_standalone(user_input, intent_override=intent_override)


def diagnose_task(user_input: str, intent_override: str | None = None) -> str:
    result = get_adapter().diagnose(user_input, intent_override=intent_override)
    return json.dumps(result, ensure_ascii=False, indent=2)
