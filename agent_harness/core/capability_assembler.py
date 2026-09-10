"""
CapabilityAssembler — 将 ProblemProfile 转化为动态模块装配链。

核心: 每个流水线阶段根据问题特征选择最合适的模块变体。
不再是"什么类别→什么链"，而是"什么特征→需要什么能力→选什么模块"。

向后兼容: STRATEGY_TO_PROFILE 映射表将 6 个 legacy strategy_id
映射为等效 ProblemProfile，产出的模块链与当前 v2 deductive 完全一致。
"""

from __future__ import annotations

from agent_harness.core.problem_profile import ProblemProfile
from agent_harness.core.router import AssemblyInstruction


class CapabilityAssembler:
    """能力装配器 — ProblemProfile → 动态模块链。

    用法:
        assembler = CapabilityAssembler()
        instructions = assembler.assemble(profile)
        spiral_cfg = assembler.derive_spiral_config(profile)
        model = assembler.derive_model(profile)
    """

    # ── 主入口 ──

    def assemble(self, profile: ProblemProfile) -> list[AssemblyInstruction]:
        """根据 ProblemProfile 生成 6 阶段动态装配链。"""
        instructions: list[AssemblyInstruction] = []
        position = 0

        for module_name, variant in [
            ("preproc", self._select_preproc(profile)),
            ("decomp", self._select_decomp(profile)),
            ("schedule", self._select_schedule(profile)),
            ("context", self._select_context(profile)),
            ("execute", self._select_execute(profile)),
            ("deliver", self._select_deliver(profile)),
        ]:
            instructions.append(AssemblyInstruction(
                module=module_name, variant=variant, position=position,
            ))
            position += 1

        return instructions

    # ── 各阶段选择规则 (优先级链, 首个匹配生效) ──

    def _select_preproc(self, p: ProblemProfile) -> str:
        if p.complexity < 0.2 and p.ambiguity < 0.15:
            return "simple"
        if p.complexity >= 0.3:
            return "deductive"
        if p.domain_code > 0.5:
            return "code"
        return "full"

    def _select_decomp(self, p: ProblemProfile) -> str:
        if p.complexity < 0.3 or p.domain_concept > 0.7:
            return "single"
        if 0.3 <= p.complexity < 0.5:
            return "linear"
        return "entropy"

    def _select_schedule(self, p: ProblemProfile) -> str:
        if p.expected_subtask_count > 3:
            return "parallel"
        return "sequential"

    def _select_context(self, p: ProblemProfile) -> str:
        if p.scope < 0.3 and p.domain_code < 0.3:
            return "minimal"
        return "full"

    def _select_execute(self, p: ProblemProfile) -> str:
        if p.risk > 0.0 or p.complexity >= 0.5:
            return "gated"
        return "default"

    def _select_deliver(self, p: ProblemProfile) -> str:
        if p.risk > 0.0 or p.complexity >= 0.5:
            return "gated"
        if p.domain_code >= 0.5:
            return "diff"
        return "report"

    # ── 派生参数 ──

    def derive_spiral_config(self, p: ProblemProfile) -> dict:
        """从 ProblemProfile 连续计算螺旋收敛参数。"""
        base_iterations = 2.0 + p.complexity * 3.0 + p.ambiguity * 2.0
        max_iterations = max(1, min(8, int(round(base_iterations))))

        convergence_threshold = 0.02 + p.complexity * 0.06 + p.ambiguity * 0.04
        convergence_threshold = round(min(0.25, convergence_threshold), 4)

        if p.ambiguity > 0.5:
            refinement_strategy = "narrow_scope"
        elif p.ambiguity > 0.2:
            refinement_strategy = "add_constraints"
        else:
            refinement_strategy = None

        return {
            "max_iterations": max_iterations,
            "convergence_threshold": convergence_threshold,
            "refinement_strategy": refinement_strategy,
        }

    def derive_model(self, p: ProblemProfile) -> str:
        """根据问题特征选择默认模型。"""
        if p.complexity > 0.65 and p.ambiguity >= 0.3:
            return "opus"
        if p.complexity > 0.4 or p.ambiguity > 0.3:
            return "sonnet"
        return "haiku"

    def derive_max_parallel(self, p: ProblemProfile) -> int:
        """根据问题特征计算最大并行子任务数。"""
        entity_count = len(p.signals.get("entities_keys", []))
        if entity_count >= 5 and p.complexity < 0.5:
            return min(8, 5 + entity_count // 2)
        if p.complexity > 0.7:
            return 1
        if p.expected_subtask_count > 3:
            return min(4, p.expected_subtask_count)
        return 1

    def derive_retry_policy(self, p: ProblemProfile) -> str:
        """根据问题特征选择重试策略。"""
        if p.ambiguity > 0.6 or p.risk > 0.5:
            return "conservative"
        if p.complexity < 0.3 and p.ambiguity < 0.2:
            return "aggressive"
        return "standard"

    def derive_max_constraints(self, p: ProblemProfile) -> int:
        """最大约束数随复杂度和范围缩放。"""
        return max(2, int(round(p.complexity * 10 + p.scope * 6)))

    # ── 向后兼容: legacy strategy_id → ProblemProfile 预设映射 ──

    STRATEGY_TO_PROFILE: dict[str, ProblemProfile] = {
        "code_feature": ProblemProfile(
            domain_code=0.80, domain_data=0.05, domain_concept=0.10, domain_system=0.05,
            complexity=0.55, ambiguity=0.30, scope=0.60, risk=0.30, context_dependency=0.70,
            expected_subtask_count=3,
        ),
        "code_fix": ProblemProfile(
            domain_code=0.70, domain_data=0.05, domain_concept=0.10, domain_system=0.15,
            complexity=0.40, ambiguity=0.40, scope=0.29, risk=0.15, context_dependency=0.60,
            expected_subtask_count=1,
        ),
        "data_analysis": ProblemProfile(
            domain_code=0.10, domain_data=0.80, domain_concept=0.05, domain_system=0.05,
            complexity=0.49, ambiguity=0.25, scope=0.50, risk=0.00, context_dependency=0.20,
            expected_subtask_count=5,
        ),
        "research": ProblemProfile(
            domain_code=0.05, domain_data=0.10, domain_concept=0.05, domain_system=0.80,
            complexity=0.35, ambiguity=0.50, scope=0.70, risk=0.00, context_dependency=0.10,
            expected_subtask_count=8,
        ),
        "simple_query": ProblemProfile(
            domain_code=0.00, domain_data=0.00, domain_concept=0.90, domain_system=0.10,
            complexity=0.15, ambiguity=0.10, scope=0.10, risk=0.00, context_dependency=0.00,
            expected_subtask_count=1,
        ),
        "refactor": ProblemProfile(
            domain_code=0.70, domain_data=0.00, domain_concept=0.10, domain_system=0.20,
            complexity=0.60, ambiguity=0.30, scope=0.60, risk=0.40, context_dependency=0.80,
            expected_subtask_count=2,
        ),
    }

    def assemble_from_strategy_id(self, strategy_id: str) -> list[AssemblyInstruction]:
        """向后兼容: 用 legacy strategy_id 预设生成装配链。

        每个预设映射后的 Profile 经 assemble() 产出与当前
        v2 deductive 策略完全一致的模块链。
        """
        profile = self.STRATEGY_TO_PROFILE.get(strategy_id)
        if profile is None:
            profile = self.STRATEGY_TO_PROFILE["simple_query"]
        return self.assemble(profile)
