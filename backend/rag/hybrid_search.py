"""混合检索引擎 — BM25 关键词 + 向量语义 + RRF 融合。

原理:
    BM25 关键词：精准匹配专业术语（SPEI、SHAP、冬小麦…）
    向量语义：捕获同义/近义表达
    RRF (Reciprocal Rank Fusion)：融合两种排名，无需分数归一化

持久化: BM25 索引可存为 pickle，重启后加载加速。
"""

from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from . import config

logger = logging.getLogger(__name__)

# 按集合名隔离的 BM25 索引（支持全库 / 论文独立收藏）
_BM25_STORES: dict[str, dict] = {}


def _tokenize(text: str) -> list[str]:
    """中英文混合分词：中文用字符 unigram+bigram，英文用单词。

    这种策略简单但有效，特别适合中文专业术语匹配。
    """
    tokens: list[str] = []
    segments = re.split(r'[^一-鿿\w]+', text.lower())

    for seg in segments:
        if not seg:
            continue
        chinese_chars = sum(1 for c in seg if '一' <= c <= '鿿')
        if chinese_chars > len(seg) * 0.5:
            chars = list(seg)
            tokens.extend(chars)
            for i in range(len(chars) - 1):
                tokens.append(chars[i] + chars[i + 1])
        else:
            tokens.append(seg)

    return tokens


def build_bm25_index(
    texts: list[str],
    ids: list[str],
    collection_name: str | None = None,
) -> None:
    """构建指定集合的 BM25 关键词索引。

    Args:
        texts: 文档文本列表。
        ids: 对应的文档 ID 列表。
        collection_name: 集合名（默认 dc_knowledge）。
    """
    global _BM25_STORES
    collection_name = collection_name or config.COLLECTION_NAME

    tokenized = [_tokenize(t) for t in texts]
    _BM25_STORES[collection_name] = {
        "index": BM25Okapi(tokenized),
        "texts": texts,
        "ids": ids,
    }
    logger.info("BM25 索引就绪: %d 文档", len(texts))


def _bm25_search(
    query: str,
    top_k: int = 10,
    collection_name: str | None = None,
) -> list[tuple[str, float, str]]:
    """BM25 关键词检索。返回 [(doc_id, score, text), ...]。"""
    global _BM25_STORES
    collection_name = collection_name or config.COLLECTION_NAME
    store = _BM25_STORES.get(collection_name)

    if store is None:
        if not load_bm25_index(collection_name=collection_name):
            return []
        store = _BM25_STORES[collection_name]

    tokenized_query = _tokenize(query)
    scores = store["index"].get_scores(tokenized_query)

    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results: list[tuple[str, float, str]] = []
    for idx, score in indexed[:top_k]:
        if score > 0:
            results.append((store["ids"][idx], float(score), store["texts"][idx]))
    return results


def _rrf_fusion(
    vector_results: list[dict],
    bm25_results: list[tuple[str, float, str]],
    k: int = 60,
) -> list[dict]:
    """RRF 融合：score(d) = Σ 1/(k + rank_i(d))。

    不依赖原始分数量纲，自动平衡向量和关键词贡献。
    """
    rrf_scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}

    # 向量 rank
    for rank, r in enumerate(vector_results, 1):
        doc_id = r.get("id", "")
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)
        doc_data[doc_id] = {
            "id": doc_id,
            "text": r.get("text", ""),
            "metadata": r.get("metadata", {}),
            "similarity": r.get("similarity", 0),
        }

    # BM25 rank
    for rank, (doc_id, _, text) in enumerate(bm25_results, 1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (k + rank)
        if doc_id not in doc_data:
            doc_data[doc_id] = {
                "id": doc_id, "text": text,
                "metadata": {}, "similarity": 0,
            }

    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results: list[dict] = []
    for doc_id, rrf_score in sorted_ids:
        entry = dict(doc_data[doc_id])
        entry["rrf_score"] = round(rrf_score, 6)
        entry["similarity"] = round(rrf_score * 100, 4)
        results.append(entry)

    return results


def hybrid_retrieve(
    question: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    collection_name: str | None = None,
) -> list[dict]:
    """混合检索：BM25 关键词 + 向量语义 + RRF 融合。

    BM25 未构建时自动回退纯向量检索。
    """
    from .embedder import embed_query
    from .vector_store import query as vs_query

    top_k = top_k or config.TOP_K
    threshold = similarity_threshold or config.SIMILARITY_THRESHOLD

    if not question.strip():
        return []

    bm25_results = _bm25_search(question, top_k=top_k * 2, collection_name=collection_name)
    try:
        query_vec = embed_query(question)
    except (MemoryError, RuntimeError, OSError, ImportError) as exc:
        if not bm25_results:
            raise
        logger.warning("向量嵌入不可用，使用 BM25 关键词检索: %s", exc)
        fallback = [
            {"id": doc_id, "text": text, "metadata": {}, "similarity": 0,
             "bm25_score": score, "retrieval_mode": "bm25"}
            for doc_id, score, text in bm25_results
        ]
        return _restore_metadata(fallback, collection_name)[:top_k]

    vector_results = vs_query(
        query_vec,
        top_k=top_k * 2,
        similarity_threshold=threshold,
        collection_name=collection_name,
    )

    if bm25_results:
        fused = _rrf_fusion(vector_results, bm25_results, k=config.RRF_K)
        fused = _restore_metadata(fused, collection_name)
        for hit in fused:
            hit["retrieval_mode"] = "hybrid"
        logger.info(
            "混合检索: vec=%d + bm25=%d → fused=%d",
            len(vector_results), len(bm25_results), len(fused),
        )
        return fused[:top_k]

    logger.info("混合检索: BM25 未就绪，回退向量 (vec=%d)", len(vector_results))
    for hit in vector_results:
        hit["retrieval_mode"] = "vector"
    return vector_results[:top_k]


def _restore_metadata(results: list[dict], collection_name: str | None) -> list[dict]:
    """从当前向量集合补齐关键词命中的来源，并剔除旧 BM25 中已删除的块。"""
    from .vector_store import _get_collection

    missing = [r["id"] for r in results if not r.get("metadata")]
    if not missing:
        return results
    rows = _get_collection(collection_name).get(ids=missing, include=["metadatas"])
    metadata = dict(zip(rows["ids"], rows["metadatas"]))
    restored = []
    for hit in results:
        if not hit.get("metadata"):
            if hit["id"] not in metadata:
                continue
            hit["metadata"] = metadata[hit["id"]]
        restored.append(hit)
    return restored


def save_bm25_index(filepath: Path | None = None, collection_name: str | None = None) -> None:
    """持久化 BM25 索引到 pickle（按集合名分文件）。"""
    global _BM25_STORES
    collection_name = collection_name or config.COLLECTION_NAME
    store = _BM25_STORES.get(collection_name)

    filepath = (
        Path(filepath)
        if filepath
        else config.CHROMA_DB_DIR / f"bm25_{collection_name}.pkl"
    )
    if store is None:
        return

    data = store
    with open(filepath, "wb") as f:
        pickle.dump(data, f)
    logger.info("BM25 索引已保存: %s", filepath)


def load_bm25_index(filepath: Path | None = None, collection_name: str | None = None) -> bool:
    """从 pickle 加载 BM25 索引（按集合名分文件）。"""
    global _BM25_STORES
    collection_name = collection_name or config.COLLECTION_NAME

    filepath = (
        Path(filepath)
        if filepath
        else config.CHROMA_DB_DIR / f"bm25_{collection_name}.pkl"
    )
    if not filepath.exists():
        return False

    try:
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        _BM25_STORES[collection_name] = data
        logger.info("BM25 索引已加载: %d 文档", len(data.get("texts") or []))
        return True
    except Exception as exc:
        logger.warning("BM25 索引加载失败: %s", exc)
        return False
