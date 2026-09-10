"""
PromptBuilder — 缓存锚定提示构建器。

核心原理（Anthropic Prompt Caching）:
- 缓存基于前缀匹配：prompt的前N个token与之前请求相同 → cache hit
- Cache write: ~125% 基础价格
- Cache hit:  ~10%  基础价格（节省90%）
- Cache TTL:  5分钟

策略:
1. 框架"骨架"作为固定前缀 → 永远命中缓存
2. 任务"血肉"追加在后 → 只有这部分按全额计费
3. 骨架更新频率极低（配置文件、模块定义、规则表）

结构:
    [Cache锚点 - 静态前缀, 首次写入后5分钟内每次命中]
    ├─ HARness System Prompt
    ├─ Module Registry (11个模块的完整定义)
    ├─ Strategy Table (6策略 + 装配链)
    ├─ Failure Classification Rules
    ├─ SpiralGate Rules
    └─ Convergence Formula

    [动态区 - 每次不同, 按量计费]
    ├─ User Input
    ├─ Current Spiral State
    └─ Retrieved Context
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════
# 框架骨架定义 — 这些内容对所有请求完全相同
# ═══════════════════════════════════════════════

HARNESS_SYSTEM_PROMPT = """You are Agent Harness v2, a modular task orchestration framework.

## Your Architecture
You operate as a "Lego" system with 6 pluggable module types, auto-assembled per task:

1. **Preprocessor** — Extract entities, detect ambiguity, estimate complexity
2. **Decomposer** — Break intent into subtask DAG
3. **Scheduler** — Order subtasks by dependency
4. **Context** — Retrieve relevant memory/files (LazyCache)
5. **Executor** — Execute subtasks with failure classification & self-heal
6. **Deliverer** — Assemble final output (diff or report)

## Spiral Convergence
You operate in spiral iterations, not linear pass:
- Each iteration narrows the solution space
- Convergence radius r: 1.0(initial) → 0.0(exact match user intent)
- r < ε (0.05) triggers delivery
- Convergence speed c = (1.0 - r_final) / N_iterations
- Higher c = better (fewer steps to reach goal)

## Failure Classification (from smart-loop v6.1 practice)
| failure_class | self_heal_strategy |
|---|---|
| ambiguous_intent | retry_refined |
| tool_error | retry_same (max 3x) |
| context_overflow | re_decompose |
| model_hallucination | re_decompose + retry_refined |
| timeout | re_decompose |
| dependency_fail | escalate_to_user |

## SpiralGate Rules
Decide how many spiral iterations a task needs:
1. complexity_score < 0.30 → reduce iterations
2. entity_items >= 4 → further reduce
3. entity_items == 0 → increase (vague)
4. input_length < 15 chars → increase
5. ambiguity_flags >= 2 → increase
6. complexity_score > 0.60 → keep max

## Intent Strategies
- code_feature: implement new functionality (opus, max 5 spirals)
- code_fix: fix bugs (sonnet, max 3 spirals)
- data_analysis: analyze data (opus, max 4 spirals)
- research: search/find information (haiku, max 3 spirals)
- simple_query: answer simple questions (haiku, max 1 spiral)
- refactor: restructure code (opus, max 4 spirals)

## Key Principle
Converge toward user's true intent by adding constraints each spiral.
Fewer steps to goal = better. Don't diverge — narrow down."""


MODULE_REGISTRY_PROMPT = """## Available Module Variants

### Preprocessor
- preproc.simple: Passthrough for simple queries
- preproc.code: Extract lang/framework/file entities from code tasks
- preproc.full: Domain-aware extraction (market, time_ranges, metrics)

### Decomposer
- decomp.single: No decomposition, single execution unit
- decomp.linear: Explore→Design→Implement→Verify chain

### Scheduler
- schedule.sequential: Strict dependency-ordered serial execution

### Context
- context.full: Full retrieval (memory + files) with LazyCache
- context.minimal: User memory only

### Executor
- execute.default: Execute subtask, classify failures, apply self-heal

### Deliverer
- deliver.diff: Code changes as diff/patch
- deliver.report: Analysis as structured report"""


STRATEGY_TABLE_PROMPT = """## Strategy Assembly Table

### code_feature
Assembly: preproc.code → decomp.linear → schedule.sequential → context.full → execute → deliver.diff
Model: opus | Max Spirals: 5 | Retry: standard

### code_fix
Assembly: preproc.code → decomp.single → schedule.sequential → context.full → execute → deliver.diff
Model: sonnet | Max Spirals: 3 | Retry: aggressive

### data_analysis
Assembly: preproc.full → decomp.linear → schedule.sequential → context.minimal → execute → deliver.report
Model: opus | Max Spirals: 4 | Retry: standard

### research
Assembly: preproc.full → decomp.linear → schedule.sequential → context.minimal → execute → deliver.report
Model: haiku | Max Spirals: 3 | Retry: conservative

### simple_query
Assembly: preproc.simple → decomp.single → schedule.sequential → context.minimal → execute → deliver.report
Model: haiku | Max Spirals: 1 | Retry: conservative

### refactor
Assembly: preproc.code → decomp.linear → schedule.sequential → context.full → execute → deliver.diff
Model: opus | Max Spirals: 4 | Retry: standard"""


# 所有静态前缀组合
FRAMEWORK_SKELETON = f"""{HARNESS_SYSTEM_PROMPT}

{MODULE_REGISTRY_PROMPT}

{STRATEGY_TABLE_PROMPT}"""


# ═══════════════════════════════════════════════
# PromptBuilder
# ═══════════════════════════════════════════════

@dataclass
class CacheMetrics:
    """缓存命中统计。"""
    total_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0
    estimated_tokens_saved: int = 0
    estimated_cost_saved: float = 0.0
    # 定价: cache_write=1.25x, cache_hit=0.10x, miss=1.00x
    skeleton_tokens: int = 0
    last_write_time: float = 0.0
    cache_ttl_seconds: int = 300  # 5 minutes

    @property
    def hit_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.cache_hits / self.total_calls

    @property
    def cache_fresh(self) -> bool:
        return (time.time() - self.last_write_time) < self.cache_ttl_seconds


@dataclass
class PromptBuilder:
    """缓存锚定提示构建器。

    用法:
        builder = PromptBuilder()
        skeleton, skeleton_hash = builder.get_skeleton()
        # 第一次: cache write (~125% cost)
        # 5min内后续: cache hit (~10% cost)

        prompt = builder.build(user_input="帮我做一个登录", state={"spiral": 1, "r": 0.8})
        # → skeleton + dynamic suffix
    """

    _skeleton: str = field(default="", init=False)
    _skeleton_hash: str = field(default="", init=False)
    _skeleton_tokens: int = field(default=0, init=False)
    metrics: CacheMetrics = field(default_factory=CacheMetrics)

    def __post_init__(self):
        self._build_skeleton()

    def _build_skeleton(self) -> None:
        """构建框架骨架——所有请求共享的静态前缀。"""
        self._skeleton = FRAMEWORK_SKELETON
        self._skeleton_hash = hashlib.sha256(self._skeleton.encode()).hexdigest()[:16]
        self._skeleton_tokens = self._estimate_tokens(self._skeleton)
        self.metrics.skeleton_tokens = self._skeleton_tokens

    def get_skeleton(self) -> tuple[str, str]:
        """返回骨架文本和哈希。哈希用于客户端判断缓存是否命中。"""
        return self._skeleton, self._skeleton_hash

    def build(
        self,
        user_input: str,
        state: Optional[dict] = None,
        context: Optional[str] = None,
        task_type: str = "classify",  # classify | execute | deliver
    ) -> dict:
        """构建完整提示。

        Returns:
            {
                "prompt": str,           # 完整prompt
                "skeleton_hash": str,    # 骨架哈希(客户端用于cache控制)
                "skeleton_tokens": int,  # 骨架token数
                "dynamic_tokens": int,   # 动态区token数
                "estimated_cache_behavior": "hit" | "write" | "miss"
            }
        """
        self.metrics.total_calls += 1

        # 判断缓存行为
        if not self.metrics.cache_fresh:
            cache_behavior = "write"
            self.metrics.cache_writes += 1
            self.metrics.last_write_time = time.time()
        elif self.metrics.total_calls == 1:
            cache_behavior = "write"
            self.metrics.cache_writes += 1
            self.metrics.last_write_time = time.time()
        else:
            cache_behavior = "hit"
            self.metrics.cache_hits += 1

        # 构建动态区
        dynamic_parts = [f"## User Input\n{user_input}"]

        if task_type == "classify":
            dynamic_parts.append(
                "\n## Task\nClassify the above user input into one of these intent classes:\n"
                "- code_feature: implementing new functionality\n"
                "- code_fix: fixing bugs/errors\n"
                "- data_analysis: analyzing data/statistics\n"
                "- research: searching/finding information\n"
                "- simple_query: simple factual questions\n"
                "- refactor: restructuring existing code\n\n"
                "Return ONLY the intent class name, nothing else."
            )

        if state:
            dynamic_parts.append(f"\n## Current State\n{json.dumps(state, ensure_ascii=False)}")

        if context:
            dynamic_parts.append(f"\n## Context\n{context}")

        dynamic_text = "\n".join(dynamic_parts)
        dynamic_tokens = self._estimate_tokens(dynamic_text)

        # 计算节省
        if cache_behavior == "hit":
            saved = self._skeleton_tokens * 0.9  # 骨架的90%被节省
            self.metrics.estimated_tokens_saved += int(saved)
            # Anthropic定价: cache_hit约为基础价的10%, 所以省了90%
            # 估算: $3/M input tokens → skeleton 2000 tokens → ~$0.006
            # cache_hit → ~$0.0006, 省了 ~$0.0054/次
            self.metrics.estimated_cost_saved += saved * 3.0 / 1_000_000

        return {
            "prompt": self._skeleton + "\n\n" + dynamic_text,
            "skeleton_hash": self._skeleton_hash,
            "skeleton_tokens": self._skeleton_tokens,
            "dynamic_tokens": dynamic_tokens,
            "total_tokens": self._skeleton_tokens + dynamic_tokens,
            "estimated_cache_behavior": cache_behavior,
            "estimated_cost_factor": 0.10 if cache_behavior == "hit" else (1.25 if cache_behavior == "write" else 1.0),
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略token估算: ~4字符/token (英文), ~2字符/token (中文)。"""
        # 简化的混合估算
        chars = len(text)
        # 假设70%英文(4 char/token) + 30%中文(2 char/token)
        return int(chars * 0.7 / 4 + chars * 0.3 / 2)


# ═══════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════

_builder: Optional[PromptBuilder] = None


def get_prompt_builder() -> PromptBuilder:
    global _builder
    if _builder is None:
        _builder = PromptBuilder()
    return _builder
