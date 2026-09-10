"""
螺旋门控 — 在 Preproc 之后、进入螺旋循环之前，判断任务的真实复杂度，
动态决定 max_iterations，避免简单任务浪费 token。

判断维度:
1. complexity_score — 低于阈值 → 减少螺旋轮次
2. ambiguity_flags — 空 → 减少螺旋轮次
3. entities 丰富度 — 越多具体实体 → 越不需要螺旋
4. 输入长度和 specificity — 越长/越具体 → 越不需要螺旋

输出: 调整后的 spiral_max_iterations (1 ~ strategy默认值)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent_harness.core.envelope import Envelope


# 各策略默认最大螺旋轮次（策略表原始值）
STRATEGY_DEFAULT_MAX_ITERATIONS = {
    "code_feature": 5,
    "code_fix": 3,
    "data_analysis": 4,
    "research": 3,
    "simple_query": 1,
    "refactor": 4,
}


@dataclass
class SpiralGate:
    """螺旋门控 — 判断任务需要多少轮螺旋收敛。

    核心逻辑:
    - 复杂度低 + 无歧义 + 实体丰富 → 1轮（不走螺旋，直接交付）
    - 复杂度中 + 少量歧义 → 2-3轮
    - 复杂度高 + 大量歧义 → 保持策略默认最大轮次

    这样简单任务可以省 60-80% token。
    """

    # 门控阈值（可调）
    complexity_low_threshold: float = 0.30    # 低于此值认为"简单明确"
    complexity_high_threshold: float = 0.60   # 高于此值认为"模糊复杂"
    ambiguity_weight: float = 0.5             # 每个歧义标记增加的轮次
    entity_richness_bonus: float = -0.5       # 每个具体实体减少的轮次
    input_short_threshold: int = 30           # 输入短于此长度认为"非常模糊"
    input_long_threshold: int = 120           # 输入长于此长度认为"比较具体"

    def assess(self, envelope: Envelope) -> dict:
        """评估任务的螺旋需求，返回调整建议。

        v4: 若存在 ProblemProfile，使用 profile-based 评估。
        """
        if envelope.problem_profile is not None:
            return self._assess_from_profile(envelope)

        strategy_id = envelope.strategy_id or "simple_query"
        original_max = STRATEGY_DEFAULT_MAX_ITERATIONS.get(
            strategy_id,
            envelope.spiral_max_iterations,
        )

        # 收集信号
        complexity = envelope.task.get("complexity_score", 0.5)
        ambiguity_flags = envelope.task.get("ambiguity_flags", [])
        entities = envelope.task.get("entities", {})
        original_input = envelope.task.get("original_input", "")
        constraints = envelope.task.get("constraints", {})

        reasons = []
        score = float(original_max)  # 从策略默认开始递减

        # 规则1: simple_query 永远不需要螺旋
        if strategy_id == "simple_query":
            return self._result(1, original_max, reasons + ["simple_query always single-pass"])

        # 规则2: 低复杂度 → 减少螺旋
        if complexity <= self.complexity_low_threshold:
            reduction = min(3, int((self.complexity_low_threshold - complexity) * 10))
            score -= max(reduction, 1)
            reasons.append(f"low complexity ({complexity:.2f} ≤ {self.complexity_low_threshold}) → -{max(reduction,1)}")

        # 规则3: 高复杂度 → 保持或增加（模糊任务需要更多螺旋）
        if complexity >= self.complexity_high_threshold:
            score = max(score, original_max)
            reasons.append(f"high complexity ({complexity:.2f} ≥ {self.complexity_high_threshold}) → keep max={original_max}")

        # 规则4: 歧义检测 → 每个歧义需要一轮来澄清
        if ambiguity_flags:
            ambiguity_bonus = len(ambiguity_flags) * self.ambiguity_weight
            score += ambiguity_bonus
            reasons.append(f"{len(ambiguity_flags)} ambiguity flags → +{ambiguity_bonus:.1f}")

        # 规则5: 实体丰富 → 需求明确，减少轮次
        # 计算实际实体条目数（list类型的value按长度计，其他的按1计）
        entity_items = 0
        for v in entities.values():
            if isinstance(v, list):
                entity_items += len(v)
            else:
                entity_items += 1

        if entity_items >= 4:
            reduction = min(3, entity_items * abs(self.entity_richness_bonus))
            score -= reduction
            reasons.append(f"{entity_items} entity items (very rich) → -{reduction:.1f}")
        elif entity_items >= 2:
            reduction = min(2, entity_items * abs(self.entity_richness_bonus) * 0.8)
            score -= reduction
            reasons.append(f"{entity_items} entity items → -{reduction:.1f}")
        elif entity_items == 0:
            score += 1
            reasons.append("zero entities (very vague) → +1")

        # 规则6: 已有显式约束 → 需求已很具体
        explicit_constraints = len(constraints)
        if explicit_constraints > 1:
            reduction = min(explicit_constraints * 0.5, 3)
            score -= reduction
            reasons.append(f"{explicit_constraints} explicit constraints → -{reduction:.1f}")

        # 规则7: 输入长度
        input_len = len(original_input)
        if input_len < self.input_short_threshold:
            score += 1
            reasons.append(f"very short input ({input_len} chars) → +1 (more spiral needed)")
        elif input_len > self.input_long_threshold:
            score -= 1
            reasons.append(f"detailed input ({input_len} chars) → -1")

        # 规则8: code_fix 通常比 code_feature 收敛更快
        if strategy_id == "code_fix":
            score -= 1
            reasons.append("code_fix converges faster than code_feature → -1")

        # 钳制
        score = max(1, min(score, original_max))
        recommended = int(round(score))

        skip_spiral = recommended <= 1

        return self._result(recommended, original_max, reasons, skip_spiral)

    def apply(self, envelope: Envelope) -> Envelope:
        """直接在 Envelope 上应用门控结果。"""
        assessment = self.assess(envelope)

        envelope.spiral_max_iterations = assessment["recommended_iterations"]

        if assessment["skip_spiral"]:
            envelope.convergence_radius = 0.0  # 直接标记为已收敛
            envelope.convergence_target = 1.0   # 任何半径都满足

        envelope.task["_spiral_gate"] = assessment
        return envelope

    def _assess_from_profile(self, envelope: Envelope) -> dict:
        """v4: 基于 ProblemProfile 的螺旋需求评估。"""
        p = envelope.problem_profile
        from agent_harness.core.capability_assembler import CapabilityAssembler
        assembler = CapabilityAssembler()
        spiral_cfg = assembler.derive_spiral_config(p)
        original_max = spiral_cfg["max_iterations"]

        reasons = []
        score = float(original_max)

        # 规则1: 平凡问题 → 单轮
        if p.is_trivial:
            return self._result(1, original_max, reasons + ["adaptive: trivial concept query, single-pass"])

        # 规则2: 低复杂度
        if p.complexity <= self.complexity_low_threshold:
            reduction = min(3, int((self.complexity_low_threshold - p.complexity) * 10))
            score -= max(reduction, 1)
            reasons.append(f"low complexity ({p.complexity:.2f}) → -{max(reduction,1)}")

        # 规则3: 高复杂度
        if p.complexity >= self.complexity_high_threshold:
            score = max(score, original_max)
            reasons.append(f"high complexity ({p.complexity:.2f}) → keep max={original_max}")

        # 规则4: 歧义
        ambiguity_flags = p.signals.get("ambiguity_flags", [])
        if ambiguity_flags:
            ambiguity_bonus = len(ambiguity_flags) * self.ambiguity_weight
            score += ambiguity_bonus
            reasons.append(f"{len(ambiguity_flags)} ambiguity flags → +{ambiguity_bonus:.1f}")

        # 规则5: 实体丰富度
        entity_keys = p.signals.get("entities_keys", [])
        entity_count = len(entity_keys)
        if entity_count >= 4:
            reduction = min(3, entity_count * abs(self.entity_richness_bonus))
            score -= reduction
            reasons.append(f"{entity_count} entity keys (very rich) → -{reduction:.1f}")
        elif entity_count >= 2:
            reduction = min(2, entity_count * abs(self.entity_richness_bonus) * 0.8)
            score -= reduction
            reasons.append(f"{entity_count} entity keys → -{reduction:.1f}")
        elif entity_count == 0:
            score += 1
            reasons.append("zero entities (very vague) → +1")

        # 规则6: 输入长度
        input_len = p.signals.get("input_len", 0)
        if input_len < self.input_short_threshold:
            score += 1
            reasons.append(f"very short input ({input_len} chars) → +1")
        elif input_len > self.input_long_threshold:
            score -= 1
            reasons.append(f"detailed input ({input_len} chars) → -1")

        # 规则7: 代码修复收敛更快
        if p.domain_code > 0.4 and p.complexity < 0.5 and p.risk > 0:
            score -= 1
            reasons.append("code_fix profile → -1")

        score = max(1, min(score, original_max))
        recommended = int(round(score))
        return self._result(recommended, original_max, reasons, recommended <= 1)

    def _result(self, recommended: int, original: int, reasons: list[str], skip: bool = False) -> dict:
        saved = original - recommended
        tokens_per_iteration = 12000  # 粗略估算每轮螺旋的 token 成本
        return {
            "recommended_iterations": recommended,
            "original_max": original,
            "skip_spiral": skip or recommended <= 1,
            "saved_iterations": saved,
            "saved_tokens_estimate": saved * tokens_per_iteration,
            "reasons": reasons,
        }


def estimate_token_savings(assessment: dict) -> str:
    """人类可读的节省估算。"""
    saved = assessment["saved_iterations"]
    if saved == 0:
        return "无节省（复杂度高，需要完整螺旋）"
    if saved <= 1:
        return f"节省 ~{assessment['saved_tokens_estimate']:,} token（减少 {saved} 轮螺旋）"
    return f"大幅节省 ~{assessment['saved_tokens_estimate']:,} token（减少 {saved} 轮螺旋，{assessment['recommended_iterations']}轮直达交付）"
