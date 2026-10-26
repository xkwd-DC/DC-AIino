"""RAG 嵌入模型的离线加载边界。"""

import sys
import types

import pytest

from rag import config as rag_config
from rag import embedder


@pytest.fixture(autouse=True)
def enough_memory(monkeypatch):
    monkeypatch.setattr(embedder, "_available_memory_mb", lambda: 8192)


def test_embedder_loads_cached_model_without_network_by_default(monkeypatch):
    calls: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, **kwargs):
            calls["model_name"] = model_name
            calls["kwargs"] = kwargs

        def get_sentence_embedding_dimension(self) -> int:
            return 1024

    fake_module = types.SimpleNamespace(
        SentenceTransformer=FakeSentenceTransformer,
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "_MODEL_DEVICE", "")
    monkeypatch.setattr(embedder, "_detect_device", lambda: "cpu")
    monkeypatch.setattr(rag_config, "EMBEDDING_LOCAL_ONLY", True)

    embedder._get_model()

    assert calls["model_name"] == "BAAI/bge-m3"
    assert calls["kwargs"]["local_files_only"] is True


def test_cuda_oom_retries_on_cpu_and_caches_successful_model(monkeypatch):
    import torch

    devices = []
    cpu_model = types.SimpleNamespace(
        max_seq_length=8192,
        get_sentence_embedding_dimension=lambda: 1024,
    )

    def load_model(_name, *, device, local_files_only):
        assert local_files_only
        devices.append(device)
        if device == "cuda":
            raise torch.cuda.OutOfMemoryError("not enough memory")
        return cpu_model

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=load_model,
    ))
    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "_MODEL_DEVICE", "")
    monkeypatch.setattr(embedder, "_detect_device", lambda: "cuda")
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    monkeypatch.setattr(rag_config, "EMBEDDING_LOCAL_ONLY", True)

    assert embedder._get_model() is cpu_model
    assert embedder._get_model() is cpu_model
    assert devices == ["cuda", "cpu"]
    assert embedder.get_device() == "cpu"


def test_model_load_failure_does_not_publish_partial_model(monkeypatch):
    def load_model(*_args, **_kwargs):
        raise OSError("missing local model")

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=load_model,
    ))
    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "_MODEL_DEVICE", "")
    monkeypatch.setattr(embedder, "_detect_device", lambda: "cpu")

    with pytest.raises(OSError, match="missing local model"):
        embedder._get_model()
    assert embedder._MODEL is None
    assert embedder._MODEL_DEVICE == ""


def test_concurrent_requests_load_model_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    loading = Event()
    release = Event()
    calls = []
    model = types.SimpleNamespace(get_sentence_embedding_dimension=lambda: 1024)

    def load_model(*_args, **_kwargs):
        calls.append(True)
        loading.set()
        assert release.wait(5)
        return model

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=load_model,
    ))
    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "_MODEL_DEVICE", "")
    monkeypatch.setattr(embedder, "_detect_device", lambda: "cpu")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(embedder._get_model)
        assert loading.wait(5)
        second = pool.submit(embedder._get_model)
        release.set()
        assert first.result(timeout=5) is model
        assert second.result(timeout=5) is model
    assert len(calls) == 1


def test_low_memory_skips_model_import_and_loading(monkeypatch):
    monkeypatch.setattr(embedder, "_MODEL", None)
    monkeypatch.setattr(embedder, "_available_memory_mb", lambda: 512)

    def unexpected_load(*_args, **_kwargs):
        raise AssertionError("内存不足时不应加载模型")

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=unexpected_load,
    ))
    with pytest.raises(MemoryError, match="512 MB"):
        embedder._get_model()
