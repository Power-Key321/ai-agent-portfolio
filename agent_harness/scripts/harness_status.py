#!/usr/bin/env python3
"""
Harness 状态栏脚本 — 供 Claude Code statusLine 使用。

在终端底部持续显示 harness 运行状态，包括：
- 活跃会话数（多窗口）
- 策略权重 TOP3
- 总反馈事件数
- 当前进化 Phase
- 路由命中率

输出: 单行短字符串，适配 CC 状态栏宽度。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FEEDBACK_DIR = Path(__file__).resolve().parent.parent / "feedback"


def get_status() -> str:
    """读取 harness 状态并格式化为状态栏字符串。"""
    parts = ["H:v2"]

    # 活跃会话数
    sessions_dir = FEEDBACK_DIR / ".active_sessions"
    if sessions_dir.exists():
        active = len(list(sessions_dir.glob("*.json")))
        parts.append(f"{active}w" if active else "·")

    # 权重 TOP3
    weights_path = FEEDBACK_DIR / "weights.json"
    if weights_path.exists():
        try:
            weights = json.loads(weights_path.read_text(encoding="utf-8"))
            if weights:
                top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:2]
                short = [f"{k.split('_')[0][:4]}:{v:.2f}" for k, v in top]
                parts.append("|".join(short))
        except Exception:
            pass

    # 事件总数和 Phase
    history_path = FEEDBACK_DIR / "convergence_history.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            total = len(history)
            # 最近10条的平均收敛
            if total >= 5:
                recent = history[-5:]
                avg_c = sum(e.get("convergence_score", 0) for e in recent) / len(recent)
                parts.append(f"n={total}")
                if avg_c > 0:
                    parts.append(f"c={avg_c:.2f}")
        except Exception:
            pass

    # 路由学习模式数
    lp_path = FEEDBACK_DIR / "learned_patterns.json"
    if lp_path.exists():
        try:
            lp = json.loads(lp_path.read_text(encoding="utf-8"))
            total_p = sum(len(v) for v in lp.values())
            if total_p > 0:
                parts.append(f"L{total_p}")
        except Exception:
            pass

    return " ".join(parts)


if __name__ == "__main__":
    try:
        print(get_status())
    except Exception as e:
        print(f"H:v2 err:{e}", file=sys.stderr)
        print("H:v2")
