"""模型不可用时，持久化 BM25 仍能提供带真实来源的问答上下文。"""

from types import SimpleNamespace

import pytest

from rag import config, embedder, hybrid_search, retriever, vector_store


@pytest.fixture()
def keyword_index(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHROMA_DB_DIR", tmp_path)
    monkeypatch.setattr(hybrid_search, "_BM25_STORES", {})
    hybrid_search.build_bm25_index(
        ["drought wheat climate", "corn growth temperature", "rice water irrigation", "soil carbon cycle"],
        ["paper:0:0", "corn:0:0", "rice:0:0", "soil:0:0"],
    )
    hybrid_search.save_bm25_index()
    hybrid_search._BM25_STORES.clear()

    collection = SimpleNamespace(get=lambda **_kwargs: {
        "ids": ["paper:0:0"],
        "metadatas": [{"source": "docs/papers/wheat.md", "title": "小麦干旱研究"}],
    })
    monkeypatch.setattr(vector_store, "_get_collection", lambda _name=None: collection)
    return collection


def test_low_memory_restores_saved_keywords_and_source_metadata(keyword_index, monkeypatch):
    def unavailable(_question):
        raise MemoryError("low memory")

    monkeypatch.setattr(embedder, "embed_query", unavailable)

    hits = hybrid_search.hybrid_retrieve("drought", top_k=3)

    assert len(hits) == 1
    assert hits[0]["retrieval_mode"] == "bm25"
    assert hits[0]["metadata"]["source"] == "docs/papers/wheat.md"
    assert "drought" in hits[0]["text"]


def test_deleted_keyword_hits_are_not_used(keyword_index, monkeypatch):
    keyword_index.get = lambda **_kwargs: {"ids": [], "metadatas": []}
    monkeypatch.setattr(embedder, "embed_query", lambda _q: (_ for _ in ()).throw(MemoryError()))

    assert hybrid_search.hybrid_retrieve("drought") == []


def test_missing_keywords_does_not_hide_embedding_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHROMA_DB_DIR", tmp_path)
    monkeypatch.setattr(hybrid_search, "_BM25_STORES", {})
    monkeypatch.setattr(embedder, "embed_query", lambda _q: (_ for _ in ()).throw(MemoryError("no model")))

    with pytest.raises(MemoryError, match="no model"):
        hybrid_search.hybrid_retrieve("drought")


def test_keyword_fallback_does_not_load_reranker(keyword_index, monkeypatch):
    monkeypatch.setattr(config, "RERANKER_ENABLED", True)
    monkeypatch.setattr(embedder, "embed_query", lambda _q: (_ for _ in ()).throw(MemoryError()))

    def unexpected_rerank(*_args, **_kwargs):
        raise AssertionError("内存不足时不应加载重排模型")

    monkeypatch.setattr(retriever, "rerank_results", unexpected_rerank)

    hits = retriever.retrieve("drought", top_k=3)

    assert len(hits) == 1
    assert hits[0]["retrieval_mode"] == "bm25"


def test_healthy_embedding_keeps_hybrid_retrieval(keyword_index, monkeypatch):
    monkeypatch.setattr(embedder, "embed_query", lambda _q: [0.1])
    monkeypatch.setattr(vector_store, "query", lambda *_args, **_kwargs: [{
        "id": "corn:0:0", "text": "corn growth temperature",
        "metadata": {"source": "docs/papers/corn.md", "title": "玉米"}, "similarity": 0.8,
    }])

    hits = hybrid_search.hybrid_retrieve("drought")

    assert {h["id"] for h in hits} == {"paper:0:0", "corn:0:0"}
    assert all(h["retrieval_mode"] == "hybrid" for h in hits)
    assert all(h["metadata"]["source"] for h in hits)
