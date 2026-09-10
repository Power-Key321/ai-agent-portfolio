"""
DeepSeek API 客户端 — 完整 chat completion + 流式 + function calling。

支持:
- 非流式 chat completion
- SSE 流式输出（回调驱动）
- OpenAI 兼容 function calling
- Probe-First 模型选择（deepseek-chat → deepseek-reasoner）
- 指数退避重试
- Token 用量追踪
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class DeepSeekClient:
    """DeepSeek API 专用客户端。

    Args:
        api_key: DeepSeek API key
        api_base: API base URL (默认 https://api.deepseek.com)
        default_model: 默认模型 (deepseek-chat)
        probe_model: 探针模型 (deepseek-chat，轻量快速)
        reasoner_model: 推理模型 (deepseek-reasoner，重型深度推理)
        max_retries: 最大重试次数
        timeout: 请求超时秒数
    """

    api_key: str
    api_base: str = "https://api.deepseek.com"
    default_model: str = "deepseek-chat"
    probe_model: str = "deepseek-chat"
    reasoner_model: str = "deepseek-reasoner"
    max_retries: int = 3
    timeout: int = 120

    # 回调
    on_stream_chunk: Optional[Callable[[str], None]] = None
    on_token_usage: Optional[Callable[[dict], None]] = None

    # 统计
    total_tokens_in: int = field(default=0, init=False)
    total_tokens_out: int = field(default=0, init=False)
    total_calls: int = field(default=0, init=False)
    total_cost_estimate: float = field(default=0.0, init=False)

    # 模型定价 ($/1M tokens)
    # deepseek-v4-* 为当前接入的实际模型（flash=快速/pro=深度），价格按 chat/reasoner 档位估算，可自行调整
    PRICING = {
        "deepseek-chat":       {"in": 0.27, "out": 1.10},
        "deepseek-reasoner":   {"in": 0.55, "out": 2.19},
        "deepseek-v4-flash":   {"in": 0.27, "out": 1.10},
        "deepseek-v4-pro":     {"in": 0.55, "out": 2.19},
    }

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        stream: bool = False,
    ) -> dict:
        """发送 chat completion 请求。

        Returns:
            {
                "content": str,
                "tool_calls": list | None,
                "finish_reason": str,
                "model": str,
                "usage": {"prompt_tokens": int, "completion_tokens": int},
                "cost": float,
            }
        """
        model = model or self.default_model
        body = {
            "model": model,
            "messages": self._build_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice

        if stream:
            return self._stream_request(body)
        return self._request(body)

    def classify(
        self,
        prompt: str,
        categories: list[str],
        model: str | None = None,
    ) -> str:
        """快速意图分类 — 单 token 返回类别名。"""
        cat_str = "\n".join(f"- {c}" for c in categories)
        system = (
            "You are a task classifier. Given a user's request, "
            "classify it into exactly ONE of these categories:\n"
            f"{cat_str}\n\n"
            "Reply with ONLY the category name, nothing else."
        )
        result = self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.probe_model,
            system=system,
            # v4 模型带 reasoning_content，推理会先消耗 token，max_tokens 需给足预算
            max_tokens=200,
            temperature=0.0,
        )
        return result["content"].strip().lower()

    def probe_then_reason(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> dict:
        """Probe-First 策略：先用轻量模型探路，复杂任务自动升级到推理模型。

        判断升级条件：
        - 响应中出现 "NEEDS_REASONER" 标记
        - 响应包含多步骤推理需求
        - finish_reason 为 "length"（被截断，说明不够用）
        """
        # Step 1: 探针尝试
        result = self.chat(
            messages=messages,
            model=self.probe_model,
            system=system,
            max_tokens=max_tokens,
            tools=tools,
        )

        content = result.get("content", "")
        needs_upgrade = (
            "NEEDS_REASONER" in content
            or "<<<NEEDS_DEEP_THINK>>>" in content
            or result.get("finish_reason") == "length"
        )

        if not needs_upgrade:
            return result

        # Step 2: 升级到推理模型
        upgraded = self.chat(
            messages=messages,
            model=self.reasoner_model,
            system=system,
            max_tokens=max(max_tokens, 8192),
            tools=tools,
        )
        upgraded["probe_upgraded"] = True
        upgraded["probe_model_used"] = self.probe_model
        return upgraded

    def _build_messages(
        self, messages: list[dict], system: str | None
    ) -> list[dict]:
        built = []
        if system:
            built.append({"role": "system", "content": system})
        built.extend(messages)
        return built

    def _request(self, body: dict) -> dict:
        """非流式请求 + 重试。"""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._do_request(body)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    time.sleep(wait)
        raise last_error  # type: ignore

    def _do_request(self, body: dict) -> dict:
        url = f"{self.api_base}/v1/chat/completions"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {e.code}: {error_body}") from e

        return self._parse_response(raw, body["model"])

    def _stream_request(self, body: dict) -> dict:
        """SSE 流式请求 — 通过 on_stream_chunk 回调推送增量文本。"""
        url = f"{self.api_base}/v1/chat/completions"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        resp = urllib.request.urlopen(req, timeout=self.timeout)

        full_content = ""
        full_reasoning = ""
        tool_call_buffers: dict[int, dict] = {}
        finish_reason = "stop"
        model = body["model"]

        for line in resp:
            line = line.decode("utf-8").strip()
            if not line or line.startswith(":"):
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason", finish_reason)

                    # 推理增量（v4 模型先输出 reasoning_content）
                    if "reasoning_content" in delta and delta["reasoning_content"]:
                        full_reasoning += delta["reasoning_content"]
                        if self.on_stream_chunk:
                            self.on_stream_chunk(delta["reasoning_content"])

                    # 文本增量
                    if "content" in delta and delta["content"]:
                        full_content += delta["content"]
                        if self.on_stream_chunk:
                            self.on_stream_chunk(delta["content"])

                    # Tool call 增量
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            buf = tool_call_buffers[idx]
                            if "id" in tc:
                                buf["id"] = tc["id"]
                            if "function" in tc:
                                if "name" in tc["function"]:
                                    buf["function"]["name"] += tc["function"]["name"]
                                if "arguments" in tc["function"]:
                                    buf["function"]["arguments"] += tc["function"]["arguments"]
                except json.JSONDecodeError:
                    continue

        # 组装 tool calls
        tool_calls = [tool_call_buffers[i] for i in sorted(tool_call_buffers)]
        if not tool_calls:
            tool_calls = None

        usage_estimate = {
            "prompt_tokens": len(data) // 4,
            "completion_tokens": (len(full_content) + len(full_reasoning)) // 4,
        }
        cost = self._estimate_cost(model, usage_estimate)

        # 推理模型: content 为空时回退到 reasoning_content
        if not full_content and full_reasoning:
            full_content = full_reasoning

        return {
            "content": full_content,
            "reasoning_content": full_reasoning,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "model": model,
            "usage": usage_estimate,
            "cost": cost,
        }

    def _parse_response(self, raw: dict, model: str) -> dict:
        choice = raw.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = raw.get("usage", {})
        cost = self._estimate_cost(model, usage)

        self.total_tokens_in += usage.get("prompt_tokens", 0)
        self.total_tokens_out += usage.get("completion_tokens", 0)
        self.total_calls += 1
        self.total_cost_estimate += cost

        if self.on_token_usage:
            self.on_token_usage({
                "model": model,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "cost": cost,
                "cumulative_cost": self.total_cost_estimate,
            })

        content = message.get("content", "") or ""
        reasoning = message.get("reasoning_content", "") or ""
        # v4 推理模型: 可能把 token 全花在 reasoning_content 上，content 为空时回退
        if not content and reasoning:
            content = reasoning

        return {
            "content": content,
            "reasoning_content": reasoning,
            "tool_calls": message.get("tool_calls"),
            "finish_reason": choice.get("finish_reason", "stop"),
            "model": model,
            "usage": usage,
            "cost": cost,
        }

    def _estimate_cost(self, model: str, usage: dict) -> float:
        pricing = self.PRICING.get(model, self.PRICING["deepseek-chat"])
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return (
            prompt_tokens / 1_000_000 * pricing["in"]
            + completion_tokens / 1_000_000 * pricing["out"]
        )

    def get_stats(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_cost_estimate": round(self.total_cost_estimate, 6),
        }
