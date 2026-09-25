"""检索器适配层 — 把四档检索器统一到 RetrievalHit 接口，供评测与消融复用。

档位（论文主表）:
    vector    纯稠密向量（BGE-M3）
    bm25      纯关键词（BM25Okapi）
    hybrid    BM25 + 向量 RRF 融合（生产默认，不重排）
    graphrag  混合召回 + 图谱展开 + RRF 融合 + BGE-Reranker 精排

消融档位:
    hybrid_rerank       混合 + 精排（等价于"去掉图谱"）
    graphrag_no_rerank  混合 + 图谱（等价于"去掉精排"）
    graphrag_no_bm25    向量 + 图谱 + 精排（等价于"去掉关键词"）

图谱通道的路由（一个明确的设计选择）:
    生产代码用 graph.search.classify_query() 在线路由 global/local，那需要每题一次
    额外的 LLM 调用。评测里改用题库自带的 query_type 做同样的路由——
    multi_hop → 社区摘要通道，其余 → 实体通道。这样路由可复现、省一次调用；
    global_search 内部的查询实体抽取仍然照常走 LLM，与线上一致。
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING

from .schema import RetrievalHit, normalize_doc

if TYPE_CHECKING:
    from graph.models import GraphIndex

logger = logging.getLogger(__name__)

RRF_K = 60

#: rag 侧用 `similarity_threshold or 默认值` 取值，传 0 会被当成"未设置"。
#: 评测要的是"不设阈值、固定取 top_k"，所以用一个极小正数。
_NO_THRESHOLD = 1e-6

#: 单个实体最多展开几个来源文档
_MAX_DOCS_PER_ENTITY = 3

#: multi_hop 走社区通道时，每个社区最多取几个实体去展开
_MAX_ENTITIES_PER_COMMUNITY = 8

#: 图谱通道取几个社区
_GRAPH_TOP_K = 3


# ─── 纯函数 ───────────────────────────────────────────────────────────────

def rrf_merge(hit_lists: list[list[RetrievalHit]], k: int = RRF_K) -> list[RetrievalHit]:
    """Reciprocal Rank Fusion：把多路召回按文档排名融合。

    在**文档级**做融合，因为四档检索器的分块粒度不同，块级排名不可比。
    """
    scores: dict[str, float] = defaultdict(float)
    first_hit: dict[str, RetrievalHit] = {}

    for hits in hit_lists:
        seen: set[str] = set()
        rank = 0
        for hit in hits:
            doc = hit.doc
            if not doc or doc in seen:
                continue
            seen.add(doc)
            rank += 1
            scores[doc] += 1.0 / (k + rank)
            first_hit.setdefault(doc, hit)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [replace(first_hit[doc], score=score) for doc, score in ordered]


def graph_expand_docs(
    index: "GraphIndex",
    entity_names: list[str],
    max_docs_per_entity: int = _MAX_DOCS_PER_ENTITY,
) -> list[RetrievalHit]:
    """把命中的实体展开成来源文档（文档级召回）。

    一个实体的 `source_chunks` 里同一个文档可能出现多次，出现次数即该文档
    对这个实体的支撑强度，据此排序。
    """
    by_name = {(e.name or "").strip().lower(): e for e in index.entities}
    hits: list[RetrievalHit] = []
    seen: set[str] = set()

    for name in entity_names:
        entity = by_name.get((name or "").strip().lower())
        if entity is None:
            continue

        counts = Counter(normalize_doc(c) for c in (entity.source_chunks or []))
        counts.pop("", None)
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

        for doc, mentions in ranked[:max_docs_per_entity]:
            if doc in seen:
                continue
            seen.add(doc)
            hits.append(
                RetrievalHit(
                    chunk_id=f"graph:{entity.name}:{doc}",
                    source=doc,
                    score=float(mentions),
                    text=entity.description or entity.name,
                )
            )

    return hits


# ─── 基类与单路检索器 ─────────────────────────────────────────────────────

def _row_to_hit(row: dict) -> RetrievalHit:
    """把 rag 模块的检索结果 dict 转成 RetrievalHit。"""
    meta = row.get("metadata") or {}
    chunk_id = str(row.get("id", ""))
    return RetrievalHit(
        chunk_id=chunk_id,
        source=meta.get("source") or chunk_id,
        score=float(row.get("similarity", 0.0) or 0.0),
        text=row.get("text", "") or "",
    )


class VectorRetriever:
    """纯稠密向量检索。"""

    name = "vector"

    def __init__(self, collection_name: str | None = None) -> None:
        self.collection_name = collection_name

    def retrieve(self, question: str, top_k: int = 10, query_type: str | None = None) -> list[RetrievalHit]:
        from rag.embedder import embed_query
        from rag.vector_store import query as vs_query

        rows = vs_query(
            embed_query(question),
            top_k=top_k,
            similarity_threshold=_NO_THRESHOLD,
            collection_name=self.collection_name,
        )
        return [_row_to_hit(r) for r in rows]


class BM25Retriever:
    """纯关键词检索。"""

    name = "bm25"

    def __init__(self, collection_name: str | None = None) -> None:
        self.collection_name = collection_name
        self._ready = False

    def _ensure_index(self) -> None:
        """加载 BM25 索引；兼容早期未按集合分文件的 `bm25_index.pkl`。"""
        if self._ready:
            return

        from rag import config
        from rag.hybrid_search import load_bm25_index

        if load_bm25_index(collection_name=self.collection_name):
            self._ready = True
            return

        legacy = config.CHROMA_DB_DIR / "bm25_index.pkl"
        if (self.collection_name or config.COLLECTION_NAME) == config.COLLECTION_NAME and legacy.exists():
            self._ready = load_bm25_index(filepath=legacy, collection_name=self.collection_name)

        if not self._ready:
            logger.warning("BM25 索引不可用（collection=%s）", self.collection_name)

    def retrieve(self, question: str, top_k: int = 10, query_type: str | None = None) -> list[RetrievalHit]:
        from rag.hybrid_search import _bm25_search

        self._ensure_index()
        rows = _bm25_search(question, top_k=top_k, collection_name=self.collection_name)
        return [
            RetrievalHit(chunk_id=chunk_id, source=chunk_id, score=float(score), text=text)
            for chunk_id, score, text in rows
        ]


# ─── 融合检索器（覆盖 hybrid / graphrag / 消融） ────────────────────────────

class FusionRetriever:
    """混合召回（±图谱通道，±精排）的可配置检索器。"""

    def __init__(
        self,
        name: str,
        use_graph: bool,
        use_rerank: bool,
        use_bm25: bool = True,
        collection_name: str | None = None,
    ) -> None:
        self.name = name
        self.use_graph = use_graph
        self.use_rerank = use_rerank
        self.use_bm25 = use_bm25
        self.collection_name = collection_name
        self._index: "GraphIndex | None" = None
        self._bm25_ready = False

    @property
    def index(self) -> "GraphIndex":
        """惰性加载图谱索引（只有图谱档位会碰到）。"""
        if self._index is None:
            from graph.graph_builder import load_index

            self._index = load_index()
        return self._index

    def _ensure_bm25(self) -> None:
        if self._bm25_ready or not self.use_bm25:
            return
        BM25Retriever(self.collection_name)._ensure_index()
        self._bm25_ready = True

    def _chunk_hits(self, question: str, fetch_k: int) -> list[RetrievalHit]:
        self._ensure_bm25()

        if self.use_bm25:
            from rag.hybrid_search import hybrid_retrieve

            rows = hybrid_retrieve(
                question,
                top_k=fetch_k,
                similarity_threshold=_NO_THRESHOLD,
                collection_name=self.collection_name,
            )
        else:
            from rag.embedder import embed_query
            from rag.vector_store import query as vs_query

            rows = vs_query(
                embed_query(question),
                top_k=fetch_k,
                similarity_threshold=_NO_THRESHOLD,
                collection_name=self.collection_name,
            )
        return [_row_to_hit(r) for r in rows]

    def _graph_hits(self, question: str, query_type: str | None) -> list[RetrievalHit]:
        from graph.search import _extract_query_entities, global_search

        if query_type == "multi_hop":
            results = global_search(question, self.index, top_k=_GRAPH_TOP_K)
            names: list[str] = []
            for result in results:
                names.extend(result.source_ids[:_MAX_ENTITIES_PER_COMMUNITY])
        else:
            names = _extract_query_entities(question)

        return graph_expand_docs(self.index, names)

    def retrieve(self, question: str, top_k: int = 10, query_type: str | None = None) -> list[RetrievalHit]:
        fetch_k = max(top_k * 4, top_k)

        chunk_hits = self._chunk_hits(question, fetch_k)
        if self.use_rerank and chunk_hits:
            chunk_hits = rerank_hits(question, chunk_hits, top_k=fetch_k)

        if not self.use_graph:
            return chunk_hits[:top_k]

        merged = rrf_merge([chunk_hits, self._graph_hits(question, query_type)])
        return merged[:top_k]


def rerank_hits(
    question: str,
    hits: list[RetrievalHit],
    top_k: int | None = None,
) -> list[RetrievalHit]:
    """用 BGE-Reranker 对候选重排（复用它自身的禁用回退）。"""
    if not hits:
        return []

    from rag.reranker import rerank

    limit = min(top_k or len(hits), len(hits))
    ranked = rerank(question, [h.text for h in hits], top_k=limit)
    return [replace(hits[index], score=float(score)) for index, score in ranked]


# ─── 注册表 ───────────────────────────────────────────────────────────────

_FUSION_SPECS: dict[str, dict[str, bool]] = {
    "hybrid": {"use_graph": False, "use_rerank": False, "use_bm25": True},
    "hybrid_rerank": {"use_graph": False, "use_rerank": True, "use_bm25": True},
    "graphrag": {"use_graph": True, "use_rerank": True, "use_bm25": True},
    "graphrag_no_rerank": {"use_graph": True, "use_rerank": False, "use_bm25": True},
    "graphrag_no_bm25": {"use_graph": True, "use_rerank": True, "use_bm25": False},
}

MAIN_SYSTEMS = ("vector", "bm25", "hybrid", "graphrag")
ABLATION_SYSTEMS = ("hybrid_rerank", "graphrag_no_rerank", "graphrag_no_bm25")
ALL_SYSTEMS = MAIN_SYSTEMS + ABLATION_SYSTEMS


def build_retriever(name: str, collection_name: str | None = None):
    """按名字构造检索器。"""
    if name == "vector":
        return VectorRetriever(collection_name)
    if name == "bm25":
        return BM25Retriever(collection_name)
    if name in _FUSION_SPECS:
        return FusionRetriever(name=name, collection_name=collection_name, **_FUSION_SPECS[name])
    raise ValueError(f"未知检索器 '{name}'，可选: {', '.join(ALL_SYSTEMS)}")


def build_retrievers(names: list[str], collection_name: str | None = None) -> list:
    return [build_retriever(name, collection_name) for name in names]
