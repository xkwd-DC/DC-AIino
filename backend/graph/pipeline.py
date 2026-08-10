"""GraphRAG 管线编排 — 一键构建图谱索引 + 多模式查询。

入口:
    build_graph_index()  → 文档分块 → 实体/关系提取 → 图谱构建
                         → 社区检测 → 摘要生成 → 持久化

    query()              → 分类查询 → 路由到 global/local/basic
                         → 组装上下文 → LLM 生成回答
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config
from .community import detect_communities
from .extractor import extract_from_chunks
from .graph_builder import (
    aggregate_relationships,
    build_graph,
    graph_to_index,
    load_index,
    merge_entities,
    save_index,
)
from .models import GraphIndex, SearchResult
from .search import basic_search, classify_query, global_search, local_search

logger = logging.getLogger(__name__)


def _chunk_documents(docs_dir: Path | None = None) -> list[tuple[str, str]]:
    """加载文档并分块，返回 [(text, chunk_id), ...]。

    使用图谱专用大块参数 (2000 chars)。
    """
    from rag.chunker import chunk_documents as rag_chunk_documents
    from rag.document_loader import load_all_documents

    docs_dir = Path(docs_dir) if docs_dir else config.DOCS_DIR
    documents = load_all_documents(docs_dir)

    if not documents:
        logger.warning("文档目录为空: %s", docs_dir)
        return []

    chunks = rag_chunk_documents(
        documents,
        chunk_size=config.GRAPH_CHUNK_SIZE,
        chunk_overlap=config.GRAPH_CHUNK_OVERLAP,
    )

    chunk_tuples = [
        (c.text, f"{c.source}:{c.chunk_index}:{c.page}")
        for c in chunks
    ]

    logger.info(
        "文档分块: %d 文档 → %d chunks (size=%d)",
        len(documents), len(chunk_tuples), config.GRAPH_CHUNK_SIZE,
    )
    return chunk_tuples


def build_graph_index(
    docs_dir: str | None = None,
    force: bool = False,
    progress_callback=None,
) -> GraphIndex:
    """全量构建知识图谱索引。

    流程:
        1. 加载文档 + 分块
        2. LLM 逐块提取实体/关系
        3. 实体合并 + 关系聚合 → NetworkX 图
        4. Louvain 社区检测
        5. LLM 社区摘要生成
        6. 持久化到 graph_data/graph_index.json

    Args:
        docs_dir: 文档目录（默认 config.DOCS_DIR）。
        force: 是否强制重建。
        progress_callback: 进度回调 (stage: str, current: int, total: int)。

    Returns:
        GraphIndex 对象。

    Raises:
        RuntimeError: 文档为空或提取无结果。
    """
    docs_path = Path(docs_dir) if docs_dir else config.DOCS_DIR

    # 已有索引则跳过（除非 force）
    if not force:
        existing = load_index()
        if existing is not None:
            logger.info("使用已有图谱索引: %s", existing.summary())
            return existing

    # ── Stage 1: 文档分块 ──
    logger.info("=== Stage 1/5: 文档分块 ===")
    chunks = _chunk_documents(docs_path)
    if not chunks:
        raise RuntimeError(f"文档目录无有效内容: {docs_path}")

    # ── Stage 2: 实体/关系提取 ──
    logger.info("=== Stage 2/5: 实体/关系提取 (%d 块) ===", len(chunks))

    def _extract_progress(current: int, total: int):
        if progress_callback:
            progress_callback("extracting", current, total)

    raw_entities, raw_relationships = extract_from_chunks(
        chunks, progress_callback=_extract_progress,
    )
    if not raw_entities:
        raise RuntimeError("未提取到任何实体，请检查文档内容或 API 连接")

    # ── Stage 3: 图谱构建 ──
    logger.info("=== Stage 3/5: 图谱构建 ===")
    if progress_callback:
        progress_callback("building_graph", 0, 1)

    entities = merge_entities(raw_entities)
    entity_names = {e.name for e in entities}
    relationships = aggregate_relationships(raw_relationships, entity_names)
    graph = build_graph(entities, relationships)

    if progress_callback:
        progress_callback("building_graph", 1, 1)

    # ── Stage 4: 社区检测 + 摘要 ──
    logger.info("=== Stage 4/5: 社区检测 + 摘要 ===")
    communities = detect_communities(graph)

    if progress_callback:
        progress_callback("summarizing", len(communities), len(communities))

    # ── Stage 5: 持久化 ──
    logger.info("=== Stage 5/5: 持久化 ===")
    if progress_callback:
        progress_callback("saving", 0, 1)

    source_files: list[str] = []
    for _, chunk_id in chunks:
        source = chunk_id.split(":")[0] if ":" in chunk_id else chunk_id
        if source not in source_files:
            source_files.append(source)

    index = graph_to_index(graph, entities, relationships, source_files, communities)
    save_index(index)

    if progress_callback:
        progress_callback("saving", 1, 1)

    logger.info("图谱索引构建完成! %s", index.summary())
    return index


def query(
    question: str,
    index: GraphIndex | None = None,
    top_k: int | None = None,
) -> dict:
    """GraphRAG 查询：自动路由 + 图谱搜索 + LLM 生成。

    Args:
        question: 用户问题。
        index: GraphIndex（为 None 时自动加载）。
        top_k: 检索数量。

    Returns:
        {"answer": str, "sources": list, "search_mode": str,
         "search_results": list, "tokens_used": int}
    """
    from .graph_builder import index_to_graph

    if index is None:
        index = load_index()
    if index is None:
        return {
            "answer": "图谱索引尚未构建。请先运行 build_graph_index()。",
            "sources": [],
            "search_mode": "none",
            "search_results": [],
        }

    graph = index_to_graph(index)

    # 分类 → 路由
    mode = classify_query(question)
    logger.info("查询路由: '%s' → %s", question[:60], mode)

    search_results: list[SearchResult] = []

    if mode == "global":
        search_results = global_search(question, index, top_k=top_k)
        if not search_results:
            mode = "local"
            search_results = local_search(question, index, graph, top_k=top_k)

    if mode == "local":
        search_results = local_search(question, index, graph, top_k=top_k)
        if not search_results:
            mode = "basic"

    if mode == "basic" or not search_results:
        search_results = basic_search(question, index, graph)
        mode = "basic"

    # 组装上下文
    top = top_k or config.GRAPH_SEARCH_TOP_K
    context = "\n\n---\n\n".join(r.content for r in search_results[:top])

    # LLM 生成
    from rag.generator import generate

    if mode == "global":
        context_header = (
            "以下是通过知识图谱社区检测发现的跨文档综合信息，"
            "请基于此回答综述型问题。\n\n"
        )
    elif mode == "local":
        context_header = (
            "以下是从知识图谱中沿实体关系遍历获取的关联信息，"
            "请基于此回答具体问题。\n\n"
        )
    else:
        context_header = "以下是与问题相关的参考信息。\n\n"

    answer, tokens = generate(question, context_header + context)

    sources = []
    for r in search_results:
        snippet = r.content[:200]
        sources.append({
            "type": r.source_type,
            "relevance": r.relevance,
            "snippet": snippet + "..." if len(r.content) > 200 else snippet,
        })

    return {
        "answer": answer,
        "sources": sources,
        "search_mode": mode,
        "search_results": [
            {"type": r.source_type, "relevance": r.relevance, "content": r.content}
            for r in search_results
        ],
        "tokens_used": tokens,
    }


def status() -> dict:
    """返回图谱索引状态。"""
    index = load_index()
    if index is None:
        return {"built": False, "index": None}

    return {
        "built": True,
        "index": {
            "version": index.version,
            "entity_count": index.entity_count,
            "relation_count": index.relation_count,
            "community_count": index.community_count,
            "source_files": len(index.source_files),
            "summary": index.summary(),
        },
    }
