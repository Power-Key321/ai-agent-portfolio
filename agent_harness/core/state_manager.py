"""
StateManager — Harness 状态持久化，支持断点续跑。

在 CC 交互模式下，每个螺旋轮次完成后自动落盘。
支持:
- adapter.save_state(slug) → 写入 master.json + sub{N}_state.json
- adapter.resume(slug) → 恢复状态，继续执行
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class StateManager:
    """Harness 状态持久化管理器。"""

    workspace_dir: str = ".claude/harness_states"

    def __post_init__(self):
        os.makedirs(self.workspace_dir, exist_ok=True)

    def save(self, slug: str, state: dict, subtask_states: list[dict] | None = None) -> str:
        """保存完整状态到磁盘。

        Args:
            slug: 任务标识（如 "jwt-middleware-20260702"）
            state: 主状态（来自 adapter.get_cc_state()）
            subtask_states: 子任务状态列表

        Returns:
            状态目录路径
        """
        task_dir = Path(self.workspace_dir) / slug
        task_dir.mkdir(parents=True, exist_ok=True)

        master = {
            "task_slug": slug,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "version": "2.0",
            "status": state.get("status", "IN_PROGRESS"),
            "intent": state.get("intent", ""),
            "strategy": state.get("strategy", ""),
            "spiral_round": state.get("spiral_round", 0),
            "convergence_radius": state.get("convergence_radius", 1.0),
            "task_data": state.get("task", {}),
            "subtask_summaries": [
                {
                    "id": st.get("subtask_id", ""),
                    "status": st.get("status", "pending"),
                    "output_summary": st.get("output_summary", ""),
                }
                for st in (subtask_states or [])
            ],
        }

        master_path = task_dir / "master.json"
        master_path.write_text(
            json.dumps(master, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if subtask_states:
            for st in subtask_states:
                sub_path = task_dir / f"sub_{st.get('subtask_id', 'unknown')}.json"
                sub_path.write_text(
                    json.dumps(st, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        return str(task_dir)

    def load(self, slug: str) -> dict | None:
        """从磁盘恢复状态。

        Returns:
            {"master": {...}, "subtasks": [...]} 或 None
        """
        task_dir = Path(self.workspace_dir) / slug
        master_path = task_dir / "master.json"

        if not master_path.exists():
            return None

        master = json.loads(master_path.read_text(encoding="utf-8"))

        subtasks = []
        for sub_file in sorted(task_dir.glob("sub_*.json")):
            subtasks.append(json.loads(sub_file.read_text(encoding="utf-8")))

        return {"master": master, "subtasks": subtasks}

    def list_sessions(self) -> list[dict]:
        """列出所有已保存的会话。"""
        task_dir = Path(self.workspace_dir)
        sessions = []
        for d in sorted(task_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir():
                master_path = d / "master.json"
                if master_path.exists():
                    m = json.loads(master_path.read_text(encoding="utf-8"))
                    sessions.append({
                        "slug": d.name,
                        "saved_at": m.get("saved_at", ""),
                        "status": m.get("status", ""),
                        "intent": m.get("intent", ""),
                        "spiral_round": m.get("spiral_round", 0),
                    })
        return sessions

    def delete(self, slug: str) -> bool:
        """删除指定会话的状态文件。"""
        import shutil
        task_dir = Path(self.workspace_dir) / slug
        if task_dir.exists():
            shutil.rmtree(task_dir)
            return True
        return False
