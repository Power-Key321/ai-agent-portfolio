"""
模块基类 — 所有乐高模块的统一接口。

每个模块变体继承 ModuleBase，实现 process() 方法。
输入输出都是 Envelope，保证任何模块可以替换。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from agent_harness.core.envelope import Envelope


@dataclass
class ModuleResult:
    """模块处理结果 — process() 的返回包装。"""

    envelope: Envelope
    success: bool = True
    error: Optional[str] = None
    failure_class: Optional[str] = None
    self_heal_strategy: Optional[str] = None


class ModuleBase(ABC):
    """所有模块的基类。

    子类只需实现 process()，输入 Envelope，返回 ModuleResult。
    """

    name: str = "base"
    variant: str = "base"

    @abstractmethod
    def process(self, envelope: Envelope) -> ModuleResult:
        """处理 Envelope，返回 ModuleResult。"""
        ...

    def __repr__(self) -> str:
        return f"{self.name}.{self.variant}"
