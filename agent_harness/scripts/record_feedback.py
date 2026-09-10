#!/usr/bin/env python3
"""
Post-Interaction 反馈记录脚本 — 由 CC hooks 调用。

用法:
  python agent_harness/scripts/record_feedback.py <event_json>
  echo '{"intent_class":"code_feature",...}' | python agent_harness/scripts/record_feedback.py --stdin

CC Hook 配置示例 (settings.json):
  {
    "hooks": {
      "on_message_complete": [
        {
          "command": "python agent_harness/scripts/record_feedback.py",
          "args": ["--auto"],
          "timeout": 5000
        }
      ]
    }
  }

--auto 模式: 从环境变量 CC_LAST_INTENT / CC_LAST_STRATEGY 等读取（由 CLAUDE.md 指令设置）。
--stdin 模式: 从 stdin 读取 JSON 事件。
直接传参模式: 第一个参数是 JSON 字符串。

轻量设计: 不含重量级依赖，启动 < 100ms，不阻塞 CC 交互。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def build_event_from_env() -> dict:
    """从环境变量构建反馈事件（--auto 模式）。"""
    return {
        "intent_class": os.environ.get("HARNESS_INTENT", "unknown"),
        "strategy_id": os.environ.get("HARNESS_STRATEGY", "unknown"),
        "signal_type": os.environ.get("HARNESS_SIGNAL", "accepted"),
        "signal_strength": float(os.environ.get("HARNESS_STRENGTH", "0.8")),
        "spiral_iterations_used": int(os.environ.get("HARNESS_SPIRALS", "0")),
        "convergence_score": float(os.environ.get("HARNESS_CONVERGENCE", "0.0")),
        "was_harnessed": os.environ.get("HARNESS_ACTIVE", "0") == "1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_minimal_event() -> dict:
    """构建最小事件（当没有 harness 数据时）。"""
    return {
        "intent_class": "simple_query",
        "strategy_id": "simple_query",
        "signal_type": "accepted",
        "signal_strength": 0.5,
        "spiral_iterations_used": 0,
        "convergence_score": 0.5,
        "was_harnessed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def record_event(event: dict) -> dict:
    """记录事件到 FeedbackEngine，并检查 MetaCognition。"""
    from agent_harness.core.auto_attach import get_auto_attach

    aa = get_auto_attach()
    aa.on_session_start()
    result = aa.on_interaction_end(event)

    return {
        "feedback_recorded": result["feedback_recorded"],
        "meta_triggered": result["meta_triggered"],
        "meta_summary": (
            {
                "signals_detected": result["meta_report"].get("signals_detected", 0),
                "improvements_applied": result["meta_report"].get("improvements_applied", 0),
                "framework_health": result["meta_report"].get("framework_health", "unknown"),
            }
            if result["meta_report"]
            else None
        ),
    }


def main():
    event = None

    if len(sys.argv) > 1:
        if sys.argv[1] == "--auto":
            event = build_event_from_env()
        elif sys.argv[1] == "--stdin":
            raw = sys.stdin.read()
            if raw.strip():
                event = json.loads(raw)
        elif sys.argv[1] in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        else:
            # 直接传 JSON 字符串
            try:
                event = json.loads(sys.argv[1])
            except json.JSONDecodeError:
                # 也许是一个文件路径
                path = Path(sys.argv[1])
                if path.exists():
                    event = json.loads(path.read_text(encoding="utf-8"))
                else:
                    print(f"ERROR: 无法解析参数: {sys.argv[1]}", file=sys.stderr)
                    sys.exit(1)
    else:
        # 无参数：尝试从 stdin 读取
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                event = json.loads(raw)

    if event is None:
        event = build_minimal_event()

    try:
        result = record_event(event)
        if result.get("meta_triggered"):
            ms = result.get("meta_summary", {})
            print(f"[Harness] 反馈已记录 | MetaCognition: {ms.get('signals_detected', 0)} 信号, "
                  f"{ms.get('improvements_applied', 0)} 改进, 健康度: {ms.get('framework_health', 'N/A')}")
        else:
            print(f"[Harness] 反馈已记录 (session: {event.get('session_id', 'N/A')})")
    except Exception as e:
        # 静默失败 — 不阻塞 CC 交互
        print(f"[Harness] 反馈记录失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
