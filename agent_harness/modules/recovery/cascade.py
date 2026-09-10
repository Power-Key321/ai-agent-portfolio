"""
RecoveryCascade — 恢复级联 — 四级逐级恢复管道：回溯→修补→折叠→守护。

用法:
    cascade = RecoveryCascade(known_tools={"read_file", "write_file", ...})
    result = cascade.recover(response_text, reasoning_content)
    # → {"recovered": bool, "output": str, "recoveries_applied": [...]}
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_harness.modules.recovery.recall import recall_tool_calls, has_missing_calls
from agent_harness.modules.recovery.mend import detect_broken_json, mend_json
from agent_harness.modules.recovery.guard import LoopGuard


@dataclass
class RecoveryCascade:
    """Tool-call 恢复管道 — 四级恢复策略串联执行。

    Args:
        known_tools: 已知工具名集合，用于 recall 过滤
        enable_recall: 启用回溯恢复
        enable_mend: 启用断点修补
        enable_guard: 启用循环守护
        guard_window: 循环守护滑动窗口大小
        guard_threshold: 循环守护重复阈值
    """

    known_tools: set[str] = field(default_factory=set)
    enable_recall: bool = True
    enable_mend: bool = True
    enable_guard: bool = True
    guard_window: int = 10
    guard_threshold: int = 3

    _loop_guard: LoopGuard | None = field(default=None, init=False)
    _recovery_log: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self):
        if self.enable_guard:
            self._loop_guard = LoopGuard(
                window_size=self.guard_window,
                repeat_threshold=self.guard_threshold,
            )

    def recover(
        self,
        response_text: str,
        reasoning_content: str = "",
        tool_name: str = "",
        tool_args: dict | None = None,
    ) -> dict:
        """执行恢复管道。

        Returns:
            {
                "recovered": bool,
                "output": str,              # 恢复后的响应文本
                "recalled_calls": list,     # 回溯的 tool-call
                "mend_applied": bool,
                "guard_result": dict | None,
                "recoveries_applied": [str],   # 应用的恢复列表
            }
        """
        result = {
            "recovered": False,
            "output": response_text,
            "recalled_calls": [],
            "mend_applied": False,
            "guard_result": None,
            "recoveries_applied": [],
        }

        # Step 1: Recall — 回溯被遗忘的 tool-call
        if self.enable_recall and has_missing_calls(response_text):
            recalled = recall_tool_calls(
                response_text, reasoning_content, self.known_tools
            )
            if recalled:
                result["recalled_calls"] = recalled
                result["recoveries_applied"].append("recall")
                result["recovered"] = True

        # Step 2: Mend — 修复不完整 JSON
        if self.enable_mend and detect_broken_json(response_text):
            repaired = mend_json(response_text)
            if repaired != response_text:
                result["output"] = repaired
                result["mend_applied"] = True
                result["recoveries_applied"].append("mend")
                result["recovered"] = True

        # Step 3: Guard — 重复调用检测
        if self.enable_guard and self._loop_guard and tool_name:
            guard_result = self._loop_guard.check(tool_name, tool_args or {})
            if guard_result["loop_detected"]:
                result["guard_result"] = guard_result
                result["recoveries_applied"].append(f"guard_{guard_result['action']}")
                result["recovered"] = True

        self._recovery_log.append({
            "recoveries_applied": result["recoveries_applied"],
            "recalled_count": len(result["recalled_calls"]),
        })

        return result

    def get_log(self) -> list[dict]:
        return self._recovery_log

    def get_stats(self) -> dict:
        total = len(self._recovery_log)
        recall_count = sum(1 for r in self._recovery_log if "recall" in r["recoveries_applied"])
        mend_count = sum(1 for r in self._recovery_log if "mend" in r["recoveries_applied"])
        guard_count = sum(1 for r in self._recovery_log if any("guard" in a for a in r["recoveries_applied"]))
        return {
            "total_recoveries": total,
            "recall": recall_count,
            "mend": mend_count,
            "guard": guard_count,
            "recovery_rate": f"{total / max(1, sum(1 for r in self._recovery_log)):.0%}",
        }
