"""
Sentinel — 权限哨兵（守护者模式 Guardian Pattern）。

每个工具调用执行前通过 Sentinel 检查权限。
支持 headless 模式（自动批准）和交互式模式（每次询问用户）。

用法:
    sentinel = Sentinel(mode="interactive")
    if sentinel.check("write_file", {"path": "/etc/passwd"}).allowed:
        execute_tool(...)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SentinelResult:
    """哨兵检查结果。"""
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False


@dataclass
class Sentinel:
    """权限哨兵 — 工具调用的安全检查（守护者模式）。

    Args:
        mode: "headless"（自动批准安全操作）| "interactive"（询问用户）| "strict"（拒绝所有写入）
        allowed_dirs: 允许文件操作的基础目录列表
        blocked_commands: 禁止的 shell 命令模式列表
        on_confirm: 交互式确认回调 (tool_name, params) → bool
    """

    mode: str = "headless"  # headless | interactive | strict
    allowed_dirs: list[str] = field(default_factory=lambda: [os.getcwd()])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };:", "> /dev/sda",
        "format c:", "del /f /s", "shutdown", "reboot",
    ])

    on_confirm: Callable[[str, dict], bool] | None = None

    _check_log: list[dict] = field(default_factory=list, init=False)

    def check(self, tool_name: str, params: dict) -> SentinelResult:
        """检查工具调用是否允许。"""
        # 只读操作 → 始终允许
        if tool_name in ("read_file", "list_files", "search", "web_search", "web_fetch"):
            result = SentinelResult(allowed=True, reason="read-only operation")
            self._log(tool_name, params, result)
            return result

        # strict 模式拒绝所有写入
        if self.mode == "strict":
            result = SentinelResult(allowed=False, reason="strict mode: write operations disabled")
            self._log(tool_name, params, result)
            return result

        # 文件写入 → 检查路径
        if tool_name in ("write_file", "edit_file", "replace_in_file"):
            filepath = params.get("filePath") or params.get("path") or params.get("file", "")
            if not self._is_path_allowed(filepath):
                result = SentinelResult(
                    allowed=False,
                    reason=f"文件路径超出允许范围: {filepath}",
                    requires_confirmation=True,
                )
                self._log(tool_name, params, result)
                return result

        # Shell 命令 → 检查危险模式
        if tool_name in ("run_command", "shell", "exec"):
            command = params.get("command") or params.get("cmd", "")
            blocked = self._check_command_blocked(command)
            if blocked:
                result = SentinelResult(
                    allowed=False,
                    reason=f"命令被阻止: {blocked}",
                    requires_confirmation=True,
                )
                self._log(tool_name, params, result)
                return result

        # headless → 自动批准
        if self.mode == "headless":
            result = SentinelResult(allowed=True, reason="headless mode auto-approve")
            self._log(tool_name, params, result)
            return result

        # interactive → 需要用户确认
        if self.mode == "interactive":
            if self.on_confirm is not None:
                confirmed = self.on_confirm(tool_name, params)
                result = SentinelResult(
                    allowed=confirmed,
                    reason="user confirmed" if confirmed else "user denied",
                    requires_confirmation=True,
                )
                self._log(tool_name, params, result)
                return result
            # 无确认回调时默认拒绝
            result = SentinelResult(allowed=False, reason="interactive mode: no confirmation callback")
            self._log(tool_name, params, result)
            return result

        result = SentinelResult(allowed=True, reason="default allow")
        self._log(tool_name, params, result)
        return result

    def _is_path_allowed(self, path: str) -> bool:
        """检查文件路径是否在允许范围内。"""
        if not path:
            return True  # 无路径=使用当前目录
        import os.path
        abs_path = os.path.abspath(path)
        for allowed in self.allowed_dirs:
            abs_allowed = os.path.abspath(allowed)
            if abs_path.startswith(abs_allowed):
                return True
        # 相对路径 → 检查拼接后是否在允许范围
        for allowed in self.allowed_dirs:
            joined = os.path.abspath(os.path.join(allowed, path))
            if joined.startswith(os.path.abspath(allowed)):
                return True
        return False

    def _check_command_blocked(self, command: str) -> str:
        """检查命令是否匹配危险模式。返回匹配到的模式或空字符串。"""
        cmd_lower = command.lower()
        for pattern in self.blocked_commands:
            if re.search(re.escape(pattern.lower()), cmd_lower):
                return pattern
        return ""

    def _log(self, tool_name: str, params: dict, result: SentinelResult) -> None:
        self._check_log.append({
            "tool": tool_name,
            "params_summary": str(params)[:100],
            "allowed": result.allowed,
            "reason": result.reason,
        })

    def get_log(self) -> list[dict]:
        return self._check_log

    def get_stats(self) -> dict:
        allowed = sum(1 for l in self._check_log if l["allowed"])
        total = len(self._check_log)
        return {
            "total_checks": total,
            "allowed": allowed,
            "blocked": total - allowed,
            "block_rate": f"{(total - allowed) / max(1, total):.1%}",
        }
