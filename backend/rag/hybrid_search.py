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

_bm25_index: BM25Okapi | None = None
_bm25_texts: list[str] | None = None
_bm25_ids: list[str] | None = None


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


def build_bm25_index(texts: list[str], ids: list[str]) -> None:
    """构建全局 BM25 关键词索引。

    Args:
        texts: 文档文本列表。
        ids: 对应的文档 ID 列表。
    """
    global _bm25_index, _bm25_texts, _bm25_ids

    tokenized = [_tokenize(t) for t in texts]
    _bm25_index = BM25Okapi(tokenized)
    _bm25_texts = texts
    _bm25_ids = ids
    logger.info("BM25 索引就绪: %d 文档", len(texts))


def _bm25_search(query: str, top_k: int = 10) -> list[tuple[str, float, str]]:
    """BM25 关键词检索。返回 [(doc_id, score, text), ...]。"""
    global _bm25_index, _bm25_texts, _bm25_ids

    if _bm25_index is None:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)

    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results: list[tuple[str, float, str]] = []
    for idx, score in indexed[:top_k]:
        if score > 0:
            results.append((_bm25_ids[idx], float(score), _bm25_texts[idx]))
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

    query_vec = embed_query(question)
    vector_results = vs_query(query_vec, top_k=top_k * 2, similarity_threshold=threshold)

    bm25_results = _bm25_search(question, top_k=top_k * 2)

    if bm25_results:
        fused = _rrf_fusion(vector_results, bm25_results, k=config.RRF_K)
        logger.info(
            "混合检索: vec=%d + bm25=%d → fused=%d",
            len(vector_results), len(bm25_results), len(fused),
        )
        return fused[:top_k]

    logger.info("混合检索: BM25 未就绪，回退向量 (vec=%d)", len(vector_results))
    return vector_results[:top_k]


def save_bm25_index(filepath: Path | None = None) -> None:
    """持久化 BM25 索引到 pickle。"""
    global _bm25_index, _bm25_texts, _bm25_ids

    filepath = Path(filepath) if filepath else config.CHROMA_DB_DIR / "bm25_index.pkl"
    if _bm25_index is None:
        return

    data = {"index": _bm25_index, "texts": _bm25_texts, "ids": _bm25_ids}
    with open(filepath, "wb") as f:
        pickle.dump(data, f)
    logger.info("BM25 索引已保存: %s", filepath)


def load_bm25_index(filepath: Path | None = None) -> bool:
    """从 pickle 加载 BM25 索引。"""
    global _bm25_index, _bm25_texts, _bm25_ids

    filepath = Path(filepath) if filepath else config.CHROMA_DB_DIR / "bm25_index.pkl"
    if not filepath.exists():
        return False

    try:
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        _bm25_index = data["index"]
        _bm25_texts = data["texts"]
        _bm25_ids = data["ids"]
        logger.info("BM25 索引已加载: %d 文档", len(_bm25_texts) if _bm25_texts else 0)
        return True
    except Exception as exc:
        logger.warning("BM25 索引加载失败: %s", exc)
        return False
