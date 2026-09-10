"""
Guard — 循环守护 — 检测并熔断重复调用循环。

当模型在短时间内重复调用相同的 (tool, args) 组合时，
检测并抑制，注入反思提示。
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field


@dataclass
class LoopGuard:
    """滑动窗口检测重复 tool-call。

    Args:
        window_size: 滑动窗口大小（最近 N 次调用）
        repeat_threshold: 同一调用在此窗口内出现 N 次视为循环
        suppress_seconds: 循环触发后抑制时间（秒）
    """

    window_size: int = 10
    repeat_threshold: int = 3
    suppress_seconds: float = 30.0

    _call_history: deque = field(default_factory=lambda: deque(maxlen=10))
    _suppressed: dict[str, float] = field(default_factory=dict)  # call_sig → suppress_until

    def check(self, tool_name: str, arguments: dict) -> dict:
        """检查一次 tool-call 是否触发了循环检测。

        Returns:
            {"loop_detected": bool, "call_sig": str, "count": int, "action": "allow"|"suppress"|"reflect"}
        """
        call_sig = self._signature(tool_name, arguments)

        # 检查是否在抑制期
        import time
        now = time.time()
        if call_sig in self._suppressed:
            if now < self._suppressed[call_sig]:
                return {
                    "loop_detected": True,
                    "call_sig": call_sig,
                    "count": 0,
                    "action": "suppress",
                    "suppress_until": self._suppressed[call_sig],
                }
            else:
                del self._suppressed[call_sig]

        # 滑动窗口检测
        self._call_history.append(call_sig)
        count = sum(1 for s in self._call_history if s == call_sig)

        if count >= self.repeat_threshold:
            # 进入抑制期
            self._suppressed[call_sig] = now + self.suppress_seconds
            return {
                "loop_detected": True,
                "call_sig": call_sig,
                "count": count,
                "action": "reflect",
                "message": f"检测到重复调用循环: {tool_name} 已被调用 {count} 次。请反思是否有更有效的方式完成此任务。",
            }

        return {
            "loop_detected": False,
            "call_sig": call_sig,
            "count": count,
            "action": "allow",
        }

    @staticmethod
    def _signature(tool_name: str, arguments: dict) -> str:
        """生成调用的唯一签名。"""
        raw = f"{tool_name}:{sorted(arguments.items())}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]


def detect_loop(content_history: list[str], pattern_threshold: int = 4) -> bool:
    """检测模型是否陷入了无意义的循环。

    检查最近 N 条助手消息是否有重复的内容模式。

    Args:
        content_history: 最近的助手消息内容列表
        pattern_threshold: 重复多少次视为循环

    Returns:
        是否检测到循环
    """
    if len(content_history) < pattern_threshold:
        return False

    recent = content_history[-pattern_threshold:]
    # 简化的循环检测：看首尾是否高度相似
    first = recent[0].strip()[-200:]
    last = recent[-1].strip()[-200:]
    if len(first) < 20 or len(last) < 20:
        return False

    # 简单的相似度检查
    common = sum(1 for a, b in zip(first, last) if a == b)
    similarity = common / max(len(first), len(last))
    return similarity > 0.8
