"""
MetaCognition — 框架自指能力的外环。

职责:
1. 读取 feedback/ 中的运行时数据
2. 检测性能退化信号（收敛速度下降、错误率上升、门控精度不足）
3. 将检测到的异常转化为"自我改进任务"
4. 启动 Harness 在自己的代码上执行改进
5. 验证改进效果，决定应用或回滚

架构：
    feedback/*.json → SignalDetector → TaskGenerator → Harness(自我执行) → Validator → 应用/回滚

这是整个乐高框架的"元乐高"层——框架本身成为优化对象。
"""

from __future__ import annotations

import json
import time
import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


# ═══════════════════════════════════════════════════════════
# 信号检测层
# ═══════════════════════════════════════════════════════════

@dataclass
class Signal:
    """检测到的异常信号。"""
    signal_type: str           # convergence_decay | error_spike | gate_miscalibration | threshold_drift
    severity: float            # 0.0(轻微) ~ 1.0(严重)
    target: str                # 受影响的组件/策略/文件
    evidence: dict             # 支撑数据
    recommended_action: str    # 建议的改进类型
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SignalDetector:
    """信号检测器 — 从反馈数据中发现需要改进的信号。"""

    def __init__(self, feedback_dir: Path):
        self.feedback_dir = feedback_dir

    def detect_all(self) -> list[Signal]:
        """执行所有检测，返回发现的信号列表。"""
        signals = []
        signals.extend(self.detect_convergence_decay())
        signals.extend(self.detect_gate_miscalibration())
        signals.extend(self.detect_error_spike())
        signals.extend(self.detect_threshold_drift())
        return sorted(signals, key=lambda s: s.severity, reverse=True)

    def detect_convergence_decay(self) -> list[Signal]:
        """检测收敛速度是否在持续下降。

        如果最近10次任务的 c 平均值 < 历史均值的 70%，触发信号。
        """
        history = self._load_json("convergence_history.json")
        if len(history) < 15:
            return []

        recent_n = min(10, len(history) // 2)
        all_scores = [e.get("convergence_score", 0) for e in history if e.get("convergence_score")]
        if not all_scores:
            return []

        recent = all_scores[-recent_n:]
        historical = all_scores[:-recent_n]

        avg_recent = sum(recent) / len(recent)
        avg_historical = sum(historical) / len(historical) if historical else avg_recent

        if avg_historical > 0 and avg_recent < avg_historical * 0.7:
            decay_ratio = avg_recent / avg_historical
            severity = min(1.0, (1.0 - decay_ratio) * 1.5)

            # 找出哪个策略表现最差
            strategy_scores: dict[str, list[float]] = {}
            for e in history[-recent_n:]:
                sid = e.get("strategy_id", "unknown")
                strategy_scores.setdefault(sid, []).append(e.get("convergence_score", 0))
            worst_strategy = min(strategy_scores, key=lambda s: sum(strategy_scores[s]) / len(strategy_scores[s]))

            return [Signal(
                signal_type="convergence_decay",
                severity=round(severity, 2),
                target=worst_strategy,
                evidence={
                    "avg_recent": round(avg_recent, 4),
                    "avg_historical": round(avg_historical, 4),
                    "decay_ratio": round(decay_ratio, 2),
                    "sample_size": recent_n,
                },
                recommended_action="optimize_strategy_params",
            )]
        return []

    def detect_gate_miscalibration(self) -> list[Signal]:
        """检测 SpiralGate 门控精度。

        如果 skip_spiral 的任务中后续有高比例的需要人工介入(modify/retry)，
        说明门控过于激进，该螺旋的任务被错误跳过了。
        """
        history = self._load_json("convergence_history.json")
        skipped = [e for e in history if e.get("spiral_iterations_used", 0) <= 1
                   and e.get("strategy_id") != "simple_query"]
        if len(skipped) < 5:
            return []

        modified = sum(1 for e in skipped if e.get("signal_type") in ("modified", "retried"))
        modify_rate = modified / len(skipped)

        if modify_rate > 0.3:
            return [Signal(
                signal_type="gate_miscalibration",
                severity=round(min(1.0, modify_rate), 2),
                target="SpiralGate.complexity_low_threshold",
                evidence={
                    "skipped_count": len(skipped),
                    "modified_count": modified,
                    "modify_rate": round(modify_rate, 2),
                },
                recommended_action="adjust_gate_thresholds",
            )]
        return []

    def detect_error_spike(self) -> list[Signal]:
        """检测某个模块的错误率是否激增。"""
        history = self._load_json("convergence_history.json")
        if len(history) < 10:
            return []

        recent = history[-10:]
        error_events = [e for e in recent if e.get("signal_type") == "retried"]
        error_rate = len(error_events) / len(recent)

        if error_rate > 0.4:
            return [Signal(
                signal_type="error_spike",
                severity=round(min(1.0, error_rate * 1.5), 2),
                target="Executor.self_heal_strategy",
                evidence={
                    "recent_tasks": len(recent),
                    "errors": len(error_events),
                    "error_rate": round(error_rate, 2),
                },
                recommended_action="review_self_heal_mapping",
            )]
        return []

    def detect_threshold_drift(self) -> list[Signal]:
        """检测动态阈值是否需要更新。"""
        thresholds = self._load_json("thresholds.json")
        if not thresholds:
            return []

        history = self._load_json("convergence_history.json")
        if len(history) < 20:
            return []

        recent_20 = history[-20:]
        avg_c = sum(e.get("convergence_score", 0) for e in recent_20) / len(recent_20)

        if avg_c < 0.15:
            theta = thresholds.get("θ_phase1_to_2", 0.15)
            new_theta = round(max(0.05, theta - 0.03), 2)
            return [Signal(
                signal_type="threshold_drift",
                severity=round((0.15 - avg_c) / 0.15, 2),
                target="θ_phase1_to_2",
                evidence={
                    "current_theta": theta,
                    "suggested_theta": new_theta,
                    "avg_convergence_20": round(avg_c, 4),
                },
                recommended_action="update_thresholds",
            )]
        return []

    def _load_json(self, filename: str) -> dict | list:
        path = self.feedback_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {} if filename.endswith("s.json") else []


# ═══════════════════════════════════════════════════════════
# 任务生成层
# ═══════════════════════════════════════════════════════════

@dataclass
class ImprovementTask:
    """自我改进任务 — 将检测到的信号转化为可执行的修改。"""

    task_id: str
    signal: Signal
    target_file: str          # 需要修改的文件
    target_param: str         # 需要调整的参数
    current_value: Any        # 当前值
    suggested_value: Any      # 建议值
    rationale: str            # 改进理由
    validation_script: str    # 验证脚本（bash命令）


class TaskGenerator:
    """任务生成器 — 将信号转化为具体的代码修改任务。"""

    def __init__(self, harness_root: Path):
        self.harness_root = harness_root

    def generate(self, signal: Signal) -> Optional[ImprovementTask]:
        """根据信号类型生成对应的改进任务。"""
        if signal.recommended_action == "adjust_gate_thresholds":
            return self._gen_gate_adjustment(signal)
        elif signal.recommended_action == "optimize_strategy_params":
            return self._gen_strategy_optimization(signal)
        elif signal.recommended_action == "update_thresholds":
            return self._gen_threshold_update(signal)
        elif signal.recommended_action == "review_self_heal_mapping":
            return self._gen_self_heal_review(signal)
        return None

    def _gen_gate_adjustment(self, signal: Signal) -> ImprovementTask:
        """生成 SpiralGate 门控阈值调整任务。"""
        gate_file = self.harness_root / "core" / "spiral_gate.py"
        return ImprovementTask(
            task_id=f"meta-{int(time.time())}",
            signal=signal,
            target_file=str(gate_file),
            target_param="complexity_low_threshold",
            current_value=0.30,
            suggested_value=round(0.30 + 0.05 * signal.severity, 2),
            rationale=f"门控过于激进：{signal.evidence.get('modify_rate', 0):.0%} 的跳过任务需要人工修正。提高阈值使更多模糊任务进入螺旋。",
            validation_script=f"python -c \"from agent_harness.core.spiral_gate import SpiralGate; g=SpiralGate(); print(g.complexity_low_threshold)\"",
        )

    def _gen_strategy_optimization(self, signal: Signal) -> ImprovementTask:
        """生成策略参数优化任务。"""
        strategy_file = self.harness_root / "strategies" / "route_table.json"
        return ImprovementTask(
            task_id=f"meta-{int(time.time())}",
            signal=signal,
            target_file=str(strategy_file),
            target_param=f"{signal.target}.spiral_config.max_iterations",
            current_value="(from file)",
            suggested_value="+1 (增加螺旋轮次以提升收敛质量)",
            rationale=f"策略 {signal.target} 收敛速度衰减至 {signal.evidence.get('avg_recent', 0):.4f}，增加螺旋轮次以提升质量。",
            validation_script=f"python -c \"import json; d=json.load(open('{strategy_file}')); print(d['strategies']['{signal.target}']['spiral_config']['max_iterations'])\"",
        )

    def _gen_threshold_update(self, signal: Signal) -> ImprovementTask:
        """生成动态阈值更新任务。"""
        thresholds_file = self.harness_root / "feedback" / "thresholds.json"
        return ImprovementTask(
            task_id=f"meta-{int(time.time())}",
            signal=signal,
            target_file=str(thresholds_file),
            target_param=signal.target,
            current_value=signal.evidence.get("current_theta", 0.15),
            suggested_value=signal.evidence.get("suggested_theta", 0.12),
            rationale=f"收敛速度持续偏低 (avg_c={signal.evidence.get('avg_convergence_20', 0):.4f})，降低Phase切换阈值以更早开始学习。",
            validation_script=f"python -c \"import json; d=json.load(open('{thresholds_file}')); print(d.get('{signal.target}', 'N/A'))\"",
        )

    def _gen_self_heal_review(self, signal: Signal) -> ImprovementTask:
        """生成自愈策略审查任务。"""
        executor_file = self.harness_root / "modules" / "execute" / "executor.py"
        return ImprovementTask(
            task_id=f"meta-{int(time.time())}",
            signal=signal,
            target_file=str(executor_file),
            target_param="FAILURE_SELF_HEAL_MAP",
            current_value="(当前映射表)",
            suggested_value="审查并优化映射",
            rationale=f"错误率 {signal.evidence.get('error_rate', 0):.0%}，可能需要调整自愈策略映射。",
            validation_script=f"python -c \"from agent_harness.modules.execute.executor import FAILURE_SELF_HEAL_MAP; print(len(FAILURE_SELF_HEAL_MAP))\"",
        )


# ═══════════════════════════════════════════════════════════
# 验证层
# ═══════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """改进验证结果。"""
    task: ImprovementTask
    passed: bool
    before_value: Any
    after_value: Any
    metrics_change: dict     # {"convergence_speed": +0.02, ...}
    verdict: str             # applied | rolled_back | skipped


class Validator:
    """验证器 — 对比改进前后的指标，决定应用还是回滚。"""

    def __init__(self, feedback_dir: Path):
        self.feedback_dir = feedback_dir
        self._snapshots: dict[str, dict] = {}

    def snapshot(self, name: str) -> None:
        """保存改进前的状态快照。"""
        self._snapshots[name] = {
            "thresholds": self._load_json("thresholds.json"),
            "weights": self._load_json("weights.json"),
        }

    def validate(self, task: ImprovementTask, before_metrics: dict, after_metrics: dict) -> ValidationResult:
        """对比前后指标，决定是否应用改进。"""
        c_before = before_metrics.get("avg_convergence", 0)
        c_after = after_metrics.get("avg_convergence", 0)
        delta = c_after - c_before

        if delta > 0.02:
            return ValidationResult(
                task=task, passed=True,
                before_value=c_before, after_value=c_after,
                metrics_change={"convergence_speed": round(delta, 4)},
                verdict="applied",
            )
        elif delta > 0:
            return ValidationResult(
                task=task, passed=True,
                before_value=c_before, after_value=c_after,
                metrics_change={"convergence_speed": round(delta, 4)},
                verdict="applied (marginal)",
            )
        else:
            return ValidationResult(
                task=task, passed=False,
                before_value=c_before, after_value=c_after,
                metrics_change={"convergence_speed": round(delta, 4)},
                verdict="rolled_back",
            )

    def _load_json(self, filename: str) -> dict:
        path = self.feedback_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}


# ═══════════════════════════════════════════════════════════
# MetaCognition 主控制器
# ═══════════════════════════════════════════════════════════

@dataclass
class MetaCognition:
    """元认知控制器 — 框架的自我感知和改进外环。

    用法:
        meta = MetaCognition(harness_root=Path("agent_harness"))
        meta.on_execute_improvement = my_harness_adapter.start  # 注入执行能力
        report = meta.run_cycle()
        # → 检测信号 → 生成任务 → 执行改进 → 验证 → 生成报告
    """

    harness_root: Path
    feedback_dir: Path | None = None

    detector: SignalDetector | None = field(init=False, default=None)
    generator: TaskGenerator | None = field(init=False, default=None)
    validator: Validator | None = field(init=False, default=None)

    # 外部注入的回调：实际执行改进任务（通过 Harness 或直接修改文件）
    on_execute_improvement: Callable[[ImprovementTask], bool] | None = None
    on_collect_metrics: Callable[[], dict] | None = None

    # 运行记录
    cycle_log: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self):
        fb_dir = self.feedback_dir or (self.harness_root / "feedback")
        self.detector = SignalDetector(fb_dir)
        self.generator = TaskGenerator(self.harness_root)
        self.validator = Validator(fb_dir)

    def run_cycle(self, max_improvements: int = 3) -> dict:
        """运行一次完整的元认知循环。

        1. 检测信号
        2. 生成改进任务
        3. 对每个任务：快照 → 执行 → 验证 → 应用/回滚
        4. 生成报告
        """
        cycle_start = datetime.now(timezone.utc)
        signals = self.detector.detect_all()

        if not signals:
            return self._make_report(cycle_start, [], "no_signals")

        improvements = []
        for sig in signals[:max_improvements]:
            task = self.generator.generate(sig)
            if task:
                improvements.append(task)

        results = []
        for task in improvements:
            self.validator.snapshot(task.task_id)

            before_metrics = self.on_collect_metrics() if self.on_collect_metrics else {}

            success = False
            if self.on_execute_improvement:
                success = self.on_execute_improvement(task)
            else:
                success = self._default_execute(task)

            after_metrics = self.on_collect_metrics() if self.on_collect_metrics else {}
            merged_after = {**before_metrics, **after_metrics}

            vr = self.validator.validate(task, before_metrics, merged_after)
            results.append(vr)

            self.cycle_log.append({
                "task_id": task.task_id,
                "signal": task.signal.signal_type,
                "severity": task.signal.severity,
                "target": task.target_file,
                "verdict": vr.verdict,
                "metrics_change": vr.metrics_change,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if success and not vr.passed:
                self._rollback(task, self.validator._snapshots.get(task.task_id, {}))

        return self._make_report(cycle_start, results, "completed")

    def get_status(self) -> dict:
        """获取当前元认知状态（不执行改进）。"""
        signals = self.detector.detect_all()
        return {
            "signals_detected": len(signals),
            "top_signal": {
                "type": signals[0].signal_type,
                "severity": signals[0].severity,
                "target": signals[0].target,
            } if signals else None,
            "cycle_count": len(self.cycle_log),
            "last_cycle": self.cycle_log[-1] if self.cycle_log else None,
            "health": "healthy" if not signals else
                      "warning" if signals[0].severity < 0.5 else
                      "needs_attention",
        }

    def _default_execute(self, task: ImprovementTask) -> bool:
        """默认执行方式 — 打印改进计划（不实际修改文件，用于测试）。"""
        print(f"\n  [MetaCognition] 检测到改进机会:")
        print(f"    信号: {task.signal.signal_type} (严重度: {task.signal.severity})")
        print(f"    目标: {task.target_file}")
        print(f"    参数: {task.target_param}")
        print(f"    当前值: {task.current_value}")
        print(f"    建议值: {task.suggested_value}")
        print(f"    理由: {task.rationale}")
        return True

    def _rollback(self, task: ImprovementTask, snapshot: dict) -> None:
        """回滚改进。"""
        print(f"  [MetaCognition] 回滚: {task.task_id} (改进未通过验证)")

    def _make_report(self, start_time: datetime, results: list, status: str) -> dict:
        applied = [r for r in results if r.verdict.startswith("applied")]
        rolled = [r for r in results if r.verdict == "rolled_back"]
        return {
            "cycle_status": status,
            "duration_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            "signals_detected": len(results),
            "improvements_applied": len(applied),
            "improvements_rolled_back": len(rolled),
            "details": [
                {
                    "target": r.task.target_param,
                    "signal": r.task.signal.signal_type,
                    "verdict": r.verdict,
                    "delta": r.metrics_change,
                }
                for r in results
            ],
            "framework_health": "improving" if len(applied) > len(rolled) else "stable",
        }
