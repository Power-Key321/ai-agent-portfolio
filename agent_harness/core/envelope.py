"""
Agent Harness 通用消息信封 + LazyCache 混合上下文方案。

Envelope: 所有模块间通信的唯一载体，轻量指针 + 按需缓存。
LazyCache: 首次 resolve() 触发加载，同轮命中缓存，跨轮清空。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4


@dataclass
class LazyCache:
    """混合上下文方案核心：指针传递 + 按需加载 + 缓存复用。

    用法:
        cache = LazyCache(resolver=context_module.resolve)
        data = cache.resolve("memory://user_role")
        # 首次 → 调用 resolver 加载 → 写入_store → 返回
        # 同轮再次 → 直接从_store返回
    """

    _store: dict[str, dict] = field(default_factory=dict)
    _resolver: Callable[[str], Optional[dict]] | None = None

    def set_resolver(self, resolver: Callable[[str], Optional[dict]]) -> None:
        self._resolver = resolver

    def resolve(self, ref: str) -> Optional[dict]:
        if ref not in self._store:
            if self._resolver is not None:
                loaded = self._resolver(ref)
                if loaded is not None:
                    self._store[ref] = loaded
        return self._store.get(ref)

    def preload(self, refs: list[str]) -> None:
        for ref in refs:
            self.resolve(ref)

    def clear(self) -> None:
        self._store.clear()

    def dump(self) -> dict:
        return {
            ref: {
                "relevance": v.get("relevance_score"),
                "tokens": v.get("token_count"),
            }
            for ref, v in self._store.items()
        }

    def total_tokens(self) -> int:
        return sum(v.get("token_count", 0) for v in self._store.values())


@dataclass
class Envelope:
    """通用消息信封 — 所有模块间通信的唯一载体。

    设计原则:
    - context.refs 只传指针，Envelope 保持轻量
    - context.cache 按需懒加载，同轮命中，跨轮清空
    - spawn() 创建子 span 时共享 cache 引用
    - spawn_next_spiral() 创建下一轮时清空 cache 但保留 refs
    """

    version: str = "2.0"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span_id: str | None = None
    intent_class: str | None = None
    strategy_id: str | None = None
    module_from: str | None = None
    module_to: str | None = None

    # 螺旋收敛
    spiral_iteration: int = 0
    spiral_max_iterations: int = 5
    convergence_radius: float = 1.0
    convergence_target: float = 0.05

    # 三个核心载荷区
    task: dict = field(default_factory=dict)
    context: dict = field(default_factory=lambda: {
        "refs": [],
        "cache": LazyCache(),
        "window_budget_total": 200000,
        "window_used_so_far": 0,
    })
    feedback: dict = field(default_factory=dict)

    # 知识图谱上下文 (v3 新增，可选)
    graph_context: dict = field(default_factory=dict)

    # 自适应问题画像 (v4 新增，可选)
    problem_profile: "ProblemProfile | None" = None  # noqa: F821

    # ── 工厂方法 ──

    def spawn(self, module_to: str) -> "Envelope":
        """创建子 span 用于模块间传递。cache 引用共享。"""
        return Envelope(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            module_from=self.module_to,
            module_to=module_to,
            intent_class=self.intent_class,
            strategy_id=self.strategy_id,
            spiral_iteration=self.spiral_iteration,
            spiral_max_iterations=self.spiral_max_iterations,
            convergence_radius=self.convergence_radius,
            convergence_target=self.convergence_target,
            task=dict(self.task),
            context=self.context,
            feedback=dict(self.feedback),
            graph_context=dict(self.graph_context),
            problem_profile=self.problem_profile,
        )

    def spawn_next_spiral(self) -> "Envelope":
        """创建下一轮螺旋的 Envelope。cache 清空，refs 保留。"""
        old_ctx = self.context
        return Envelope(
            trace_id=self.trace_id,
            intent_class=self.intent_class,
            strategy_id=self.strategy_id,
            spiral_iteration=self.spiral_iteration + 1,
            spiral_max_iterations=self.spiral_max_iterations,
            convergence_radius=self.convergence_radius,
            convergence_target=self.convergence_target,
            task=dict(self.task),
            context={
                "refs": list(old_ctx.get("refs", [])),
                "cache": LazyCache(),
                "window_budget_total": old_ctx.get("window_budget_total", 200000),
                "window_used_so_far": 0,
            },
            feedback=dict(self.feedback),
            graph_context=dict(self.graph_context),
            problem_profile=self.problem_profile,
        )

    @property
    def converged(self) -> bool:
        return self.convergence_radius < self.convergence_target

    @property
    def exhausted(self) -> bool:
        return self.spiral_iteration >= self.spiral_max_iterations

    @property
    def should_continue_spiral(self) -> bool:
        return not self.converged and not self.exhausted

    def add_constraint(self, key: str, value: Any) -> None:
        """螺旋每轮新增约束，用于收敛半径计算。"""
        self.task.setdefault("constraints", {})
        self.task.setdefault("constraints_added_this_round", [])
        self.task["constraints"][key] = value
        self.task["constraints_added_this_round"].append(key)

    def to_dict(self) -> dict:
        return {
            "envelope": {
                "version": self.version,
                "trace_id": self.trace_id,
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "intent_class": self.intent_class,
                "strategy_id": self.strategy_id,
                "module_from": self.module_from,
                "module_to": self.module_to,
                "spiral_iteration": self.spiral_iteration,
                "convergence_radius": self.convergence_radius,
            },
            "task": self.task,
            "feedback": self.feedback,
        }
