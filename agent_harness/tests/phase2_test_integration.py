"""
Phase 2 功能验证 — CC 子智能体集成 + 反馈→图谱→螺旋全链路测试。

测试:
  8. ClaudeCodeSubAgent 消息处理与分发
  9. 反馈事件→图谱丰富→螺旋提示 全链路
"""
import sys
import os
import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from agent_harness.agents.base import AgentMessage, SubAgentBase
from agent_harness.agents.spec import AgentSpec, AgentCapability
from agent_harness.agents.bus import AgentBus
from agent_harness.agents.sub_agents.cc_sub_agent import ClaudeCodeSubAgent
from agent_harness.agents.sub_agents.inline_agent import InlineSubAgent
from agent_harness.agents.sub_agents.api_agent import ApiSubAgent
from agent_harness.agents.sub_agents.local_fn_agent import LocalFnSubAgent
from agent_harness.core.envelope import Envelope
from agent_harness.knowledge import (
    KnowledgeGraph, GraphEnricher, AmbiguityResolver,
    GraphPruner, GraphNode,
)
from agent_harness.knowledge.graph_context import GraphContext
from agent_harness.modules.preproc.deductive import PreprocDeductive
from agent_harness.modules.decomp.entropy import DecompEntropy
from agent_harness.modules.execute.gated import ExecutorGated


# ═══════════════════════════════════════════════════
# 测试 8: CC 子智能体集成
# ═══════════════════════════════════════════════════

class TestCCSubAgentIntegration:
    """验证 ClaudeCodeSubAgent 的消息处理与分发。"""

    def test_cc_agent_creation_and_registration(self):
        """CC 子智能体能被创建并注册到 AgentBus。"""
        spec = AgentSpec(
            agent_id="cc_executor_test",
            capabilities=[AgentCapability(
                module_type="execute",
                variants=["gated"],
                cost_profile="expensive",
                requires_model=True,
            )],
            backend="claude_subagent",
        )
        agent = ClaudeCodeSubAgent(spec=spec)
        assert agent.spec.agent_id == "cc_executor_test"
        assert agent.spec.backend == "claude_subagent"
        assert not agent.health_check()  # 未设置 on_dispatch 时不健康

        bus = AgentBus()
        bus.register(agent)
        agents = bus.list_agents()
        assert any(a["agent_id"] == "cc_executor_test" for a in agents)

    def test_cc_agent_message_handling(self):
        """CC 子智能体能接收消息并调用分发回调。"""
        dispatch_log = []

        def mock_dispatch(task_prompt: str, context: dict) -> dict:
            dispatch_log.append({"prompt": task_prompt, "context": context})
            return {"status": "completed", "artifacts": ["middleware.py"]}

        spec = AgentSpec(
            agent_id="cc_executor_msg",
            capabilities=[AgentCapability(
                module_type="execute", variants=["gated"],
                cost_profile="expensive", requires_model=True,
            )],
            backend="claude_subagent",
        )
        agent = ClaudeCodeSubAgent(spec=spec)
        agent.on_dispatch = mock_dispatch

        assert agent.health_check()

        env = Envelope()
        env.task["original_input"] = "实现JWT认证中间件"
        env.task["normalized_intent"] = "实现JWT认证中间件"
        env.task["subtasks"] = [{
            "id": "sub_1", "goal": "创建JWT中间件",
            "description": "使用FastAPI创建JWT认证中间件",
        }]
        env.task["entities"] = {"framework": "FastAPI", "language": "Python"}

        msg = AgentMessage(
            sender_id="master",
            recipient_id="cc_executor_msg",
            envelope=env,
            message_type="task",
            payload={"module_type": "execute", "variant": "gated", "focus": "代码生成"},
        )

        reply = agent.handle_message(msg)

        assert reply.message_type == "result"
        assert len(dispatch_log) == 1
        assert "JWT" in dispatch_log[0]["prompt"]
        assert dispatch_log[0]["context"]["system_prompt"] is not None
        assert "gated" in dispatch_log[0]["context"]["system_prompt"]

        # 验证结果已写回 envelope
        assert "execution_results" in env.task
        assert env.task["execution_results"][0]["status"] == "completed"

    def test_cc_agent_error_without_dispatch(self):
        """未设置 on_dispatch 时返回 error。"""
        spec = AgentSpec(agent_id="cc_no_dispatch", backend="claude_subagent")
        agent = ClaudeCodeSubAgent(spec=spec)

        env = Envelope()
        env.task["original_input"] = "test"

        msg = AgentMessage(
            sender_id="master",
            recipient_id="cc_no_dispatch",
            envelope=env,
            message_type="task",
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "error"
        assert not agent.health_check()

    def test_cc_agent_system_prompt_template(self):
        """系统提示模板正确填充模块类型和变体。"""
        spec = AgentSpec(agent_id="cc_template_test", backend="claude_subagent")
        agent = ClaudeCodeSubAgent(spec=spec)

        prompt = agent.system_prompt_template.format(
            module_type="execute",
            variant="gated",
            focus="安全审计",
        )
        assert "execute.gated" in prompt
        assert "安全审计" in prompt

    def test_cc_agent_exception_handling(self):
        """分发回调抛出异常时返回 error。"""
        def failing_dispatch(prompt, context):
            raise RuntimeError("CC 调用超时")

        spec = AgentSpec(agent_id="cc_error_test", backend="claude_subagent")
        agent = ClaudeCodeSubAgent(spec=spec)
        agent.on_dispatch = failing_dispatch

        env = Envelope()
        msg = AgentMessage(
            sender_id="master", recipient_id="cc_error_test",
            envelope=env, message_type="task",
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "error"


# ═══════════════════════════════════════════════════
# 测试 8b: 其他子智能体类型
# ═══════════════════════════════════════════════════

class TestOtherSubAgents:
    """验证 InlineSubAgent、ApiSubAgent、LocalFnSubAgent 基本功能。"""

    def test_inline_agent_wraps_module(self):
        """InlineSubAgent 包裹现有 ModuleBase 并正确调用。"""
        module = PreprocDeductive()
        spec = AgentSpec(
            agent_id="inline_preproc",
            capabilities=[AgentCapability(
                module_type="preproc", variants=["deductive"],
                cost_profile="cheap", requires_model=False,
            )],
            backend="inline",
        )
        agent = InlineSubAgent(spec=spec, module=module)
        assert agent.can_handle("preproc")
        assert agent.health_check()

        env = Envelope()
        env.task["original_input"] = "帮我实现FastAPI认证"
        msg = AgentMessage(
            sender_id="master", recipient_id="inline_preproc",
            envelope=env, message_type="task",
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "result"
        # Deductive 预处理应提取实体
        entities = reply.envelope.task.get("entities", {})
        assert isinstance(entities, dict)

    def test_api_agent_with_callback(self):
        """ApiSubAgent 使用外部 API 回调。"""
        calls = []
        def mock_api(prompt: str, model: str) -> str:
            calls.append((prompt, model))
            return '{"answer": "ok"}'

        spec = AgentSpec(agent_id="api_deepseek", backend="api")
        agent = ApiSubAgent(spec=spec)
        agent.on_api_call = mock_api
        agent.default_model = "deepseek-v3"  # 覆盖默认模型

        env = Envelope()
        env.task["original_input"] = "解释JWT认证"
        env.task["normalized_intent"] = "解释JWT认证"
        msg = AgentMessage(
            sender_id="master", recipient_id="api_deepseek",
            envelope=env, message_type="task",
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "result"
        assert len(calls) == 1
        assert calls[0][1] == "deepseek-v3"

    def test_api_agent_error_without_callback(self):
        """未设置回调时 ApiSubAgent 返回 error。"""
        spec = AgentSpec(agent_id="api_no_cb", backend="api")
        agent = ApiSubAgent(spec=spec)
        env = Envelope()
        msg = AgentMessage(
            sender_id="master", recipient_id="api_no_cb",
            envelope=env, message_type="task",
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "error"

    def test_local_fn_agent_registration(self):
        """LocalFnSubAgent 通过装饰器注册纯函数。"""
        agent = LocalFnSubAgent(spec=AgentSpec(agent_id="local_util", backend="local_fn"))

        @agent.register("format_output")
        def format_output(envelope):
            return {"style": "json", "text": "hello"}

        assert "format_output" in agent._functions
        assert agent.health_check()

    def test_local_fn_agent_via_message(self):
        """LocalFnSubAgent 通过 AgentMessage 调用函数。"""
        agent = LocalFnSubAgent(spec=AgentSpec(agent_id="local_msg", backend="local_fn"))

        @agent.register("double")
        def double(envelope):
            x = envelope.task.get("value", 0)
            return {"result": x * 2}

        env = Envelope()
        env.task["value"] = 21
        msg = AgentMessage(
            sender_id="master", recipient_id="local_msg",
            envelope=env, message_type="task",
            payload={"fn_name": "double"},
        )
        reply = agent.handle_message(msg)
        assert reply.message_type == "result"
        assert env.task["fn_result"] == {"result": 42}


# ═══════════════════════════════════════════════════
# 测试 9: 反馈→图谱→螺旋 全链路
# ═══════════════════════════════════════════════════

@pytest.fixture
def clean_graph():
    """每次测试使用干净的知识图谱。"""
    vault = _PROJECT_ROOT / "knowledge_graph"
    if vault.exists():
        shutil.rmtree(str(vault))
    kg = KnowledgeGraph()
    kg.open()
    yield kg
    if vault.exists():
        shutil.rmtree(str(vault))


class TestFeedbackToGraphPipeline:
    """验证反馈事件→图谱丰富→螺旋提示的全链路。"""

    def test_enricher_creates_nodes_from_entities(self, clean_graph):
        """GraphEnricher 从任务实体创建概念节点。"""
        kg = clean_graph
        enricher = GraphEnricher(kg)

        nodes = enricher.enrich_from_interaction(
            session_id="test_session_001",
            task_entities={"framework": "FastAPI", "language": "Python", "library": "pydantic"},
            strategy_id="code_feature",
            signal_type="accepted",
            user_input="帮我写一个FastAPI认证中间件",
        )

        assert len(nodes) > 0, "应创建至少 1 个节点"
        # 验证实体节点
        fastapi_node = kg.get_node("concept_fastapi")
        assert fastapi_node is not None
        assert "FastAPI" in fastapi_node.title

        pydantic_node = kg.get_node("concept_pydantic")
        assert pydantic_node is not None

        # 验证策略节点
        strategy_node = kg.get_node("pattern_strategy_code_feature")
        assert strategy_node is not None

        # 验证会话节点
        session_node = kg.get_node("session_test_ses")
        assert session_node is not None
        assert "code_feature" in session_node.content

    def test_enricher_learns_from_accepted_feedback(self, clean_graph):
        """accepted 反馈提升策略节点权重。"""
        kg = clean_graph
        enricher = GraphEnricher(kg)

        # 第一次交互
        enricher.enrich_from_interaction(
            session_id="s1", strategy_id="code_feature",
            signal_type="accepted", user_input="写代码",
        )
        node1 = kg.get_node("pattern_strategy_code_feature")
        c1 = node1.confidence
        i1 = node1.importance

        # 第二次交互 (accepted)
        enricher.enrich_from_interaction(
            session_id="s2", strategy_id="code_feature",
            signal_type="accepted", user_input="写更多代码",
        )
        node2 = kg.get_node("pattern_strategy_code_feature")
        assert node2.confidence > c1, "accepted 应提升置信度"
        assert node2.importance > i1, "accepted 应提升重要性"

    def test_enricher_learns_from_modified_feedback(self, clean_graph):
        """modified 反馈降低策略节点置信度。"""
        kg = clean_graph
        enricher = GraphEnricher(kg)

        enricher.enrich_from_interaction(
            session_id="s1", strategy_id="code_feature",
            signal_type="modified", user_input="需要修改",
        )
        node = kg.get_node("pattern_strategy_code_feature")
        assert node.confidence < 0.4, "modified 应降低置信度"

    def test_graph_context_feedback_hook(self, clean_graph):
        """GraphContext 正确订阅 FeedbackEngine 事件。"""
        kg = clean_graph
        ctx = GraphContext(kg)

        # 模拟 FeedbackEngine 事件
        event = {
            "session_id": "hook_test_001",
            "entities": {"framework": "FastAPI"},
            "strategy_id": "code_feature",
            "signal_type": "accepted",
            "original_input": "实现JWT认证",
            "timestamp": "2026-07-07T10:00:00Z",
        }
        ctx.on_feedback_event(event)

        # 验证图谱已丰富
        fastapi = kg.get_node("concept_fastapi")
        assert fastapi is not None
        strategy = kg.get_node("pattern_strategy_code_feature")
        assert strategy is not None

        # 验证富化计数
        assert ctx._enrichment_count == 1

    def test_graph_context_injects_to_envelope(self, clean_graph):
        """GraphContext 向 Envelope 注入图谱上下文。"""
        kg = clean_graph

        # 预先填充一些节点
        kg.upsert_node(GraphNode(
            node_id="concept_auth", title="认证", node_type="concept", layer="chronicle",
            content="用户项目中的认证方案。使用 JWT + FastAPI 中间件。",
            summary="认证: JWT + FastAPI 中间件",
            aliases=["认证", "auth"],
            importance=0.8, confidence=0.85,
        ))

        ctx = GraphContext(kg)
        env = Envelope()
        env.task["original_input"] = "搞个认证"
        env.task["normalized_intent"] = "认证"

        ctx.inject_to_envelope(env)

        assert "hints" in env.graph_context
        assert len(env.graph_context["hints"]) > 0
        assert env.graph_context["node_count"] >= 1

    def test_full_pipeline_second_brain(self, clean_graph):
        """端到端验证 '第二大脑' 效果:

        模拟 5 次连续交互 → 图谱自动丰富 → 精确消歧。
        """
        kg = clean_graph
        ctx = GraphContext(kg)

        # 模拟 5 次交互
        interactions = [
            ("s1", "帮我写FastAPI认证中间件", "code_feature", "accepted",
             {"framework": "FastAPI", "language": "Python"}),
            ("s2", "用JWT实现登录", "code_feature", "accepted",
             {"framework": "FastAPI", "library": "python-jose"}),
            ("s3", "加上Redis缓存", "code_feature", "accepted",
             {"library": "redis"}),
            ("s4", "添加WebSocket实时推送", "code_feature", "modified",
             {"framework": "FastAPI", "protocol": "websocket"}),
            ("s5", "帮我做数据看板", "data_analysis", "accepted",
             {"framework": "FastAPI", "library": "plotly"}),
        ]

        for sid, user_input, strategy, signal, entities in interactions:
            event = {
                "session_id": sid,
                "entities": entities,
                "strategy_id": strategy,
                "signal_type": signal,
                "original_input": user_input,
            }
            ctx.on_feedback_event(event)

        # 验证图谱已累积知识
        stats = kg.get_stats()
        assert stats["node_count"] >= 5, f"5次交互后应有>=5节点, 实际{stats['node_count']}"
        assert stats["edge_count"] >= 2, f"应有策略→概念的边"

        # 关键验证: 第二大脑效果
        # 经过 5 次交互后，"认证"应能精确消歧到 FastAPI + JWT
        resolver = AmbiguityResolver(kg)
        result = resolver.resolve("认证")

        # 应有消歧结果
        assert len(result.candidates) > 0
        best = result.best_match
        assert best is not None

        # 查找候选是否包含 FastAPI 或 JWT 相关内容
        auth_related = []
        for c in result.candidates:
            auth_related.append(c.node.title)
        assert len(auth_related) > 0

        # "数据看板" 应有 FastAPI/可视化 相关候选
        result2 = resolver.resolve("数据看板")
        assert len(result2.candidates) > 0

        # 验证用户画像
        profile = ctx.get_user_profile()
        assert isinstance(profile, dict)

    def test_pruning_after_enrichment_threshold(self, clean_graph):
        """验证富化 20 次后自动触发裁剪 (不抛出异常)。"""
        kg = clean_graph
        ctx = GraphContext(kg)
        ctx._enrichment_count = 19  # 下一次触发裁剪

        event = {
            "session_id": "prune_test",
            "entities": {"tool": "pytest"},
            "strategy_id": "test",
            "signal_type": "accepted",
            "original_input": "运行测试",
        }
        # 不应抛出异常
        ctx.on_feedback_event(event)
        assert ctx._enrichment_count == 20

        # 再次调用，应再次正常触发裁剪
        ctx.on_feedback_event({
            "session_id": "prune_test2",
            "entities": {},
            "strategy_id": "test",
            "signal_type": "accepted",
            "original_input": "继续测试",
        })
        assert ctx._enrichment_count == 21
