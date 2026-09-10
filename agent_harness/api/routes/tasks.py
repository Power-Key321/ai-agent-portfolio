"""
任务执行路由 — /api/task/*

POST   /api/task/start        — 提交任务
WS     /api/task/{id}/stream  — 流式推送执行过程
GET    /api/task/{id}/status  — 查询任务状态
GET    /api/tasks             — 列出所有任务
"""

from __future__ import annotations

import json
import uuid
import threading
import asyncio
import queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

router = APIRouter(prefix="/api/task", tags=["tasks"])

# ── 内存任务存储 ──

@dataclass
class TaskRecord:
    task_id: str
    intent: str
    strategy: str
    status: str  # pending | running | completed | failed
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None
    spiral_iterations: int = 0
    cost_estimate: float = 0.0
    events: list[dict] = field(default_factory=list)

_tasks: dict[str, TaskRecord] = {}
_event_queues: dict[str, queue.Queue] = {}
_adapter_instance: Any = None


def get_adapter():
    global _adapter_instance
    if _adapter_instance is None:
        from agent_harness.adapters.deepseek import DeepSeekAdapter
        _adapter_instance = DeepSeekAdapter()
    return _adapter_instance


def set_adapter(adapter):
    global _adapter_instance
    _adapter_instance = adapter


def _push_event(task_id: str, event: dict):
    """推送事件到 WebSocket 队列。"""
    if task_id in _event_queues:
        _event_queues[task_id].put(event)


def _run_task(task_id: str, user_input: str, intent_override: str | None):
    """在线程中执行任务，推送每步事件。"""
    record = _tasks.get(task_id)
    if not record:
        return

    try:
        adapter = get_adapter()
        record.status = "running"

        # Step 1: 诊断/装配
        _push_event(task_id, {
            "type": "phase",
            "phase": "diagnose",
            "message": "正在分析任务意图和装配模块链...",
        })
        print(f"[Task {task_id}] Starting diagnose...", flush=True)
        diagnosis = adapter.diagnose(user_input, intent_override=intent_override)
        print(f"[Task {task_id}] Diagnose complete: {diagnosis['intent']}", flush=True)
        _push_event(task_id, {
            "type": "assembly",
            "intent": diagnosis["intent"],
            "strategy": diagnosis["strategy"],
            "modules": diagnosis["assembly"],
        })

        # Step 2: 执行
        _push_event(task_id, {
            "type": "phase",
            "phase": "execute",
            "message": "正在执行六模块流水线...",
        })
        print(f"[Task {task_id}] Starting adapter.start()...", flush=True)

        result = adapter.start(user_input, intent_override=intent_override)

        print(f"[Task {task_id}] adapter.start() complete!", flush=True)

        # 收集螺旋信息
        spiral_info = result.get("convergence", {})
        record.spiral_iterations = spiral_info.get("iterations", 0)
        record.cost_estimate = result.get("cost_estimate", 0)

        _push_event(task_id, {
            "type": "phase",
            "phase": "deliver",
            "message": "正在交付结果...",
        })

        record.status = "completed"
        record.finished_at = datetime.now(timezone.utc).isoformat()
        record.result = result

        _push_event(task_id, {
            "type": "completed",
            "result": result,
            "spiral_iterations": record.spiral_iterations,
            "cost_estimate": record.cost_estimate,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Task {task_id}] ERROR: {e}", flush=True)
        record.status = "failed"
        record.error = str(e)
        record.finished_at = datetime.now(timezone.utc).isoformat()
        _push_event(task_id, {
            "type": "error",
            "error": str(e),
        })


@router.post("/start")
async def start_task(payload: dict):
    """提交任务，返回 task_id 和初始装配计划。

    Body:
        {"input": "帮我实现一个JWT认证", "intent_override": "code_feature" (可选)}
    """
    user_input = payload.get("input", "")
    if not user_input:
        raise HTTPException(status_code=400, detail="缺少 'input' 字段")

    intent_override = payload.get("intent_override")
    task_id = str(uuid.uuid4())[:8]

    record = TaskRecord(
        task_id=task_id,
        intent="",
        strategy="",
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _tasks[task_id] = record

    # 创建事件队列
    q: queue.Queue = queue.Queue()
    _event_queues[task_id] = q

    # 获取诊断信息
    try:
        adapter = get_adapter()
        diagnosis = adapter.diagnose(user_input, intent_override=intent_override)
        record.intent = diagnosis["intent"]
        record.strategy = diagnosis["strategy"]
    except Exception as e:
        record.intent = intent_override or "unknown"
        record.strategy = "default"

    # 启动后台执行
    thread = threading.Thread(
        target=_run_task,
        args=(task_id, user_input, intent_override),
        daemon=True,
    )
    thread.start()

    return {
        "task_id": task_id,
        "status": "pending",
        "intent": record.intent,
        "strategy": record.strategy,
    }


@router.websocket("/{task_id}/stream")
async def stream_task(ws: WebSocket, task_id: str):
    """WebSocket 端点 — 流式推送任务执行过程。

    每步完成推送一个 JSON 事件：
        {"type": "phase" | "assembly" | "completed" | "error", ...}
    """
    await ws.accept()

    if task_id not in _tasks:
        await ws.send_json({"type": "error", "error": "未知 task_id"})
        await ws.close()
        return

    q = _event_queues.get(task_id)
    if q is None:
        await ws.send_json({"type": "error", "error": "任务无事件队列"})
        await ws.close()
        return

    try:
        while True:
            # 检查客户端是否断开
            try:
                # 非阻塞检查
                data = await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                if data == "ping":
                    await ws.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass

            # 拉取事件
            try:
                event = q.get(timeout=0.1)
                await ws.send_json(event)
                if event["type"] in ("completed", "error"):
                    break
            except queue.Empty:
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@router.get("/{task_id}/status")
async def task_status(task_id: str):
    """查询任务状态。"""
    record = _tasks.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": record.task_id,
        "intent": record.intent,
        "strategy": record.strategy,
        "status": record.status,
        "created_at": record.created_at,
        "finished_at": record.finished_at,
        "spiral_iterations": record.spiral_iterations,
        "cost_estimate": record.cost_estimate,
        "error": record.error,
    }


@router.get("s")
async def list_tasks():
    """列出所有任务。"""
    return [
        {
            "task_id": r.task_id,
            "intent": r.intent,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in _tasks.values()
    ]
