"""
DynamicStrategy — 根据预处理结果动态调整策略参数。

静态策略表适合冷启动，但实际运行中，同类意图的不同输入可能需要不同的
模型选择、螺旋轮次、并行度。DynamicStrategy 在策略匹配后、执行前
调整这些参数。

调整因子:
1. complexity_score → 影响 spiral_max_iterations 和 model 选择
2. entity richness → 影响 max_parallel_subtasks
3. ambiguity flags → 影响 retry_policy
4. input specificity → 影响 convergence_threshold
"""

from __future__ import annotations

from agent_harness.core.envelope import Envelope


# 策略默认值（从 route_table.json 的可选覆盖）
STRATEGY_DEFAULTS = {
    "code_feature": {
        "model": "opus", "max_iterations": 5, "max_parallel": 3,
        "retry_policy": "standard", "convergence_threshold": 0.05,
    },
    "code_fix": {
        "model": "sonnet", "max_iterations": 3, "max_parallel": 1,
        "retry_policy": "aggressive", "convergence_threshold": 0.08,
    },
    "data_analysis": {
        "model": "opus", "max_iterations": 4, "max_parallel": 5,
        "retry_policy": "standard", "convergence_threshold": 0.05,
    },
    "research": {
        "model": "haiku", "max_iterations": 3, "max_parallel": 8,
        "retry_policy": "conservative", "convergence_threshold": 0.10,
    },
    "simple_query": {
        "model": "haiku", "max_iterations": 1, "max_parallel": 1,
        "retry_policy": "conservative", "convergence_threshold": 0.20,
    },
    "refactor": {
        "model": "opus", "max_iterations": 4, "max_parallel": 2,
        "retry_policy": "standard", "convergence_threshold": 0.05,
    },
}


def adjust_strategy(envelope: Envelope) -> Envelope:
    """根据 envelope 中的预处理结果动态调整策略参数。

    在 Router.classify() 之后、Orchestrator.execute() 之前调用。
    """
    sid = envelope.strategy_id or "simple_query"
    defaults = STRATEGY_DEFAULTS.get(sid, STRATEGY_DEFAULTS["simple_query"])

    complexity = envelope.task.get("complexity_score", 0.5)
    entities = envelope.task.get("entities", {})
    ambiguity_flags = envelope.task.get("ambiguity_flags", [])
    constraints = envelope.task.get("constraints", {})
    original_input = envelope.task.get("original_input", "")

    # ── 模型选择 ──
    model = _select_model(sid, defaults["model"], complexity, len(ambiguity_flags))

    # ── 螺旋轮次 ──
    max_iterations = _adjust_iterations(
        defaults["max_iterations"], complexity, ambiguity_flags, entities, len(original_input)
    )

    # ── 并行度 ──
    entity_count = sum(len(v) if isinstance(v, list) else 1 for v in entities.values())
    max_parallel = _adjust_parallel(defaults["max_parallel"], entity_count, complexity)

    # ── 收敛阈值 ──
    convergence_threshold = _adjust_threshold(
        defaults["convergence_threshold"], complexity, len(constraints)
    )

    # ── 重试策略 ──
    retry_policy = _select_retry(defaults["retry_policy"], len(ambiguity_flags), complexity)

    # 写入 envelope
    envelope.task["_dynamic_adjustments"] = {
        "model": model,
        "max_iterations": max_iterations,
        "max_parallel_subtasks": max_parallel,
        "convergence_threshold": convergence_threshold,
        "retry_policy": retry_policy,
        "reasons": [],
    }

    envelope.spiral_max_iterations = max_iterations
    envelope.convergence_target = convergence_threshold
    envelope.task["max_parallel_subtasks"] = max_parallel

    return envelope


def _select_model(strategy: str, default: str, complexity: float, ambiguity_count: int) -> str:
    """Probe-First 分级模型选择 — 轻量探针先行，按需升级。

    分级逻辑:
    - flash (haiku): 简单明确任务，1× 成本
    - auto (sonnet): 中等复杂度，1-3× 成本
    - pro (opus): 高复杂度/多歧义/用户显式要求，~12× 成本

    辅助调用（摘要、子任务、修复重试）强制使用 flash。
    """
    if complexity > 0.65 and ambiguity_count >= 2:
        if default == "haiku":
            return "sonnet"
        return "opus"
    if complexity < 0.25 and ambiguity_count == 0:
        if default == "opus":
            return "sonnet"
        if default == "sonnet":
            return "haiku"
    return default


# 辅助调用强制使用的模型（所有辅助调用强制使用最轻量模型以控制成本）
AUX_CALL_MODEL = "haiku"

# auto-upgrade 触发器: 模型响应中出现这些标记时升级
AUTO_UPGRADE_TRIGGERS = [
    "<<<NEEDS_PRO>>>",
    "<<<NEEDS_OPUS>>>",
    "此任务需要更强大的模型",
    "this task requires a more capable model",
]


def select_model_for_task(
    strategy: str,
    complexity: float,
    ambiguity_count: int,
    is_aux_call: bool = False,
    previous_failures: int = 0,
    user_requested_model: str | None = None,
) -> str:
    """Flash-First 模型选择（对外公开接口）。

    Args:
        strategy: 策略 ID
        complexity: 任务复杂度 (0-1)
        ambiguity_count: 歧义标记数
        is_aux_call: 是否为辅助调用（摘要、子 Agent、修复重试等）
        previous_failures: 连续失败次数（触发自动升级）
        user_requested_model: 用户显式指定的模型（优先级最高）

    Returns:
        模型名称: "haiku" | "sonnet" | "opus"
    """
    # 辅助调用强制 flash
    if is_aux_call:
        return AUX_CALL_MODEL

    # 用户显式选择优先
    if user_requested_model:
        return user_requested_model

    # 连续失败触发自动升级
    if previous_failures >= 3:
        return "opus"
    if previous_failures >= 2:
        return "sonnet"

    # 策略默认模型 + 动态调整
    defaults = {
        "code_feature": "opus", "code_fix": "sonnet", "data_analysis": "opus",
        "research": "haiku", "simple_query": "haiku", "refactor": "opus",
    }
    default = defaults.get(strategy, "sonnet")

    return _select_model(strategy, default, complexity, ambiguity_count)


def detect_auto_upgrade(response_text: str) -> bool:
    """检测模型响应中是否包含自动升级请求。"""
    response_lower = response_text.lower()
    return any(trigger.lower() in response_lower for trigger in AUTO_UPGRADE_TRIGGERS)


def _adjust_iterations(
    default: int, complexity: float, ambiguity_flags: list, entities: dict, input_len: int
) -> int:
    """动态调整螺旋轮次。"""
    adjusted = default

    if complexity < 0.25:
        adjusted = max(1, adjusted - 2)
    elif complexity < 0.40:
        adjusted = max(1, adjusted - 1)

    if len(ambiguity_flags) >= 2:
        adjusted = min(default + 1, adjusted + 1)

    entity_count = sum(len(v) if isinstance(v, list) else 1 for v in entities.values())
    if entity_count >= 5:
        adjusted = max(1, adjusted - 1)

    if input_len > 150:
        adjusted = max(1, adjusted - 1)
    elif input_len < 20:
        adjusted = min(default, adjusted + 1)

    return max(1, adjusted)


def _adjust_parallel(default: int, entity_count: int, complexity: float) -> int:
    if entity_count >= 5 and complexity < 0.5:
        return min(default + 2, 8)
    if complexity > 0.7:
        return max(1, default - 1)
    return default


def _adjust_threshold(default: float, complexity: float, constraint_count: int) -> float:
    if constraint_count >= 3:
        return max(0.02, default * 0.7)
    if complexity > 0.7:
        return default * 1.2
    return default


def _select_retry(default: str, ambiguity_count: int, complexity: float) -> str:
    if complexity > 0.7 and ambiguity_count >= 2:
        return "conservative"
    return default
