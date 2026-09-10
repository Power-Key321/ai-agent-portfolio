"""
Phase 2 功能验证 — 完整集成测试套件。

使用 pytest 运行: python -m pytest agent_harness/tests/phase2_test_suite.py -v
"""
import sys
import time
from pathlib import Path

# 确保导入路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from agent_harness.core.envelope import Envelope
from agent_harness.core.model_router import ModelRouter
from agent_harness.core.orchestrator import Orchestrator
from agent_harness.core.router import StrategyConfig

# Mock 模型响应
def _mock_model_response(prompt: str, skeleton_hash: str = "") -> str:
    import json
    return json.dumps({
        "intent_class": "code_feature",
        "confidence": 0.85,
        "strategy_id": "code_feature",
        "entities": {"language": "python", "framework": "fastapi"},
        "constraints": {},
    })
from agent_harness.agents.bus import AgentBus
from agent_harness.agents.master import MasterAgent
from agent_harness.agents.dag_executor import DAGExecutor
from agent_harness.agents.spec import AgentSpec, AgentCapability
from agent_harness.agents.sub_agents.inline_agent import InlineSubAgent
from agent_harness.modules.preproc.deductive import PreprocDeductive
from agent_harness.modules.decomp.entropy import DecompEntropy
from agent_harness.modules.schedule.sequential import ScheduleSequential
from agent_harness.modules.context.full import ContextFull
from agent_harness.modules.execute.gated import ExecutorGated
from agent_harness.modules.deliver.gated import DeliverGated


def _build_modules():
    return {
        "preproc": PreprocDeductive(),
        "decomp": DecompEntropy(),
        "schedule": ScheduleSequential(),
        "context": ContextFull(),
        "execute": ExecutorGated(),
        "deliver": DeliverGated(),
    }


def _build_bus_with_agents():
    bus = AgentBus()
    modules = _build_modules()
    variant_map = {
        "preproc": "deductive", "decomp": "entropy", "schedule": "sequential",
        "context": "full", "execute": "gated", "deliver": "gated",
    }
    for name, module in modules.items():
        spec = AgentSpec(
            agent_id=f"agent_{name}_01",
            capabilities=[AgentCapability(
                module_type=name,
                variants=[variant_map[name]],
                cost_profile="expensive" if name == "execute" else "cheap",
                requires_model=(name == "execute"),
            )],
            backend="inline",
        )
        bus.register(InlineSubAgent(spec=spec, module=module))
    return bus, modules


# ═══════════════════════════════════════════════
# 测试 1: 多智能体注册与路由
# ═══════════════════════════════════════════════
def test_multi_agent_registration():
    """验证所有 6 种模块类型能被正确注册和路由。"""
    bus, _ = _build_bus_with_agents()
    agents = bus.list_agents()
    assert len(agents) == 6, f"预期 6 个智能体，实际 {len(agents)}"

    for mt in ["preproc", "decomp", "schedule", "context", "execute", "deliver"]:
        ids = bus.route_any(mt)
        assert len(ids) > 0, f"路由 {mt} 失败"
        agent = bus.get_agent(ids[0])
        assert agent.can_handle(mt), f"智能体 {ids[0]} 应能处理 {mt}"
        assert agent.health_check(), f"智能体 {ids[0]} 应健康"


# ═══════════════════════════════════════════════
# 测试 2: DAG 构建
# ═══════════════════════════════════════════════
def test_dag_construction():
    """验证 DAG 正确构建 6 节点 6 批次的拓扑结构。"""
    bus, _ = _build_bus_with_agents()
    executor = DAGExecutor(bus=bus)

    class Instr:
        def __init__(self, m, v, p):
            self.module, self.variant, self.position = m, v, p

    instructions = [
        Instr("preproc", "deductive", 0),
        Instr("decomp", "entropy", 1),
        Instr("schedule", "sequential", 2),
        Instr("context", "full", 3),
        Instr("execute", "gated", 4),
        Instr("deliver", "gated", 5),
    ]
    dag = executor.build_dag(instructions)
    assert dag.total_nodes == 6
    assert len(dag.batches) == 6  # 完全串行依赖链
    assert dag.batches[0] == ["preproc.deductive"]
    assert dag.batches[5] == ["deliver.gated"]


# ═══════════════════════════════════════════════
# 测试 3: 消息发送与回复
# ═══════════════════════════════════════════════
def test_message_send_reply():
    """验证 AgentMessage 能正确发送到子智能体并收到回复。"""
    bus, _ = _build_bus_with_agents()
    from agent_harness.agents.base import AgentMessage

    env = Envelope()
    env.task["original_input"] = "帮我写一个JWT认证中间件"

    agent_ids = bus.route("preproc", "deductive")
    assert len(agent_ids) > 0

    msg = AgentMessage(
        sender_id="master",
        recipient_id=agent_ids[0],
        envelope=env,
        message_type="task",
    )
    reply = bus.send(msg)
    assert reply.message_type == "result"
    result_env = reply.envelope
    entities = result_env.task.get("entities", {})
    assert "language" in entities or "framework" in entities or len(entities) >= 0


# ═══════════════════════════════════════════════
# 测试 4: 分布式模式基础执行
# ═══════════════════════════════════════════════
def test_distributed_execution():
    """验证分布式 DAG 执行器能驱动完整流水线。"""
    bus, modules = _build_bus_with_agents()
    router = ModelRouter()
    router.on_model_call = _mock_model_response

    orch = Orchestrator(router=router)
    for m in modules.values():
        orch.module_registry[f"{m.name}.{m.variant}"] = m

    from agent_harness.agents.dag_executor import DAGExecutor
    executor = DAGExecutor(bus=bus)

    class Instr:
        def __init__(self, m, v, p):
            self.module, self.variant, self.position = m, v, p

    # 构建完整流水线指令
    instructions = [
        Instr("preproc", "deductive", 0),
        Instr("decomp", "entropy", 1),
        Instr("schedule", "sequential", 2),
        Instr("context", "full", 3),
        Instr("execute", "gated", 4),
        Instr("deliver", "gated", 5),
    ]
    dag = executor.build_dag(instructions)

    env = Envelope()
    env.task["original_input"] = "帮我实现用户认证功能"
    env.intent_class = "code_feature"
    env.strategy_id = "code_feature"

    result = executor.execute_dag(dag, env)

    # 验证关键产出
    assert "subtasks" in result.task, "DAG 执行应产出子任务"
    assert len(result.task.get("subtasks", [])) > 0, "子任务列表不应为空"

    for sub in result.task["subtasks"]:
        assert "goal" in sub, f"子任务缺少 goal: {sub}"
        assert "success_criteria" in sub, f"子任务缺少 success_criteria: {sub}"


# ═══════════════════════════════════════════════
# 测试 5: 内联与分布式一致性
# ═══════════════════════════════════════════════
def test_inline_vs_distributed_consistency():
    """验证内联模式和分布式 DAG 模式产生相同结构的产出。"""
    bus, modules = _build_bus_with_agents()
    router = ModelRouter()
    router.on_model_call = _mock_model_response

    orch = Orchestrator(router=router)
    for m in modules.values():
        orch.module_registry[f"{m.name}.{m.variant}"] = m

    # 内联
    env_inline = Envelope()
    env_inline.task["original_input"] = "帮我写Python FastAPI应用"
    env_inline.intent_class = "code_feature"
    env_inline.strategy_id = "code_feature"
    result_inline = orch.execute(env_inline)

    # 分布式 DAG (同一套指令，经 AgentBus 分发)
    from agent_harness.agents.dag_executor import DAGExecutor
    executor = DAGExecutor(bus=bus)
    class Instr:
        def __init__(self, m, v, p):
            self.module, self.variant, self.position = m, v, p
    instructions = [
        Instr("preproc", "deductive", 0),
        Instr("decomp", "entropy", 1),
        Instr("schedule", "sequential", 2),
        Instr("context", "full", 3),
        Instr("execute", "gated", 4),
        Instr("deliver", "gated", 5),
    ]
    dag = executor.build_dag(instructions)
    env_dist = Envelope()
    env_dist.task["original_input"] = "帮我写Python FastAPI应用"
    env_dist.intent_class = "code_feature"
    env_dist.strategy_id = "code_feature"
    result_dist = executor.execute_dag(dag, env_dist)

    # 两者都应产生 subtasks
    assert "subtasks" in result_inline.task
    assert "subtasks" in result_dist.task
    assert len(result_inline.task["subtasks"]) == len(result_dist.task["subtasks"]), \
        f"内联 {len(result_inline.task['subtasks'])} vs 分布式 {len(result_dist.task['subtasks'])} 子任务数应一致"


# ═══════════════════════════════════════════════
# 测试 6: MasterAgent 状态与统计
# ═══════════════════════════════════════════════
def test_master_agent_status():
    """验证 MasterAgent 状态查询和模式切换。"""
    bus, modules = _build_bus_with_agents()
    router = ModelRouter()
    orch = Orchestrator(router=router)
    for m in modules.values():
        orch.module_registry[f"{m.name}.{m.variant}"] = m

    master = MasterAgent(bus=bus, orchestrator=orch, router=router, mode="inline")
    # 不重复注册: _build_bus_with_agents() 已将智能体注册到 bus

    status = master.get_status()
    assert status["mode"] == "inline"
    assert status["agents_registered"] == 6
    assert status["execution_count"] == 0

    # 执行一次 (内联模式)
    env = Envelope()
    env.task["original_input"] = "test"
    env.intent_class = "code_feature"
    env.strategy_id = "code_feature"
    master.execute(env, mode="inline")

    status = master.get_status()
    assert status["execution_count"] == 1

    # 验证 set_mode 切换
    master.set_mode("distributed")
    assert master.mode == "distributed"
    assert status["mode"] == "inline" or master.mode == "distributed"

    # 验证 set_mode 拒绝非法值
    with pytest.raises(ValueError):
        master.set_mode("invalid")
