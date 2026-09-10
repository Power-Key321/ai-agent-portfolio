"""验证并行调度 + 可观测性功能。"""
import sys, traceback
from pathlib import Path
# 确保项目根目录在 path 中
_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

errors = []

# 1. 验证模块导入
try:
    from agent_harness.core.observability import (
        MetricsCollector, HarnessReport, get_collector, reset_collector,
    )
    print("[OK] observability module imported")
except Exception as ex:
    errors.append(f"observability import: {ex}")

# 2. 验证 Executor 并行方法
try:
    from agent_harness.modules.execute.executor import Executor, CircuitBreaker
    executor_obj = Executor()
    assert hasattr(executor_obj, "_spawn_isolated"), "missing _spawn_isolated"
    assert hasattr(executor_obj, "_execute_parallel_batch"), "missing _execute_parallel_batch"
    print("[OK] Executor has parallel methods")
except Exception as ex:
    errors.append(f"Executor: {ex}")

# 3. 验证 ExecutorGated 并行方法
try:
    from agent_harness.modules.execute.gated import ExecutorGated
    gated_obj = ExecutorGated()
    assert hasattr(gated_obj, "_execute_parallel_batch"), "missing _execute_parallel_batch"
    print("[OK] ExecutorGated has parallel methods")
except Exception as ex:
    errors.append(f"ExecutorGated: {ex}")

# 4. 验证 MetricsCollector 功能
try:
    reset_collector()
    c = get_collector()
    c.record_module("test.module", 100, True)
    c.record_module("test.module", 200, True)
    c.record_module("test.module", 50, False, "test error")
    c.record_gate("s1", "completeness", True, "good")
    c.record_gate("s1", "accuracy", False, "low")
    c.record_degradation("s2", "test reason", 2, "skip")
    c.record_spiral(1, 0.5)
    c.record_spiral(2, 0.3)
    c.record_execution("code_feature", "code_feature", 5, 1000.0, True)
    snap = c.get_snapshot()
    assert snap["modules"]["test.module"]["count"] == 3, f"count mismatch: {snap}"
    assert abs(snap["modules"]["test.module"]["failure_rate"] - 0.333) < 0.001, f"failure_rate: {snap}"
    assert snap["gates"]["completeness"]["passed"] == 1
    assert snap["gates"]["accuracy"]["failed"] == 1
    assert snap["degradation"]["total_events"] == 1
    assert len(snap["convergence"]["trace"]) == 2
    print("[OK] MetricsCollector snapshot correct")
except Exception as ex:
    errors.append(f"MetricsCollector: {ex}")
    traceback.print_exc()

# 5. 验证 HarnessReport
try:
    report = HarnessReport(c.get_snapshot())
    full = report.render()
    short = report.render_short()
    assert "Agent Harness" in full
    assert "final_r=" in short
    print("[OK] HarnessReport renders correctly")
except Exception as ex:
    errors.append(f"HarnessReport: {ex}")

# 6. 验证 AdapterBase 有新方法
try:
    from agent_harness.adapters.base import AdapterBase
    assert hasattr(AdapterBase, "get_report"), "missing get_report"
    assert hasattr(AdapterBase, "get_report_short"), "missing get_report_short"
    print("[OK] AdapterBase has report methods")
except Exception as ex:
    errors.append(f"AdapterBase: {ex}")

# 7. 验证 ClaudeCodeAdapter 能正常初始化
try:
    from agent_harness.adapters.claude_code import get_adapter
    adapter = get_adapter()
    print("[OK] ClaudeCodeAdapter initialized")
except Exception as ex:
    errors.append(f"ClaudeCodeAdapter: {ex}")

# 8. 验证 Orchestrator 接入 observability
try:
    from agent_harness.core.orchestrator import Orchestrator
    from agent_harness.core.router import Router
    o = Orchestrator(router=Router())
    print("[OK] Orchestrator works with observability")
except Exception as ex:
    errors.append(f"Orchestrator: {ex}")

# 9. 验证并行执行
try:
    from agent_harness.core.envelope import Envelope
    env = Envelope()
    env.task["subtasks"] = [
        {"id": "s1", "description": "task 1", "dependencies": []},
        {"id": "s2", "description": "task 2", "dependencies": []},
    ]
    env.task["execution_plan"] = {
        "strategy": "parallel",
        "batches": [{
            "batch_id": "b1",
            "subtask_ids": ["s1", "s2"],
            "parallel": True,
            "parallel_count": 2,
            "timeout_ms": 5000,
        }],
    }
    env.task["max_parallel_subtasks"] = 2
    exec_result = executor_obj.process(env)
    results = exec_result.envelope.task.get("execution_results", [])
    assert len(results) == 2, f"expected 2 results, got {len(results)}"
    assert all(r["status"] == "success" for r in results)
    print("[OK] Parallel execution produces correct results")
except Exception as ex:
    errors.append(f"Parallel execution: {ex}")
    traceback.print_exc()

# 10. 验证 ExecutorGated 并行 + 门检
try:
    env2 = Envelope()
    env2.task["subtasks"] = [
        {"id": "s1", "description": "task 1", "dependencies": [],
         "entropy_stage": "处理层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items", "target": 1}},
        {"id": "s2", "description": "task 2", "dependencies": [],
         "entropy_stage": "验证层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items", "target": 1}},
    ]
    env2.task["execution_plan"] = {
        "strategy": "parallel",
        "batches": [{
            "batch_id": "b1",
            "subtask_ids": ["s1", "s2"],
            "parallel": True,
            "parallel_count": 2,
            "timeout_ms": 5000,
        }],
    }
    env2.task["max_parallel_subtasks"] = 2
    result = gated_obj.process(env2)
    gate_log = result.envelope.task.get("gate_log", [])
    assert len(gate_log) == 2, f"expected 2 gate entries, got {len(gate_log)}"
    assert all("gates" in g for g in gate_log)
    print("[OK] ExecutorGated parallel + gate checks work")
except Exception as ex:
    errors.append(f"ExecutorGated parallel: {ex}")
    traceback.print_exc()

# 11. 完整流程: schedule → execute 带并行
try:
    from agent_harness.modules.schedule.parallel import ScheduleParallel
    env3 = Envelope()
    env3.task["subtasks"] = [
        {"id": "s1", "description": "独立任务1", "dependencies": [],
         "entropy_stage": "处理层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items", "target": 1}},
        {"id": "s2", "description": "独立任务2", "dependencies": [],
         "entropy_stage": "处理层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items", "target": 1}},
        {"id": "s3", "description": "依赖任务", "dependencies": ["s1", "s2"],
         "entropy_stage": "验证层", "fallback_strategy": "skip",
         "quant_metric": {"name": "items", "target": 1}},
    ]
    env3.task["max_parallel_subtasks"] = 4
    sp = ScheduleParallel()
    plan_result = sp.process(env3)
    plan = plan_result.envelope.task.get("execution_plan", {})
    assert plan["strategy"] == "parallel"
    first_batch = plan["batches"][0]
    assert first_batch["parallel"] is True, f"first batch should be parallel: {first_batch}"
    assert set(first_batch["subtask_ids"]) == {"s1", "s2"}
    assert plan["batches"][1]["subtask_ids"] == ["s3"]
    print("[OK] ScheduleParallel plans correctly")

    # 执行
    exec_result2 = gated_obj.process(plan_result.envelope)
    results2 = exec_result2.envelope.task.get("execution_results", [])
    assert len(results2) == 3, f"expected 3 results, got {len(results2)}"
    print("[OK] ScheduleParallel → ExecutorGated full pipeline")
except Exception as ex:
    errors.append(f"Full pipeline: {ex}")
    traceback.print_exc()

# 12. 验证端到端: adapter.start() 含 metrics
try:
    from agent_harness.adapters.claude_code import get_adapter as _ga
    _adapter = _ga()
    result = _adapter.start("写一个用户登录模块", intent_override="code_feature")
    assert result["intent_class"] == "code_feature"
    assert "metrics" in result
    assert "report_short" in result
    snap = result["metrics"]
    assert "modules" in snap
    assert "gates" in snap
    assert "convergence" in snap
    print("[OK] adapter.start() returns metrics + report_short")

    # 完整报告
    full_report = _adapter.get_report()
    assert "Agent Harness" in full_report
    assert "Gate Pass" in full_report
    assert "Convergence" in full_report
    print("[OK] get_report() shows gates, convergence, execution summary")
except Exception as ex:
    errors.append(f"End-to-end report: {ex}")
    traceback.print_exc()

# ── 汇总 ──
if errors:
    print(f"\n*** {len(errors)} ERROR(S) ***")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print(f"\n=== All 12 validation checks PASSED ===")
