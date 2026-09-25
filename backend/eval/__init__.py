"""检索评测模块 — 四档检索器的统一接口与指标计算。

用途:
    1. 论文实验表格（向量 / BM25 / 混合 / GraphRAG 四档对照 + 消融）
    2. 记忆系统可行性验证（把 wiki 注册成第二个 collection 复用同一套评测）

入口:
    python -m eval.runner --suite eval/suites/dc_rag_v1.json --systems vector,bm25,hybrid,graphrag
"""

from .metrics import aggregate, evaluate_item, ndcg_at_k, recall_at_k, reciprocal_rank

__all__ = [
    "aggregate",
    "evaluate_item",
    "ndcg_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
