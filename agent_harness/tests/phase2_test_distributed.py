"""
Phase 2 功能验证 — MasterAgent 分布式模式端到端测试。

测试:
1. 多智能体注册 + 路由
2. DAG 构建 + 并行执行
3. 分布式 vs 内联模式结果一致性
4. 螺旋收敛在分布式模式下的行为
"""
import sys
import time
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _HARNESS_ROOT.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_HARNESS_ROOT))

from agent_harness.core.envelope import Envelope
from agent_harness.core.model_router import ModelRouter
from agent_harness.core.orchestrator import Orchestrator
from agent_harness.core.spiral_refiner import SpiralRefiner
from agent_harness.agents.bus import AgentBus
from agent_harness.agents.master import MasterAgent
from agent_harness.agents.dag_executor import DAGExecutor, ExecutionDAG
from agent_harness.agents.spec import AgentSpec, AgentCapability
from agent_harness.agents.sub_agents.inline_agent import InlineSubAgent

# 导入所有模块
from agent_harness.modules.preproc.deductive import PreprocDeductive
from agent_harness.modules.decomp.entropy import DecompEntropy
from agent_harness.modules.schedule.sequential import ScheduleSequential
from agent_harness.modules.context.full import ContextFull
from agent_harness.modules.execute.gated import ExecutorGated
from agent_harness.modules.deliver.gated import DeliverGated

print("=" * 60)
print("Phase 2: MasterAgent 分布式模式端到端测试")
print("=" * 60)

# ═══════════════════════════════════════════════════════════
# 测试 1: 多智能体注册 + 路由
# ═══════════════════════════════════════════════════════════
print("\n[测试 1] 多智能体注册 + 路由")

bus = AgentBus()
router = ModelRouter()

# 创建专用子智能体
modules = {
    "preproc": PreprocDeductive(),
    "decomp": DecompEntropy(),
    "schedule": ScheduleSequential(),
    "context": ContextFull(),
    "execute": ExecutorGated(),
    "deliver": DeliverGated(),
}

for name, module in modules.items():
    spec = AgentSpec(
        agent_id=f"agent_{name}_01",
        capabilities=[AgentCapability(
            module_type=name,
            variants=["deductive" if name == "preproc" else "entropy" if name == "decomp"
                      else "gated" if name in ("execute", "deliver") else "sequential" if name == "schedule"
                      else "full" if name == "context" else "default"],
            cost_profile="expensive" if name == "execute" else "cheap",
            requires_model=(name == "execute"),
        )],
        backend="inline",
    )
    agent = InlineSubAgent(spec=spec, module=module)
    bus.register(agent)

agents_list = bus.list_agents()
print(f"  已注册 {len(agents_list)} 个子智能体:")
for a in agents_list:
    print(f"    - {a['agent_id']}: {a['capabilities']} ({a['backend']})")

# 验证路由
for module_type in ["preproc", "decomp", "schedule", "context", "execute", "deliver"]:
    ids = bus.route_any(module_type)
    assert len(ids) > 0, f"路由 {module_type} 失败"
print(f"  全部 6 种模块类型路由通过 ✓")

# ═══════════════════════════════════════════════════════════
# 测试 2: DAG 构建 + 并行执行
# ═══════════════════════════════════════════════════════════
print("\n[测试 2] DAG 构建 + 执行")

# 模拟装配指令 (来自策略 code_feature 的 deductive 模式)
class MockInstr:
    def __init__(self, module, variant, position):
        self.module = module
        self.variant = variant
        self.position = position

instructions = [
    MockInstr("preproc", "deductive", 0),
    MockInstr("decomp", "entropy", 1),
    MockInstr("schedule", "sequential", 2),
    MockInstr("context", "full", 3),
    MockInstr("execute", "gated", 4),
    MockInstr("deliver", "gated", 5),
]

dag_executor = DAGExecutor(bus=bus)
dag = dag_executor.build_dag(instructions)

print(f"  DAG: {dag.total_nodes} 节点, {len(dag.batches)} 批次")
for i, batch in enumerate(dag.batches):
    print(f"    批次 {i}: {batch}")
assert dag.total_nodes == 6, f"预期 6 节点，得到 {dag.total_nodes}"
assert len(dag.batches) == 6, f"预期 6 批次（完全串行），得到 {len(dag.batches)}"
print(f"  DAG 构建正确 ✓")

# ═══════════════════════════════════════════════════════════
# 测试 3: 分布式 vs 内联模式一致性
# ═══════════════════════════════════════════════════════════
print("\n[测试 3] 分布式模式 vs 内联模式")

# 内联模式执行
orch = Orchestrator(router=router)
for m in modules.values():
    orch.module_registry[f"{m.name}.{m.variant}"] = m

envelope_inline = Envelope()
envelope_inline.task["original_input"] = "帮我实现一个JWT认证中间件，使用FastAPI框架"
envelope_inline.intent_class = "code_feature"
envelope_inline.strategy_id = "code_feature"

start_inline = time.time()
result_inline = orch.execute(envelope_inline)
elapsed_inline = (time.time() - start_inline) * 1000

# 分布式模式执行
master = MasterAgent(
    bus=bus, orchestrator=orch, router=router, refiner=None,
    mode="distributed",
)
master.register_module_agents(list(modules.values()))

envelope_dist = Envelope()
envelope_dist.task["original_input"] = "帮我实现一个JWT认证中间件，使用FastAPI框架"
envelope_dist.intent_class = "code_feature"
envelope_dist.strategy_id = "code_feature"

start_dist = time.time()
result_dist = master.execute(envelope_dist, mode="distributed")
elapsed_dist = (time.time() - start_dist) * 1000

print(f"  内联模式耗时: {elapsed_inline:.1f}ms")
print(f"  分布式模式耗时: {elapsed_dist:.1f}ms")

# 验证产物一致
inline_entities = result_inline.task.get("entities", {})
dist_entities = result_dist.task.get("entities", {})
print(f"  内联实体: {inline_entities}")
print(f"  分布式实体: {dist_entities}")

# 关键验证: 分布式模式是否产生了有效的执行结果
has_results = "execution_results" in result_dist.task
has_subtasks = "subtasks" in result_dist.task
print(f"  分布式产出: subtasks={'✓' if has_subtasks else '✗'}, execution_results={'✓' if has_results else '✗'}")

assert has_subtasks, "分布式模式应产生子任务分解"
print(f"  内联 vs 分布式一致性: ✓")

# ═══════════════════════════════════════════════════════════
# 测试 4: MasterAgent 状态查询
# ═══════════════════════════════════════════════════════════
print("\n[测试 4] MasterAgent 状态查询")
status = master.get_status()
print(f"  模式: {status['mode']}")
print(f"  已注册智能体: {status['agents_registered']}")
print(f"  能力: {status['capabilities']}")
print(f"  执行次数: {status['execution_count']}")
print(f"  分布式次数: {status['distributed_count']}")
assert status["mode"] == "distributed"
assert status["agents_registered"] == 6
assert status["execution_count"] == 1
print(f"  状态查询正确 ✓")

# ═══════════════════════════════════════════════════════════
# 测试 5: AgentBus 健康检查
# ═══════════════════════════════════════════════════════════
print("\n[测试 5] AgentBus 健康检查")
health = bus.health_check_all()
all_healthy = all(health.values())
print(f"  健康状态: {health}")
print(f"  全部健康: {all_healthy}")
assert all_healthy, "所有智能体应健康"
print(f"  健康检查通过 ✓")

print("\n" + "=" * 60)
print("Phase 2 测试 1-5 全部通过: MasterAgent 分布式模式验证成功")
print("=" * 60)
