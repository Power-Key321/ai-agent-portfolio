"""
Auto-Attach 自动挂靠引擎 — 让 Harness 透明嵌入 Claude Code 的每一条对话。

职责:
1. 多进程文件锁 — 多窗口并发安全写入 feedback 文件
2. 会话隔离 — 每个 CC 窗口唯一 session_id，状态不冲突
3. 学习持久化 — ModelRouter learned_patterns 自动落盘/恢复
4. 自动反馈记录 — 每次交互后记录收敛数据
5. MetaCognition 调度 — 每 N 次交互触发一次框架自进化

平移友好: 所有持久化数据在项目目录内，复制项目 = 复制进化状态。
"""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════
# 多进程文件锁（Windows + Linux 兼容）
# ═══════════════════════════════════════════════════════════

class FileLock:
    """跨平台文件锁 — 多窗口并发安全。

    策略: lockfile + PID 检查 + 过期清理。
    不依赖 fcntl/msvcrt，纯文件系统实现，保证可平移。
    """

    def __init__(self, lock_path: Path, timeout: float = 5.0, stale_seconds: float = 30.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self._acquired = False

    def acquire(self) -> bool:
        """获取锁，超时返回 False。"""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                # 检查是否有过期锁
                if self.lock_path.exists():
                    stale = self._is_stale()
                    if stale:
                        self.lock_path.unlink(missing_ok=True)
                    else:
                        time.sleep(0.05 + 0.05 * (hash(str(os.getpid())) % 10) / 10)
                        continue
                # 创建锁文件
                content = f"{os.getpid()}\n{time.time()}\n{socket.gethostname()}"
                self.lock_path.write_text(content, encoding="utf-8")
                # 双重验证
                time.sleep(0.02)
                if self._verify_owner():
                    self._acquired = True
                    return True
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)
        return False

    def release(self) -> None:
        """释放锁。"""
        if self._acquired and self.lock_path.exists():
            try:
                current = self.lock_path.read_text(encoding="utf-8").strip()
                if str(os.getpid()) in current:
                    self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass
        self._acquired = False

    def _is_stale(self) -> bool:
        """检查锁是否过期（进程已死）。"""
        try:
            content = self.lock_path.read_text(encoding="utf-8").strip()
            lines = content.split("\n")
            if len(lines) >= 2:
                lock_time = float(lines[1])
                if time.time() - lock_time > self.stale_seconds:
                    return True
                # 检查 PID 是否存在
                pid = int(lines[0])
                try:
                    os.kill(pid, 0)
                    return False  # 进程存在
                except (OSError, ProcessLookupError):
                    return True  # 进程不存在
        except Exception:
            return True
        return False

    def _verify_owner(self) -> bool:
        """验证当前进程确实是锁的持有者。"""
        try:
            content = self.lock_path.read_text(encoding="utf-8").strip()
            return str(os.getpid()) in content
        except Exception:
            return False

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"无法获取锁: {self.lock_path}")
        return self

    def __exit__(self, *args):
        self.release()


def atomic_write_json(path: Path, data: Any) -> None:
    """原子写入 JSON — 先写临时文件再 rename，防止写一半被读取。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)  # 在 Windows 上也是原子的（同卷）
    finally:
        tmp_path.unlink(missing_ok=True)


def atomic_read_json(path: Path) -> Any:
    """安全读取 JSON — 如果 .tmp 文件残留（崩溃恢复），优先使用正式文件。"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # 文件损坏，尝试从 .tmp 恢复
        for tmp in sorted(path.parent.glob(path.name + ".tmp.*"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(tmp.read_text(encoding="utf-8"))
                atomic_write_json(path, data)
                return data
            except Exception:
                continue
        return None


# ═══════════════════════════════════════════════════════════
# 会话隔离
# ═══════════════════════════════════════════════════════════

@dataclass
class SessionIdentity:
    """唯一会话标识 — 每个 CC 窗口一个独立 session。"""
    session_id: str
    hostname: str
    pid: int
    started_at: str
    window_label: str  # 用户可自定义的窗口标签

    @classmethod
    def create(cls, window_label: str = "") -> SessionIdentity:
        return cls(
            session_id=str(uuid.uuid4())[:12],
            hostname=socket.gethostname(),
            pid=os.getpid(),
            started_at=datetime.now(timezone.utc).isoformat(),
            window_label=window_label or f"cc-{os.getpid()}",
        )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "started_at": self.started_at,
            "window_label": self.window_label,
        }


# ═══════════════════════════════════════════════════════════
# 学习模式持久化
# ═══════════════════════════════════════════════════════════

class LearnedPatternStore:
    """ModelRouter 学习模式的持久化存储。

    路径: agent_harness/feedback/learned_patterns.json
    """

    def __init__(self, feedback_dir: Path):
        self.path = feedback_dir / "learned_patterns.json"
        self._lock_path = feedback_dir / ".learned_patterns.lock"

    def save(self, patterns: dict[str, list[str]]) -> None:
        """原子保存学习到的模式。"""
        lock = FileLock(self._lock_path)
        if lock.acquire():
            try:
                atomic_write_json(self.path, patterns)
            finally:
                lock.release()

    def load(self) -> dict[str, list[str]]:
        """加载已持久化的学习模式。"""
        data = atomic_read_json(self.path)
        if data is None:
            return {}
        return {k: v for k, v in data.items() if isinstance(v, list)}

    def merge_and_save(self, new_patterns: dict[str, list[str]]) -> dict[str, list[str]]:
        """合并新学习模式到持久化存储（多窗口安全）。"""
        lock = FileLock(self._lock_path)
        if lock.acquire():
            try:
                existing = self.load()
                for intent, patterns in new_patterns.items():
                    if intent not in existing:
                        existing[intent] = []
                    for p in patterns:
                        if p not in existing[intent]:
                            existing[intent].append(p)
                # 每个意图最多保留 50 个模式
                for intent in existing:
                    existing[intent] = existing[intent][-50:]
                atomic_write_json(self.path, existing)
                return existing
            finally:
                lock.release()
        return new_patterns


# ═══════════════════════════════════════════════════════════
# MetaCognition 调度器
# ═══════════════════════════════════════════════════════════

@dataclass
class MetaCognitionScheduler:
    """MetaCognition 周期调度器。

    不是每次交互都触发自进化（成本太高），而是积累到一定阈值后触发。
    """

    feedback_dir: Path
    harness_root: Path
    trigger_interval: int = 10  # 每 10 次交互触发一次
    _interaction_count: int = field(default=0, init=False)
    _count_path: Path | None = field(default=None, init=False)

    def __post_init__(self):
        self._count_path = self.feedback_dir / ".meta_interaction_count"
        self._load_count()

    def record_interaction(self) -> bool:
        """记录一次交互。返回 True 表示应该触发 MetaCognition。"""
        self._interaction_count += 1
        self._save_count()
        if self._interaction_count >= self.trigger_interval:
            self._interaction_count = 0
            self._save_count()
            return True
        return False

    def run_meta_cognition_if_due(self) -> dict | None:
        """如果到了触发周期，运行一次 MetaCognition 并返回报告。"""
        if not self.record_interaction():
            return None
        try:
            from agent_harness.core.meta_cognition import MetaCognition
            meta = MetaCognition(harness_root=self.harness_root, feedback_dir=self.feedback_dir)
            report = meta.run_cycle(max_improvements=2)
            return report
        except Exception:
            return {"cycle_status": "error", "error": "MetaCognition 执行失败"}

    def _load_count(self) -> None:
        if self._count_path and self._count_path.exists():
            try:
                self._interaction_count = int(self._count_path.read_text().strip())
            except Exception:
                self._interaction_count = 0

    def _save_count(self) -> None:
        if self._count_path:
            try:
                self._count_path.write_text(str(self._interaction_count))
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════
# 自动反馈记录器
# ═══════════════════════════════════════════════════════════

@dataclass
class AutoFeedbackRecorder:
    """每次 CC 交互后自动记录反馈数据。

    由 post-interaction hook 调用，轻量级，不阻塞用户。
    """

    feedback_dir: Path
    session: SessionIdentity
    _lock_dir: Path = field(init=False)

    def __post_init__(self):
        self._lock_dir = self.feedback_dir / ".locks"
        self._lock_dir.mkdir(parents=True, exist_ok=True)

    def record(self, event: dict) -> bool:
        """记录一次交互事件。

        event 至少包含:
        - intent_class: 意图分类
        - strategy_id: 策略ID
        - signal_type: accepted|modified|retried|ignored
        - spiral_iterations: 螺旋轮次
        - convergence_score: 收敛分数
        - was_harnessed: 是否走了 harness 流程
        """
        event.setdefault("session_id", self.session.session_id)
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        event.setdefault("hostname", self.session.hostname)

        # 追加到收敛历史（带锁保护）
        self._append_convergence(event)

        # 更新权重
        self._update_weights(event)

        return True

    def _append_convergence(self, event: dict) -> None:
        """原子追加收敛历史（多窗口安全）。"""
        history_path = self.feedback_dir / "convergence_history.json"
        lock = FileLock(self._lock_dir / "convergence_history.lock")

        if lock.acquire():
            try:
                history = atomic_read_json(history_path) or []
                history.append(event)
                # 保留最近 500 条
                if len(history) > 500:
                    history = history[-500:]
                atomic_write_json(history_path, history)
            finally:
                lock.release()

    def _update_weights(self, event: dict) -> None:
        """更新策略权重（增量式）。"""
        weights_path = self.feedback_dir / "weights.json"
        lock = FileLock(self._lock_dir / "weights.lock")

        sid = event.get("strategy_id", "unknown")
        signal = event.get("signal_type", "accepted")

        if lock.acquire():
            try:
                weights = atomic_read_json(weights_path) or {}
                current = weights.get(sid, 0.5)

                # 增量更新: accepted +0.02, modified -0.01, retried -0.03
                deltas = {"accepted": 0.02, "modified": -0.01, "retried": -0.03, "ignored": -0.005}
                delta = deltas.get(signal, 0.0)
                weights[sid] = max(0.1, min(0.95, current + delta))

                atomic_write_json(weights_path, weights)
            finally:
                lock.release()


# ═══════════════════════════════════════════════════════════
# AutoAttach 主控制器
# ═══════════════════════════════════════════════════════════

@dataclass
class AutoAttach:
    """自动挂靠主控制器 — 一切自动化的入口。

    用法:
        aa = AutoAttach(harness_root=Path("agent_harness"))
        aa.on_session_start()        # CC 启动时调用
        aa.on_interaction_end({...}) # 每次交互结束时调用
        aa.on_session_end()          # CC 关闭时调用
    """

    harness_root: Path
    feedback_dir: Path | None = None
    session: SessionIdentity | None = field(default=None, init=False)
    recorder: AutoFeedbackRecorder | None = field(default=None, init=False)
    scheduler: MetaCognitionScheduler | None = field(default=None, init=False)
    pattern_store: LearnedPatternStore | None = field(default=None, init=False)

    def __post_init__(self):
        if self.feedback_dir is None:
            self.feedback_dir = self.harness_root / "feedback"

    def on_session_start(self, window_label: str = "") -> SessionIdentity:
        """CC 会话启动时初始化。"""
        self.session = SessionIdentity.create(window_label)
        self.recorder = AutoFeedbackRecorder(
            feedback_dir=self.feedback_dir,
            session=self.session,
        )
        self.scheduler = MetaCognitionScheduler(
            feedback_dir=self.feedback_dir,
            harness_root=self.harness_root,
        )
        self.pattern_store = LearnedPatternStore(self.feedback_dir)
        self._write_session_marker()
        return self.session

    def on_interaction_end(self, event: dict) -> dict:
        """每次 CC 交互结束时调用。

        Returns:
            {"feedback_recorded": bool, "meta_triggered": bool, "meta_report": dict|None}
        """
        if self.recorder is None:
            self.on_session_start()

        result = {"feedback_recorded": False, "meta_triggered": False, "meta_report": None}

        # 1. 记录反馈
        if self.recorder:
            self.recorder.record(event)
            result["feedback_recorded"] = True

        # 2. 检查是否需要 MetaCognition
        if self.scheduler and self.scheduler.record_interaction():
            result["meta_triggered"] = True
            result["meta_report"] = self.scheduler.run_meta_cognition_if_due()

        return result

    def on_session_end(self) -> None:
        """CC 会话结束时清理。"""
        self._remove_session_marker()

    def load_learned_patterns(self) -> dict[str, list[str]]:
        """加载已持久化的学习模式（供 ModelRouter 初始化）。"""
        if self.pattern_store is None:
            self.pattern_store = LearnedPatternStore(self.feedback_dir)
        return self.pattern_store.load()

    def save_learned_patterns(self, patterns: dict[str, list[str]]) -> None:
        """保存学习模式到持久化存储。"""
        if self.pattern_store is None:
            self.pattern_store = LearnedPatternStore(self.feedback_dir)
        self.pattern_store.merge_and_save(patterns)

    def get_portability_bundle(self) -> dict:
        """导出完整的可平移数据包。

        复制项目到新电脑后，调用此方法验证数据完整性。
        Returns:
            {"files": [...], "checksum": "...", "summary": {...}}
        """
        import hashlib
        files = []
        checksums = []

        for f in self.feedback_dir.glob("*.json"):
            if f.name.startswith("."):
                continue
            content = f.read_bytes()
            files.append({
                "path": str(f.relative_to(self.harness_root.parent)),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest()[:16],
            })
            checksums.append(hashlib.sha256(content).digest())

        combined = b"".join(checksums)
        return {
            "files": files,
            "checksum": hashlib.sha256(combined).hexdigest(),
            "summary": {
                "total_files": len(files),
                "total_size_kb": sum(f["size"] for f in files) // 1024,
                "session_id": self.session.session_id if self.session else None,
            },
        }

    def verify_portability(self, bundle: dict) -> bool:
        """验证可平移数据包的完整性。"""
        import hashlib
        for f_info in bundle.get("files", []):
            f_path = self.harness_root.parent / f_info["path"]
            if not f_path.exists():
                return False
            actual = hashlib.sha256(f_path.read_bytes()).hexdigest()[:16]
            if actual != f_info["sha256"]:
                return False
        return True

    def _write_session_marker(self) -> None:
        """写入会话标记文件（用于多窗口发现）。"""
        if self.session:
            marker_dir = self.feedback_dir / ".active_sessions"
            marker_dir.mkdir(parents=True, exist_ok=True)
            marker = marker_dir / f"{self.session.session_id}.json"
            atomic_write_json(marker, self.session.to_dict())

    def _remove_session_marker(self) -> None:
        """移除会话标记。"""
        if self.session:
            marker = self.feedback_dir / ".active_sessions" / f"{self.session.session_id}.json"
            marker.unlink(missing_ok=True)

    @staticmethod
    def list_active_sessions(feedback_dir: Path) -> list[dict]:
        """列出所有活跃的 CC 窗口会话。"""
        marker_dir = feedback_dir / ".active_sessions"
        if not marker_dir.exists():
            return []
        sessions = []
        for m in marker_dir.glob("*.json"):
            data = atomic_read_json(m)
            if data:
                sessions.append(data)
        return sessions


# ── 模块级便捷函数 ──

_global_auto_attach: Optional[AutoAttach] = None


def get_auto_attach(harness_root: Path | None = None) -> AutoAttach:
    """获取全局 AutoAttach 单例。"""
    global _global_auto_attach
    if _global_auto_attach is None:
        if harness_root is None:
            from pathlib import Path as _Path
            harness_root = _Path(__file__).resolve().parent.parent
        _global_auto_attach = AutoAttach(harness_root=harness_root)
    return _global_auto_attach
