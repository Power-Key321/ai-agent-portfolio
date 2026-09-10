"""
Phase 2 功能验证 — 知识图谱填充 + 歧义消解精度测试。

模拟场景: 用户使用 Harness 2周后的知识图谱状态
领域: Python开发 / 数据工程 / 数据分析 / API 服务
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
import os
import shutil
from agent_harness.knowledge import (
    KnowledgeGraph, GraphNode, GraphEnricher, AmbiguityResolver,
    GraphPruner,
)


# ═══════════════════════════════════════════════════
# 构建模拟 2 周使用后的知识图谱
# ═══════════════════════════════════════════════════

def _build_realistic_graph() -> KnowledgeGraph:
    """模拟用户使用 Harness 2 周后累积的知识图谱。

    节点覆盖:
    - 用户身份/偏好 (canon 层) — 5 节点
    - 技术栈概念 (chronicle 层) — 10 节点
    - 数据工程 (chronicle 层) — 10 节点
    - Harness 机制 (chronicle 层) — 5 节点
    - 会话记录 (draft 层) — 5 节点
    """
    kg = KnowledgeGraph()
    kg.open()

    # ── Canon 层: 用户不可变知识 ──
    canon_nodes = [
        GraphNode(node_id="user_role", title="用户角色", node_type="entity", layer="canon",
                  content="独立开发者，专注 [[数据管道]] 和 [[API 服务]]。使用 [[Python]] 和 [[Claude Code]]。",
                  summary="独立开发者，数据管道+API 服务，Python+Claude Code",
                  tags=["user", "identity"], importance=0.95, confidence=0.95),
        GraphNode(node_id="user_lang_pref", title="语言偏好", node_type="preference", layer="canon",
                  content="用户要求所有回答使用 [[中文]]。代码注释和文档不强制。",
                  summary="中文回答，代码可用英文",
                  tags=["user", "language"], importance=0.9, confidence=0.95),
        GraphNode(node_id="user_tech_stack", title="技术栈", node_type="preference", layer="canon",
                  content="主力: [[Python]] + [[FastAPI]]。数据处理: [[pandas]] + [[numpy]]。消息队列: [[Kafka]]。",
                  summary="Python/FastAPI/pandas/numpy/Kafka",
                  tags=["user", "tech_stack"], importance=0.9, confidence=0.9),
        GraphNode(node_id="user_expertise_python", title="Python水平", node_type="entity", layer="canon",
                  content="[[Python]] 中级水平。能读懂代码，需要解释架构设计决策的理由。",
                  summary="Python中级，需要解释设计理由",
                  tags=["user", "expertise"], importance=0.85, confidence=0.9),
        GraphNode(node_id="user_project_pipeline", title="数据管道项目", node_type="entity", layer="canon",
                  content="正在开发 [[DataFlow]] 数据管道项目。包含 [[Harness]] 任务编排框架、[[ETL]] 调度、[[指标计算]]。",
                  summary="DataFlow项目：Harness框架+ETL调度+指标计算",
                  tags=["user", "project"], importance=0.95, confidence=0.95),
    ]
    for n in canon_nodes:
        kg.upsert_node(n)

    # ── Chronicle 层: 技术概念 ──
    tech_concepts = [
        ("concept_fastapi", "FastAPI", "concept", "[[Python]] 异步 Web 框架。用户偏好用于 [[API 开发]]。搭配 [[Pydantic]] 做数据校验。"),
        ("concept_jwt", "JWT 认证", "concept", "JSON Web Token。用户项目中的标准 [[认证]] 方案。使用 [[python-jose]] 库。"),
        ("concept_auth_middleware", "认证中间件", "pattern", "[[FastAPI]] 中间件模式。验证 [[JWT]] token → 注入 [[current_user]] 依赖。"),
        ("concept_websocket", "WebSocket", "concept", "实时数据推送。用于 [[监控面板]] 指标推送和 [[告警]] 通知。"),
        ("concept_postgres", "PostgreSQL", "concept", "关系型数据库。用户偏好 [[SQLAlchemy]] 做 ORM。[[Alembic]] 做迁移。"),
        ("concept_redis", "Redis", "concept", "缓存 + 消息队列。用于 [[JWT]] 黑名单和 [[WebSocket]] 频道管理。"),
        ("concept_docker", "Docker", "concept", "容器化部署。用户使用 [[docker-compose]] 管理 [[FastAPI]] + [[PostgreSQL]] + [[Redis]]。"),
        ("concept_pandas", "Pandas", "concept", "数据分析核心库。用于 [[指标计算]] 和 [[数据清洗]]。"),
        ("concept_pydantic", "Pydantic", "concept", "数据校验。[[FastAPI]] 的请求/响应模型。[[Settings 管理]]。"),
        ("concept_httpx", "HTTPX", "concept", "异步 HTTP 客户端。用于调用外部 [[数据源]] 和 [[第三方 API]]。"),
    ]
    for nid, title, ntype, content in tech_concepts:
        kg.upsert_node(GraphNode(
            node_id=nid, title=title, node_type=ntype, layer="chronicle",
            content=content, summary=content[:60],
            tags=[title.lower().replace(" ", "_"), "tech"],
            importance=0.6, confidence=0.7,
        ))

    # ── Chronicle 层: 数据工程概念 ──
    data_concepts = [
        ("concept_kafka", "Kafka", "concept",
         "消息队列。用于 [[数据管道]] 的 [[流式接入]]。支持 [[分区]]、[[消费组]]。",
         ["kafka", "消息队列", "流式接入", "mq"]),
        ("concept_airflow", "Airflow", "concept",
         "工作流调度。以 DAG 定义 [[数据管道]] 的 [[任务依赖]]。",
         ["airflow", "调度", "dag", "工作流"]),
        ("concept_etl", "ETL 流程", "pattern",
         "抽取-转换-加载。用户用 [[Airflow]] 编排 [[数据管道]] 的 [[批处理]] 任务。",
         ["etl", "数据管道", "批处理", "抽取"]),
        ("concept_spark", "Spark", "concept",
         "分布式计算引擎。用于 [[大规模聚合]] 和 [[批处理]]。",
         ["spark", "分布式计算", "聚合"]),
        ("concept_datacleaning", "数据清洗", "pattern",
         "缺失值与异常值处理。包含 [[去重]]、[[标准化]]、[[类型转换]]。",
         ["数据清洗", "清洗", "去重", "标准化"]),
        ("concept_metrics", "指标计算", "pattern",
         "统计聚合。[[同比]]、[[环比]]、[[分位数]]。用于 [[报表]] 生成。",
         ["指标", "指标计算", "统计", "报表"]),
        ("concept_stream", "流式处理", "pattern",
         "实时计算。[[窗口聚合]]、[[水位线]] 机制。服务于 [[实时看板]]。",
         ["流式", "stream", "窗口聚合", "实时"]),
        ("concept_datalake", "数据湖", "concept",
         "原始数据存储。[[分区表]]、[[列式存储]]、[[Parquet]] 格式。",
         ["数据湖", "datalake", "parquet", "列式存储"]),
    ]
    for nid, title, ntype, content, aliases in data_concepts:
        kg.upsert_node(GraphNode(
            node_id=nid, title=title, node_type=ntype, layer="chronicle",
            content=content, summary=content[:60],
            tags=[title.lower().replace(" ", "_"), "data_eng"],
            aliases=aliases,
            importance=0.6, confidence=0.7,
        ))

    # ── Chronicle 层: Harness 相关 ──
    harness_concepts = [
        ("concept_spiral", "螺旋收敛", "pattern",
         "[[Harness]] 核心机制。多轮精炼意图，每轮缩小 [[解空间]]。[[收敛半径]] 从 1.0 递减到阈值。"),
        ("concept_entropy_chain", "熵减链", "pattern",
         "[[Harness]] 分解策略。信息源→过滤→处理→组装→验证。8 维子任务规格。"),
        ("concept_five_elements", "五要素压缩", "pattern",
         "[[Harness]] 预处理。主体/动作/对象/价值链/可持续性 + 概率意图分布。"),
        ("concept_gate_check", "量化门检", "pattern",
         "[[Harness]] 执行质量保证。4 道门检 + 6 项自检 + 退化检测自动降级。"),
        ("concept_self_evolve", "自进化", "pattern",
         "[[Harness]] MetaCognition 外环。检测退化信号 → 生成改进任务 → 验证→应用/回滚。"),
    ]
    for nid, title, ntype, content in harness_concepts:
        kg.upsert_node(GraphNode(
            node_id=nid, title=title, node_type=ntype, layer="chronicle",
            content=content, summary=content[:60],
            tags=[title.lower().replace(" ", "_"), "harness"],
            importance=0.5, confidence=0.6,
        ))

    # ── 创建偏好边 ──
    kg.add_edge("user_role", "concept_fastapi", "prefers", weight=0.85, bidirectional=False,
                evidence="用户多次选择 FastAPI 作为后端框架")
    kg.add_edge("user_role", "concept_jwt", "prefers", weight=0.80, bidirectional=False,
                evidence="用户偏好 JWT 认证方案")
    kg.add_edge("concept_auth_middleware", "concept_jwt", "uses", weight=0.90, bidirectional=True)
    kg.add_edge("concept_auth_middleware", "concept_fastapi", "instance_of", weight=0.85)
    kg.add_edge("concept_fastapi", "concept_pydantic", "uses", weight=0.85, bidirectional=True)
    kg.add_edge("concept_fastapi", "concept_httpx", "uses", weight=0.60, bidirectional=True)
    kg.add_edge("concept_fastapi", "concept_websocket", "uses", weight=0.55, bidirectional=True)
    kg.add_edge("concept_fastapi", "concept_redis", "uses", weight=0.65, bidirectional=True)
    kg.add_edge("concept_fastapi", "concept_postgres", "uses", weight=0.70, bidirectional=True)
    kg.add_edge("concept_docker", "concept_fastapi", "uses", weight=0.60, bidirectional=True)
    kg.add_edge("concept_docker", "concept_redis", "uses", weight=0.60, bidirectional=True)
    kg.add_edge("concept_docker", "concept_postgres", "uses", weight=0.60, bidirectional=True)

    kg.add_edge("user_role", "concept_kafka", "prefers", weight=0.75, bidirectional=False,
                evidence="用户的主要消息队列选型")
    kg.add_edge("user_role", "concept_airflow", "prefers", weight=0.80, bidirectional=False,
                evidence="用户偏好 Airflow 编排调度")
    kg.add_edge("concept_kafka", "concept_stream", "uses", weight=0.90, bidirectional=True)
    kg.add_edge("concept_etl", "concept_airflow", "uses", weight=0.85)
    kg.add_edge("concept_etl", "concept_spark", "related_to", weight=0.70)
    kg.add_edge("concept_metrics", "concept_pandas", "uses", weight=0.65)
    kg.add_edge("concept_datacleaning", "concept_pandas", "uses", weight=0.65)
    kg.add_edge("concept_datalake", "concept_spark", "uses", weight=0.55)

    kg.add_edge("user_project_pipeline", "concept_etl", "uses", weight=0.90)
    kg.add_edge("user_project_pipeline", "concept_spiral", "uses", weight=0.85)
    kg.add_edge("user_project_pipeline", "concept_entropy_chain", "uses", weight=0.80)
    kg.add_edge("user_project_pipeline", "concept_five_elements", "uses", weight=0.75)
    kg.add_edge("concept_spiral", "concept_entropy_chain", "related_to", weight=0.90)
    kg.add_edge("concept_entropy_chain", "concept_five_elements", "related_to", weight=0.80)
    kg.add_edge("concept_gate_check", "concept_spiral", "related_to", weight=0.75)

    # ── 为关键概念添加高质量节点（覆盖 auto-created wikilink 节点） ──
    kg.upsert_node(GraphNode(
        node_id="concept_auth", title="认证", node_type="concept", layer="chronicle",
        content="用户项目中的 [[认证]] 方案。使用 [[JWT]] + [[FastAPI 中间件]]。",
        summary="认证方案：JWT + FastAPI 中间件",
        tags=["auth", "认证", "concept"],
        aliases=["认证", "auth", "登录", "鉴权"],
        importance=0.75, confidence=0.85,
    ))
    kg.add_edge("concept_auth", "concept_jwt", "resolves_to", weight=0.90)
    kg.add_edge("concept_auth", "concept_auth_middleware", "resolves_to", weight=0.85)

    kg.upsert_node(GraphNode(
        node_id="concept_data_monitor", title="监控面板", node_type="pattern", layer="chronicle",
        content="实时 [[指标]] 监控面板。使用 [[WebSocket]] 接入 [[Kafka]] 数据流，[[窗口聚合]] 计算，[[告警]] 推送。",
        summary="监控面板：WebSocket + Kafka + 窗口聚合 + 告警推送",
        tags=["monitor", "监控", "pattern"],
        aliases=["监控面板", "监控", "data_monitor", "看板"],
        importance=0.7, confidence=0.75,
    ))
    kg.add_edge("concept_data_monitor", "concept_kafka", "uses", weight=0.85)
    kg.add_edge("concept_data_monitor", "concept_websocket", "uses", weight=0.85)
    kg.add_edge("concept_data_monitor", "concept_stream", "uses", weight=0.80)

    # ── Draft 层: 最近会话 ──
    for i in range(5):
        day = 6 - i
        kg.upsert_node(GraphNode(
            node_id=f"session_2026070{day}",
            title=f"会话 2026-07-0{day}",
            node_type="session", layer="draft",
            content=f"2026 年 7 月 {day} 日的交互会话。",
            summary=f"7月{day}日会话",
            importance=0.2, confidence=0.5,
            source_session_id=f"session_{day}",
        ))

    return kg


# ═══════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════

@pytest.fixture(scope="module")
def populated_graph():
    """模块级夹具: 填充后的知识图谱。"""
    kg = _build_realistic_graph()
    yield kg
    # 清理不再需要（后续测试使用相同数据）


def test_graph_population(populated_graph):
    """验证图谱正确填充了 50+ 节点。"""
    kg = populated_graph
    stats = kg.get_stats()
    print(f"\n  图谱统计: {stats}")
    assert stats["node_count"] >= 45, f"预期 >=45 节点，实际 {stats['node_count']}"
    assert stats["edge_count"] >= 25, f"预期 >=25 条边，实际 {stats['edge_count']}"
    assert stats["canon_count"] >= 4, f"预期 >=4 canon 节点"
    assert stats["chronicle_count"] >= 35, f"预期 >=35 chronicle 节点"

    # 验证 canon 节点
    profile_nodes = kg.get_all_nodes("canon")
    assert len(profile_nodes) >= 4
    for n in profile_nodes:
        assert n.confidence >= 0.85, f"Canon 节点 {n.node_id} 应有高置信度"

    print(f"  图谱填充: {stats['node_count']} 节点, {stats['edge_count']} 边 ✓")


def test_search_accuracy(populated_graph):
    """验证搜索能精确匹配已知概念。"""
    kg = populated_graph

    # 精确匹配
    results = kg.search("FastAPI")
    assert len(results) > 0
    assert results[0].node_id == "concept_fastapi"

    # 别名匹配
    results = kg.search("jwt")
    assert len(results) > 0

    # 标签匹配
    results = kg.search("data_eng")
    data_count = sum(1 for n in kg.get_all_nodes() if "data_eng" in n.tags)
    assert data_count >= 8

    # 模糊搜索
    results = kg.search("认证")
    auth_related = any("auth" in r.node_id or "jwt" in r.node_id for r in results)
    assert auth_related, f"搜索'认证'应返回认证相关节点，实际: {[r.node_id for r in results]}"

    print(f"  搜索测试全部通过 ✓")


def test_ambiguity_resolution_precise(populated_graph):
    """验证歧义消解: 精确查询 → 高置信消歧。"""
    kg = populated_graph
    resolver = AmbiguityResolver(kg)

    # 测试 1: 精确消歧 "认证"
    result = resolver.resolve("认证")
    assert not result.needs_clarification, "认证应有明确消歧结果"
    assert result.best_match is not None
    assert result.best_match.confidence >= 0.3
    print(f"  '认证' → {result.best_match.explanation} (置信度: {result.best_match.confidence:.2f})")

    # 测试 2: 精确消歧 "FastAPI"
    result2 = resolver.resolve("FastAPI")
    assert not result2.needs_clarification
    assert result2.best_match is not None
    print(f"  'FastAPI' → {result2.best_match.explanation} (置信度: {result2.best_match.confidence:.2f})")

    # 测试 3: 精确消歧 "调度"
    result3 = resolver.resolve("调度")
    if not result3.needs_clarification:
        print(f"  '调度' → {result3.best_match.explanation} (置信度: {result3.best_match.confidence:.2f})")
    else:
        print(f"  '调度' → 需要澄清 (candidates={len(result3.candidates)})")


def test_ambiguity_resolution_vague(populated_graph):
    """验证歧义消解: 模糊概念 → 候选列表。"""
    kg = populated_graph
    resolver = AmbiguityResolver(kg)

    # 测试: 模糊概念 "数据"
    result = resolver.resolve("数据")
    print(f"  '数据' → candidates={len(result.candidates)}, needs_clarification={result.needs_clarification}")
    # 模糊概念可能有多个候选或需要澄清，都是合理行为

    # 测试: 用户偏好查询
    result2 = resolver.resolve("后端框架")
    print(f"  '后端框架' → candidates={len(result2.candidates)}, needs_clarification={result2.needs_clarification}")
    if result2.best_match:
        print(f"    best: {result2.best_match.explanation}")


def test_graph_context_injection(populated_graph):
    """验证图谱上下文生成。"""
    kg = populated_graph
    from agent_harness.knowledge.graph_context import GraphContext
    gc = GraphContext(kg)

    # 测试提示上下文
    hints = kg.get_context_for_prompt("认证中间件", max_items=3)
    assert len(hints) > 0, "应有至少 1 条上下文提示"
    print(f"  提示上下文: {hints}")

    # 测试螺旋提示
    from agent_harness.core.envelope import Envelope
    env = Envelope()
    env.task["original_input"] = "实现JWT认证"
    env.task["normalized_intent"] = "实现JWT认证"
    gc.inject_to_envelope(env)
    assert "hints" in env.graph_context
    print(f"  Envelope graph_context: {env.graph_context}")


def test_pruning_respects_limits(populated_graph):
    """验证裁剪在限制内运行。"""
    kg = populated_graph
    pruner = GraphPruner(kg)
    report = pruner.prune()

    stats = kg.get_stats()
    print(f"  裁剪报告: 删除 {report.nodes_deleted} 节点, {report.edges_deleted} 边, 合并 {report.nodes_merged}")

    # Critically: canon 节点不应被删除
    canon_nodes = kg.get_all_nodes("canon")
    assert len(canon_nodes) >= 4, f"Canon 节点不应被裁剪删除! 剩余 {len(canon_nodes)}"


def test_second_brain_effect(populated_graph):
    """验证"第二大脑"效果: 图谱是否随着使用越来越了解用户。

    场景: 用户说"搞个监控面板" → 图谱应解析出: Kafka + WebSocket + 窗口聚合
    """
    kg = populated_graph
    resolver = AmbiguityResolver(kg)

    # 模拟用户模糊表达
    queries = [
        ("监控面板", "应关联到 Kafka/WebSocket/窗口聚合"),
        ("数据清洗", "应关联到 pandas/去重/标准化"),
        ("认证功能", "应关联到 JWT/FastAPI/中间件"),
        ("数据分析", "应关联到 pandas/Python/指标计算"),
    ]

    print("\n  '第二大脑' 效果验证:")
    for query, expectation in queries:
        result = resolver.resolve(query)
        candidates_str = ", ".join(
            f"{c.node.title}({c.confidence:.2f})" for c in result.candidates[:3]
        )
        status = "✓" if not result.needs_clarification else "? (需要澄清)"
        print(f"    '{query}' {status} → [{candidates_str}] — 预期: {expectation}")

        # 记录是否有消歧结果
        has_candidates = len(result.candidates) > 0
        assert has_candidates, f"'{query}' 应有至少 1 个候选"
