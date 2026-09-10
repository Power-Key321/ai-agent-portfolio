"""
Mend — 断点修补 — 检测并修复截断的 JSON 响应。
"""

from __future__ import annotations

import json
import re


def detect_broken_json(text: str) -> bool:
    """检测文本末尾是否有不完整的 JSON。"""
    # 尝试找最后一个 {
    last_open = text.rfind("{")
    if last_open == -1:
        return False

    tail = text[last_open:]
    # 数括号
    depth = 0
    in_string = False
    escape = False
    for ch in tail:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

    return depth > 0


def mend_json(text: str) -> str:
    """尝试修复不完整的 JSON。

    策略:
    1. 补全缺失的闭合括号
    2. 如果仍无效，截断到最后一个完整的 JSON 对象
    """
    if not detect_broken_json(text):
        return text

    # 策略1: 补全括号
    last_open = text.rfind("{")
    if last_open == -1:
        return text

    tail = text[last_open:]
    depth = 0
    in_string = False
    escape = False
    for ch in tail:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

    repair = text + ("}" * depth)

    # 验证修复结果
    if _validate_json_tail(repair):
        return repair

    # 策略2: 截断到最后一个完整 JSON
    return _truncate_to_last_valid(text)


def _validate_json_tail(text: str) -> bool:
    """检查文本末尾的 JSON 是否有效。"""
    last_open = text.rfind("{")
    if last_open == -1:
        return True
    tail = text[last_open:]
    try:
        json.loads(tail)
        return True
    except json.JSONDecodeError:
        return False


def _truncate_to_last_valid(text: str) -> str:
    """截断文本到最后一个完整的 JSON 对象。"""
    # 从后往前找完整的 JSON 块
    braces = [m.start() for m in re.finditer(r'\{', text)]
    for pos in reversed(braces):
        candidate = text[:pos]
        # 从 pos 往后找到配对的 }
        depth = 0
        in_string = False
        escape = False
        end = -1
        for i, ch in enumerate(text[pos:], pos):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > 0:
            return text[:end]
    return text
