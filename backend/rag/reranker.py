"""重排序模块 — BGE-Reranker Cross-Encoder 精排。

模型: BAAI/bge-reranker-v2-m3
    - Cross-encoder: query+document 联合编码，精度 > Bi-encoder
    - GPU 推理 ~10ms/对, CPU ~100ms/对
    - 自动检测 CUDA，支持 fp16 加速

流程: 粗排结果 (top_k*2) → Reranker 精排 → 输出 top_k
"""

from __future__ import annotations

import logging
import os

from . import config

logger = logging.getLogger(__name__)

# 复用 embedder 的 TF 禁用策略，避免 FlagEmbedding/transformers 探测 tensorflow 报错。
os.environ.setdefault("USE_TF", "0")

_RERANKER: "FlagReranker | None" = None  # type: ignore[name-defined]


def _get_reranker() -> "FlagReranker":  # type: ignore[name-defined]
    """Lazy load BGE-Reranker cross-encoder 模型。"""
    global _RERANKER
    if _RERANKER is None:
        if not config.RERANKER_ENABLED:
            raise RuntimeError("Reranker 已禁用")

        from FlagEmbedding import FlagReranker

        device = None
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
        except ImportError:
            pass

        logger.info("加载重排序模型 %s (device=%s)...", config.RERANKER_MODEL_NAME, device or "cpu")
        _RERANKER = FlagReranker(
            config.RERANKER_MODEL_NAME,
            use_fp16=(device == "cuda"),
            device=device,
        )
        logger.info("重排序模型就绪")

    return _RERANKER


def rerank(
    query: str,
    documents: list[str],
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """对候选文档进行 cross-encoder 重排序。

    Args:
        query: 用户问题。
        documents: 候选文档文本列表。
        top_k: 返回前 N 条。

    Returns:
        [(original_index, relevance_score), ...] 按分数降序。
    """
    if not documents:
        return []

    if not config.RERANKER_ENABLED:
        return [(i, 1.0) for i in range(min(len(documents), top_k or len(documents)))]

    top_k = top_k or config.RERANKER_TOP_N
    reranker = _get_reranker()

    pairs = [[query, doc] for doc in documents]

    try:
        scores = reranker.compute_score(pairs, normalize=True)

        if isinstance(scores, float):
            scores = [scores]

        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        result = indexed[:top_k]

        logger.info(
            "重排序: %d → %d (top=%.4f)",
            len(documents), len(result), result[0][1] if result else 0,
        )
        return result

    except Exception as exc:
        logger.error("重排序失败: %s，返回原始顺序", exc)
        return [(i, 1.0) for i in range(min(len(documents), top_k))]


def rerank_results(
    query: str,
    results: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    """对检索结果进行重排序（保持原有结构，增加 rerank_score 字段）。

    Args:
        query: 用户问题。
        results: 检索结果列表，每项含 "text" 字段。
        top_k: 返回前 N 条。

    Returns:
        重排序后的结果列表。
    """
    if not results:
        return []

    top_k = top_k or config.RERANKER_TOP_N
    documents = [r.get("text", "") for r in results]

    ranked = rerank(query, documents, top_k=min(top_k, len(documents)))

    reranked: list[dict] = []
    for original_idx, score in ranked:
        entry = dict(results[original_idx])
        entry["rerank_score"] = round(score, 4)
        entry["similarity"] = round(score, 4)
        reranked.append(entry)

    return reranked
