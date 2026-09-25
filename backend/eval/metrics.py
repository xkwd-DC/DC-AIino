"""检索指标 — Recall@k / MRR / nDCG@k（二值相关性）。

约定:
    - `gold` 与 `ranked` 里的元素都是"可比较的检索单元标识"（本项目用文档路径，
      见 schema.py 的文档级判定：不同检索器分块粒度不同，块级比较不成立）。
    - 重复命中只计一次（同一文档的多个 chunk 不该刷高召回）。
    - 空 gold 一律返回 0.0，而不是 1.0——避免无标注的条目把均值拉高。
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _dedup(ranked: Sequence[str]) -> list[str]:
    """保序去重。"""
    seen: set[str] = set()
    out: list[str] = []
    for doc in ranked:
        if doc in seen:
            continue
        seen.add(doc)
        out.append(doc)
    return out


def recall_at_k(gold: set[str], ranked: Sequence[str], k: int) -> float:
    """前 k 个结果命中了多少比例的 gold。"""
    if not gold:
        return 0.0
    top_k = _dedup(ranked)[:k]
    return len(gold.intersection(top_k)) / len(gold)


def reciprocal_rank(gold: set[str], ranked: Sequence[str]) -> float:
    """第一个命中项排名倒数。"""
    if not gold:
        return 0.0
    for rank, doc in enumerate(_dedup(ranked), start=1):
        if doc in gold:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(gold: set[str], ranked: Sequence[str], k: int) -> float:
    """二值相关性的 nDCG@k。"""
    if not gold:
        return 0.0
    top_k = _dedup(ranked)[:k]
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc in enumerate(top_k, start=1)
        if doc in gold
    )
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def evaluate_item(
    gold: set[str],
    ranked: Sequence[str],
    ks: Sequence[int] = (5, 10),
) -> dict[str, float]:
    """单个问题的全部指标。"""
    metrics: dict[str, float] = {}
    for k in ks:
        metrics[f"recall@{k}"] = recall_at_k(gold, ranked, k)
        metrics[f"ndcg@{k}"] = ndcg_at_k(gold, ranked, k)
    metrics["mrr"] = reciprocal_rank(gold, ranked)
    return metrics


def aggregate(per_item: list[dict[str, float]]) -> dict[str, float]:
    """跨问题求均值，附带有效条目数。"""
    if not per_item:
        return {"n_items": 0}

    keys = sorted({key for item in per_item for key in item})
    result = {
        key: sum(item.get(key, 0.0) for item in per_item) / len(per_item)
        for key in keys
    }
    result["n_items"] = len(per_item)
    return result
