"""
反馈引擎 — Phase 2：记录 + 自动应用。

职责:
1. 接收每次任务完成的反馈信号
2. 记录策略权重、收敛速度历史（多窗口安全 + 原子写入）
3. 记录动态阈值状态
4. Phase 2: 自动应用权重更新和阈值自适应
5. 会话隔离: 每个 CC 窗口独立记录，全局合并
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── 轻量级原子读写（避免循环导入） ──

def _atomic_read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


class SimpleFileLock:
    """简化版文件锁 — 避免循环导入 auto_attach.FileLock。"""

    def __init__(self, lock_path: Path, timeout: float = 3.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._acquired = False

    def acquire(self) -> bool:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                if self.lock_path.exists():
                    try:
                        age = time.time() - self.lock_path.stat().st_mtime
                        if age > 30:
                            self.lock_path.unlink(missing_ok=True)
                        else:
                            time.sleep(0.05)
                            continue
                    except Exception:
                        time.sleep(0.05)
                        continue
                self.lock_path.write_text(str(os.getpid()), encoding="utf-8")
                time.sleep(0.02)
                if self.lock_path.read_text().strip() == str(os.getpid()):
                    self._acquired = True
                    return True
            except Exception:
                time.sleep(0.1)
        return False

    def release(self) -> None:
        if self._acquired:
            try:
                if self.lock_path.exists():
                    if self.lock_path.read_text().strip() == str(os.getpid()):
                        self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass
        self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"无法获取锁: {self.lock_path}")
        return self

    def __exit__(self, *args):
        self.release()


# ═══════════════════════════════════════════════════════════
# FeedbackEngine Phase 2
# ═══════════════════════════════════════════════════════════

def _default_storage_dir() -> Path:
    """默认反馈存储目录。

    默认落在包内 feedback/；环境变量 AGENT_HARNESS_STATE_DIR 可覆盖，
    让测试与多环境部署把状态写进隔离目录，避免彼此污染。
    """
    root = os.environ.get("AGENT_HARNESS_STATE_DIR")
    return Path(root) if root else Path(__file__).resolve().parent.parent / "feedback"


@dataclass
class FeedbackEngine:
    """反馈引擎 — Phase 2：记录 + 自动权重更新。

    Args:
        storage_dir: 反馈数据存储目录
    """

    storage_dir: Path = field(default_factory=_default_storage_dir)
    auto_apply: bool = True   # Phase 2 开关：是否自动应用反馈到权重

    # v3: 反馈事件钩子列表 (KnowledgeGraph 等外部系统可订阅)
    on_event_recorded: list = field(default_factory=list)

    # 内存态
    _weights: dict[str, float] = field(default_factory=dict, init=False)
    _convergence_history: list[dict] = field(default_factory=list, init=False)
    _thresholds: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock_dir = self.storage_dir / ".locks"
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

    # ── 记录接口 ──

    def record(self, event: dict) -> None:
        """记录一次任务反馈事件（多窗口安全）。

        event 格式:
        {
            "trace_id": "...",
            "session_id": "...",
            "strategy_id": "code_feature",
            "signal_type": "accepted|modified|retried|ignored",
            "signal_strength": 0.0-1.0,
            "spiral_iterations_used": 3,
            "convergence_score": 0.323,
            "timestamp": "iso8601",
            "was_harnessed": true,
        }
        """
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._convergence_history.append(event)

        sid = event.get("strategy_id", "unknown")
        self._weights.setdefault(sid, 0.5)

        # 原子持久化
        self._save_weights_atomic()
        self._append_convergence_atomic(event)

        # Phase 2: 自动应用反馈
        if self.auto_apply:
            self.apply_feedback(event)

        # v3: 通知所有订阅的外部系统 (如 KnowledgeGraph)
        for hook in self.on_event_recorded:
            try:
                hook(event)
            except Exception:
                pass

    def record_task_result(self, task_result: dict) -> None:
        """从 harness 任务结果中提取反馈并记录。"""
        event = {
            "trace_id": task_result.get("trace_id", ""),
            "strategy_id": task_result.get("strategy_id", "unknown"),
            "signal_type": "accepted",
            "signal_strength": 0.8,
            "spiral_iterations_used": task_result.get("spiral_iterations", 0),
            "convergence_score": task_result.get("convergence", {}).get("convergence_speed", 0.0),
            "was_harnessed": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.record(event)

    # ── Phase 2: 自动应用反馈 ──

    def apply_feedback(self, event: dict) -> dict:
        """Phase 2 核心：根据单次事件增量更新权重和阈值。

        增量规则:
        - accepted: 权重 +0.01（确认策略有效）
        - modified: 权重 -0.005（用户修正，策略可能不完全匹配）
        - retried: 权重 -0.02（执行失败，策略或参数有问题）
        - ignored: 权重 -0.002（微弱负面信号）

        长期效果：权重收敛到各策略的真实有效率。

        Returns:
            {"weights_updated": bool, "thresholds_updated": bool, "phase": str}
        """
        sid = event.get("strategy_id", "unknown")
        signal = event.get("signal_type", "accepted")
        convergence_score = event.get("convergence_score", 0.0)

        result = {"weights_updated": False, "thresholds_updated": False, "phase": self.get_current_phase()}

        # 增量权重更新
        deltas = {"accepted": 0.01, "modified": -0.005, "retried": -0.02, "ignored": -0.002}
        delta = deltas.get(signal, 0.0)
        current = self._weights.get(sid, 0.5)
        self._weights[sid] = max(0.1, min(0.95, current + delta))
        result["weights_updated"] = True

        # 阈值自适应：当连续低收敛时，降低 Phase 切换阈值
        if convergence_score > 0 and convergence_score < 0.15:
            theta = self._thresholds.get("θ_phase1_to_2", 0.15)
            self._thresholds["θ_phase1_to_2"] = max(0.05, theta - 0.005)
            result["thresholds_updated"] = True

        # 持久化更新后的权重和阈值
        self._save_weights_atomic()
        if result["thresholds_updated"]:
            self._save_thresholds_atomic()

        result["phase"] = self.get_current_phase()
        return result

    def apply_feedback_batch(self, min_events: int = 20) -> dict:
        """批量应用反馈 — 从历史数据中重新计算最优权重。

        当积累足够事件后，用历史统计替代增量更新。
        """
        if len(self._convergence_history) < min_events:
            return {"applied": False, "reason": f"事件不足 ({len(self._convergence_history)} < {min_events})"}

        # 按策略统计成功率
        strategy_stats: dict[str, dict] = {}
        for e in self._convergence_history:
            sid = e.get("strategy_id", "unknown")
            if sid not in strategy_stats:
                strategy_stats[sid] = {"total": 0, "accepted": 0, "modified": 0, "retried": 0}
            strategy_stats[sid]["total"] += 1
            signal = e.get("signal_type", "accepted")
            strategy_stats[sid][signal] = strategy_stats[sid].get(signal, 0) + 1

        # 计算贝叶斯平滑权重
        prior_weight = 0.5
        prior_strength = 10  # 先验强度（伪计数）
        updates = {}
        for sid, stats in strategy_stats.items():
            n = stats["total"]
            success_rate = (stats.get("accepted", 0) + 0.5 * stats.get("modified", 0)) / max(n, 1)
            # 贝叶斯平滑: (prior * strength + observed * n) / (strength + n)
            smoothed = (prior_weight * prior_strength + success_rate * n) / (prior_strength + n)
            updates[sid] = round(smoothed, 4)

        self._weights.update(updates)
        self._save_weights_atomic()

        return {"applied": True, "updated_strategies": list(updates.keys()), "new_weights": updates}

    # ── 查询接口 ──

    def get_weight(self, strategy_id: str) -> float:
        return self._weights.get(strategy_id, 0.5)

    def get_all_weights(self) -> dict[str, float]:
        return dict(self._weights)

    def get_recent_convergence(self, n: int = 20) -> list[dict]:
        return self._convergence_history[-n:]

    def get_average_convergence(self, strategy_id: Optional[str] = None) -> float:
        items = self._convergence_history
        if strategy_id:
            items = [e for e in items if e.get("strategy_id") == strategy_id]
        if not items:
            return 0.0
        scores = [e.get("convergence_score", 0.0) for e in items]
        return sum(scores) / len(scores)

    def get_thresholds(self) -> dict:
        return dict(self._thresholds)

    def get_session_stats(self, session_id: str) -> dict:
        """获取特定会话的统计。"""
        items = [e for e in self._convergence_history if e.get("session_id") == session_id]
        if not items:
            return {"session_id": session_id, "total_events": 0}
        strategies = {}
        for e in items:
            sid = e.get("strategy_id", "unknown")
            strategies.setdefault(sid, 0)
            strategies[sid] += 1
        return {
            "session_id": session_id,
            "total_events": len(items),
            "strategies": strategies,
            "avg_convergence": sum(e.get("convergence_score", 0) for e in items) / len(items),
        }

    # ── 动态阈值查询 ──

    def get_current_phase(self) -> str:
        """根据当前权重状态判断处于哪个 Phase。"""
        if not self._weights:
            return "phase_1"
        max_w = max(self._weights.values())
        std_w = self._weight_std()
        theta_12 = self._thresholds.get("θ_phase1_to_2", 0.15)
        theta_23 = self._thresholds.get("θ_phase2_to_3", 0.65)

        if std_w <= theta_12:
            return "phase_1"
        if max_w <= theta_23:
            return "phase_2"
        return "phase_3"

    def summary(self) -> dict:
        return {
            "phase": self.get_current_phase(),
            "weights": dict(self._weights),
            "thresholds": dict(self._thresholds),
            "total_events": len(self._convergence_history),
            "recent_avg_convergence": self.get_average_convergence(),
            "auto_apply": self.auto_apply,
        }

    # ── 持久化（多窗口安全） ──

    def _load_state(self) -> None:
        self._weights = _atomic_read_json(self.storage_dir / "weights.json") or {}
        self._convergence_history = _atomic_read_json(self.storage_dir / "convergence_history.json") or []
        self._thresholds = _atomic_read_json(self.storage_dir / "thresholds.json") or {
            "θ_phase1_to_2": 0.15,
            "θ_phase2_to_3": 0.65,
            "learning_rate": 0.05,
        }

    def _save_weights_atomic(self) -> None:
        lock = SimpleFileLock(self._lock_dir / "weights.lock")
        if lock.acquire():
            try:
                # 合并最新数据
                existing = _atomic_read_json(self.storage_dir / "weights.json") or {}
                existing.update(self._weights)
                self._weights = existing
                _atomic_write_json(self.storage_dir / "weights.json", existing)
            finally:
                lock.release()

    def _append_convergence_atomic(self, event: dict) -> None:
        lock = SimpleFileLock(self._lock_dir / "convergence_history.lock")
        if lock.acquire():
            try:
                history = _atomic_read_json(self.storage_dir / "convergence_history.json") or []
                history.append(event)
                if len(history) > 500:
                    history = history[-500:]
                _atomic_write_json(self.storage_dir / "convergence_history.json", history)
                self._convergence_history = history
            finally:
                lock.release()

    def _save_thresholds_atomic(self) -> None:
        _atomic_write_json(self.storage_dir / "thresholds.json", self._thresholds)

    def _weight_std(self) -> float:
        import math
        if len(self._weights) < 2:
            return 0.0
        values = list(self._weights.values())
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
