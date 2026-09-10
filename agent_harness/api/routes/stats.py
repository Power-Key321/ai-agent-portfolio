"""
统计与进化数据路由 — /api/stats, /api/evolution

GET  /api/stats       — Carbon Engine 统计
GET  /api/evolution   — 进化数据（权重/模式/收敛历史）
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["stats"])

FEEDBACK_DIR = Path(__file__).resolve().parent.parent.parent / "feedback"


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/stats")
async def get_stats():
    """Carbon Engine 核心统计。

    Returns:
        {
            "version": "2.0",
            "brand": "Carbon Engine",
            "adapter": "deepseek",
            "weights": {...},
            "convergence": {"total_events": N, "recent_quality": 0.X},
            "learned_patterns": N,
        }
    """
    weights = _read_json(FEEDBACK_DIR / "weights.json") or {}
    history = _read_json(FEEDBACK_DIR / "convergence_history.json") or []
    patterns = _read_json(FEEDBACK_DIR / "learned_patterns.json") or {}

    # 计算近期收敛质量
    recent_quality = 0.0
    if len(history) >= 5:
        recent = history[-5:]
        scores = [e.get("convergence_score", 0) for e in recent if isinstance(e, dict)]
        if scores:
            recent_quality = sum(scores) / len(scores)

    total_patterns = sum(len(v) for v in patterns.values()) if isinstance(patterns, dict) else 0

    return {
        "version": "2.0",
        "brand": "Carbon Engine",
        "framework": "Harness v2 — 碳基大脑演绎法",
        "weights": weights,
        "convergence": {
            "total_events": len(history),
            "recent_quality": round(recent_quality, 4),
        },
        "learned_patterns": total_patterns,
    }


@router.get("/evolution")
async def get_evolution():
    """进化数据 — 权重变化趋势、学习模式、收敛历史。

    Returns:
        {
            "weights": {...},
            "patterns": {...},
            "convergence_history": [...],  # 最近 50 条
            "thresholds": {...},
            "health": "stable" | "degrading" | "improving",
        }
    """
    weights = _read_json(FEEDBACK_DIR / "weights.json") or {}
    patterns = _read_json(FEEDBACK_DIR / "learned_patterns.json") or {}
    history = _read_json(FEEDBACK_DIR / "convergence_history.json") or []
    thresholds = _read_json(FEEDBACK_DIR / "thresholds.json") or {}

    # 健康评估
    health = "stable"
    if len(history) >= 10:
        old = history[-10:-5] if len(history) >= 10 else history[:len(history)//2]
        new = history[-5:]
        old_avg = sum(e.get("convergence_score", 0) for e in old if isinstance(e, dict)) / max(1, len(old))
        new_avg = sum(e.get("convergence_score", 0) for e in new if isinstance(e, dict)) / max(1, len(new))
        if old_avg > 0 and new_avg / old_avg < 0.8:
            health = "degrading"
        elif old_avg > 0 and new_avg / old_avg > 1.15:
            health = "improving"

    return {
        "weights": weights,
        "patterns": patterns if isinstance(patterns, dict) else {},
        "convergence_history": history[-50:] if isinstance(history, list) else [],
        "thresholds": thresholds if isinstance(thresholds, dict) else {},
        "health": health,
    }
