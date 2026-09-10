"""
Knowledge Graph — 跨会话知识图谱 ("第二大脑")。

仿 Obsidian vault 架构:
- 节点以独立 JSON 文件存储，内容支持 [[wikilinks]] 双向链接
- 三层分区: canon(不可变正典) / chronicle(编年) / draft(草稿)
- 自动丰富：每次交互后提取概念、创建节点、强化边
- 歧义消解：模糊概念沿图谱遍历找到精确意图
"""

from agent_harness.knowledge.graph_node import GraphNode
from agent_harness.knowledge.graph_edge import GraphEdge
from agent_harness.knowledge.storage import GraphStorage
from agent_harness.knowledge.knowledge_graph import KnowledgeGraph
from agent_harness.knowledge.ambiguity_resolver import AmbiguityResolver, AmbiguityResolution, ResolvedMeaning
from agent_harness.knowledge.enricher import GraphEnricher
from agent_harness.knowledge.pruner import GraphPruner

__all__ = [
    "GraphNode",
    "GraphEdge",
    "GraphStorage",
    "KnowledgeGraph",
    "AmbiguityResolver",
    "AmbiguityResolution",
    "ResolvedMeaning",
    "GraphEnricher",
    "GraphPruner",
]
