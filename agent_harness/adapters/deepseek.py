"""
DeepSeek Adapter — 将 Agent Harness 对接到 DeepSeek API（完整任务执行）。

与 ClaudeCodeAdapter 共享完全相同核心（六模块流水线 + 螺旋收敛），
仅切换模型后端为 DeepSeek。

用法:
    python -m agent_harness.main "任务描述" --deepseek
    # 或
    adapter = DeepSeekAdapter(api_key="sk-xxx")
    result = adapter.start("帮我实现一个JWT认证")
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

from agent_harness.adapters.base import AdapterBase
from agent_harness.adapters.deepseek_client import DeepSeekClient
from agent_harness.core.envelope import Envelope
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.modules.preproc.deductive import PreprocDeductive
from agent_harness.modules.decomp.entropy import DecompEntropy
from agent_harness.modules.schedule.sequential import ScheduleSequential
from agent_harness.modules.context.full import ContextFull
from agent_harness.modules.execute.gated import ExecutorGated
from agent_harness.modules.deliver.gated import DeliverGated


# 意图分类类别
INTENT_CATEGORIES = [
    "code_feature",
    "code_fix",
    "data_analysis",
    "research",
    "simple_query",
    "refactor",
]

# 工具定义（OpenAI 兼容格式）
BUILTIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入指定文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "写入内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "在代码库中搜索符号或模式",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "搜索模式"},
                    "path": {"type": "string", "description": "搜索路径（可选）"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "执行 shell 命令并返回输出",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                },
                "required": ["command"],
            },
        },
    },
]


@dataclass
class DeepSeekAdapter(AdapterBase):
    """DeepSeek 适配器 — 完整任务执行引擎。

    实现 AdapterBase 的 2 个抽象方法:
    - _register_modules: 返回模块池（与 CC 版本共用）
    - _resolve_model_call: 调用 DeepSeek API 进行意图分类
    """

    adapter_name: str = "deepseek"
    api_key: str = ""
    api_base: str = ""
    model: str | None = None           # 解析后: deepseek-v4-flash
    reasoner_model: str | None = None  # 解析后: deepseek-v4-pro
    on_stream_chunk: Optional[Callable[[str], None]] = None
    on_tool_call: Optional[Callable[[str, dict], Any]] = None
    on_token_usage: Optional[Callable[[dict], None]] = None

    _client: DeepSeekClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # 解析配置: 显式参数 > 环境变量 > 项目配置文件 > Claude 当前配置 > 默认值
        self._resolve_config()

        self._client = DeepSeekClient(
            api_key=self.api_key,
            api_base=self.api_base,
            default_model=self.model,
            reasoner_model=self.reasoner_model,
            on_stream_chunk=self.on_stream_chunk,
            on_token_usage=self.on_token_usage,
        )

        if not hasattr(self, "model_router") or self.model_router is None:
            AdapterBase.__init__(self)
        if self._client.api_key and self.model_router is not None:
            self.model_router.on_model_call = self._resolve_model_call

    def _resolve_config(self) -> None:
        """按优先级解析 DeepSeek 配置，兼容当前 Claude Code 的 DeepSeek 接入。"""
        proj = self._load_project_config()

        # API Key: 显式 > DEEPSEEK_API_KEY > ANTHROPIC_AUTH_TOKEN > Claude settings > 项目配置
        if not self.api_key:
            self.api_key = (
                os.environ.get("DEEPSEEK_API_KEY", "")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
                or self._load_key_from_claude_config()
                or proj.get("api_key", "")
            )

        # API Base: 显式 > DEEPSEEK_API_BASE > 项目配置 > DeepSeek 官方默认
        if not self.api_base:
            self.api_base = (
                os.environ.get("DEEPSEEK_API_BASE", "")
                or proj.get("api_base", "")
                or "https://api.deepseek.com"
            )

        # 模型: 显式 > DEEPSEEK_MODEL/DEEPSEEK_REASONER_MODEL > 项目配置 > 当前 v4 模型
        if not self.model:
            self.model = (
                os.environ.get("DEEPSEEK_MODEL", "")
                or proj.get("model", "")
                or "deepseek-v4-flash"
            )
        if not self.reasoner_model:
            self.reasoner_model = (
                os.environ.get("DEEPSEEK_REASONER_MODEL", "")
                or proj.get("reasoner_model", "")
                or "deepseek-v4-pro"
            )

    @staticmethod
    def _load_project_config() -> dict:
        """读取项目内 deepseek_config.json（随项目目录迁移）。"""
        path = _HARNESS_ROOT / "deepseek_config.json"
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    @staticmethod
    def _load_key_from_claude_config() -> str:
        """从 Claude Code 配置中读取 DeepSeek API key。"""
        config_paths = [
            Path.home() / ".claude" / "settings.json",
            Path.home() / ".claude.json",
        ]
        for config_path in config_paths:
            try:
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    env_config = config.get("env", {})
                    auth_token = env_config.get("ANTHROPIC_AUTH_TOKEN", "")
                    base_url = env_config.get("ANTHROPIC_BASE_URL", "")
                    if auth_token and "deepseek.com" in base_url:
                        return auth_token
            except Exception:
                continue
        return ""

    @property
    def client(self) -> DeepSeekClient:
        if self._client is None:
            self._client = DeepSeekClient(
                api_key=self.api_key,
                api_base=self.api_base,
                default_model=self.model,
                reasoner_model=self.reasoner_model,
            )
        return self._client

    def _register_modules(self) -> list[ModuleBase]:
        """注册模块池 — 与 CC 适配器共享完全相同的模块。"""
        executor = ExecutorGated(on_execute=self._execute_subtask)
        return [
            PreprocDeductive(),
            DecompEntropy(),
            ScheduleSequential(),
            ContextFull(),
            executor,
            DeliverGated(),
        ]

    def _resolve_model_call(self, prompt: str, skeleton_hash: str) -> str:
        """调用 DeepSeek API 进行意图分类。"""
        if not self.client.api_key:
            return "simple_query"

        try:
            return self.client.classify(prompt, INTENT_CATEGORIES)
        except Exception:
            return "simple_query"

    def _execute_subtask(self, envelope: Envelope, subtask: dict) -> ModuleResult:
        """执行单个子任务 — 通过 DeepSeek API 真实执行。

        构建包含上下文的 prompt，调用 DeepSeek，
        将结果记录到 envelope._artifacts。
        """
        if not self.client.api_key:
            print(f"[DeepSeek] NO API KEY - using stub", file=sys.stderr, flush=True)
            return self._stub_execute(envelope, subtask)

        print(f"[DeepSeek] _execute_subtask: {subtask.get('id','?')[:40]}", file=sys.stderr, flush=True)
        try:
            context_parts = []
            # 从 envelope 提取上下文约束
            constraints = envelope.task.get("constraints", {})
            if constraints:
                context_parts.append(f"约束条件: {json.dumps(constraints, ensure_ascii=False)}")

            entities = envelope.task.get("entities", {})
            if entities:
                context_parts.append(f"相关实体: {json.dumps(entities, ensure_ascii=False)}")

            # 已有 artifacts 的摘要
            artifacts = envelope.task.get("_artifacts", [])
            if artifacts:
                recent = artifacts[-3:]  # 最近3条
                art_summary = "; ".join(
                    a.get("description", a.get("type", "?"))[:100] for a in recent
                )
                context_parts.append(f"前序输出: {art_summary}")

            context_block = "\n".join(context_parts) if context_parts else ""

            system_prompt = (
                "你是 Carbon Engine 的子任务执行器。"
                "请根据子任务描述和上下文，生成具体的执行结果。\n"
                f"{context_block}"
            )

            print(f"[DeepSeek] Calling chat API...", file=sys.stderr, flush=True)
            result = self.client.chat(
                messages=[{"role": "user", "content": subtask.get("description", str(subtask))}],
                system=system_prompt,
                max_tokens=2048,
            )
            print(f"[DeepSeek] Chat API returned, len={len(result.get('content',''))}", file=sys.stderr, flush=True)

            content = result.get("content", "")
            envelope.task.setdefault("_artifacts", []).append({
                "type": "subtask_result",
                "subtask": subtask.get("id", ""),
                "description": subtask.get("description", "")[:200],
                "output": content[:5000],
                "model": result.get("model", "unknown"),
                "tokens": result.get("usage", {}),
                "cost": result.get("cost", 0),
            })

            return ModuleResult(envelope=envelope)

        except Exception as e:
            envelope.task.setdefault("_artifacts", []).append({
                "type": "subtask_error",
                "subtask": subtask.get("id", ""),
                "error": str(e),
            })
            return ModuleResult(envelope=envelope, success=False, error=str(e))

    def _stub_execute(self, envelope: Envelope, subtask: dict) -> ModuleResult:
        """无 API key 时的 stub 执行 — 仅记录子任务规格。"""
        envelope.task.setdefault("_artifacts", []).append({
            "type": "subtask_spec",
            "subtask": subtask.get("id", ""),
            "description": subtask.get("description", ""),
        })
        return ModuleResult(envelope=envelope)

    # ── 高级方法 ──

    def chat_with_tools(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict] | None = None,
        use_reasoner: bool = False,
    ) -> dict:
        """发送带工具定义的对话请求。

        Args:
            prompt: 用户输入
            system: 系统提示
            tools: 工具定义列表（OpenAI 兼容格式）
            use_reasoner: 是否使用推理模型

        Returns:
            {"content": str, "tool_calls": list | None, "model": str, "cost": float, ...}
        """
        tools = tools or BUILTIN_TOOLS
        model = self.reasoner_model if use_reasoner else self.model

        result = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            tools=tools,
            model=model,
        )
        return result

    def probe_chat(
        self,
        prompt: str,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict:
        """Probe-First 对话 — 先用轻量模型，复杂任务自动升级。"""
        tools = tools or BUILTIN_TOOLS
        return self.client.probe_then_reason(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            tools=tools,
        )

    def stream_chat(
        self,
        prompt: str,
        system: str | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> dict:
        """流式对话 — 通过回调推送增量文本。

        Args:
            prompt: 用户输入
            system: 系统提示
            on_chunk: 每收到一个文本增量时调用

        Returns:
            完整响应 dict
        """
        original_callback = self.client.on_stream_chunk
        if on_chunk:
            self.client.on_stream_chunk = on_chunk

        try:
            result = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system=system,
                stream=True,
            )
        finally:
            self.client.on_stream_chunk = original_callback

        return result

    def get_cost_report(self) -> dict:
        """获取成本统计。"""
        if self._client:
            return self._client.get_stats()
        return {"total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0, "total_cost_estimate": 0}

    def run_standalone(self, user_input: str, intent_override: str | None = None) -> str:
        """独立运行 — 完整执行任务，返回 JSON 字符串（与 CC 适配器对齐）。"""
        result = self.start(user_input, intent_override=intent_override)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def get_deepseek_adapter(api_key: str | None = None) -> DeepSeekAdapter:
    """获取 DeepSeek 适配器单例。"""
    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    return DeepSeekAdapter(**kwargs)
