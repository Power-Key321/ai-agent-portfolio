"""
Agent Harness 单元测试套件。

覆盖:
- Envelope/LazyCache: 创建、工厂方法、缓存语义
- Router._match_intent: 意图匹配准确率
- ModelRouter: 三层路由策略
- SpiralGate: 门控决策
- Convergence: 收敛公式
- Executor: 超时、断路器、失败分类
- HarnessConfig: 加载、校验、环境变量

运行: python -m pytest agent_harness/tests/test_unit.py -v
"""

import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# ═══════════════════════════════════════
# Envelope & LazyCache
# ═══════════════════════════════════════

def test_envelope_creation():
    from agent_harness.core.envelope import Envelope
    env = Envelope()
    assert env.version == "2.0"
    assert env.spiral_iteration == 0
    assert env.convergence_radius == 1.0
    assert env.should_continue_spiral is True


def test_envelope_spawn():
    from agent_harness.core.envelope import Envelope
    parent = Envelope()
    child = parent.spawn("test.module")
    assert child.trace_id == parent.trace_id
    assert child.parent_span_id == parent.span_id
    assert child.context is parent.context  # 共享引用


def test_envelope_spawn_next_spiral():
    from agent_harness.core.envelope import Envelope
    env = Envelope()
    env2 = env.spawn_next_spiral()
    assert env2.spiral_iteration == 1
    assert env2.context is not env.context  # 新 cache
    assert env2.context["refs"] == env.context["refs"]  # refs 保留


def test_lazy_cache_resolve():
    from agent_harness.core.envelope import LazyCache
    call_count = 0

    def resolver(ref):
        nonlocal call_count
        call_count += 1
        return {"data": ref, "token_count": 10}

    cache = LazyCache()
    cache.set_resolver(resolver)
    r1 = cache.resolve("test://a")
    r2 = cache.resolve("test://a")  # 缓存命中
    assert r1 == r2
    assert call_count == 1  # 只调用一次


def test_lazy_cache_clear():
    from agent_harness.core.envelope import LazyCache
    call_count = 0

    def resolver(ref):
        nonlocal call_count
        call_count += 1
        return {"data": ref}

    cache = LazyCache()
    cache.set_resolver(resolver)
    cache.resolve("a")
    cache.clear()
    cache.resolve("a")
    assert call_count == 2  # clear后重新加载


# ═══════════════════════════════════════
# Router._match_intent
# ═══════════════════════════════════════

def test_match_intent_code_feature():
    from agent_harness.core.router import Router
    r = Router()
    r.load_strategies()
    sid, conf = r._match_intent("帮我实现一个JWT认证")
    assert sid == "code_feature"
    assert conf > 0


def test_match_intent_code_fix():
    from agent_harness.core.router import Router
    r = Router()
    r.load_strategies()
    sid, conf = r._match_intent("修复src/auth.py的bug")
    assert sid == "code_fix"


def test_match_intent_simple_query():
    from agent_harness.core.router import Router
    r = Router()
    r.load_strategies()
    sid, conf = r._match_intent("什么是闭包")
    assert sid == "simple_query"


def test_match_intent_no_match():
    from agent_harness.core.router import Router
    r = Router()
    r.load_strategies()
    sid, conf = r._match_intent("xyzzy thud foo bar")
    assert sid == "" or conf == 0.0  # 无匹配


# ═══════════════════════════════════════
# ModelRouter
# ═══════════════════════════════════════

def test_model_router_regex_layer():
    from agent_harness.core.model_router import ModelRouter
    from agent_harness.core.envelope import Envelope
    mr = ModelRouter()
    env = Envelope()
    result = mr.classify(env, "什么是闭包")
    assert result.method == "regex"
    assert result.intent_class == "simple_query"


def test_model_router_model_layer():
    from agent_harness.core.model_router import ModelRouter
    from agent_harness.core.envelope import Envelope
    def cb(prompt, sk_hash):
        return "code_feature"
    mr = ModelRouter(on_model_call=cb)
    env = Envelope()
    result = mr.classify(env, "帮我搞一个不知道什么的系统")
    assert result.method == "model"
    assert result.intent_class == "code_feature"


def test_model_router_learning():
    from agent_harness.core.model_router import ModelRouter
    from agent_harness.core.envelope import Envelope
    def cb(prompt, sk_hash):
        return "code_feature"
    mr = ModelRouter(on_model_call=cb)

    # 第一次: model
    env1 = Envelope()
    r1 = mr.classify(env1, "帮我搞一个用户认证系统")
    assert r1.method == "model"

    # 第二次: learned_regex
    env2 = Envelope()
    r2 = mr.classify(env2, "帮我搞一个用户认证系统")
    assert r2.method == "learned_regex"
    assert r2.tokens_consumed == 0


def test_model_router_delegation():
    from agent_harness.core.model_router import ModelRouter
    from agent_harness.core.envelope import Envelope
    mr = ModelRouter()
    env = Envelope()
    mr.classify(env, "帮我实现登录功能")
    strategy = mr.match(env)
    assert strategy.strategy_id == "code_feature"
    instructions = mr.assemble(strategy)
    # 六大层 + 收尾的 deliver.neg_verify（否定结论外部对照，对所有策略自动追加）
    assert len(instructions) == 7
    assert (instructions[-1].module, instructions[-1].variant) == ("deliver", "neg_verify")


# ═══════════════════════════════════════
# SpiralGate
# ═══════════════════════════════════════

def test_spiral_gate_simple_query():
    from agent_harness.core.spiral_gate import SpiralGate
    from agent_harness.core.envelope import Envelope
    gate = SpiralGate()
    env = Envelope()
    env.strategy_id = "simple_query"
    a = gate.assess(env)
    assert a["skip_spiral"] is True
    assert a["recommended_iterations"] == 1


def test_spiral_gate_low_complexity():
    from agent_harness.core.spiral_gate import SpiralGate
    from agent_harness.core.envelope import Envelope
    gate = SpiralGate()
    env = Envelope()
    env.strategy_id = "code_feature"
    env.task["complexity_score"] = 0.20
    env.task["entities"] = {"language": ["python"], "framework": ["fastapi"]}
    a = gate.assess(env)
    assert a["recommended_iterations"] < a["original_max"]


def test_spiral_gate_high_complexity():
    from agent_harness.core.spiral_gate import SpiralGate
    from agent_harness.core.envelope import Envelope
    gate = SpiralGate()
    env = Envelope()
    env.strategy_id = "code_feature"
    env.task["complexity_score"] = 0.70
    env.task["ambiguity_flags"] = ["no_lang", "very_short"]
    a = gate.assess(env)
    assert a["recommended_iterations"] >= a["original_max"] - 1


# ═══════════════════════════════════════
# Convergence
# ═══════════════════════════════════════

def test_convergence_radius_formula():
    from agent_harness.core.convergence import compute_convergence_radius
    # 添加约束后半径应缩小
    r = compute_convergence_radius(1.0, 3, "code_feature", 1.0)
    assert r < 1.0
    assert r > 0.0


def test_convergence_speed():
    from agent_harness.core.convergence import compute_convergence_speed
    c = compute_convergence_speed(1.0, 0.1, 3)
    assert c == 0.3


def test_convergence_tracker():
    from agent_harness.core.convergence import ConvergenceTracker
    ct = ConvergenceTracker(strategy_id="code_feature")
    ct.record_iteration(constraints_added=2, user_feedback_clarity=1.0)
    ct.record_iteration(constraints_added=1, user_feedback_clarity=0.5)
    c = ct.finalize()
    assert c > 0
    assert ct.r_current < ct.r_initial


# ═══════════════════════════════════════
# Executor
# ═══════════════════════════════════════

def test_executor_failure_classification():
    from agent_harness.modules.execute.executor import classify_failure
    assert classify_failure("file not found: foo.py") == "model_hallucination"
    assert classify_failure("request timed out after 30s") == "timeout"
    assert classify_failure("context window exceeded") == "context_overflow"
    assert classify_failure("permission denied") == "dependency_fail"
    assert classify_failure("ambiguous request") == "ambiguous_intent"
    assert classify_failure("some random error") == "tool_error"


def test_circuit_breaker():
    from agent_harness.modules.execute.executor import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    assert cb.is_open is False
    cb.failure()
    cb.failure()
    assert cb.is_open is False
    cb.failure()
    assert cb.is_open is True


def test_circuit_breaker_reset():
    from agent_harness.modules.execute.executor import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=2, reset_seconds=0.01)
    cb.failure()
    cb.failure()
    assert cb.is_open is True
    time.sleep(0.05)  # 超过冷却期
    assert cb.state == "HALF_OPEN"
    cb.success()
    assert cb.is_open is False


def test_executor_timeout():
    from agent_harness.modules.execute.executor import Executor
    from agent_harness.core.envelope import Envelope
    from agent_harness.modules.base import ModuleResult

    def slow_execute(envelope, subtask):
        time.sleep(0.5)
        return ModuleResult(envelope=envelope)

    executor = Executor(on_execute=slow_execute, timeout_ms=100)
    env = Envelope()
    env.task["subtasks"] = [{"id": "s1", "dependencies": []}]
    env.task["execution_plan"] = {
        "batches": [{"batch_id": "b1", "subtask_ids": ["s1"], "timeout_ms": 100}],
    }
    result = executor.process(env)
    assert not result.success
    assert result.failure_class == "timeout"


def test_executor_default_execute():
    from agent_harness.modules.execute.executor import Executor
    from agent_harness.core.envelope import Envelope
    executor = Executor()
    env = Envelope()
    env.task["subtasks"] = [{"id": "s1", "type": "code_gen", "dependencies": [], "description": "test task"}]
    env.task["execution_plan"] = {
        "batches": [{"batch_id": "b1", "subtask_ids": ["s1"]}],
    }
    result = executor.process(env)
    assert result.success
    artifacts = env.task.get("execution_results", [])
    assert len(artifacts) == 1
    assert artifacts[0]["subtask_id"] == "s1"


# ═══════════════════════════════════════
# HarnessConfig
# ═══════════════════════════════════════

def test_config_defaults():
    from agent_harness.core.config import HarnessConfig
    config = HarnessConfig()
    config.load()
    assert config.get("spiral.convergence_threshold") == 0.05
    assert config.get("executor.timeout_ms") == 60000
    assert config.valid


def test_config_env_override(monkeypatch=None):
    from agent_harness.core.config import HarnessConfig
    os.environ["HARNESS_SPIRAL_MAX_ITER"] = "10"
    os.environ["HARNESS_EXEC_TIMEOUT_MS"] = "30000"
    config = HarnessConfig()
    config.load()
    assert config.get("spiral.max_iterations") == 10
    assert config.get("executor.timeout_ms") == 30000
    # cleanup
    del os.environ["HARNESS_SPIRAL_MAX_ITER"]
    del os.environ["HARNESS_EXEC_TIMEOUT_MS"]


def test_config_json_file():
    from agent_harness.core.config import HarnessConfig
    with TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "harness_config.json"
        config_file.write_text(json.dumps({
            "spiral": {"max_iterations": 8},
            "router": {"regex_confidence_threshold": 0.50},
        }), encoding="utf-8")
        config = HarnessConfig(config_path=config_file)
        config.load()
        assert config.get("spiral.max_iterations") == 8
        assert config.get("router.regex_confidence_threshold") == 0.50
        # 未覆盖的保持默认
        assert config.get("spiral.convergence_threshold") == 0.05


def test_config_validation():
    from agent_harness.core.config import HarnessConfig
    with TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "harness_config.json"
        config_file.write_text(json.dumps({
            "spiral": {"max_iterations": "not_a_number"},
        }), encoding="utf-8")
        config = HarnessConfig(config_path=config_file)
        config.load()
        # 类型校验应捕获此问题
        assert len(config.errors) >= 1 or not config.valid


# ═══════════════════════════════════════
# PromptBuilder
# ═══════════════════════════════════════

def test_prompt_builder_skeleton():
    from agent_harness.core.prompt_builder import PromptBuilder
    pb = PromptBuilder()
    skeleton, sk_hash = pb.get_skeleton()
    assert len(skeleton) > 500
    assert len(sk_hash) == 16
    assert pb._skeleton_tokens > 100


def test_prompt_builder_cache_behavior():
    from agent_harness.core.prompt_builder import PromptBuilder
    pb = PromptBuilder()
    # 第一次: write
    d1 = pb.build(user_input="test1", task_type="classify")
    assert d1["estimated_cache_behavior"] == "write"
    # 第二次: hit
    d2 = pb.build(user_input="test2", task_type="classify")
    assert d2["estimated_cache_behavior"] == "hit"
    assert pb.metrics.hit_rate > 0


# ═══════════════════════════════════════
# Logging
# ═══════════════════════════════════════

def test_logger_creation():
    from agent_harness.core.logging_setup import get_logger
    logger = get_logger("test")
    assert logger.name == "test"
    logger.info("test_message", key="value")
    logger.debug("debug_message")
    logger.warning("warning_message", trace_id="abc")


def test_logger_trace_context():
    from agent_harness.core.logging_setup import set_trace_id, get_trace_id
    set_trace_id("test-trace-123")
    assert get_trace_id() == "test-trace-123"
    set_trace_id("")  # reset


# ═══════════════════════════════════════
# Dynamic Strategy
# ═══════════════════════════════════════

def test_dynamic_strategy_model_selection():
    from agent_harness.core.dynamic_strategy import adjust_strategy, _select_model
    # 高复杂度 → 升到 opus
    assert _select_model("code_feature", "opus", 0.7, 3) == "opus"
    # haiku + 高复杂度 → 升到 sonnet
    assert _select_model("research", "haiku", 0.7, 3) == "sonnet"
    # 低复杂度 + opus → 降到 sonnet
    assert _select_model("code_feature", "opus", 0.2, 0) == "sonnet"


def test_dynamic_strategy_adjust_iterations():
    from agent_harness.core.dynamic_strategy import _adjust_iterations
    # 低复杂度减少轮次
    assert _adjust_iterations(5, 0.2, [], {}, 100) < 5
    # 多歧义不减少
    assert _adjust_iterations(5, 0.3, ["a", "b", "c"], {}, 15) >= 5


def test_dynamic_strategy_full():
    from agent_harness.core.dynamic_strategy import adjust_strategy
    from agent_harness.core.envelope import Envelope
    env = Envelope()
    env.strategy_id = "code_feature"
    env.task["complexity_score"] = 0.85
    env.task["ambiguity_flags"] = ["no_lang", "very_short", "no_file"]
    env.task["entities"] = {}
    env.task["original_input"] = "帮我搞"
    env.task["constraints"] = {}
    env = adjust_strategy(env)
    # 高复杂度应保持高螺旋数
    assert env.spiral_max_iterations >= 4
    assert "max_parallel_subtasks" in env.task


# ═══════════════════════════════════════
# ScheduleParallel
# ═══════════════════════════════════════

def test_schedule_parallel():
    from agent_harness.modules.schedule.parallel import ScheduleParallel
    from agent_harness.core.envelope import Envelope
    sp = ScheduleParallel()
    env = Envelope()
    env.task["max_parallel_subtasks"] = 4
    env.task["subtasks"] = [
        {"id": "s1", "description": "独立任务1", "estimated_tokens": 5000, "dependencies": []},
        {"id": "s2", "description": "独立任务2", "estimated_tokens": 5000, "dependencies": []},
        {"id": "s3", "description": "依赖s1", "estimated_tokens": 5000, "dependencies": ["s1"]},
        {"id": "s4", "description": "依赖s1,s2", "estimated_tokens": 5000, "dependencies": ["s1", "s2"]},
    ]
    result = sp.process(env)
    assert result.success
    plan = env.task["execution_plan"]
    assert plan["strategy"] == "parallel"
    # s1+s2 可并行 → 归为同一批次
    first_batch = plan["batches"][0]
    assert "s1" in first_batch["subtask_ids"]
    assert "s2" in first_batch["subtask_ids"]
    assert first_batch["parallel"] is True


# ═══════════════════════════════════════
# LayeredContext
# ═══════════════════════════════════════

def test_layered_context_prefix():
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext(
        system_prompt="You are a helpful assistant.",
        tool_specs='{"read_file": "read a file"}',
        rules="Be concise.",
    )
    assert len(mem.prefix) > 0
    assert len(mem.prefix_hash) == 16
    assert mem.prefix_tokens > 0


def test_layered_context_prefix_immutable():
    """前缀 hash 在整个 session 中不变"""
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext(system_prompt="Test system prompt")
    h1 = mem.prefix_hash
    mem.append_assistant("some response")
    mem.append_tool_result("read_file", "file content")
    assert mem.prefix_hash == h1


def test_layered_context_append():
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext()
    mem.append_assistant("Hello, I will help you.")
    assert mem.log_entry_count == 1
    mem.append_tool_result("read_file", "file content here")
    assert mem.log_entry_count == 2
    assert mem.log_tokens > 0


def test_layered_context_tool_result_truncation():
    """超过 3000 字符的 tool result 自动截断"""
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext()
    long_result = "x" * 5000
    mem.append_tool_result("read_file", long_result)
    entry = mem._log_entries[-1]
    assert len(entry["content"]) < 5000
    assert entry["original_length"] == 5000


def test_layered_context_assemble():
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext(system_prompt="Test prompt")
    result = mem.assemble("Hello world")
    assert "prompt" in result
    assert "prefix_hash" in result
    assert "total_tokens" in result
    assert "cacheable_prefix_tokens" in result
    assert result["prefix_hash"] == mem.prefix_hash
    assert "Hello world" in result["prompt"]


def test_layered_context_distill():
    """distill 只提取计划/决策/约束/结论/下一步"""
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext()
    mem.scratch["plan"] = "Step 1: read file"
    mem.scratch["decision"] = "use haiku model"
    mem.scratch["constraint"] = "budget < $0.10"
    mem.scratch["temp_notes"] = "ignore this"  # 不应被蒸馏
    mem.scratch["random_draft"] = "blah blah"  # 不应被蒸馏
    distilled = mem.distill()
    assert "plan" in distilled
    assert "decision" in distilled
    assert "constraint" in distilled
    assert "temp_notes" not in distilled
    assert "random_draft" not in distilled


def test_layered_context_scratch_reset():
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext()
    mem.scratch["plan"] = "do something"
    assert len(mem.scratch) > 0
    mem.reset_scratch()
    assert len(mem.scratch) == 0
    assert mem.total_turns == 1


def test_layered_context_get_stats():
    from agent_harness.core.layered_context import LayeredContext
    mem = LayeredContext(system_prompt="Test")
    stats = mem.get_stats()
    assert "prefix_tokens" in stats
    assert "prefix_hash" in stats
    assert "log_entries" in stats
    assert stats["log_entries"] == 0


# ═══════════════════════════════════════
# Recovery: Recall
# ═══════════════════════════════════════

def test_recall_json_tool_calls():
    from agent_harness.modules.recovery.recall import recall_tool_calls
    text = 'I will read the file. {"name": "read_file", "arguments": {"path": "/tmp/test.txt"}}'
    found = recall_tool_calls(text)
    assert len(found) >= 1
    assert found[0]["tool_name"] == "read_file"
    assert found[0]["arguments"]["path"] == "/tmp/test.txt"


def test_recall_from_reasoning_content():
    from agent_harness.modules.recovery.recall import recall_tool_calls
    reasoning = 'I need to write code. {"name": "write_file", "arguments": {"path": "x.py", "content": "print(1)"}}'
    response = "Let me write that file for you."
    found = recall_tool_calls(response, reasoning_content=reasoning)
    assert len(found) >= 1
    assert found[0]["tool_name"] == "write_file"


def test_recall_with_known_tools_filter():
    from agent_harness.modules.recovery.recall import recall_tool_calls
    # 注意：regex 中的 .+? 要求 arguments 至少有 1 个字符，空 {} 不匹配
    text = '{"name": "unknown_tool_xyz", "arguments": {"key": "val"}}'
    found = recall_tool_calls(text, known_tools={"read_file", "write_file"})
    assert len(found) == 0
    found2 = recall_tool_calls(text)
    assert len(found2) >= 1  # 无过滤时允许


def test_recall_func_call_pattern():
    from agent_harness.modules.recovery.recall import recall_tool_calls
    text = "I will call read_file(/path/to/file)"
    found = recall_tool_calls(text)
    assert any(f["tool_name"] == "read_file" for f in found)


def test_recall_code_block_json():
    from agent_harness.modules.recovery.recall import recall_tool_calls
    text = '```json\n{"name": "search", "arguments": {"query": "test"}}\n```'
    found = recall_tool_calls(text)
    assert len(found) >= 1
    assert found[0]["tool_name"] == "search"


def test_has_missing_calls():
    from agent_harness.modules.recovery.recall import has_missing_calls
    # 模型说要做某事但没有 JSON tool-call → 应检测到遗漏
    text = "我需要调用 read_file 来读取配置文件。"
    assert has_missing_calls(text) is True
    # 没有意图声明 → 不应检测到遗漏
    text2 = "The configuration is loaded successfully."
    assert has_missing_calls(text2) is False


# ═══════════════════════════════════════
# Recovery: Mend
# ═══════════════════════════════════════

def test_detect_broken_json():
    from agent_harness.modules.recovery.mend import detect_broken_json
    # 不完整的 JSON
    assert detect_broken_json('{"name": "test", "args": {"key"') is True
    # 完整的 JSON
    assert detect_broken_json('{"name": "test", "args": {"key": "val"}}') is False
    # 无 JSON
    assert detect_broken_json("plain text") is False


def test_mend_json_brackets():
    from agent_harness.modules.recovery.mend import mend_json
    # 截断在值之后、闭合括号之前，确保字符串完整且 JSON 可验证
    truncated = '{"tool": "read_file", "args": {"path": "/tmp/data.txt"'
    repaired = mend_json(truncated)
    assert repaired != truncated
    assert repaired.endswith("}")


def test_mend_json_already_valid():
    from agent_harness.modules.recovery.mend import mend_json
    valid = '{"name": "test"}'
    assert mend_json(valid) == valid


# ═══════════════════════════════════════
# Recovery: Fold
# ═══════════════════════════════════════

def test_fold_schema():
    from agent_harness.modules.recovery.fold import fold_schema
    schema = {
        "user": {"name": str, "address": {"city": str, "zip": int}},
        "action": str,
    }
    flat = fold_schema(schema)
    assert "user.name" in flat
    assert "user.address.city" in flat
    assert "user.address.zip" in flat
    assert "action" in flat


def test_unfold_arguments():
    from agent_harness.modules.recovery.fold import unfold_arguments
    flat = {"user.name": "Alice", "user.address.city": "NYC", "user.address.zip": 10001}
    nested = unfold_arguments(flat)
    assert nested["user"]["name"] == "Alice"
    assert nested["user"]["address"]["city"] == "NYC"
    assert nested["user"]["address"]["zip"] == 10001


def test_fold_roundtrip():
    from agent_harness.modules.recovery.fold import fold_schema, unfold_arguments
    schema = {
        "config": {"timeout": int, "retries": int, "url": str},
    }
    flat = fold_schema(schema)
    assert "config.timeout" in flat
    nested = unfold_arguments({"config.timeout": 30, "config.retries": 3, "config.url": "http://x"})
    assert nested == {"config": {"timeout": 30, "retries": 3, "url": "http://x"}}


def test_should_fold():
    from agent_harness.modules.recovery.fold import should_fold
    deep_schema = {"a": {"b": {"c": {"d": int}}}}  # depth 4 > 2
    assert should_fold(deep_schema, max_depth=2) is True
    shallow = {"a": str, "b": int}
    assert should_fold(shallow) is False


# ═══════════════════════════════════════
# Recovery: Guard
# ═══════════════════════════════════════

def test_loop_guard_normal():
    from agent_harness.modules.recovery.guard import LoopGuard
    sd = LoopGuard(window_size=10, repeat_threshold=3)
    # 不同参数 → 不触发
    for i in range(5):
        r = sd.check("read_file", {"path": f"/tmp/file_{i}.txt"})
        assert r["loop_detected"] is False


def test_loop_guard_repeat():
    from agent_harness.modules.recovery.guard import LoopGuard
    sd = LoopGuard(window_size=10, repeat_threshold=3)
    r = None
    for _ in range(3):
        r = sd.check("read_file", {"path": "/tmp/same.txt"})
    assert r["loop_detected"] is True
    assert r["action"] == "reflect"


def test_loop_guard_suppress():
    from agent_harness.modules.recovery.guard import LoopGuard
    sd = LoopGuard(window_size=10, repeat_threshold=2, suppress_seconds=0.5)
    for _ in range(2):
        sd.check("read_file", {"path": "/tmp/x.txt"})
    # 第三次 → 抑制
    r = sd.check("read_file", {"path": "/tmp/x.txt"})
    assert r["loop_detected"] is True
    assert r["action"] == "suppress"


def test_loop_signature_consistency():
    """相同参数生成相同签名"""
    from agent_harness.modules.recovery.guard import LoopGuard
    sig1 = LoopGuard._signature("read_file", {"path": "/a", "mode": "r"})
    sig2 = LoopGuard._signature("read_file", {"mode": "r", "path": "/a"})  # 不同顺序
    assert sig1 == sig2


def test_detect_loop():
    from agent_harness.modules.recovery.guard import detect_loop
    # 重复内容
    repeated = ["x" * 100 + "unique_tail_a"] * 5
    assert detect_loop(repeated, pattern_threshold=4) is True
    # 不同内容 — 每个条目尾部 200 字符完全不同
    varied = [
        "A" * 250 + "END_UNIQUE_SEQUENCE_ZERO",
        "B" * 250 + "END_UNIQUE_SEQUENCE_ONE",
        "C" * 250 + "END_UNIQUE_SEQUENCE_TWO",
        "D" * 250 + "END_UNIQUE_SEQUENCE_THREE",
        "E" * 250 + "END_UNIQUE_SEQUENCE_FOUR",
    ]
    assert detect_loop(varied, pattern_threshold=4) is False
    # 太短
    assert detect_loop(["hi", "hi", "hi", "hi"], pattern_threshold=4) is False


# ═══════════════════════════════════════
# Recovery: Cascade
# ═══════════════════════════════════════

def test_recovery_cascade_recall():
    from agent_harness.modules.recovery.cascade import RecoveryCascade
    pipeline = RecoveryCascade(
        known_tools={"read_file", "write_file"},
        enable_mend=False,
        enable_guard=False,
    )
    # reasoning_content 中有 tool-call JSON，但 response_text 中没有 → recall 捞回
    result = pipeline.recover(
        response_text='I will read the config file now.',
        reasoning_content='I should use this tool: {"name": "read_file", "arguments": {"path": "/etc/config.json"}}',
    )
    assert "recall" in result["recoveries_applied"]


def test_recovery_cascade_mend():
    from agent_harness.modules.recovery.cascade import RecoveryCascade
    pipeline = RecoveryCascade(
        known_tools=set(),
        enable_recall=False,
        enable_guard=False,
    )
    # 纯大括号截断（不含[]，修复器只处理大括号）
    result = pipeline.recover(
        response_text='{"data": {"key1": "val1", "key2": {"nested_key": "nested_val"',
    )
    assert "mend" in result["recoveries_applied"]
    assert result["mend_applied"] is True


def test_recovery_cascade_guard():
    from agent_harness.modules.recovery.cascade import RecoveryCascade
    pipeline = RecoveryCascade(
        known_tools=set(),
        enable_recall=False,
        enable_mend=False,
        guard_window=5,
        guard_threshold=2,
    )
    # 同一工具多次调用触发 storm
    result = None
    for _ in range(3):
        result = pipeline.recover(
            response_text="ok",
            tool_name="read_file",
            tool_args={"path": "/tmp/repeat.txt"},
        )
    assert result is not None
    assert any("guard" in a for a in result["recoveries_applied"])


def test_recovery_cascade_no_recovery_needed():
    from agent_harness.modules.recovery.cascade import RecoveryCascade
    pipeline = RecoveryCascade(known_tools={"read_file"})
    result = pipeline.recover(
        response_text='{"status": "ok"}',
        tool_name="read_file",
        tool_args={"path": "/tmp/unique.txt"},
    )
    assert result["recovered"] is False


def test_recovery_cascade_stats():
    from agent_harness.modules.recovery.cascade import RecoveryCascade
    pipeline = RecoveryCascade(known_tools=set(), enable_recall=False, enable_mend=False)
    # 无 loop_guard，所以 guard 永远不触发
    pipeline._recovery_log.append({"recoveries_applied": [], "recalled_count": 0})
    pipeline._recovery_log.append({"recoveries_applied": ["mend"], "recalled_count": 0})
    stats = pipeline.get_stats()
    assert stats["total_recoveries"] == 2
    assert stats["mend"] == 1
    assert stats["recall"] == 0


# ═══════════════════════════════════════
# Sentinel
# ═══════════════════════════════════════

def test_sentinel_readonly_always_allowed():
    from agent_harness.core.sentinel import Sentinel
    gate = Sentinel(mode="strict")
    assert gate.check("read_file", {"path": "/tmp/test.txt"}).allowed is True
    assert gate.check("web_search", {"query": "test"}).allowed is True


def test_sentinel_strict_mode_blocks_writes():
    from agent_harness.core.sentinel import Sentinel
    gate = Sentinel(mode="strict")
    result = gate.check("write_file", {"path": "/tmp/test.txt"})
    assert result.allowed is False
    assert "strict" in result.reason.lower()


def test_sentinel_headless_auto_approves():
    from agent_harness.core.sentinel import Sentinel
    import os
    gate = Sentinel(mode="headless", allowed_dirs=[os.getcwd(), "/tmp"])
    result = gate.check("write_file", {"path": "/tmp/test.txt"})
    assert result.allowed is True


def test_sentinel_path_traversal_blocked():
    from agent_harness.core.sentinel import Sentinel
    import os
    gate = Sentinel(mode="headless", allowed_dirs=[os.getcwd()])
    # 写入系统路径应被阻止
    result = gate.check("write_file", {"path": "C:/Windows/System32/test.dll"})
    assert result.allowed is False
    assert "超出" in result.reason or "not allowed" in result.reason.lower()


def test_sentinel_blocked_commands():
    from agent_harness.core.sentinel import Sentinel
    gate = Sentinel(mode="headless")
    result = gate.check("run_command", {"command": "rm -rf /"})
    assert result.allowed is False
    assert "阻止" in result.reason or "blocked" in result.reason.lower()


def test_sentinel_safe_command_allowed():
    from agent_harness.core.sentinel import Sentinel
    gate = Sentinel(mode="headless")
    result = gate.check("run_command", {"command": "ls -la"})
    assert result.allowed is True


def test_sentinel_stats():
    from agent_harness.core.sentinel import Sentinel
    gate = Sentinel(mode="headless")
    gate.check("read_file", {})
    gate.check("write_file", {"path": "good.txt"})
    gate.check("write_file", {"path": "/etc/shadow"})
    stats = gate.get_stats()
    assert stats["total_checks"] == 3
    assert stats["allowed"] == 2
    assert stats["blocked"] == 1


# ═══════════════════════════════════════
# CostDashboard
# ═══════════════════════════════════════

def test_cost_dashboard_record_call():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard()
    cost = dash.record_call(model="opus", tokens_in=10000, tokens_out=1000)
    assert cost > 0
    assert dash.total_input_tokens == 10000
    assert dash.total_output_tokens == 1000
    assert dash.model_calls["opus"] == 1


def test_cost_dashboard_cache_hit_pricing():
    """cache hit 价格远低于普通 input"""
    from agent_harness.core.cost_dashboard import CostDashboard
    dash1 = CostDashboard()
    cost_normal = dash1.record_call(model="opus", tokens_in=100000, tokens_out=0, cache_hit=False)
    dash2 = CostDashboard()
    cost_cache = dash2.record_call(model="opus", tokens_in=100000, tokens_out=0, cache_hit=True)
    assert cost_cache < cost_normal  # cache hit ~10% of normal price
    assert dash2.total_cache_hit_tokens == 100000


def test_cost_dashboard_cache_write():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard()
    dash.record_call(model="opus", tokens_in=100000, tokens_out=0, cache_write=True)
    assert dash.total_cache_write_tokens == 100000


def test_cost_dashboard_end_turn():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard()
    dash.record_call(model="sonnet", tokens_in=5000, tokens_out=500)
    summary = dash.end_turn()
    assert summary["turn"] == 1
    assert "cost" in summary
    assert "cost_color" in summary
    assert dash.turn_input_tokens == 0  # 本轮重置
    assert dash.turn_cost == 0.0


def test_cost_dashboard_multiple_turns():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard()
    dash.record_call(model="haiku", tokens_in=1000, tokens_out=200)
    dash.end_turn()
    dash.record_call(model="sonnet", tokens_in=2000, tokens_out=800)
    dash.end_turn()
    assert len(dash.turn_history) == 2
    assert dash.total_cost > 0


def test_cost_dashboard_report():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard(session_budget=10.0)
    dash.record_call(model="opus", tokens_in=50000, tokens_out=10000)
    dash.record_call(model="haiku", tokens_in=1000, tokens_out=100)
    report = dash.report()
    assert "Cost Dashboard" in report
    assert "Session Cost" in report
    assert "Cache Hit Rate" in report
    assert "opus" in report
    assert "haiku" in report


def test_cost_dashboard_summary():
    from agent_harness.core.cost_dashboard import CostDashboard
    dash = CostDashboard()
    dash.record_call(model="sonnet", tokens_in=3000, tokens_out=500)
    dash.end_turn()
    s = dash.summary()
    assert "session_cost" in s
    assert "budget_percent" in s
    assert "cache_hit_rate" in s
    assert "model_breakdown" in s
    assert s["turns"] == 1


def test_cost_dashboard_color_thresholds():
    from agent_harness.core.cost_dashboard import CostDashboard
    assert CostDashboard._color_for(0.01) == "green"
    assert CostDashboard._color_for(0.10) == "yellow"
    assert CostDashboard._color_for(0.50) == "red"


def test_cost_dashboard_token_format():
    from agent_harness.core.cost_dashboard import CostDashboard
    assert CostDashboard._format_tokens(500) == "500"
    assert "K" in CostDashboard._format_tokens(5000)
    assert "M" in CostDashboard._format_tokens(2000000)


# ═══════════════════════════════════════
# Flash-First Model Selection
# ═══════════════════════════════════════

def test_select_model_for_task_aux_call():
    from agent_harness.core.dynamic_strategy import select_model_for_task
    # 辅助调用强制使用 haiku
    model = select_model_for_task("code_feature", 0.8, 3, is_aux_call=True)
    assert model == "haiku"


def test_select_model_for_task_user_override():
    from agent_harness.core.dynamic_strategy import select_model_for_task
    model = select_model_for_task("simple_query", 0.1, 0, user_requested_model="opus")
    assert model == "opus"


def test_select_model_for_task_failure_upgrade():
    from agent_harness.core.dynamic_strategy import select_model_for_task
    # 3 次失败 → 升级到 opus
    assert select_model_for_task("simple_query", 0.1, 0, previous_failures=3) == "opus"
    # 2 次失败 → 升级到 sonnet
    assert select_model_for_task("simple_query", 0.1, 0, previous_failures=2) == "sonnet"


def test_detect_auto_upgrade_trigger():
    from agent_harness.core.dynamic_strategy import detect_auto_upgrade
    assert detect_auto_upgrade("<<<NEEDS_PRO>>>") is True
    assert detect_auto_upgrade("<<<NEEDS_OPUS>>>") is True
    assert detect_auto_upgrade("此任务需要更强大的模型") is True
    assert detect_auto_upgrade("this task requires a more capable model") is True
    assert detect_auto_upgrade("everything looks good here") is False


# ═══════════════════════════════════════
# AdapterBase
# ═══════════════════════════════════════

def test_adapter_base_protocol():
    from agent_harness.adapters.base import AdapterBase
    from agent_harness.modules.base import ModuleBase, ModuleResult
    from agent_harness.core.envelope import Envelope

    class TestAdapter(AdapterBase):
        adapter_name = "test"
        def _register_modules(self):
            return []
        def _resolve_model_call(self, prompt, sk_hash):
            return "simple_query"

    adapter = TestAdapter()
    result = adapter.diagnose("什么是闭包")
    assert "intent" in result
    assert "strategy" in result
    assert "assembly" in result


# ═══════════════════════════════════════
# Main runner
# ═══════════════════════════════════════

def main():
    import traceback

    tests = [
        # Envelope
        test_envelope_creation,
        test_envelope_spawn,
        test_envelope_spawn_next_spiral,
        test_lazy_cache_resolve,
        test_lazy_cache_clear,
        # Router
        test_match_intent_code_feature,
        test_match_intent_code_fix,
        test_match_intent_simple_query,
        test_match_intent_no_match,
        # ModelRouter
        test_model_router_regex_layer,
        test_model_router_model_layer,
        test_model_router_learning,
        test_model_router_delegation,
        # SpiralGate
        test_spiral_gate_simple_query,
        test_spiral_gate_low_complexity,
        test_spiral_gate_high_complexity,
        # Convergence
        test_convergence_radius_formula,
        test_convergence_speed,
        test_convergence_tracker,
        # Executor
        test_executor_failure_classification,
        test_circuit_breaker,
        test_circuit_breaker_reset,
        test_executor_timeout,
        test_executor_default_execute,
        # Config
        test_config_defaults,
        test_config_json_file,
        test_config_validation,
        # PromptBuilder
        test_prompt_builder_skeleton,
        test_prompt_builder_cache_behavior,
        # Logging
        test_logger_creation,
        test_logger_trace_context,
        # Dynamic Strategy
        test_dynamic_strategy_model_selection,
        test_dynamic_strategy_adjust_iterations,
        test_dynamic_strategy_full,
        # ScheduleParallel
        test_schedule_parallel,
        # LayeredContext
        test_layered_context_prefix,
        test_layered_context_prefix_immutable,
        test_layered_context_append,
        test_layered_context_tool_result_truncation,
        test_layered_context_assemble,
        test_layered_context_distill,
        test_layered_context_scratch_reset,
        test_layered_context_get_stats,
        # Recovery: Recall
        test_recall_json_tool_calls,
        test_recall_from_reasoning_content,
        test_recall_with_known_tools_filter,
        test_recall_func_call_pattern,
        test_recall_code_block_json,
        test_has_missing_calls,
        # Recovery: Mend
        test_detect_broken_json,
        test_mend_json_brackets,
        test_mend_json_already_valid,
        # Recovery: Fold
        test_fold_schema,
        test_unfold_arguments,
        test_fold_roundtrip,
        test_should_fold,
        # Recovery: Guard
        test_loop_guard_normal,
        test_loop_guard_repeat,
        test_loop_guard_suppress,
        test_loop_signature_consistency,
        test_detect_loop,
        # Recovery: Cascade
        test_recovery_cascade_recall,
        test_recovery_cascade_mend,
        test_recovery_cascade_guard,
        test_recovery_cascade_no_recovery_needed,
        test_recovery_cascade_stats,
        # Sentinel
        test_sentinel_readonly_always_allowed,
        test_sentinel_strict_mode_blocks_writes,
        test_sentinel_headless_auto_approves,
        test_sentinel_path_traversal_blocked,
        test_sentinel_blocked_commands,
        test_sentinel_safe_command_allowed,
        test_sentinel_stats,
        # CostDashboard
        test_cost_dashboard_record_call,
        test_cost_dashboard_cache_hit_pricing,
        test_cost_dashboard_cache_write,
        test_cost_dashboard_end_turn,
        test_cost_dashboard_multiple_turns,
        test_cost_dashboard_report,
        test_cost_dashboard_summary,
        test_cost_dashboard_color_thresholds,
        test_cost_dashboard_token_format,
        # Flash-First Model Selection
        test_select_model_for_task_aux_call,
        test_select_model_for_task_user_override,
        test_select_model_for_task_failure_upgrade,
        test_detect_auto_upgrade_trigger,
        # AdapterBase
        test_adapter_base_protocol,
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

    # test_config_env_override is special (modifies os.environ)
    try:
        test_config_env_override()
        passed += 1
        print(f"  PASS test_config_env_override")
    except Exception as e:
        failed += 1
        print(f"  ERROR test_config_env_override: {e}")

    print(f"\n{'='*40}")
    print(f"  结果: {passed} passed, {failed} failed ({passed+failed} total)")
    print(f"{'='*40}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
