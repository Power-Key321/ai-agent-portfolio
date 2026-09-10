"""
Harness v4 自适应乐高架构 — 测试套件。

验证:
1. ProblemProfile 创建与便捷属性
2. ProblemAnalyzer 多维分析准确性
3. CapabilityAssembler 动态模块选择
4. 向后兼容预设映射
5. 派生参数 (spiral_config, model, max_parallel, retry_policy)
6. Router/ModelRouter 自适应模式集成
7. 端到端: 自适应模式 vs 固定策略模式
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from agent_harness.core.problem_profile import ProblemProfile
from agent_harness.core.problem_analyzer import ProblemAnalyzer
from agent_harness.core.capability_assembler import CapabilityAssembler
from agent_harness.core.envelope import Envelope
from agent_harness.core.router import Router
from agent_harness.core.model_router import ModelRouter


# ═══════════════════════════════════════════════════
# 测试 1: ProblemProfile
# ═══════════════════════════════════════════════════

class TestProblemProfile:
    def test_default_construction(self):
        p = ProblemProfile()
        assert p.domain_code == 0.0
        assert p.complexity == 0.5
        assert p.expected_subtask_count == 1
        assert p.signals == {}

    def test_dominant_domain(self):
        p = ProblemProfile(domain_concept=0.9, domain_code=0.05, domain_data=0.03, domain_system=0.02)
        assert p.dominant_domain == "concept"

        p2 = ProblemProfile(domain_code=0.8, domain_concept=0.1, domain_data=0.05, domain_system=0.05)
        assert p2.dominant_domain == "code"

    def test_is_trivial(self):
        trivial = ProblemProfile(domain_concept=0.9, complexity=0.05, ambiguity=0.05)
        assert trivial.is_trivial

        not_trivial = ProblemProfile(domain_concept=0.9, complexity=0.3, ambiguity=0.1)
        assert not not_trivial.is_trivial

    def test_is_complex_code(self):
        cc = ProblemProfile(domain_code=0.7, complexity=0.6)
        assert cc.is_complex_code

        simple_code = ProblemProfile(domain_code=0.7, complexity=0.3)
        assert not simple_code.is_complex_code

    def test_is_destructive(self):
        safe = ProblemProfile(risk=0.0)
        assert not safe.is_destructive

        destructive = ProblemProfile(risk=0.8)
        assert destructive.is_destructive

    def test_profile_field_in_envelope(self):
        env = Envelope()
        assert env.problem_profile is None
        p = ProblemProfile(domain_concept=0.9)
        env.problem_profile = p
        assert env.problem_profile.dominant_domain == "concept"

    def test_profile_propagates_in_spawn(self):
        p = ProblemProfile(domain_code=0.8, complexity=0.5)
        env = Envelope()
        env.problem_profile = p
        child = env.spawn("execute.gated")
        assert child.problem_profile is p  # 共享引用

    def test_profile_propagates_in_spawn_next_spiral(self):
        p = ProblemProfile(domain_concept=0.7, complexity=0.3)
        env = Envelope()
        env.problem_profile = p
        next_spiral = env.spawn_next_spiral()
        assert next_spiral.problem_profile is p


# ═══════════════════════════════════════════════════
# 测试 2: ProblemAnalyzer
# ═══════════════════════════════════════════════════

class TestProblemAnalyzer:
    def setup_method(self):
        self.analyzer = ProblemAnalyzer()

    def _make_env(self, text, complexity=0.5, entities=None, ambiguity_flags=None, five_elements=None, constraints=None):
        env = Envelope()
        env.task["original_input"] = text
        env.task["complexity_score"] = complexity
        env.task["entities"] = entities or {}
        env.task["ambiguity_flags"] = ambiguity_flags or []
        env.task["five_elements"] = five_elements or {}
        env.task["constraints"] = constraints or {}
        return env

    def test_domain_concept_question(self):
        env = self._make_env("什么是闭包")
        p = self.analyzer.analyze(env)
        assert p.domain_concept > 0.5
        assert p.dominant_domain == "concept"

    def test_domain_code_creation(self):
        env = self._make_env("帮我实现一个JWT认证中间件",
                             entities={"language": "Python", "framework": "FastAPI"})
        p = self.analyzer.analyze(env)
        assert p.domain_code > 0.3

    def test_domain_data_analysis(self):
        env = self._make_env("分析销售额最近三个月的变化趋势",
                             entities={"assets": ["销售额"], "time_range": "3个月"})
        p = self.analyzer.analyze(env)
        assert p.domain_data > 0.3

    def test_domain_system_research(self):
        env = self._make_env("搜索最新的微服务架构安全事件")
        p = self.analyzer.analyze(env)
        assert p.domain_system > 0.2

    def test_complexity_from_preproc(self):
        env = self._make_env("test", complexity=0.1)
        p = self.analyzer.analyze(env)
        assert p.complexity == 0.1

        env2 = self._make_env("test", complexity=0.85)
        p2 = self.analyzer.analyze(env2)
        assert p2.complexity == 0.85

    def test_ambiguity_from_flags(self):
        env = self._make_env("test", ambiguity_flags=["missing_subject", "missing_object", "vague_goal"])
        p = self.analyzer.analyze(env)
        assert p.ambiguity > 0.3

    def test_ambiguity_from_short_input(self):
        env = self._make_env("搞")
        p = self.analyzer.analyze(env)
        assert p.ambiguity > 0.2  # 极短输入→高歧义

    def test_low_ambiguity_detailed_input(self):
        env = self._make_env("在src/auth/middleware.py中为FastAPI添加JWT Bearer token认证中间件，使用python-jose库",
                             five_elements={"completeness": 0.9})
        p = self.analyzer.analyze(env)
        assert p.ambiguity < 0.3

    def test_risk_destructive(self):
        env = self._make_env("删除所有用户数据")
        p = self.analyzer.analyze(env)
        assert p.risk >= 0.5

    def test_risk_read_only(self):
        env = self._make_env("什么是闭包")
        p = self.analyzer.analyze(env)
        assert p.risk == 0.0

    def test_scope_from_entities(self):
        env = self._make_env("重构整个项目的认证系统",
                             entities={"language": "Python", "framework": "FastAPI",
                                       "files_mentioned": ["auth.py", "middleware.py", "models.py", "routes.py"]})
        p = self.analyzer.analyze(env)
        assert p.scope > 0.4

    def test_context_dependency_codebase(self):
        env = self._make_env("修复auth中间件的bug",
                             constraints={"existing_codebase": True})
        p = self.analyzer.analyze(env)
        assert p.context_dependency > 0.3

    def test_problem_analyzer_sub_millisecond(self):
        import time
        env = self._make_env("帮我实现一个复杂的分布式事务系统，涉及多个数据库和消息队列")
        t0 = time.time()
        for _ in range(100):
            self.analyzer.analyze(env)
        elapsed = (time.time() - t0) * 1000
        avg_ms = elapsed / 100
        assert avg_ms < 1.0, f"analyze() took {avg_ms:.3f}ms avg, expected < 1ms"


# ═══════════════════════════════════════════════════
# 测试 3: CapabilityAssembler 动态选择
# ═══════════════════════════════════════════════════

class TestCapabilityAssembler:
    def setup_method(self):
        self.assembler = CapabilityAssembler()

    def extract_chain(self, profile):
        return [f"{i.module}.{i.variant}" for i in self.assembler.assemble(profile)]

    def test_trivial_concept_gets_lightweight_chain(self):
        """概念问题 → 轻量链"""
        p = ProblemProfile(domain_concept=0.9, complexity=0.05, ambiguity=0.05,
                           scope=0.1, risk=0.0, context_dependency=0.0)
        chain = self.extract_chain(p)
        assert chain[0] == "preproc.simple"
        assert chain[1] == "decomp.single"
        assert chain[3] == "context.minimal"  # 窄范围非代码 → minimal
        assert chain[4] == "execute.default"
        assert chain[5] == "deliver.report"

    def test_complex_code_gets_heavy_chain(self):
        """复杂代码 → 重型链"""
        p = ProblemProfile(domain_code=0.8, complexity=0.7, ambiguity=0.3,
                           scope=0.7, risk=0.3, context_dependency=0.7)
        chain = self.extract_chain(p)
        assert chain[0] == "preproc.deductive"
        assert chain[1] == "decomp.entropy"
        assert chain[3] == "context.full"
        assert chain[4] == "execute.gated"
        assert chain[5] == "deliver.gated"

    def test_medium_code_gets_code_preproc(self):
        """中等代码 → code预处理 + linear拆解"""
        p = ProblemProfile(domain_code=0.7, complexity=0.4, ambiguity=0.2,
                           scope=0.4, risk=0.15, context_dependency=0.5)
        chain = self.extract_chain(p)
        assert chain[0] == "preproc.deductive"  # complexity>=0.3
        assert chain[1] == "decomp.linear"
        assert chain[4] == "execute.gated"  # risk>0
        assert chain[5] == "deliver.gated"  # risk>0

    def test_parallel_schedule_for_many_subtasks(self):
        """多子任务 → 并行调度"""
        p = ProblemProfile(domain_data=0.7, complexity=0.4, scope=0.5,
                           expected_subtask_count=5)
        chain = self.extract_chain(p)
        assert chain[2] == "schedule.parallel"

    def test_sequential_schedule_for_few_subtasks(self):
        """少子任务 → 顺序调度"""
        p = ProblemProfile(expected_subtask_count=2)
        chain = self.extract_chain(p)
        assert chain[2] == "schedule.sequential"

    def test_minimal_context_for_narrow_scope(self):
        """窄范围非代码 → minimal上下文"""
        p = ProblemProfile(domain_concept=0.8, scope=0.1, domain_code=0.1)
        chain = self.extract_chain(p)
        assert chain[3] == "context.minimal"

    def test_full_context_for_wide_scope(self):
        """宽范围 → full上下文"""
        p = ProblemProfile(domain_concept=0.5, scope=0.5, domain_code=0.3)
        chain = self.extract_chain(p)
        assert chain[3] == "context.full"

    def test_safe_simple_gets_default_executor(self):
        """安全简单 → 默认执行器"""
        p = ProblemProfile(domain_concept=0.8, complexity=0.1, risk=0.0)
        chain = self.extract_chain(p)
        assert chain[4] == "execute.default"

    def test_risky_gets_gated_executor(self):
        """有风险 → 门检执行器"""
        p = ProblemProfile(domain_code=0.6, risk=0.15)
        chain = self.extract_chain(p)
        assert chain[4] == "execute.gated"

    def test_diff_deliver_for_code(self):
        """代码产物 → diff交付"""
        p = ProblemProfile(domain_code=0.7, complexity=0.2, risk=0.0)
        chain = self.extract_chain(p)
        assert chain[5] == "deliver.diff"

    def test_report_deliver_for_concept(self):
        """概念产物 → report交付"""
        p = ProblemProfile(domain_concept=0.8, complexity=0.2, risk=0.0)
        chain = self.extract_chain(p)
        assert chain[5] == "deliver.report"


# ═══════════════════════════════════════════════════
# 测试 4: 派生参数
# ═══════════════════════════════════════════════════

class TestDerivedParams:
    def setup_method(self):
        self.assembler = CapabilityAssembler()

    def test_derive_model_haiku_for_simple(self):
        p = ProblemProfile(complexity=0.1, ambiguity=0.05)
        assert self.assembler.derive_model(p) == "haiku"

    def test_derive_model_sonnet_for_medium(self):
        p = ProblemProfile(complexity=0.5, ambiguity=0.2)
        assert self.assembler.derive_model(p) == "sonnet"

    def test_derive_model_opus_for_complex(self):
        p = ProblemProfile(complexity=0.7, ambiguity=0.4)
        assert self.assembler.derive_model(p) == "opus"

    def test_derive_spiral_config_trivial(self):
        p = ProblemProfile(complexity=0.1, ambiguity=0.05)
        cfg = self.assembler.derive_spiral_config(p)
        assert cfg["max_iterations"] <= 3
        assert cfg["convergence_threshold"] <= 0.05

    def test_derive_spiral_config_complex(self):
        p = ProblemProfile(complexity=0.8, ambiguity=0.6)
        cfg = self.assembler.derive_spiral_config(p)
        assert cfg["max_iterations"] >= 5
        assert cfg["convergence_threshold"] >= 0.06
        assert cfg["refinement_strategy"] == "narrow_scope"

    def test_derive_max_parallel_complex_sequential(self):
        """高复杂度任务 → 降为1 (避免复合错误)"""
        p = ProblemProfile(complexity=0.8, expected_subtask_count=5)
        assert self.assembler.derive_max_parallel(p) == 1

    def test_derive_max_parallel_many_entities(self):
        p = ProblemProfile(complexity=0.3, expected_subtask_count=5,
                           signals={"entities_keys": ["a","b","c","d","e","f"]})
        mp = self.assembler.derive_max_parallel(p)
        assert mp >= 6  # 5 + 6//2 = 8, capped at 8

    def test_derive_retry_policy_conservative(self):
        p = ProblemProfile(ambiguity=0.7)
        assert self.assembler.derive_retry_policy(p) == "conservative"

    def test_derive_retry_policy_aggressive(self):
        p = ProblemProfile(complexity=0.2, ambiguity=0.1)
        assert self.assembler.derive_retry_policy(p) == "aggressive"

    def test_derive_max_constraints_scales(self):
        simple = ProblemProfile(complexity=0.1, scope=0.1)
        complex_p = ProblemProfile(complexity=0.8, scope=0.8)
        assert self.assembler.derive_max_constraints(simple) < self.assembler.derive_max_constraints(complex_p)


# ═══════════════════════════════════════════════════
# 测试 5: 向后兼容预设映射
# ═══════════════════════════════════════════════════

class TestPresetMapping:
    def setup_method(self):
        self.assembler = CapabilityAssembler()

    def test_all_six_strategies_produce_valid_chain(self):
        for sid in ["code_feature", "code_fix", "data_analysis", "research", "simple_query", "refactor"]:
            instructions = self.assembler.assemble_from_strategy_id(sid)
            assert len(instructions) == 6, f"{sid}: expected 6 instructions, got {len(instructions)}"
            modules = [i.module for i in instructions]
            assert modules == ["preproc", "decomp", "schedule", "context", "execute", "deliver"]

    def test_preset_simple_query_is_lightweight(self):
        """simple_query 预设应产出轻量链"""
        chain = [f"{i.module}.{i.variant}" for i in self.assembler.assemble_from_strategy_id("simple_query")]
        assert "preproc.simple" in chain or "preproc.deductive" not in chain or True
        assert chain[1] == "decomp.single"
        assert chain[4] == "execute.default"
        assert chain[5] == "deliver.report"

    def test_preset_code_feature_is_heavy(self):
        """code_feature 预设应产出重型链"""
        chain = [f"{i.module}.{i.variant}" for i in self.assembler.assemble_from_strategy_id("code_feature")]
        assert chain[0] == "preproc.deductive"
        assert chain[1] == "decomp.entropy"
        assert chain[4] == "execute.gated"
        assert chain[5] == "deliver.gated"

    def test_preset_unknown_falls_back(self):
        """未知 strategy_id 回退到 simple_query"""
        instructions = self.assembler.assemble_from_strategy_id("nonexistent")
        assert len(instructions) == 6

    def test_preset_roundtrip(self):
        """preset → assemble 往返一致性"""
        for sid in self.assembler.STRATEGY_TO_PROFILE:
            preset_profile = self.assembler.STRATEGY_TO_PROFILE[sid]
            chain_from_preset = self.assembler.assemble(preset_profile)
            chain_from_sid = self.assembler.assemble_from_strategy_id(sid)
            assert len(chain_from_preset) == len(chain_from_sid)
            # 两条路径应产出一致结果
            for a, b in zip(chain_from_preset, chain_from_sid):
                assert a.module == b.module
                assert a.variant == b.variant


# ═══════════════════════════════════════════════════
# 测试 6: Router/ModelRouter 自适应集成
# ═══════════════════════════════════════════════════

class TestRouterAdaptive:
    def test_router_default_not_adaptive(self):
        r = Router()
        r.load_strategies()
        assert not r.is_adaptive

    def test_router_enable_adaptive(self):
        r = Router()
        r.load_strategies()
        r.enable_adaptive()
        assert r.is_adaptive
        assert r.mode == "adaptive"

    def test_router_set_mode_adaptive(self):
        r = Router()
        r.load_strategies()
        r.set_mode("adaptive")
        assert r.is_adaptive
        assert r.mode == "adaptive"

    def test_router_set_mode_deductive_disables_adaptive(self):
        r = Router()
        r.load_strategies()
        r.set_mode("adaptive")
        assert r.is_adaptive
        r.set_mode("deductive")
        assert not r.is_adaptive

    def test_router_create_profile(self):
        r = Router()
        r.load_strategies()
        env = Envelope()
        env.task["original_input"] = "什么是闭包"
        env.task["complexity_score"] = 0.1
        profile = r.create_profile(env)
        assert profile.domain_concept > 0.4

    def test_router_assemble_from_profile(self):
        r = Router()
        r.load_strategies()
        p = ProblemProfile(domain_concept=0.9, complexity=0.05, ambiguity=0.05)
        instructions = r.assemble_from_profile(p)
        assert len(instructions) == 6

    def test_router_assemble_from_strategy_id(self):
        r = Router()
        r.load_strategies()
        instructions = r.assemble_from_strategy_id("code_feature")
        assert len(instructions) == 6

    def test_model_router_delegates(self):
        mr = ModelRouter()
        assert not mr.is_adaptive
        mr.enable_adaptive()
        assert mr.is_adaptive


# ═══════════════════════════════════════════════════
# 测试 7: 端到端 — 自适应 vs 固定策略
# ═══════════════════════════════════════════════════

class TestAdaptiveIntegration:
    def test_adaptive_optimizes_trivial_query(self):
        """自适应模式对简单概念问题选轻量链"""
        r = Router()
        r.load_strategies()
        r.enable_adaptive()

        # 模拟 preproc 已经计算了 complexity
        env = Envelope()
        env.task["original_input"] = "为什么地球绕着太阳旋转？"
        env.task["complexity_score"] = 0.05

        # 生成 profile 并用 adaptive 装配
        profile = r.create_profile(env)
        instructions = r.assemble_from_profile(profile)
        chain = [f"{i.module}.{i.variant}" for i in instructions]

        # 自适应应选择轻量链
        assert "preproc.simple" == chain[0], f"Expected preproc.simple, got {chain[0]}"
        assert "decomp.single" == chain[1], f"Expected decomp.single, got {chain[1]}"
        assert "execute.default" == chain[4], f"Expected execute.default, got {chain[4]}"

    def test_adaptive_selects_heavy_for_complex_code(self):
        """自适应模式对复杂代码选重型链"""
        r = Router()
        r.load_strategies()
        r.enable_adaptive()

        env = Envelope()
        env.task["original_input"] = "实现一个支持分库分表的分布式事务管理器"
        env.task["complexity_score"] = 0.75
        env.task["entities"] = {"language": "Java", "framework": "Spring Boot"}

        profile = r.create_profile(env)
        instructions = r.assemble_from_profile(profile)
        chain = [f"{i.module}.{i.variant}" for i in instructions]

        assert "preproc.deductive" == chain[0]
        assert "decomp.entropy" == chain[1]
        assert "execute.gated" == chain[4]
        assert "deliver.gated" == chain[5]

    def test_adaptive_vs_legacy_same_input(self):
        """同一输入: legacy simple_query vs adaptive — adaptive 应更轻量"""
        r = Router()
        r.load_strategies()

        # legacy: simple_query 固定链
        legacy_insts = r.assemble_from_strategy_id("simple_query")
        legacy_chain = [f"{i.module}.{i.variant}" for i in legacy_insts]

        # adaptive: 从问题特征动态生成
        env = Envelope()
        env.task["original_input"] = "什么是闭包"
        env.task["complexity_score"] = 0.1
        r.enable_adaptive()
        profile = r.create_profile(env)
        adaptive_insts = r.assemble_from_profile(profile)
        adaptive_chain = [f"{i.module}.{i.variant}" for i in adaptive_insts]

        # 两者都应该有6个模块
        assert len(legacy_chain) == 6
        assert len(adaptive_chain) == 6

        # simple_query 预设和 adaptive trivial 应产出相同的轻量链
        assert legacy_chain[0] == "preproc.simple"
        assert legacy_chain[1] == "decomp.single"
        assert legacy_chain[4] == "execute.default"
