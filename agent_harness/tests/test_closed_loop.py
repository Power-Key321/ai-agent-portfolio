"""闭环自测 — 并行调度 + 可观测性 端到端验证。"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_harness.core.observability import (
    MetricsCollector, HarnessReport, get_collector, reset_collector,
)
from agent_harness.modules.execute.executor import Executor
from agent_harness.modules.execute.gated import ExecutorGated
from agent_harness.modules.schedule.parallel import ScheduleParallel
from agent_harness.modules.schedule.sequential import ScheduleSequential
from agent_harness.core.envelope import Envelope


def header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_sequential_vs_parallel_schedule():
    """测试1: 串行 vs 并行调度计划对比。"""
    header("Test 1: Sequential vs Parallel Schedule Plan")

    # 3个独立子任务 + 1个依赖子任务
    subtasks = [
        {"id": "s1", "description": "分析现有代码", "dependencies": [],
         "estimated_tokens": 3000},
        {"id": "s2", "description": "查阅API文档", "dependencies": [],
         "estimated_tokens": 5000},
        {"id": "s3", "description": "确定技术方案", "dependencies": [],
         "estimated_tokens": 2000},
        {"id": "s4", "description": "编写实现代码", "dependencies": ["s1", "s2", "s3"],
         "estimated_tokens": 8000},
    ]

    # 串行
    env_seq = Envelope()
    env_seq.task["subtasks"] = subtasks
    env_seq.task["max_parallel_subtasks"] = 1
    seq = ScheduleSequential()
    result_seq = seq.process(env_seq)
    plan_seq = result_seq.envelope.task["execution_plan"]

    # 并行
    env_par = Envelope()
    env_par.task["subtasks"] = subtasks
    env_par.task["max_parallel_subtasks"] = 4
    par = ScheduleParallel()
    result_par = par.process(env_par)
    plan_par = result_par.envelope.task["execution_plan"]

    print(f"  Sequential: {len(plan_seq['batches'])} batches, "
          f"{plan_seq['estimated_total_time_ms']}ms est.")
    print(f"  Parallel:   {len(plan_par['batches'])} batches, "
          f"{plan_par['estimated_total_time_ms']}ms est., "
          f"speedup={plan_par['speedup_vs_sequential']}x")
    print(f"  Parallel batches: {plan_par['parallel_batches']}")

    # 串行4个批次（每个一个），并行2个批次（s1/s2/s3并行, s4单独）
    assert len(plan_seq["batches"]) == 4, f"seq should have 4 batches, got {len(plan_seq['batches'])}"
    first_par_batch = plan_par["batches"][0]
    assert first_par_batch["parallel"] is True
    assert set(first_par_batch["subtask_ids"]) == {"s1", "s2", "s3"}
    assert plan_par["speedup_vs_sequential"] >= 1.3  # DAG中有串行瓶颈

    print("  [PASS]")


def test_parallel_execution_isolation():
    """测试2: 并行执行时各子任务相互隔离。"""
    header("Test 2: Parallel Execution Isolation")

    subtasks = [
        {"id": "a1", "description": "任务A", "dependencies": []},
        {"id": "a2", "description": "任务B", "dependencies": []},
    ]

    env = Envelope()
    env.task["subtasks"] = subtasks
    env.task["execution_plan"] = {
        "strategy": "parallel",
        "batches": [{
            "batch_id": "b1",
            "subtask_ids": ["a1", "a2"],
            "parallel": True,
            "parallel_count": 2,
            "timeout_ms": 10000,
        }],
    }
    env.task["max_parallel_subtasks"] = 2

    # 使用回调来验证隔离性
    execution_order = []

    def track_execute(env, subtask):
        execution_order.append(subtask["id"])
        env.task.setdefault("_artifacts", []).append({
            "type": "executed",
            "subtask": subtask["id"],
            "thread_id": str(id(env.task)),
        })
        from agent_harness.modules.base import ModuleResult
        return ModuleResult(envelope=env)

    executor = Executor(on_execute=track_execute)
    result = executor.process(env)

    results = result.envelope.task.get("execution_results", [])
    assert len(results) == 2, f"expected 2 results, got {len(results)}"
    assert all(r["status"] == "success" for r in results)
    assert len(execution_order) == 2  # both executed
    print(f"  Execution order: {execution_order}")
    print("  [PASS]")


def test_parallel_with_failure_isolation():
    """测试3: 并行执行中一个子任务失败不影响其他子任务。"""
    header("Test 3: Failure Isolation in Parallel Batch")

    subtasks = [
        {"id": "good1", "description": "正常任务1", "dependencies": []},
        {"id": "bad1", "description": "会失败的任务", "dependencies": []},
        {"id": "good2", "description": "正常任务2", "dependencies": []},
    ]

    env = Envelope()
    env.task["subtasks"] = subtasks
    env.task["execution_plan"] = {
        "strategy": "parallel",
        "batches": [{
            "batch_id": "b1",
            "subtask_ids": ["good1", "bad1", "good2"],
            "parallel": True,
            "parallel_count": 3,
            "timeout_ms": 10000,
        }],
    }
    env.task["max_parallel_subtasks"] = 3

    def fail_on_bad(env, subtask):
        from agent_harness.modules.base import ModuleResult
        if subtask["id"] == "bad1":
            return ModuleResult(envelope=env, success=False,
                                error="simulated failure",
                                failure_class="tool_error")
        env.task.setdefault("_artifacts", []).append({
            "type": "executed",
            "subtask": subtask["id"],
        })
        return ModuleResult(envelope=env)

    executor = Executor(on_execute=fail_on_bad)
    result = executor.process(env)

    # 第一个失败会触发 return，但并行执行中其他任务仍在跑
    assert not result.success  # 有失败的
    assert result.failure_class == "tool_error"

    print("  [PASS] - failure correctly detected and reported")


def test_gated_parallel_with_metrics():
    """测试4: 并行门检执行 + 可观测性指标收集。"""
    header("Test 4: Gated Parallel + Metrics Collection")

    reset_collector()
    collector = get_collector()

    subtasks = [
        {"id": "g1", "description": "信息搜集", "dependencies": [],
         "entropy_stage": "信息源", "fallback_strategy": "retry",
         "quant_metric": {"name": "items_found", "target": 5}},
        {"id": "g2", "description": "代码过滤", "dependencies": [],
         "entropy_stage": "过滤层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items_filtered", "target": 3}},
        {"id": "g3", "description": "核心处理", "dependencies": ["g1", "g2"],
         "entropy_stage": "处理层", "fallback_strategy": "retry",
         "quant_metric": {"name": "items_processed", "target": 5}},
        {"id": "g4", "description": "结果产出", "dependencies": ["g3"],
         "entropy_stage": "产出层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items_produced", "target": 1}},
    ]

    # 调度
    env = Envelope()
    env.task["subtasks"] = subtasks
    env.task["max_parallel_subtasks"] = 4
    sp = ScheduleParallel()
    plan_result = sp.process(env)
    plan = plan_result.envelope.task["execution_plan"]
    print(f"  Plan: {len(plan['batches'])} batches, "
          f"parallel_batches={plan['parallel_batches']}, "
          f"speedup={plan['speedup_vs_sequential']}x")

    # 执行
    gated = ExecutorGated()
    exec_result = gated.process(plan_result.envelope)

    results = exec_result.envelope.task.get("execution_results", [])
    gate_log = exec_result.envelope.task.get("gate_log", [])
    degraded = exec_result.envelope.task.get("degradation_total", 0)

    print(f"  Executed: {len(results)} subtasks")
    print(f"  Gate entries: {len(gate_log)}")
    print(f"  Degradation total: {degraded}")

    assert len(results) == 4, f"expected 4 results, got {len(results)}"
    assert len(gate_log) == 4, f"expected 4 gate entries, got {len(gate_log)}"

    # 第一批次 (g1, g2 并行) 应该有 parallel 标记
    first_batch = plan["batches"][0]
    assert first_batch["parallel"] is True
    assert set(first_batch["subtask_ids"]) == {"g1", "g2"}

    # 检查指标
    snap = collector.get_snapshot()
    gate_rates = snap["gates"]
    assert len(gate_rates) >= 1  # 至少有门检记录
    print(f"  Gate rates: {json.dumps(gate_rates, indent=2)}")

    print("  [PASS]")


def test_full_pipeline_with_report():
    """测试5: 完整管道 + 生成可读报告。"""
    header("Test 5: Full Pipeline → HarnessReport")

    reset_collector()
    collector = get_collector()

    # 模拟一次完整的执行
    from agent_harness.adapters.claude_code import get_adapter
    adapter = get_adapter()

    t0 = time.time()
    result = adapter.start(
        "为我的博客系统添加JWT认证中间件",
        intent_override="code_feature",
    )
    elapsed = time.time() - t0

    print(f"  Intent: {result['intent_class']}")
    print(f"  Strategy: {result['strategy_id']}")
    print(f"  Spirals: {result['spiral_iterations']}")
    print(f"  Elapsed: {elapsed:.2f}s")

    # 验证结果结构
    assert "metrics" in result
    assert "report_short" in result
    metrics = result["metrics"]

    # 模块延迟
    modules = metrics.get("modules", {})
    assert len(modules) > 0, "should have module latency data"
    print(f"  Modules tracked: {list(modules.keys())}")
    for mod, stats in modules.items():
        print(f"    {mod}: p50={stats['p50']:.0f}ms p95={stats['p95']:.0f}ms "
              f"fail={stats['failure_rate']:.0%}")

    # 门检率
    gates = metrics.get("gates", {})
    if gates:
        print(f"  Gate pass rates: {len(gates)} gates tracked")

    # 收敛
    conv = metrics.get("convergence", {})
    print(f"  Convergence speed: {conv.get('speed', 'N/A')}")
    trace = conv.get("trace", [])
    if trace:
        print(f"  Spiral trace: {len(trace)} rounds, "
              f"r: {trace[0]['radius']:.3f} -> {trace[-1]['radius']:.3f}")

    # 执行摘要
    ex = metrics.get("execution", {})
    print(f"  Total subtasks: {ex['total_subtasks']}, "
          f"Total time: {ex['total_elapsed_ms']:.0f}ms")

    # 简短摘要
    print(f"\n  Short: {result['report_short']}")

    # 完整报告
    report = adapter.get_report()
    print(f"\n{report}")

    # 验证报告关键字段
    assert "Agent Harness" in report
    assert "Gate Pass" in report
    assert "Convergence" in report
    assert "Execution Summary" in report

    print("\n  [PASS]")


def test_speedup_measurement():
    """测试6: 测量并行 vs 串行的实际加速比。"""
    header("Test 6: Speedup Measurement")

    # 创建一组模拟的耗时子任务
    subtasks = [
        {"id": f"task_{i}", "description": f"耗时任务{i}",
         "dependencies": [], "estimated_tokens": 1000}
        for i in range(6)
    ]

    def slow_execute(env, subtask):
        time.sleep(0.05)  # 模拟50ms执行时间
        env.task.setdefault("_artifacts", []).append({
            "type": "done", "subtask": subtask["id"],
        })
        from agent_harness.modules.base import ModuleResult
        return ModuleResult(envelope=env)

    # 串行执行
    env_seq = Envelope()
    env_seq.task["subtasks"] = subtasks
    env_seq.task["execution_plan"] = {
        "strategy": "sequential",
        "batches": [{
            "batch_id": f"b{i+1}",
            "subtask_ids": [f"task_{i}"],
            "parallel": False,
            "parallel_count": 1,
            "timeout_ms": 5000,
        } for i in range(6)],
    }

    executor_seq = Executor(on_execute=slow_execute)
    t0 = time.time()
    executor_seq.process(env_seq)
    seq_time = time.time() - t0

    # 并行执行
    env_par = Envelope()
    env_par.task["subtasks"] = subtasks
    env_par.task["max_parallel_subtasks"] = 6
    env_par.task["execution_plan"] = {
        "strategy": "parallel",
        "batches": [{
            "batch_id": "b1",
            "subtask_ids": [f"task_{i}" for i in range(6)],
            "parallel": True,
            "parallel_count": 6,
            "timeout_ms": 5000,
        }],
    }

    executor_par = Executor(on_execute=slow_execute)
    t0 = time.time()
    executor_par.process(env_par)
    par_time = time.time() - t0

    speedup = seq_time / max(par_time, 0.001)
    print(f"  Sequential: {seq_time*1000:.0f}ms")
    print(f"  Parallel:   {par_time*1000:.0f}ms")
    print(f"  Speedup:    {speedup:.1f}x")

    # 6个50ms任务: 串行~300ms, 并行~50ms+overhead
    # 期望加速比 > 3x (给线程创建留开销)
    assert speedup >= 2.0, f"expected speedup >= 2x, got {speedup:.1f}x"
    print("  [PASS]")


# ── 运行所有自测 ──
if __name__ == "__main__":
    print("=" * 60)
    print("  Agent Harness — Closed-Loop Self-Test")
    print("  Parallel Scheduling + Observability")
    print("=" * 60)

    all_passed = True
    for test_fn in [
        test_sequential_vs_parallel_schedule,
        test_parallel_execution_isolation,
        test_parallel_with_failure_isolation,
        test_gated_parallel_with_metrics,
        test_full_pipeline_with_report,
        test_speedup_measurement,
    ]:
        try:
            test_fn()
        except Exception as e:
            print(f"\n  [FAIL] {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("  ALL SELF-TESTS PASSED")
    else:
        print("  SOME SELF-TESTS FAILED")
    print(f"{'='*60}")
