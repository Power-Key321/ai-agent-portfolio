"""
CostDashboard — 实时成本/缓存监控面板，Probe-First 分级模型调度 + 前缀缓存优化。

提供:
- 实时每轮/每 session 费用
- 缓存命中率监控
- 模型调用分级统计
- 颜色阈值（绿色便宜/黄色注意/红色昂贵）
- 可嵌入 CLI TUI 或作为独立报告

用法:
    dash = CostDashboard()
    dash.record_call(model="opus", tokens_in=5000, tokens_out=1000, cache_hit=True)
    dash.record_call(model="haiku", tokens_in=2000, tokens_out=500, cache_hit=False)
    print(dash.report())
"""

from __future__ import annotations

import time as time_mod
from dataclasses import dataclass, field
from typing import Optional


# 模型定价 ($/M tokens, input/output)
MODEL_PRICING = {
    "opus": {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_hit": 1.50},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_hit": 0.30},
    "haiku": {"input": 0.25, "output": 1.25, "cache_write": 0.31, "cache_hit": 0.025},
}

# 成本阈值（美元）
COST_THRESHOLDS = {
    "green": 0.05,   # 低于此值 = 绿色（便宜）
    "yellow": 0.20,  # 低于此值 = 黄色（注意）
    # 高于 yellow = 红色（昂贵）
}


@dataclass
class CostDashboard:
    """实时成本监控面板。

    每轮和每 session 的 token 消耗、缓存命中率、费用。
    """

    session_budget: float = 5.0  # session 预算上限

    # 累计统计
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_hit_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0

    # 按模型分级
    model_calls: dict[str, int] = field(default_factory=lambda: {"opus": 0, "sonnet": 0, "haiku": 0})
    model_costs: dict[str, float] = field(default_factory=lambda: {"opus": 0.0, "sonnet": 0.0, "haiku": 0.0})

    # 本轮
    turn_input_tokens: int = 0
    turn_output_tokens: int = 0
    turn_cost: float = 0.0

    # 历史
    turn_history: list[dict] = field(default_factory=list)
    session_start: float = field(default_factory=time_mod.time)

    def record_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int = 0,
        cache_hit: bool = False,
        cache_write: bool = False,
    ) -> float:
        """记录一次模型调用，返回本次费用。"""
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["sonnet"])

        if cache_hit:
            cost_in = (tokens_in / 1_000_000) * pricing["cache_hit"]
            self.total_cache_hit_tokens += tokens_in
        elif cache_write:
            cost_in = (tokens_in / 1_000_000) * pricing["cache_write"]
            self.total_cache_write_tokens += tokens_in
        else:
            cost_in = (tokens_in / 1_000_000) * pricing["input"]

        cost_out = (tokens_out / 1_000_000) * pricing["output"]
        cost = cost_in + cost_out

        self.total_input_tokens += tokens_in
        self.total_output_tokens += tokens_out
        self.total_cost += cost

        self.turn_input_tokens += tokens_in
        self.turn_output_tokens += tokens_out
        self.turn_cost += cost

        if model in self.model_calls:
            self.model_calls[model] += 1
            self.model_costs[model] += cost

        return cost

    def end_turn(self) -> dict:
        """结束一轮，记录历史并重置本轮计数器。"""
        summary = {
            "turn": len(self.turn_history) + 1,
            "input_tokens": self.turn_input_tokens,
            "output_tokens": self.turn_output_tokens,
            "cost": round(self.turn_cost, 6),
            "cost_color": self._color_for(self.turn_cost),
            "timestamp": time_mod.time(),
        }
        self.turn_history.append(summary)

        self.turn_input_tokens = 0
        self.turn_output_tokens = 0
        self.turn_cost = 0.0

        return summary

    # ── 报告 ──

    def report(self) -> str:
        """生成人类可读的成本报告。"""
        elapsed = time_mod.time() - self.session_start
        cache_hit_rate = (
            self.total_cache_hit_tokens / max(1, self.total_cache_hit_tokens + self.total_input_tokens)
        )
        budget_pct = (self.total_cost / self.session_budget * 100) if self.session_budget > 0 else 0

        lines = [
            "═" * 45,
            f"  Cost Dashboard  |  {self._format_duration(elapsed)}",
            "─" * 45,
            f"  Session Cost:    ${self.total_cost:.4f}  ({budget_pct:.0f}% of ${self.session_budget:.2f} budget)",
            f"  Cache Hit Rate:  {cache_hit_rate:.1%}",
            f"  Total Tokens:    {self._format_tokens(self.total_input_tokens + self.total_output_tokens)}",
            "─" * 45,
            "  By Model:",
        ]

        for model in ["opus", "sonnet", "haiku"]:
            calls = self.model_calls.get(model, 0)
            cost = self.model_costs.get(model, 0.0)
            if calls > 0:
                lines.append(
                    f"    {model:<8} {calls:>3} calls  ${cost:.4f}"
                    f"  ({cost / max(1, self.total_cost) * 100:.0f}%)"
                )

        lines.append("─" * 45)
        if self.turn_history:
            last_turn = self.turn_history[-1]
            lines.append(f"  Last Turn:       ${last_turn['cost']:.4f} [{last_turn['cost_color'].upper()}]")
        if self.turn_cost > 0:
            lines.append(f"  Current Turn:    ${self.turn_cost:.4f} [{self._color_for(self.turn_cost).upper()}]")
        lines.append("═" * 45)

        return "\n".join(lines)

    def summary(self) -> dict:
        """返回结构化的成本摘要。"""
        return {
            "session_cost": round(self.total_cost, 6),
            "budget_percent": round(self.total_cost / max(0.0001, self.session_budget) * 100, 1),
            "cache_hit_rate": round(
                self.total_cache_hit_tokens / max(1, self.total_cache_hit_tokens + self.total_input_tokens), 3
            ),
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "model_breakdown": {
                model: {"calls": self.model_calls[model], "cost": round(self.model_costs[model], 6)}
                for model in self.model_calls
            },
            "turns": len(self.turn_history),
            "elapsed_seconds": int(time_mod.time() - self.session_start),
        }

    # ── 工具 ──

    @staticmethod
    def _color_for(cost: float) -> str:
        if cost < COST_THRESHOLDS["green"]:
            return "green"
        if cost < COST_THRESHOLDS["yellow"]:
            return "yellow"
        return "red"

    @staticmethod
    def _format_tokens(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(n)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h{m:02d}m"
        if m:
            return f"{m}m{s:02d}s"
        return f"{s}s"
