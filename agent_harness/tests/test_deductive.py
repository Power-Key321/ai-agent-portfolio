"""
碳基演绎法增强模块测试 — 对比经典模式 vs 演绎增强模式。

覆盖:
- T1: 5要素本质压缩准确性
- T2: 概率推断分布合理性
- T3: 熵减链分解（各意图类型的阶段数）
- T4: 8维补全完整度
- T5: 量化门检（4道）正确性
- T6: 退化检测触发条件
- T7: 交付自检（6项）
- T8: 经典 vs 演绎全链路对比 (code_feature)
- T9: 经典 vs 演绎全链路对比 (data_analysis)
- T10: 经典 vs 演绎全链路对比 (code_fix)
- T11: 各意图类型熵减链分解正确性
- T12: 歧义检测和缺失维度标记
- T13: 模式切换稳定性

运行: python -m pytest agent_harness/tests/test_deductive.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════
# Helpers
# ═══════════════════════════════════════

def _mock_model(prompt: str, skeleton_hash: str = "") -> str:
    p = prompt.lower()
    if any(kw in p for kw in ['实现', '开发', '写', '创建', '添加', '做', '搞']):
        return 'code_feature'
    if any(kw in p for kw in ['修复', 'fix', 'bug', '报错', '错误']):
        return 'code_fix'
    if any(kw in p for kw in ['分析', '统计', '数据']):
        return 'data_analysis'
    if any(kw in p for kw in ['搜索', '查找', '找', '调研']):
        return 'research'
    if any(kw in p for kw in ['重构', '整理']):
        return 'refactor'
    return 'simple_query'


# ═══════════════════════════════════════
# T1: 5要素本质压缩
# ═══════════════════════════════════════

def test_five_elements_compression_code_feature():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    fe = engine.compress_to_five_elements(
        "帮我实现一个FastAPI的JWT认证中间件",
        intent_class="code_feature",
    )

    assert fe.subject == "构建者", f"应为构建者，实为 {fe.subject}"
    assert "构建" in fe.action
    assert len(fe.object) > 0  # 应提取到 FastAPI / JWT 等
    assert "→" in fe.value_chain or "设计" in fe.value_chain
    assert fe.sustainability == "有限搜索(N轮收敛)"
    assert fe.completeness >= 0.6  # 至少3/5要素有值


def test_five_elements_compression_code_fix():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    fe = engine.compress_to_five_elements(
        "修复src/auth.py的登录验证空指针bug",
        intent_class="code_fix",
    )

    assert fe.subject == "维护者"
    assert "修复" in fe.action or "诊断" in fe.action
    assert fe.completeness >= 0.6


def test_five_elements_compression_simple_query():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    fe = engine.compress_to_five_elements(
        "什么是闭包",
        intent_class="simple_query",
    )

    assert fe.subject == "解释者"
    assert fe.sustainability == "一次性"


def test_five_elements_compression_data_analysis():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    fe = engine.compress_to_five_elements(
        "分析最近一周销售额的变化和订单量趋势",
        intent_class="data_analysis",
    )

    assert fe.subject == "分析者"
    assert "分析" in fe.action
    assert len(fe.object) > 0


# ═══════════════════════════════════════
# T2: 概率推断
# ═══════════════════════════════════════

def test_probabilistic_inference_clear_signal():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    probs = engine.infer_intent_probabilities("帮我实现用户登录功能")

    assert len(probs) > 0
    top = probs[0]
    assert top["intent"] == "code_feature"
    assert top["probability"] >= 0.4
    assert top["confidence"] in ("high", "medium")


def test_probabilistic_inference_mixed_signals():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    probs = engine.infer_intent_probabilities("分析并修复这个数据错误")

    assert len(probs) >= 2  # 应至少有 code_fix 和 data_analysis
    intents = [p["intent"] for p in probs]
    assert "code_fix" in intents or "data_analysis" in intents


def test_probabilistic_inference_no_signal():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    probs = engine.infer_intent_probabilities("你好")

    # 无明确信号时，simple_query 应占主导
    if probs:
        assert probs[0]["confidence"] in ("low", "medium")


# ═══════════════════════════════════════
# T3: 熵减链分解（各意图类型）
# ═══════════════════════════════════════

def test_entropy_chain_code_feature():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    specs = engine.build_entropy_subtasks(
        "code_feature", "实现JWT认证中间件",
        complexity=0.5,
    )

    assert len(specs) == 5  # 信息源→过滤→处理→产出→验证
    stages = [s.entropy_stage for s in specs]
    assert stages == ["信息源", "过滤层", "处理层", "产出层", "验证层"]

    # 8维补全验证
    for spec in specs:
        assert spec.goal, f"{spec.entropy_stage} 缺目标"
        assert spec.success_criteria, f"{spec.entropy_stage} 缺成功标准"
        assert spec.actions, f"{spec.entropy_stage} 缺动作"
        assert spec.quant_metric_name, f"{spec.entropy_stage} 缺量化指标"
        assert spec.stop_conditions, f"{spec.entropy_stage} 缺停止条件"
        assert spec.risk_prediction, f"{spec.entropy_stage} 缺风险预判"
        assert spec.fallback_strategy, f"{spec.entropy_stage} 缺降级策略"

    # 验证依赖关系正确
    assert specs[1].input_dependencies == ["信息源"]  # 过滤层依赖信息源
    assert specs[2].input_dependencies == ["过滤层"]   # 处理层依赖过滤层
    assert specs[0].input_dependencies == []           # 信息源无依赖


def test_entropy_chain_code_fix():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    specs = engine.build_entropy_subtasks(
        "code_fix", "修复空指针bug",
    )

    assert len(specs) == 4  # 信息源→过滤→处理→验证（bug修复不需要产出层）
    stages = [s.entropy_stage for s in specs]
    assert "信息源" in stages
    assert "验证层" in stages


def test_entropy_chain_simple_query():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    specs = engine.build_entropy_subtasks(
        "simple_query", "什么是闭包",
    )

    assert len(specs) == 2  # 信息源→产出层
    assert specs[0].entropy_stage == "信息源"
    assert specs[1].entropy_stage == "产出层"


def test_entropy_chain_data_analysis():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    specs = engine.build_entropy_subtasks(
        "data_analysis", "分析用户增长趋势",
    )

    assert len(specs) == 5
    # 验证处理层有合理的 token 估算
    processing = [s for s in specs if s.entropy_stage == "处理层"][0]
    assert processing.quant_metric_target > 0


# ═══════════════════════════════════════
# T4: 8维补全完整度
# ═══════════════════════════════════════

def test_eight_dimension_completeness():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    for intent in ["code_feature", "code_fix", "data_analysis",
                    "research", "refactor", "simple_query"]:
        specs = engine.build_entropy_subtasks(intent, f"测试{intent}任务")
        for spec in specs:
            # 每个 spec 的 8 个维度都不应为空
            assert spec.name, f"{intent}/{spec.entropy_stage}: name 为空"
            assert spec.goal, f"{intent}/{spec.entropy_stage}: goal 为空"
            assert spec.success_criteria, f"{intent}/{spec.entropy_stage}: criteria 为空"
            assert spec.quant_metric_name, f"{intent}/{spec.entropy_stage}: metric 为空"
            assert spec.stop_conditions, f"{intent}/{spec.entropy_stage}: stop 为空"
            assert spec.fallback_strategy, f"{intent}/{spec.entropy_stage}: fallback 为空"


# ═══════════════════════════════════════
# T5: 量化门检
# ═══════════════════════════════════════

def test_gate_checks_all_pass():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtask = {"type": "code_gen"}
    result = {"items_found": 5, "changes_made": 3}

    gates = engine.run_gate_checks(subtask, result, round_num=1)

    assert len(gates) == 4
    assert all(g.passed for g in gates)


def test_gate_checks_empty_result():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtask = {"type": "code_gen"}
    result = {}

    gates = engine.run_gate_checks(subtask, result)

    assert len(gates) == 1  # G1 失败后短路
    assert not gates[0].passed
    assert gates[0].degradation


def test_gate_checks_explore_no_new_items():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtask = {"type": "explore"}
    result = {"items_found": 0}

    gates = engine.run_gate_checks(subtask, result)

    # G1/G2/G3 pass (有产出、有数字、可比较), G4 fail (0新增)
    g4 = [g for g in gates if g.gate_name == "G4_新增判定"]
    assert len(g4) > 0
    assert not g4[0].passed


def test_gate_checks_verify_type():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtask = {"type": "verify"}
    result = {"confirmed": 3}

    gates = engine.run_gate_checks(subtask, result)

    g4 = [g for g in gates if g.gate_name == "G4_确认判定"]
    assert len(g4) > 0
    assert g4[0].passed


# ═══════════════════════════════════════
# T6: 退化检测
# ═══════════════════════════════════════

def test_degradation_detection_all_pass():
    from agent_harness.core.deduction_engine import get_deduction_engine, GateResult
    engine = get_deduction_engine()

    gates = [
        GateResult(True, "G1", "ok"),
        GateResult(True, "G2", "ok"),
        GateResult(True, "G3", "ok"),
        GateResult(True, "G4", "ok"),
    ]

    should, reason = engine.detect_degradation(gates, degradation_streak=0)
    assert not should
    assert reason == ""


def test_degradation_detection_all_fail():
    from agent_harness.core.deduction_engine import get_deduction_engine, GateResult
    engine = get_deduction_engine()

    gates = [
        GateResult(False, "G1", "fail", degradation=True),
        GateResult(False, "G2", "fail", degradation=True),
        GateResult(False, "G3", "fail", degradation=True),
        GateResult(False, "G4", "fail", degradation=True),
    ]

    should, reason = engine.detect_degradation(gates, degradation_streak=0)
    assert should
    assert "全部" in reason


def test_degradation_detection_streak_exceeded():
    from agent_harness.core.deduction_engine import get_deduction_engine, GateResult
    engine = get_deduction_engine()

    # 2道门检中1道退化 + streak已达上限 → 触发降级
    gates = [
        GateResult(True, "G1", "ok"),
        GateResult(False, "G4", "no improvement", degradation=True),
    ]

    should, reason = engine.detect_degradation(gates, degradation_streak=3, max_streak=3)
    assert should
    assert "连续3轮" in reason


# ═══════════════════════════════════════
# T7: 交付自检（6项）
# ═══════════════════════════════════════

def test_self_check_all_pass():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtasks = [
        {"id": "s1", "entropy_stage": "信息源", "dependencies": [],
         "stop_conditions": {"max_rounds": 5}, "fallback_strategy": "使用缓存"},
        {"id": "s2", "entropy_stage": "过滤层", "dependencies": ["s1"],
         "stop_conditions": {"max_rounds": 3}, "fallback_strategy": "放宽条件"},
        {"id": "s3", "entropy_stage": "处理层", "dependencies": ["s2"],
         "stop_conditions": {"max_rounds": 10}, "fallback_strategy": "降级处理"},
    ]
    execution_results = [
        {"subtask_id": "s1", "status": "success"},
        {"subtask_id": "s2", "status": "success"},
        {"subtask_id": "s3", "status": "success"},
    ]

    result = engine.run_self_check(subtasks, execution_results, "code_feature", 50000)
    assert result["passed"]
    assert result["estimated_risk"] == "low"
    assert len(result["checks"]) == 6


def test_self_check_missing_dependencies():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtasks = [
        {"id": "s1", "entropy_stage": "信息源", "dependencies": [],
         "stop_conditions": {"max_rounds": 5}},
        {"id": "s2", "entropy_stage": "过滤层", "dependencies": [],  # 缺少依赖!
         "stop_conditions": {"max_rounds": 3}},
    ]
    execution_results = [
        {"subtask_id": "s1", "status": "success"},
        {"subtask_id": "s2", "status": "success"},
    ]

    result = engine.run_self_check(subtasks, execution_results, "code_feature", 30000)
    # 过滤层没有声明依赖信息源 → 自检2应失败
    check2 = [c for c in result["checks"] if "依赖" in c["check"]]
    assert len(check2) > 0


def test_self_check_high_cost_warning():
    from agent_harness.core.deduction_engine import get_deduction_engine
    engine = get_deduction_engine()

    subtasks = [
        {"id": "s1", "entropy_stage": "信息源", "dependencies": [],
         "stop_conditions": {"max_rounds": 10}, "fallback_strategy": "缓存"},
    ]
    execution_results = [{"subtask_id": "s1", "status": "success"}]

    result = engine.run_self_check(subtasks, execution_results, "code_feature", 300000)
    assert len(result["warnings"]) > 0  # 高 token 应触发警告


# ═══════════════════════════════════════
# T8-T10: 经典 vs 演绎 全链路对比
# ═══════════════════════════════════════

def test_classic_vs_deductive_code_feature():
    """对比经典模式 vs 演绎增强模式处理 code_feature。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    # Classic
    adapter_classic = ClaudeCodeAdapter(on_model_call=_mock_model)
    adapter_classic.model_router.set_mode("classic")
    result_c = adapter_classic.start("帮我实现一个JWT认证中间件")

    # Deductive
    adapter_deductive = ClaudeCodeAdapter(on_model_call=_mock_model)
    adapter_deductive.model_router.set_mode("deductive")
    result_d = adapter_deductive.start("帮我实现一个JWT认证中间件")

    # 两者都应正确分类
    assert result_c["intent_class"] == "code_feature"
    assert result_d["intent_class"] == "code_feature"

    # 演绎模式应有更丰富的产出
    # 1. 分解策略不同
    assert result_c["execution_log"][0]["module"] == "preproc.code"
    assert result_d["execution_log"][0]["module"] == "preproc.deductive"

    # 2. 演绎模式有5要素
    # (无法直接从 result 读取，因为 task 内部状态不暴露在顶层)


def test_classic_vs_deductive_data_analysis():
    """对比经典模式 vs 演绎增强模式处理 data_analysis。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter_d = ClaudeCodeAdapter(on_model_call=_mock_model)
    adapter_d.model_router.set_mode("deductive")
    result = adapter_d.start("分析最近一周的用户增长趋势")

    assert result["intent_class"] == "data_analysis"
    exec_log = result["execution_log"]

    # 演绎模式应有 7 个模块：六大层 + 收尾的 deliver.neg_verify
    assert len(exec_log) == 7

    # 验证使用了增强模块
    module_keys = [e["module"] for e in exec_log]
    assert "deliver.neg_verify" in module_keys
    assert "preproc.deductive" in module_keys
    assert "decomp.entropy" in module_keys
    assert "execute.gated" in module_keys
    assert "deliver.gated" in module_keys


def test_classic_vs_deductive_code_fix():
    """对比经典模式 vs 演绎增强模式处理 code_fix。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    adapter.model_router.set_mode("deductive")
    result = adapter.start("修复src/auth.py的登录验证bug")

    assert result["intent_class"] == "code_fix"
    module_keys = [e["module"] for e in result["execution_log"]]

    # code_fix 在演绎模式下也使用熵减链（4阶段）
    assert "decomp.entropy" in module_keys
    # 分解质量记录应存在
    assert result["spiral_iterations"] >= 0


# ═══════════════════════════════════════
# T11: 各意图类型熵减链分解正确性
# ═══════════════════════════════════════

def test_all_strategies_deductive():
    """6种策略类型在演绎模式下均能正确装配和执行。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)

    cases = [
        ("帮我实现登录功能", "code_feature"),
        ("修复src/main.py的空指针bug", "code_fix"),
        ("分析最近的用户增长数据", "data_analysis"),
        ("搜索Python异步编程最佳实践", "research"),
        ("什么是闭包", "simple_query"),
        ("重构用户认证模块的代码结构", "refactor"),
    ]

    for user_input, expected in cases:
        result = adapter.start(user_input)
        assert result["intent_class"] == expected, \
            f"'{user_input}' → {result['intent_class']} (expected {expected})"
        assert result["strategy_id"] == expected

        # 所有增强模块都在装配链中
        module_keys = [e["module"] for e in result["execution_log"]]
        assert "preproc.deductive" in module_keys
        assert "decomp.entropy" in module_keys
        assert "execute.gated" in module_keys
        assert "deliver.gated" in module_keys


# ═══════════════════════════════════════
# T12: 歧义检测和缺失维度标记
# ═══════════════════════════════════════

def test_preproc_deductive_ambiguity_detection():
    from agent_harness.core.envelope import Envelope
    from agent_harness.modules.preproc.deductive import PreprocDeductive

    preproc = PreprocDeductive()

    # 极其模糊的输入（无关键词、无实体、无框架信息）
    envelope = Envelope()
    envelope.intent_class = "code_fix"
    envelope.task["original_input"] = "帮我看看这个东西"

    result = preproc.process(envelope)
    fe = result.envelope.task.get("five_elements", {})

    # 虽然有值（引擎总是尽力推断），但 flags 应标记缺失维度
    flags = result.envelope.task.get("ambiguity_flags", [])
    # 应有歧义标记：至少缺少语言/框架信息
    assert len(flags) > 0, f"预期有歧义标记，实际 flags={flags}"
    assert any("no_lang_or_framework" in f for f in flags), \
        f"应标记缺少语言/框架，实际 flags={flags}"


def test_preproc_deductive_rich_input():
    from agent_harness.core.envelope import Envelope
    from agent_harness.modules.preproc.deductive import PreprocDeductive

    preproc = PreprocDeductive()

    # 详细输入
    envelope = Envelope()
    envelope.intent_class = "code_feature"
    envelope.task["original_input"] = (
        "帮我在src/auth/middleware.py中实现一个FastAPI的JWT认证中间件，"
        "支持HS256算法，过期时间24小时，需要从Authorization header提取token"
    )

    result = preproc.process(envelope)
    fe = result.envelope.task.get("five_elements", {})

    assert fe["completeness"] >= 0.6  # 信息丰富
    entities = result.envelope.task.get("entities", {})
    assert entities.get("language") == "python" or entities.get("framework") == "fastapi"


# ═══════════════════════════════════════
# T13: 模式切换稳定性
# ═══════════════════════════════════════

def test_mode_switching_stability():
    """同一输入在 classic/deductive 模式间切换 3 次，结果应各自一致。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    for mode in ["classic", "deductive"]:
        results = []
        for _ in range(3):
            adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
            adapter.model_router.set_mode(mode)
            r = adapter.start("帮我实现一个简单的TODO应用")
            results.append({
                "intent": r["intent_class"],
                "strategy": r["strategy_id"],
                "route": r["route_method"],
            })

        for key in ["intent", "strategy", "route"]:
            values = [r[key] for r in results]
            assert len(set(values)) == 1, \
                f"[{mode}] {key} 不一致: {values}"


# ═══════════════════════════════════════
# Runner
# ═══════════════════════════════════════

def main():
    import traceback

    tests = [
        test_five_elements_compression_code_feature,
        test_five_elements_compression_code_fix,
        test_five_elements_compression_simple_query,
        test_five_elements_compression_data_analysis,
        test_probabilistic_inference_clear_signal,
        test_probabilistic_inference_mixed_signals,
        test_probabilistic_inference_no_signal,
        test_entropy_chain_code_feature,
        test_entropy_chain_code_fix,
        test_entropy_chain_simple_query,
        test_entropy_chain_data_analysis,
        test_eight_dimension_completeness,
        test_gate_checks_all_pass,
        test_gate_checks_empty_result,
        test_gate_checks_explore_no_new_items,
        test_gate_checks_verify_type,
        test_degradation_detection_all_pass,
        test_degradation_detection_all_fail,
        test_degradation_detection_streak_exceeded,
        test_self_check_all_pass,
        test_self_check_missing_dependencies,
        test_self_check_high_cost_warning,
        test_classic_vs_deductive_code_feature,
        test_classic_vs_deductive_data_analysis,
        test_classic_vs_deductive_code_fix,
        test_all_strategies_deductive,
        test_preproc_deductive_ambiguity_detection,
        test_preproc_deductive_rich_input,
        test_mode_switching_stability,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
            print(f"  PASS {test_fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {test_fn.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"  演绎增强测试: {passed} passed, {failed} failed ({passed + failed} total)")
    print(f"{'='*50}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
