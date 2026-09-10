"""
LayeredContext — 分层上下文记忆模型。

三层架构:
  ┌─────────────────────────────────────────┐
  │ IMMUTABLE CANON                         │ ← 不可变正典，整个 session 固定，hash 锁定
  │   system prompt + tool specs + rules     │   缓存命中候选（前缀匹配）
  ├─────────────────────────────────────────┤
  │ MONOTONIC CHRONICLE                     │ ← 单调编年，只能追加不能修改
  │   [assistant₁][tool_result₁][assistant₂] │   旧轮次自动成为新轮次的缓存前缀
  ├─────────────────────────────────────────┤
  │ VOLATILE SKETCH                         │ ← 易失草稿，每轮重置，永不上传
  │   当前思考、临时状态、草稿                │   信息必须蒸馏后才能进入 Chronicle
  └─────────────────────────────────────────┘

三条硬性不变量:
  1. Canon 一次计算，hash 锁定，session 内不修改
  2. Chronicle 纯追加，绝不重写任何已有条目
  3. Sketch 中的信息必须通过 distill() 后才能进入 Chronicle
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LayeredContext:
    """分层上下文记忆模型 — 最大化缓存命中率的上下文管理。

    用法:
        ctx = LayeredContext(system_prompt, tool_specs)
        # 每轮:
        ctx.scratch["plan"] = "当前计划..."
        prompt = ctx.assemble(user_input)
        # 模型返回后:
        ctx.append_assistant(response_text)
        ctx.append_tool_result(tool_name, result)
        # 轮次结束:
        distilled = ctx.distill()  # scratch → chronicle
        ctx.reset_scratch()
    """

    # Zone 1: 不可变正典（hash 锁定，session 内不修改）
    _prefix: str = ""
    _prefix_hash: str = ""
    _prefix_tokens: int = 0

    # Zone 2: 单调编年（单调递增）
    _log_entries: list[dict] = field(default_factory=list)
    _log_tokens: int = 0

    # Zone 3: 易失草稿（每轮重置）
    scratch: dict = field(default_factory=dict)

    # 统计
    total_turns: int = 0
    prefix_hits: int = 0
    log_hits: int = 0

    def __init__(
        self,
        system_prompt: str = "",
        tool_specs: str = "",
        rules: str = "",
    ):
        # 手动初始化 dataclass 字段（因为自定义 __init__ 覆盖了生成的）
        self._log_entries = []
        self._log_tokens = 0
        self.scratch = {}
        self.total_turns = 0
        self.prefix_hits = 0
        self.log_hits = 0
        self._graph: "KnowledgeGraph | None" = None  # noqa: F821 — v3 知识图谱引用
        self._build_prefix(system_prompt, tool_specs, rules)

    def set_graph(self, graph: "KnowledgeGraph") -> None:  # noqa: F821
        """v3: 挂载知识图谱。assemble() 时可选注入图谱上下文。"""
        self._graph = graph
        if not graph.is_open:
            graph.open()

    # ── Zone 1: 前缀管理 ──

    def _build_prefix(self, system: str, tools: str, rules: str) -> None:
        parts = []
        if system:
            parts.append(system)
        if tools:
            parts.append(f"## Available Tools\n{tools}")
        if rules:
            parts.append(f"## Rules\n{rules}")
        self._prefix = "\n\n".join(parts)
        self._prefix_hash = hashlib.sha256(self._prefix.encode()).hexdigest()[:16]
        self._prefix_tokens = self._estimate_tokens(self._prefix)

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def prefix_hash(self) -> str:
        return self._prefix_hash

    @property
    def prefix_tokens(self) -> int:
        return self._prefix_tokens

    # ── Zone 2: 日志管理 ──

    def append_assistant(self, content: str, metadata: dict | None = None) -> None:
        """追加助手消息到日志。"""
        entry = {
            "role": "assistant",
            "content": content,
            "tokens": self._estimate_tokens(content),
            "timestamp": time.time(),
        }
        if metadata:
            entry["metadata"] = metadata
        self._log_entries.append(entry)
        self._log_tokens += entry["tokens"]

    def append_tool_result(self, tool_name: str, result: str) -> None:
        """追加工具调用结果到日志。"""
        # 超过阈值的结果自动压缩以减少后续轮次的上下文成本
        truncated = result[:3000] if len(result) > 3000 else result
        if len(result) > 3000:
            truncated += f"\n[... 结果已截断，原始长度 {len(result)} 字符]"

        entry = {
            "role": "tool",
            "tool_name": tool_name,
            "content": truncated,
            "original_length": len(result),
            "tokens": self._estimate_tokens(truncated),
            "timestamp": time.time(),
        }
        self._log_entries.append(entry)
        self._log_tokens += entry["tokens"]

    def get_log_since(self, turn: int) -> str:
        """获取从指定轮次开始的日志内容。"""
        # TODO: 当日志表有 turn 字段时使用；当前返回全部
        return self._format_log(self._log_entries)

    def get_full_log(self) -> str:
        """获取完整日志的格式化文本。"""
        return self._format_log(self._log_entries)

    @property
    def log_tokens(self) -> int:
        return self._log_tokens

    @property
    def log_entry_count(self) -> int:
        return len(self._log_entries)

    # ── Zone 3: 草稿管理 ──

    def reset_scratch(self) -> None:
        """每轮结束后重置草稿区。"""
        self.scratch.clear()
        self.total_turns += 1

    def distill(self) -> str:
        """从草稿区蒸馏关键信息，准备进入编年日志。

        只有经过 distill() 的信息才能从 Sketch 转移到 Chronicle。
        此方法自动过滤临时草稿，仅保留结构化关键字段。
        """
        if not self.scratch:
            return ""
        # 提取关键决策和约束，忽略临时草稿
        keep_keys = {"plan", "decision", "constraint", "conclusion", "next_step"}
        distilled = {k: v for k, v in self.scratch.items() if k in keep_keys}
        if not distilled:
            return ""
        return json.dumps(distilled, ensure_ascii=False)

    # ── 组装 ──

    def assemble(self, user_input: str) -> dict:
        """组装完整 prompt: Canon + Chronicle + Sketch + User Input。

        这样 Canon 和 Chronicle 的前缀部分会被缓存命中。
        """
        parts = [self._prefix]

        if self._log_entries:
            parts.append("\n## Conversation History\n" + self._format_log(self._log_entries))

        # Sketch 中的关键信息（非全部）
        if self.scratch:
            scratch_text = self.distill()
            if scratch_text:
                parts.append(f"\n## Current Context\n{scratch_text}")

        parts.append(f"\n## User Input\n{user_input}")

        full_prompt = "\n\n".join(parts)
        total_tokens = self._estimate_tokens(full_prompt)

        return {
            "prompt": full_prompt,
            "prefix_hash": self._prefix_hash,
            "prefix_tokens": self._prefix_tokens,
            "log_tokens": self._log_tokens,
            "total_tokens": total_tokens,
            # 缓存分析
            "cacheable_prefix_tokens": self._prefix_tokens + self._log_tokens,
            "volatile_tokens": total_tokens - self._prefix_tokens - self._log_tokens,
        }

    # ── 工具方法 ──

    @staticmethod
    def _format_log(entries: list[dict]) -> str:
        lines = []
        for e in entries:
            role = e.get("role", "?")
            if role == "assistant":
                lines.append(f"Assistant: {e['content'][:2000]}")
            elif role == "tool":
                tool_name = e.get("tool_name", "unknown")
                lines.append(f"Tool [{tool_name}]: {e['content'][:1000]}")
        return "\n".join(lines)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        chars = len(text)
        return int(chars * 0.7 / 4 + chars * 0.3 / 2)

    def get_stats(self) -> dict:
        return {
            "prefix_tokens": self._prefix_tokens,
            "prefix_hash": self._prefix_hash,
            "log_entries": self.log_entry_count,
            "log_tokens": self._log_tokens,
            "total_turns": self.total_turns,
            "estimated_cacheable_ratio": (
                (self._prefix_tokens + self._log_tokens)
                / max(1, self._prefix_tokens + self._log_tokens + 200)
            ),
        }
