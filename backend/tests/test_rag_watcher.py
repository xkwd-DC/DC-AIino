"""RAG 文档监控的启动边界。"""

from rag import config as rag_config
from rag import watcher


def test_rag_autosync_does_not_load_index_dependencies_when_disabled(monkeypatch):
    monkeypatch.setattr(rag_config, "AUTO_INDEX_ENABLED", False)

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("自动索引关闭时不应执行重建或启动 watchdog")

    monkeypatch.setattr(watcher, "reindex_modified", unexpected_call)
    monkeypatch.setattr(watcher, "start_watcher", unexpected_call)

    result = watcher.start_autosync()

    assert result == {
        "enabled": False,
        "reindexed": None,
        "watcher_started": False,
    }
