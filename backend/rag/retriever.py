"""检索引擎 — 混合检索 + 重排序 + 来源去重。

检索流水线:
    问题 → 混合检索（BM25 + 向量 + RRF）→ 重排序（Cross-Encoder）→ 去重
"""

from __future__ import annotations

import logging

from . import config
from .hybrid_search import hybrid_retrieve
from .reranker import rerank_results

logger = logging.getLogger(__name__)

_MAX_PER_SOURCE = 2  # 同一来源最多保留的 chunk 数


def retrieve(
    question: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    use_hybrid: bool = True,
    use_rerank: bool = True,
    collection_name: str | None = None,
) -> list[dict]:
    """检索与问题最相关的文档块。

    流程:
        1. 混合检索（BM25 + 向量 + RRF 融合）
        2. Reranker 重排序
        3. 来源去重保证多样性

    Args:
        question: 用户问题。
        top_k: 最终返回条数。
        similarity_threshold: 相似度阈值。
        use_hybrid: 是否启用混合检索。
        use_rerank: 是否启用重排序。

    Returns:
        list[dict]，每项含 id, text, metadata, similarity。
    """
    top_k = top_k or config.TOP_K
    threshold = similarity_threshold or config.SIMILARITY_THRESHOLD

    if not question.strip():
        return []

    # 1. 混合检索（取 top_k * 4 候选给 reranker）
    fetch_k = top_k * 4
    if use_hybrid:
        results = hybrid_retrieve(
            question,
            top_k=fetch_k,
            similarity_threshold=threshold,
            collection_name=collection_name,
        )
    else:
        from .embedder import embed_query
        from .vector_store import query as vs_query
        query_vec = embed_query(question)
        results = vs_query(
            query_vec,
            top_k=fetch_k,
            similarity_threshold=threshold,
            collection_name=collection_name,
        )

    if not results:
        return []

    # 2. 重排序
    if use_rerank and config.RERANKER_ENABLED:
        try:
            results = rerank_results(question, results, top_k=min(top_k * 2, len(results)))
        except Exception as exc:
            logger.warning("重排序跳过: %s", exc)

    # 3. 来源去重
    seen: dict[str, int] = {}
    deduped: list[dict] = []
    for r in results:
        meta = r.get("metadata", {})
        title = meta.get("title", "") or "__unknown__"
        if seen.get(title, 0) >= _MAX_PER_SOURCE:
            continue
        seen[title] = seen.get(title, 0) + 1
        deduped.append(r)
        if len(deduped) >= top_k:
            break

    logger.info(
        "检索: '%s' → %d (fetch=%d, hybrid=%s, rerank=%s)",
        question[:60], len(deduped), len(results),
        use_hybrid, use_rerank and config.RERANKER_ENABLED,
    )
    return deduped


def build_context(results: list[dict], max_chars: int = 3000) -> str:
    """将检索结果组装为 LLM 上下文。"""
    if not results:
        return "（未找到相关文档）"

    parts: list[str] = []
    char_count = 0

    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        source = meta.get("source", "未知")
        title = meta.get("title", "")

        header = (
            f"【来源 {i}】{title} ({source})" if title
            else f"【来源 {i}】{source}"
        )
        body = r.get("text", "")

        chunk_text = f"{header}\n{body}"
        if char_count + len(chunk_text) > max_chars and parts:
            remaining = max_chars - char_count
            if remaining > 200:
                parts.append(f"{header}\n{body[:remaining]}...")
            break

        parts.append(chunk_text)
        char_count += len(chunk_text)

    context = "\n\n---\n\n".join(parts)
    logger.info("上下文: %d 片段, ~%d chars", len(parts), char_count)
    return context
