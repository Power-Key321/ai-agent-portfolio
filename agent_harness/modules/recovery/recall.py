"""
Recall — 从推理内容中回溯被遗忘的工具调用。

某些模型（如 DeepSeek）在 <think> 标签中生成了完整的 tool-call JSON，
但最终输出中却丢失了。Recall 扫描 reasoning_content 或完整的响应文本，
用正则 + JSON parser 找回这些被遗忘的调用。
"""

from __future__ import annotations

import json
import re
from typing import Optional


# JSON tool-call 模式：{"name": "...", "arguments": {...}}
TOOL_CALL_PATTERN = re.compile(
    r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{.+?\})\s*\}',
    re.DOTALL,
)

# 备选：函数调用模式  function_name(arg1, arg2)
FUNC_CALL_PATTERN = re.compile(
    r'(read_file|write_file|edit_file|run_command|search|web_fetch|web_search)\s*\((.+?)\)',
    re.DOTALL,
)


def recall_tool_calls(
    response_text: str,
    reasoning_content: str = "",
    known_tools: set[str] | None = None,
) -> list[dict]:
    """从模型响应中捞回所有可能的 tool-call。

    扫描顺序:
    1. reasoning_content（模型推理过程）
    2. response_text（模型主输出）
    3. 代码块中的 JSON

    Args:
        response_text: 模型的主响应文本
        reasoning_content: 模型的推理内容（如 DeepSeek 的 reasoning_content）
        known_tools: 已知工具名集合，用于过滤误匹配

    Returns:
        找到的 tool-call 列表 [{"tool_name": str, "arguments": dict}]
    """
    found = []
    search_texts = [reasoning_content, response_text]

    for text in search_texts:
        if not text:
            continue

        # 模式1: JSON tool-call
        for match in TOOL_CALL_PATTERN.finditer(text):
            try:
                tool_name = match.group(1)
                args_str = match.group(2)
                arguments = json.loads(args_str)
                if known_tools is None or tool_name in known_tools:
                    found.append({"tool_name": tool_name, "arguments": arguments, "source": "json_regex", "matched_in": "reasoning" if text == reasoning_content else "response"})
            except json.JSONDecodeError:
                continue

        # 模式2: 函数调用模式
        for match in FUNC_CALL_PATTERN.finditer(text):
            tool_name = match.group(1)
            args_str = match.group(2)
            if known_tools is None or tool_name in known_tools:
                found.append({"tool_name": tool_name, "arguments": {"raw": args_str}, "source": "func_call_regex", "matched_in": "reasoning" if text == reasoning_content else "response"})

        # 模式3: 代码块中的 JSON
        code_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        for block in code_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and "name" in data and "arguments" in data:
                    if known_tools is None or data["name"] in known_tools:
                        found.append({"tool_name": data["name"], "arguments": data["arguments"], "source": "code_block", "matched_in": "reasoning" if text == reasoning_content else "response"})
            except json.JSONDecodeError:
                # 可能是多行 JSON
                for candidate in re.finditer(r'\{\s*"name"[^}]*\}', block):
                    try:
                        data = json.loads(candidate.group())
                        if "name" in data:
                            found.append({"tool_name": data["name"], "arguments": data.get("arguments", {}), "source": "code_block_fragment", "matched_in": "reasoning" if text == reasoning_content else "response"})
                    except json.JSONDecodeError:
                        continue

    return found


def has_missing_calls(
    response_text: str,
    expected_tools: set[str] | None = None,
) -> bool:
    """检测模型响应是否应该包含 tool-call 但遗漏了。

    启发式信号:
    - 响应提到要调用某工具但没有实际 JSON
    - 响应在推理中描述了工具调用
    """
    intent_patterns = [
        r'(?:需要|应该|我将|让我|let me|I will|I need to)\s*(?:调用|使用|执行|call|use|run)\s*(\w+)',
        r'(?:read|write|edit|search|run|execute)\s+(?:the\s+)?(\S+)',
    ]
    for pattern in intent_patterns:
        intents = re.findall(pattern, response_text, re.IGNORECASE)
        if intents:
            # 检查是否真的有对应的 tool-call JSON
            actual_calls = recall_tool_calls(response_text)
            if not actual_calls:
                return True
    return False
