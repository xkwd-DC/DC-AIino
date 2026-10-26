"""状态查询不能触发嵌入模型加载。"""

from types import SimpleNamespace

from rag import embedder, vector_store


def test_status_reads_collection_without_loading_embedding_model(client, monkeypatch):
    def unexpected_load():
        raise AssertionError("状态查询不应加载 BGE-M3")

    collection = SimpleNamespace(count=lambda: 42)
    store = SimpleNamespace(get_or_create_collection=lambda **_kwargs: collection)
    monkeypatch.setattr(vector_store, "_get_client", lambda: store)
    monkeypatch.setattr(vector_store, "_COLLECTIONS", {})
    monkeypatch.setattr(embedder, "_get_model", unexpected_load)

    response = client.get("/api/rag/status")

    assert response.status_code == 200
    assert response.json["data"]["collection"]["count"] == 42
