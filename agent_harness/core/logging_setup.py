"""
HarnessLogger — 结构化日志，带 trace_id 链路追踪。

用法:
    from agent_harness.core.logging_setup import get_logger
    logger = get_logger("module_name")
    logger.info("task_started", trace_id="abc123", strategy="code_feature")
    logger.error("execution_failed", trace_id="abc123", error="timeout", subtask="s3")
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

# ContextVar: 跨调用链传递 trace_id，无需显式传参
_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
_span_id_ctx: ContextVar[str] = ContextVar("span_id", default="")


def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_ctx.get()


def set_span_id(span_id: str) -> None:
    _span_id_ctx.set(span_id)


def get_span_id() -> str:
    return _span_id_ctx.get()


class HarnessLogger:
    """结构化日志记录器。

    每条日志自动附带 trace_id 和 span_id（若已设置）。

    Args:
        name: 日志器名称（通常为模块名）
        level: 日志级别
        log_file: 可选的日志文件路径
    """

    def __init__(
        self,
        name: str,
        level: str = "INFO",
        log_file: str | None = None,
    ):
        self.name = name
        self._logger = logging.getLogger(f"harness.{name}")
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self._logger.handlers.clear()

        # 控制台 handler
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        self._logger.addHandler(console)

        # 文件 handler
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            ))
            self._logger.addHandler(file_handler)

        self._logger.propagate = False

    def _format(self, msg: str, **kwargs) -> str:
        trace_id = _trace_id_ctx.get()
        span_id = _span_id_ctx.get()
        extras = {k: v for k, v in kwargs.items() if v is not None}

        parts = []
        if trace_id:
            parts.append(f"trace={trace_id[:8]}")
        if span_id:
            parts.append(f"span={span_id[:8]}")

        if extras:
            parts.append(json.dumps(extras, ensure_ascii=False, default=str))

        if parts:
            return f"{msg} | {' '.join(parts)}"
        return msg

    def debug(self, msg: str, **kwargs) -> None:
        self._logger.debug(self._format(msg, **kwargs))

    def info(self, msg: str, **kwargs) -> None:
        self._logger.info(self._format(msg, **kwargs))

    def warning(self, msg: str, **kwargs) -> None:
        self._logger.warning(self._format(msg, **kwargs))

    def error(self, msg: str, **kwargs) -> None:
        self._logger.error(self._format(msg, **kwargs))


# 日志器缓存
_loggers: dict[str, HarnessLogger] = {}


def get_logger(name: str = "harness") -> HarnessLogger:
    if name not in _loggers:
        log_level = os.environ.get("HARNESS_LOG_LEVEL", "INFO")
        log_file = os.environ.get("HARNESS_LOG_FILE", "")
        _loggers[name] = HarnessLogger(name, level=log_level, log_file=log_file or None)
    return _loggers[name]
