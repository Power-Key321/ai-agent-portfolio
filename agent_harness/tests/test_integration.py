"""
Agent Harness 集成测试 — 端到端贯穿完整链路。

覆盖:
- T1: diagnose 模式（分类 + 装配，不执行）
- T2: code_feature 全链路（六层模块 → 交付 diff）
- T3: simple_query 短路（跳过螺旋直接返回）
- T4: code_fix 链路 + 断路器
- T5: 多轮螺旋收敛

运行: python -m pytest agent_harness/tests/test_integration.py -v
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _mock_model(prompt: str, skeleton_hash: str = "") -> str:
    """模拟 LLM 分类回调 — 按关键词推断意图。"""
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
# T1: Diagnose 模式
# ═══════════════════════════════════════

def test_integration_diagnose():
    """诊断模式：分类 + 装配，不执行螺旋。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    result = adapter.diagnose("帮我实现一个JWT认证中间件")

    assert result["intent"] == "code_feature"
    assert result["strategy"] == "code_feature"
    assert result["model"] == "opus"
    assert result["route"]["method"] == "regex"  # "实现" 命中正则
    assert len(result["assembly"]) == 7  # preproc > decomp > sched > ctx > exec > deliver > deliver.neg_verify
    module_names = [a[0] for a in result["assembly"]]
    assert "preproc" in module_names
    assert "execute" in module_names
    assert "deliver" in module_names


def test_integration_diagnose_simple_query():
    """简单查询应匹配 simple_query 策略。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    result = adapter.diagnose("什么是闭包")

    assert result["intent"] == "simple_query"
    assert result["strategy"] == "simple_query"
    assert result["spiral_config"]["max_iterations"] == 1


# ═══════════════════════════════════════
# T2: Code Feature 全链路
# ═══════════════════════════════════════

def test_integration_code_feature_full_pipeline():
    """端到端：从输入到交付，贯穿六层模块。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    result = adapter.start("帮我实现一个FastAPI health endpoint")

    # 意图正确
    assert result["intent_class"] == "code_feature"
    assert result["strategy_id"] == "code_feature"
    assert result["route_method"] == "regex"

    # 执行了螺旋
    assert result["spiral_iterations"] > 0

    # 执行日志非空，每步有 module 和 success
    exec_log = result["execution_log"]
    assert len(exec_log) > 0
    for entry in exec_log:
        assert "module" in entry
        assert "success" in entry

    # 模块有序执行: preproc → decomp → schedule → context → execute → deliver
    module_order = [e["module"] for e in exec_log if e["success"]]
    assert any("preproc" in m for m in module_order)
    assert any("decomp" in m for m in module_order)
    assert any("schedule" in m for m in module_order)
    assert any("context" in m for m in module_order)
    assert any("execute" in m for m in module_order)
    assert any("deliver" in m for m in module_order)
    # 演绎增强模式下使用了具体的新变体
    assert any("deductive" in m or "entropy" in m or "gated" in m for m in module_order)

    # 收敛摘要非空
    conv = result["convergence"]
    assert len(conv) > 0


# ═══════════════════════════════════════
# T3: Simple Query 短路
# ═══════════════════════════════════════

def test_integration_simple_query_short_circuit():
    """simple_query 应该不进入螺旋循环。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    result = adapter.start("什么是闭包")

    assert result["intent_class"] == "simple_query"
    # simple_query 在循环内通过 break 短路
    assert result["spiral_iterations"] <= 1


# ═══════════════════════════════════════
# T4: Code Fix 链路 + 验证模块输出
# ═══════════════════════════════════════

def test_integration_code_fix_pipeline():
    """code_fix 在演绎模式下使用 decomp.entropy + deliver.gated。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
    result = adapter.start("修复src/auth.py的登录验证bug")

    assert result["intent_class"] == "code_fix"
    assert result["strategy_id"] == "code_fix"

    exec_log = result["execution_log"]
    # 演绎模式: preproc.deductive → decomp.entropy → ... → execute.gated → deliver.gated
    module_keys = [e["module"] for e in exec_log]
    assert any("decomp.entropy" in m for m in module_keys)
    assert any("deliver.gated" in m for m in module_keys)


# ═══════════════════════════════════════
# T5: 多轮螺旋收敛
# ═══════════════════════════════════════

def test_integration_spiral_convergence():
    """验证 refine() 后收敛半径递减（refine 根据反馈信号降低半径）。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter
    from agent_harness.core.envelope import Envelope

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)

    envelope = Envelope()
    envelope.task["original_input"] = "帮我实现一个用户认证系统"
    adapter.model_router.classify(envelope, "帮我实现一个用户认证系统")

    envelope = adapter.refiner.start(envelope)
    assert envelope.convergence_radius == 1.0

    # execute_spiral 第一轮: clarity=0（无用户反馈），半径不变
    envelope = adapter.refiner.execute_spiral(envelope)
    assert envelope.convergence_radius == 1.0

    # refine 收到 accepted → clarity=1.0 → 半径下降
    envelope.feedback["accepted"] = True
    envelope = adapter.refiner.refine(envelope, {"signal": "accepted"})
    assert envelope.convergence_radius < 1.0  # refine 后收敛
    assert envelope.convergence_radius > 0.0


# ═══════════════════════════════════════
# T6: 所有策略类型诊断
# ═══════════════════════════════════════

def test_integration_all_strategies_diagnose():
    """六种策略类型均能正确匹配和装配（演绎增强模式）。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(on_model_call=_mock_model)

    cases = [
        ("帮我实现登录功能", "code_feature", "preproc.deductive", "deliver.gated"),
        ("修复src/main.py的空指针bug", "code_fix", "preproc.deductive", "deliver.gated"),
        ("分析最近的用户增长数据", "data_analysis", "preproc.deductive", "deliver.gated"),
        ("搜索Python异步编程最佳实践", "research", "preproc.deductive", "deliver.gated"),
        ("什么是闭包", "simple_query", "preproc.deductive", "deliver.gated"),
        ("重构用户认证模块的代码结构", "refactor", "preproc.deductive", "deliver.gated"),
    ]

    for user_input, expected_strategy, expected_preproc, expected_deliver in cases:
        result = adapter.diagnose(user_input)
        assert result["strategy"] == expected_strategy, \
            f"输入 '{user_input}' 应匹配 {expected_strategy}，实际 {result['strategy']}"
        assembly = [f"{a[0]}.{a[1]}" for a in result["assembly"]]
        assert expected_preproc in assembly, \
            f"输入 '{user_input}' 装配链应包含 {expected_preproc}，实际 {assembly}"
        assert expected_deliver in assembly, \
            f"输入 '{user_input}' 装配链应包含 {expected_deliver}，实际 {assembly}"


# ═══════════════════════════════════════
# T7: 重复执行稳定性
# ═══════════════════════════════════════

def test_integration_repeatability():
    """同一输入多次执行，结果应稳定一致。"""
    from agent_harness.adapters.claude_code import ClaudeCodeAdapter

    results = []
    for _ in range(3):
        adapter = ClaudeCodeAdapter(on_model_call=_mock_model)
        r = adapter.start("帮我实现一个简单的TODO应用")
        results.append({
            "intent": r["intent_class"],
            "strategy": r["strategy_id"],
            "route": r["route_method"],
        })

    # 三次执行应完全一致
    for key in ["intent", "strategy", "route"]:
        values = [r[key] for r in results]
        assert len(set(values)) == 1, f"{key} 不一致: {values}"


# ═══════════════════════════════════════
# Runner
# ═══════════════════════════════════════

def main():
    import traceback

    tests = [
        test_integration_diagnose,
        test_integration_diagnose_simple_query,
        test_integration_code_feature_full_pipeline,
        test_integration_simple_query_short_circuit,
        test_integration_code_fix_pipeline,
        test_integration_spiral_convergence,
        test_integration_all_strategies_diagnose,
        test_integration_repeatability,
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

    print(f"\n{'='*40}")
    print(f"  集成测试: {passed} passed, {failed} failed ({passed + failed} total)")
    print(f"{'='*40}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
