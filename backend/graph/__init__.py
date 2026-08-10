"""GraphRAG 模块 — 基于知识图谱的检索增强生成。

提供与 rag/ 模块并行的图谱增强检索能力：
    - 实体/关系提取（DeepSeek LLM）
    - NetworkX 知识图谱构建
    - Louvain 社区检测 + 分层摘要
    - 多模式搜索（Global / Local / Basic）

用法:
    from graph import build_graph_index, query, status

    # 构建图谱索引（首次或强制重建）
    index = build_graph_index(force=True)

    # 查询
    result = query("华北平原小麦面临的主要气候风险有哪些？")
    print(result["answer"])

    # 状态
    print(status())
"""

from __future__ import annotations

from .models import Community, Entity, GraphIndex, Relationship, SearchResult
from .pipeline import build_graph_index, query, status

__all__ = [
    # 管线
    "build_graph_index",
    "query",
    "status",
    # 数据模型
    "Entity",
    "Relationship",
    "Community",
    "GraphIndex",
    "SearchResult",
]

__version__ = "0.1.0"
