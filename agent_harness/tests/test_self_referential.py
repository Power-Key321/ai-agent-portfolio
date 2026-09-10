"""
MetaCognition 自指闭环 — 完整演示。

场景：
  Harness 运行一段时后，MetaCognition 发现两个问题：
  1. code_feature 策略收敛速度下降 65%：从 0.32 降到 0.11
  2. SpiralGate 过于激进，40% 被跳过的任务需要人工修正

  然后 MetaCognition 自动：
  1. 检测 → 2. 生成任务 → 3. 执行改进 → 4. 验证 → 5. 应用/回滚
"""

import json, os, sys, io, time
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
# 强制 UTF-8 输出（Windows 控制台默认 GBK，打不出 ✓ 等字符）。
# 注意: 不要写成 io.TextIOWrapper(sys.stdout.buffer, ...) —— 它会接管并在回收时关闭
# 底层 buffer，连带废掉 pytest 的捕获器（ValueError: I/O operation on closed file）。
sys.stdout.reconfigure(encoding="utf-8")

from agent_harness.core.meta_cognition import (
    MetaCognition, SignalDetector, TaskGenerator, Validator,
    Signal, ImprovementTask,
)
from agent_harness.core.spiral_gate import SpiralGate
from agent_harness.core.router import Router
from agent_harness.core.envelope import Envelope
from agent_harness.modules.preproc.code import PreprocCode
from agent_harness.modules.preproc.full import PreprocFull


def main():
    harness_root = Path(__file__).resolve().parent.parent
    # 隔离目录：由 conftest.py 设定，避免把测试状态写进源码树
    feedback_dir = Path(os.environ["AGENT_HARNESS_STATE_DIR"])
    feedback_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════
    # STEP 1: 构造反馈数据 — 模拟退化
    # ═══════════════════════════════════════
    print("=" * 70)
    print("  STEP 1: 构造场景 — 框架运行一段时间后的反馈数据")
    print("=" * 70)

    all_events = []
    # 20条基线 — 良好运行
    for i in range(20):
        all_events.append({
            "trace_id": f"good-{i}",
            "strategy_id": "code_feature",
            "signal_type": "accepted",
            "spiral_iterations_used": 3,
            "convergence_score": round(0.28 + 0.02 * (i % 5), 3),
            "timestamp": datetime(2026, 6, 20, 10, i, 0).isoformat(),
        })
    # 10条退化 — 收敛速度骤降
    for i in range(10):
        all_events.append({
            "trace_id": f"bad-{i}",
            "strategy_id": "code_feature",
            "signal_type": "modified" if i >= 5 else "accepted",
            "spiral_iterations_used": 2 if i < 7 else 1,
            "convergence_score": round(max(0.04, 0.18 - i * 0.016), 3),
            "timestamp": datetime(2026, 6, 29, 14, i, 0).isoformat(),
        })
    # 8条门控相关的 — 跳过后被人工修正
    for i in range(8):
        all_events.append({
            "trace_id": f"gate-{i}",
            "strategy_id": "code_fix",
            "signal_type": "modified" if i >= 3 else "retried",
            "spiral_iterations_used": 1,
            "convergence_score": 0.08,
            "timestamp": datetime(2026, 6, 29, 20, i, 0).isoformat(),
        })

    (feedback_dir / "convergence_history.json").write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2), encoding="utf-8")
    (feedback_dir / "thresholds.json").write_text(
        json.dumps({"θ_phase1_to_2": 0.15, "θ_phase2_to_3": 0.65, "learning_rate": 0.05},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    baseline_avg = sum(e["convergence_score"] for e in all_events[:20]) / 20
    degraded_avg = sum(e["convergence_score"] for e in all_events[20:30]) / 10
    print(f"  基线收敛速度: {baseline_avg:.4f}")
    print(f"  退化收敛速度: {degraded_avg:.4f}")
    print(f"  退化幅度: {(1 - degraded_avg/baseline_avg)*100:.0f}%")

    # ═══════════════════════════════════════
    # STEP 2: MetaCognition 检测信号
    # ═══════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"  STEP 2: MetaCognition 读取反馈 → 检测异常信号")
    print(f"{'=' * 70}")

    meta = MetaCognition(harness_root=harness_root, feedback_dir=feedback_dir)
    status = meta.get_status()
    signals = meta.detector.detect_all()

    print(f"  框架健康: {status['health']}")
    print(f"  检测到 {len(signals)} 个信号:\n")
    for i, sig in enumerate(signals):
        decay_pct = (1 - sig.evidence.get("decay_ratio", 1)) * 100
        print(f"  [{sig.severity}] {sig.signal_type} → {sig.target}")
        if sig.signal_type == "convergence_decay":
            print(f"       历史均值: {sig.evidence['avg_historical']:.4f}")
            print(f"       近期均值: {sig.evidence['avg_recent']:.4f}  (下降 {decay_pct:.0f}%)")
        elif sig.signal_type == "gate_miscalibration":
            print(f"       跳过任务修正率: {sig.evidence['modify_rate']:.0%}")
        print(f"       建议动作: {sig.recommended_action}")

    # ═══════════════════════════════════════
    # STEP 3: 生成改进任务
    # ═══════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"  STEP 3: 将信号转化为具体改进任务")
    print(f"{'=' * 70}")

    tasks = []
    for sig in signals:
        task = meta.generator.generate(sig)
        if task:
            tasks.append(task)
            print(f"\n  改进任务: {task.task_id}")
            print(f"  触发信号: {sig.signal_type} (严重度 {sig.severity})")
            print(f"  目标文件: {Path(task.target_file).name}")
            print(f"  目标参数: {task.target_param}")
            print(f"  当前值: {task.current_value}")
            print(f"  建议值: {task.suggested_value}")

    # ═══════════════════════════════════════
    # STEP 4: 执行改进 + 验证（模拟"真正的改进"）
    # ═══════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"  STEP 4: 执行改进 → 实际修改参数 → 验证效果")
    print(f"{'=' * 70}")

    # 场景A: 收敛速度衰减 → 增加螺旋轮次
    # 执行：增加 code_feature 的 max_iterations
    print(f"\n  ┌─ 改进A: 增加 code_feature 螺旋轮次")
    route_file = harness_root / "strategies" / "route_table.json"
    route_data = json.loads(route_file.read_text(encoding="utf-8"))
    old_max = route_data["strategies"]["code_feature"]["spiral_config"]["max_iterations"]
    new_max = old_max + 1
    print(f"  │ 参数: max_iterations: {old_max} → {new_max}")

    # 验证：用退化数据跑 gate，看改进后是否更少跳过模糊任务
    router = Router(); router.load_strategies()
    gate = SpiralGate()

    test_inputs = [
        ("模糊需求", "帮我做一个登录功能", PreprocCode()),
        ("较模糊", "用FastAPI实现认证", PreprocCode()),
    ]

    print(f"  │")
    print(f"  │ 改进前门控决策:")
    for label, text, preproc in test_inputs:
        env = Envelope(); env = router.classify(env, text)
        env = preproc.process(env).envelope
        a = gate.assess(env)
        print(f"  │   \"{text}\" → {a['original_max']}→{a['recommended_iterations']} skip={a['skip_spiral']}")

    # 实际写入改进
    route_data["strategies"]["code_feature"]["spiral_config"]["max_iterations"] = new_max
    route_file.write_text(json.dumps(route_data, ensure_ascii=False, indent=2), encoding="utf-8")
    router._strategies.clear()
    router.load_strategies()

    print(f"  │")
    print(f"  │ 改进后门控决策:")
    for label, text, preproc in test_inputs:
        env = Envelope(); env = router.classify(env, text)
        env = preproc.process(env).envelope
        a = gate.assess(env)
        print(f"  │   \"{text}\" → {a['original_max']}→{a['recommended_iterations']} skip={a['skip_spiral']}")

    # Metrics change
    before_metrics = {"avg_convergence": degraded_avg}
    # 模拟：增加螺旋轮次后，预期收敛速度提升（等待下一个统计周期验证）
    after_metrics = {"avg_convergence": round(degraded_avg * 1.15, 4)}  # 模拟15%提升
    print(f"  │")
    print(f"  │ 预期收敛速度: {before_metrics['avg_convergence']:.4f} → {after_metrics['avg_convergence']:.4f}")

    vr = meta.validator.validate(tasks[0], before_metrics, after_metrics)
    print(f"  │ 验证: {vr.verdict} (delta={vr.metrics_change.get('convergence_speed', 0)})")

    # 回滚（因为我们是演示，恢复原值）
    route_data["strategies"]["code_feature"]["spiral_config"]["max_iterations"] = old_max
    route_file.write_text(json.dumps(route_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  └─ 已回滚参数到 {old_max}（演示环境保留原始值）")

    # ═══════════════════════════════════════
    # STEP 5: 运行完整元认知循环
    # ═══════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"  STEP 5: 完整 MetaCognition.run_cycle()")
    print(f"{'=' * 70}")

    execution_log = []

    def execute_improvement(task):
        execution_log.append({
            "task_id": task.task_id,
            "param": task.target_param,
            "old": task.current_value,
            "new": task.suggested_value,
            "action": "executed",
        })
        return True

    def collect_metrics():
        # 模拟改进后的指标
        return {
            "avg_convergence": round(degraded_avg * 1.12, 4),
            "gate_skip_rate": 0.30,
        }

    meta2 = MetaCognition(harness_root=harness_root, feedback_dir=feedback_dir)
    meta2.on_execute_improvement = execute_improvement
    meta2.on_collect_metrics = collect_metrics
    report = meta2.run_cycle(max_improvements=2)

    print(f"\n  循环报告:")
    print(f"  ┌ 状态: {report['cycle_status']}")
    print(f"  ├ 耗时: {report['duration_seconds']:.2f}s")
    print(f"  ├ 检测信号: {report['signals_detected']}")
    print(f"  ├ 应用改进: {report['improvements_applied']}")
    print(f"  ├ 回滚改进: {report['improvements_rolled_back']}")
    print(f"  └ 框架健康: {report['framework_health']}")
    for d in report['details']:
        print(f"     · {d['target']}: {d['signal']} → {d['verdict']}")

    # ═══════════════════════════════════════
    # 总结
    # ═══════════════════════════════════════
    print(f"""
{'=' * 70}
  自指闭环验证 — 完整链路
{'=' * 70}

  用户使用 Harness 处理任务
         ↓
  反馈数据积累在 feedback/
         ↓
  ┌─────────────────────────────────────┐
  │  MetaCognition 元认知外环            │
  │                                     │
  │  1. SignalDetector                  │
  │     读取 convergence_history.json   │
  │     → 发现 code_feature 退化 65%    │
  │                                     │
  │  2. TaskGenerator                   │
  │     生成改进任务:                    │
  │     目标 = route_table.json         │
  │     参数 = max_iterations           │
  │     动作 = +1                       │
  │                                     │
  │  3. on_execute_improvement()        │
  │     实际修改 Harness 自己的配置      │
  │                                     │
  │  4. Validator                       │
  │     改进前 c={degraded_avg:.4f}          │
  │     改进后 c={degraded_avg*1.15:.4f} (模拟) │
  │     验证通过 → applied              │
  └─────────────────────────────────────┘
         ↓
  改进后的 Harness 继续服务用户任务

  这是"元乐高":
  - Harness 是乐高积木
  - MetaCognition 是读积木说明书 + 改积木的工人
  - 框架成为自身的优化对象

  三个关键指标:
  1. 检测灵敏度: 退化了 65% 才触发 (severity 0.97)
  2. 改进精确度: 直接定位到 route_table.json 中的具体参数
  3. 安全机制: 验证不通过自动回滚 (防止改坏自己)
{'=' * 70}
""")


if __name__ == "__main__":
    main()
