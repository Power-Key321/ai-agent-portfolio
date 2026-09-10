"""
Observability — 结构化指标收集、延迟分布、收敛追踪与可读报告。

MetricsCollector: 指标收集器，记录模块延迟/门检通过率/退化事件/螺旋收敛
HarnessReport: 从 collector 快照生成人类可读的执行报告
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from agent_harness.core.logging_setup import get_logger, get_trace_id


@dataclass
class MetricsCollector:
    """指标收集器 — 贯穿执行全生命周期的度量点。

    追踪维度:
    - 模块级: 每次 process() 调用的延迟、成功/失败
    - 门检级: 每道门的通过/失败计数
    - 退化: 退化事件次数和 streak 分布
    - 螺旋: 每轮收敛半径的变化轨迹
    - 执行: 端到端执行摘要
    """

    _module_latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _module_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _module_successes: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    _gate_passes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _gate_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    _degradation_events: list[dict] = field(default_factory=list)
    _degradation_total: int = 0

    _spiral_trace: list[dict] = field(default_factory=list)
    _convergence_speed: float = 0.0

    _execution_count: int = 0
    _total_subtasks: int = 0
    _total_elapsed_ms: float = 0.0

    _created_at: float = field(default_factory=time.time)
    _session_id: str = field(default_factory=lambda: get_trace_id() or "unknown")

    def record_module(self, module_key: str, elapsed_ms: int,
                      success: bool, error: str | None = None) -> None:
        self._module_latencies[module_key].append(float(elapsed_ms))
        if success:
            self._module_successes[module_key] += 1
        else:
            self._module_failures[module_key] += 1
            if error:
                get_logger("metrics").warning(
                    "module_failure", module=module_key, error=error[:200],
                )

    def record_gate(self, subtask_id: str, gate_name: str, passed: bool,
                    detail: str = "") -> None:
        if passed:
            self._gate_passes[gate_name] += 1
        else:
            self._gate_failures[gate_name] += 1

    def record_degradation(self, subtask_id: str, reason: str,
                           streak: int, fallback: str) -> None:
        self._degradation_total += 1
        self._degradation_events.append({
            "subtask_id": subtask_id,
            "reason": reason[:200],
            "streak": streak,
            "fallback": fallback,
        })
        get_logger("metrics").warning(
            "degradation", subtask=subtask_id, reason=reason[:100],
            streak=streak, fallback=fallback,
        )

    def record_spiral(self, iteration: int, radius: float,
                      constraints_added: int = 0) -> None:
        prev = self._spiral_trace[-1]["radius"] if self._spiral_trace else 1.0
        self._spiral_trace.append({
            "iteration": iteration,
            "radius": radius,
            "delta": prev - radius,
        })
        if len(self._spiral_trace) >= 2:
            deltas = [abs(self._spiral_trace[i]["radius"] - self._spiral_trace[i-1]["radius"])
                      for i in range(1, len(self._spiral_trace))]
            self._convergence_speed = sum(deltas) / len(deltas) if deltas else 0.0

    def record_execution(self, intent: str, strategy: str,
                         subtask_count: int, total_elapsed_ms: float,
                         success: bool) -> None:
        self._execution_count += 1
        self._total_subtasks += subtask_count
        self._total_elapsed_ms += total_elapsed_ms

    # ── 查询接口 ──

    def get_module_percentiles(self) -> dict:
        """计算每个模块的 p50/p95/p99 延迟。"""
        result = {}
        for key, latencies in self._module_latencies.items():
            if not latencies:
                continue
            sorted_lat = sorted(latencies)
            n = len(sorted_lat)
            result[key] = {
                "count": n,
                "p50": sorted_lat[n // 2],
                "p95": sorted_lat[int(n * 0.95)],
                "p99": sorted_lat[int(n * 0.99)],
                "min": sorted_lat[0],
                "max": sorted_lat[-1],
                "total_ms": sum(sorted_lat),
                "failure_rate": round(
                    self._module_failures[key] / max(1, n), 3
                ),
            }
        return result

    def get_gate_pass_rates(self) -> dict:
        """计算每道门的通过率。"""
        rates = {}
        all_gates = set(list(self._gate_passes.keys()) + list(self._gate_failures.keys()))
        for gate in all_gates:
            passed = self._gate_passes.get(gate, 0)
            failed = self._gate_failures.get(gate, 0)
            total = passed + failed
            rates[gate] = {
                "passed": passed,
                "failed": failed,
                "rate": round(passed / max(1, total), 3),
            }
        return rates

    def get_degradation_summary(self) -> dict:
        return {
            "total_events": self._degradation_total,
            "events": self._degradation_events[-10:],
            "max_streak": max(
                (e["streak"] for e in self._degradation_events), default=0
            ),
        }

    def get_convergence_trace(self) -> list[dict]:
        return self._spiral_trace

    def get_snapshot(self) -> dict:
        """完整指标快照。"""
        return {
            "session_id": self._session_id,
            "elapsed_seconds": round(time.time() - self._created_at, 2),
            "modules": self.get_module_percentiles(),
            "gates": self.get_gate_pass_rates(),
            "degradation": self.get_degradation_summary(),
            "convergence": {
                "speed": round(self._convergence_speed, 4),
                "trace": self._spiral_trace,
            },
            "execution": {
                "count": self._execution_count,
                "total_subtasks": self._total_subtasks,
                "total_elapsed_ms": self._total_elapsed_ms,
            },
        }


class HarnessReport:
    """从 MetricsCollector 快照生成人类可读的执行报告。"""

    def __init__(self, snapshot: dict):
        self._data = snapshot

    def render(self) -> str:
        """渲染为格式化的文本报告。"""
        lines = []
        lines.append("=" * 62)
        lines.append(f"  Agent Harness — Execution Report")
        lines.append(f"  Session: {self._data['session_id'][:16]}")
        lines.append(f"  Elapsed: {self._data['elapsed_seconds']}s")
        lines.append("=" * 62)

        # 模块延迟
        modules = self._data.get("modules", {})
        if modules:
            lines.append("")
            lines.append("── Module Latency (ms) " + "─" * 38)
            lines.append(f"  {'Module':<30s} {'n':>5s} {'p50':>7s} {'p95':>7s} {'p99':>7s} {'fail%':>6s}")
            lines.append("  " + "-" * 58)
            for mod, stats in sorted(modules.items()):
                lines.append(
                    f"  {mod:<30s} {stats['count']:>5d} "
                    f"{stats['p50']:>6.0f}ms {stats['p95']:>6.0f}ms "
                    f"{stats['p99']:>6.0f}ms {stats['failure_rate']:>5.1%}"
                )

        # 门检通过率
        gates = self._data.get("gates", {})
        if gates:
            lines.append("")
            lines.append("── Gate Pass Rates " + "─" * 42)
            for gate, stats in sorted(gates.items()):
                bar = self._bar(stats["rate"])
                lines.append(
                    f"  {gate:<25s} {stats['rate']:>5.0%}  {bar}"
                )

        # 退化
        degrad = self._data.get("degradation", {})
        if degrad.get("total_events", 0) > 0:
            lines.append("")
            lines.append(f"── Degradation Events: {degrad['total_events']} "
                         f"(max streak: {degrad['max_streak']}) " + "─" * 18)
            for evt in degrad.get("events", [])[-5:]:
                lines.append(
                    f"  [{evt['subtask_id']}] streak={evt['streak']} "
                    f"fallback={evt['fallback'][:40]}"
                )

        # 收敛轨迹
        trace = self._data.get("convergence", {}).get("trace", [])
        if trace:
            lines.append("")
            lines.append("── Convergence Trace " + "─" * 41)
            lines.append(f"  Speed: {self._data['convergence']['speed']}")
            for point in trace:
                marker = "●" if point["delta"] > 0 else "○"
                lines.append(
                    f"  Round {point['iteration']}: r={point['radius']:.4f} "
                    f"Δ={point['delta']:+.4f} {marker}"
                )

        # 执行摘要
        ex = self._data.get("execution", {})
        if ex:
            lines.append("")
            lines.append("── Execution Summary " + "─" * 41)
            lines.append(f"  Executions:    {ex['count']}")
            lines.append(f"  Total subtasks:{ex['total_subtasks']}")
            lines.append(f"  Total time:    {ex['total_elapsed_ms']:.0f}ms")

        lines.append("")
        lines.append("=" * 62)
        return "\n".join(lines)

    def render_short(self) -> str:
        """单行摘要。"""
        modules = self._data.get("modules", {})
        gates = self._data.get("gates", {})
        degrad = self._data.get("degradation", {})
        trace = self._data.get("convergence", {}).get("trace", [])

        slowest = max(
            ((k, v["p95"]) for k, v in modules.items()), default=("—", 0),
            key=lambda x: x[1],
        )
        worst_gate = min(
            ((k, v["rate"]) for k, v in gates.items()), default=("—", 1.0),
            key=lambda x: x[1],
        )
        final_r = trace[-1]["radius"] if trace else 1.0

        return (
            f"[Harness] modules={len(modules)} slowest={slowest[0]}(p95={slowest[1]:.0f}ms) "
            f"degradations={degrad.get('total_events', 0)} "
            f"worst_gate={worst_gate[0]}({worst_gate[1]:.0%}) "
            f"final_r={final_r:.4f}"
        )

    @staticmethod
    def _bar(ratio: float, width: int = 15) -> str:
        filled = int(ratio * width)
        if ratio >= 0.9:
            ch = "█"
        elif ratio >= 0.7:
            ch = "▓"
        elif ratio >= 0.5:
            ch = "▒"
        else:
            ch = "░"
        return ch * filled + " " * (width - filled)


# ── 全局单例 ──
_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_collector() -> None:
    global _collector
    _collector = MetricsCollector()
