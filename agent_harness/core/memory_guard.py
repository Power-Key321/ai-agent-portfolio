"""
MemoryGuard — 上下文窗口守护，集成 LayeredContext 到螺旋执行循环。

在每个螺旋轮次前后检查窗口预算：
- 预算 < 20%: 自动总结前一轮的 artifacts 到压缩形式
- 预算 < 10%: 丢弃最早的非关键 artifacts，仅保留摘要
- 预算充足: 正常运行，仅追踪用量
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_harness.core.layered_context import LayeredContext


@dataclass
class MemoryGuard:
    """上下文窗口守护 — 在螺旋循环中保护窗口预算。

    集成 LayeredContext 的 AppendOnlyLog 用于累积压缩的前轮结果。
    """

    window_budget_total: int = 200000     # 总预算（tokens）
    window_used: int = 0                  # 已用量
    compress_threshold: float = 0.20      # 20% 剩余时触发压缩
    critical_threshold: float = 0.10      # 10% 剩余时触发丢弃
    summary_target_tokens: int = 2000     # 总结目标 token 数

    _memory: LayeredContext | None = field(default=None, init=False, repr=False)
    _round_usage: list[dict] = field(default_factory=list, init=False)
    _compression_count: int = field(default=0, init=False)

    def __post_init__(self):
        self._memory = LayeredContext(
            system_prompt="Agent Harness — 乐高式模块化任务编排框架",
            tool_specs="preproc, decomp, schedule, context, execute, deliver",
            rules="碳基大脑演绎法: 5要素压缩→熵减链→门检→退化检测→自检",
        )

    @property
    def remaining_budget(self) -> int:
        return max(0, self.window_budget_total - self.window_used)

    @property
    def budget_ratio(self) -> float:
        return self.remaining_budget / max(1, self.window_budget_total)

    @property
    def is_critical(self) -> bool:
        return self.budget_ratio < self.critical_threshold

    @property
    def needs_compression(self) -> bool:
        return self.budget_ratio < self.compress_threshold

    def track_round(self, round_num: int, tokens_used: int,
                     artifacts_count: int) -> None:
        """追踪一轮螺旋的用量。"""
        self.window_used += tokens_used
        self._round_usage.append({
            "round": round_num,
            "tokens": tokens_used,
            "artifacts": artifacts_count,
            "cumulative_used": self.window_used,
            "budget_remaining": self.remaining_budget,
            "compressed": False,
        })

    def maybe_compress(self, envelope) -> str | None:
        """如果预算紧张，压缩前轮 artifacts。

        Returns:
            压缩摘要文本，如果不需要压缩则返回 None
        """
        if not self.needs_compression:
            return None

        self._compression_count += 1
        artifacts = envelope.task.get("_artifacts", [])

        if not artifacts:
            return None

        # 生成压缩摘要
        summary_parts = []
        for a in artifacts[-20:]:  # 只总结最近 20 条
            summary_parts.append(
                f"[{a.get('type', '?')}] {a.get('description', a.get('output_summary', ''))[:200]}"
            )

        summary = f"[压缩轮次 #{self._compression_count}] " + " | ".join(summary_parts)
        summary = summary[:self.summary_target_tokens * 4]  # 粗略估算 4 chars/token

        # 记录压缩到 AppendOnlyLog
        self._memory.append("assistant", summary)

        # 如果危机级别，丢弃原始 artifacts，只保留摘要
        if self.is_critical:
            envelope.task["_artifacts"] = [
                {"type": "compressed_summary", "content": summary, "round": self._compression_count}
            ]
        else:
            # 温和压缩：保留摘要但不丢弃原始数据
            envelope.task.setdefault("_compressed_summaries", []).append(summary)

        # 标记最近一轮为已压缩
        if self._round_usage:
            self._round_usage[-1]["compressed"] = True

        return summary

    def reset_for_new_session(self, window_budget: int | None = None) -> None:
        """重置以开始新会话。"""
        if window_budget is not None:
            self.window_budget_total = window_budget
        self.window_used = 0
        self._round_usage = []
        self._compression_count = 0
        self._memory = LayeredContext(
            system_prompt="Agent Harness — 乐高式模块化任务编排框架",
            tool_specs="preproc, decomp, schedule, context, execute, deliver",
            rules="碳基大脑演绎法: 5要素压缩→熵减链→门检→退化检测→自检",
        )

    def get_usage_report(self) -> dict:
        """获取用量报告。"""
        return {
            "budget_total": self.window_budget_total,
            "used": self.window_used,
            "remaining": self.remaining_budget,
            "budget_ratio": round(self.budget_ratio, 2),
            "compression_count": self._compression_count,
            "is_critical": self.is_critical,
            "rounds_tracked": len(self._round_usage),
            "round_details": self._round_usage[-5:],  # 最近 5 轮
        }
