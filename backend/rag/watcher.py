"""文件监控 — watchdog 自动增量索引。

监听 docs/ 目录的文件增删改，自动更新 ChromaDB 向量库。
启动时执行完整性检查（hash 比对），修复不一致。

用法:
    from rag.watcher import start_watcher, stop_watcher
    start_watcher()
    # ... Flask 运行中，自动监控 ...
    stop_watcher()
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from . import config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

# ─── 状态 ──────────────────────────────────────────────────────────────────
_observer: "Observer | None" = None
_running = False
_lock = threading.Lock()

# 防抖：累积变更事件，定时批量处理
_debounce_timer: threading.Timer | None = None
_debounce_interval = 3.0  # 秒
_pending_changes: set[str] = set()  # 累积的变更文件路径集合
_pending_deletes: set[str] = set()

# ─── 哈希追踪 ──────────────────────────────────────────────────────────────
_HASHES_FILE = config.CHROMA_DB_DIR / "file_hashes.json"


def _load_hashes() -> dict[str, str]:
    """加载已索引文件的哈希记录。"""
    if not _HASHES_FILE.exists():
        return {}
    try:
        with open(_HASHES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("哈希文件损坏，重建: %s", exc)
        return {}


def _save_hashes(hashes: dict[str, str]) -> None:
    """持久化哈希记录。"""
    _HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)


def _file_hash(filepath: Path) -> str:
    """计算文件 SHA256 哈希（用于变更检测）。"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _rel_path(filepath: Path) -> str:
    """将绝对路径转为相对于项目根的路径。"""
    try:
        return str(filepath.relative_to(config.DOCS_DIR.parent))
    except ValueError:
        return str(filepath)


# ─── 增量索引逻辑 ──────────────────────────────────────────────────────────


def _index_file(filepath: Path) -> bool:
    """索引单个文件（删旧 → 加载 → 分块 → 嵌入 → 写入）。成功返回 True。"""
    from .pipeline import index_file  # noqa: import-outside-toplevel

    rel = _rel_path(filepath)
    try:
        result = index_file(filepath)
        if result["status"] == "ok":
            hashes = _load_hashes()
            hashes[rel] = _file_hash(filepath)
            _save_hashes(hashes)
            logger.info("监控: 已索引 %s (%d chunks)", rel, result["chunks"])
            return True
        else:
            logger.info("监控: 跳过 %s — %s", rel, result.get("message", "未知"))
            return False
    except Exception as exc:
        logger.exception("监控: 索引失败 %s: %s", rel, exc)
        return False


def _remove_file(filepath: Path) -> bool:
    """从索引移除文件。成功返回 True。"""
    from .pipeline import remove_file  # noqa: import-outside-toplevel

    rel = _rel_path(filepath)
    try:
        result = remove_file(filepath)
        hashes = _load_hashes()
        hashes.pop(rel, None)
        _save_hashes(hashes)
        logger.info("监控: 已移除 %s (%d 条)", rel, result["deleted"])
        return True
    except Exception as exc:
        logger.exception("监控: 移除失败 %s: %s", rel, exc)
        return False


def _process_changes() -> None:
    """批量处理累积的文件变更（防抖后调用）。"""
    global _pending_changes, _pending_deletes
    with _lock:
        changes = _pending_changes.copy()
        deletes = _pending_deletes.copy()
        _pending_changes.clear()
        _pending_deletes.clear()

    if not changes and not deletes:
        return

    logger.info("监控: 处理 %d 个变更 + %d 个删除", len(changes), len(deletes))

    hashes = _load_hashes()
    modified_count = 0

    for abs_path_str in changes:
        fp = Path(abs_path_str)
        if not fp.exists():
            if _remove_file(fp):
                modified_count += 1
            continue

        suffix = fp.suffix.lower()
        if suffix not in (".md", ".pdf"):
            continue

        rel = _rel_path(fp)
        old_hash = hashes.get(rel)
        try:
            new_hash = _file_hash(fp)
        except OSError:
            continue

        if old_hash == new_hash:
            continue

        if _index_file(fp):
            modified_count += 1

    for abs_path_str in deletes:
        fp = Path(abs_path_str)
        if _remove_file(fp):
            modified_count += 1
        else:
            rel = _rel_path(fp)
            hashes = _load_hashes()
            if rel in hashes:
                hashes.pop(rel)
                _save_hashes(hashes)

    if modified_count > 0:
        logger.info("监控: 本轮更新 %d 个文件完成", modified_count)


def _debounce_flush() -> None:
    """防抖定时器到期，刷新累积变更。"""
    global _debounce_timer
    _debounce_timer = None
    _process_changes()


def _schedule_flush() -> None:
    """安排一次防抖刷新（重置现有定时器）。"""
    global _debounce_timer
    if _debounce_timer is not None:
        _debounce_timer.cancel()
    _debounce_timer = threading.Timer(_debounce_interval, _debounce_flush)
    _debounce_timer.daemon = True
    _debounce_timer.start()


# ─── watchdog 事件处理器 ────────────────────────────────────────────────────


class _DocsEventHandler:
    """docs/ 目录文件系统事件处理器。"""

    def on_created(self, event: "FileSystemEvent") -> None:
        if event.is_directory:
            return
        src = event.src_path
        if not src.lower().endswith((".md", ".pdf")):
            return
        with _lock:
            _pending_changes.add(src)
        logger.debug("监控: 检测到新增 %s", src)
        _schedule_flush()

    def on_modified(self, event: "FileSystemEvent") -> None:
        if event.is_directory:
            return
        src = event.src_path
        if not src.lower().endswith((".md", ".pdf")):
            return
        with _lock:
            _pending_changes.add(src)
        logger.debug("监控: 检测到修改 %s", src)
        _schedule_flush()

    def on_deleted(self, event: "FileSystemEvent") -> None:
        if event.is_directory:
            return
        src = event.src_path
        if not src.lower().endswith((".md", ".pdf")):
            return
        with _lock:
            _pending_deletes.add(src)
        logger.debug("监控: 检测到删除 %s", src)
        _schedule_flush()

    def on_moved(self, event: "FileSystemEvent") -> None:
        if event.is_directory:
            return
        src = event.src_path
        dest = event.dest_path
        if not src.lower().endswith((".md", ".pdf")):
            return
        with _lock:
            _pending_deletes.add(src)
            _pending_changes.add(dest)
        logger.debug("监控: 检测到移动 %s → %s", src, dest)
        _schedule_flush()


# ─── 启动时完整性检查 ──────────────────────────────────────────────────────


def reindex_modified() -> dict:
    """启动时检查所有文档：比较哈希，重新索引变更的文件。

    Returns:
        {"checked": N, "reindexed": M, "removed": K, "errors": L}
    """
    if not config.DOCS_DIR.exists():
        logger.warning("文档目录不存在，跳过完整性检查: %s", config.DOCS_DIR)
        return {"checked": 0, "reindexed": 0, "removed": 0, "errors": 0}

    hashes = _load_hashes()
    current_files: set[str] = set()
    reindexed = 0
    removed = 0
    errors = 0

    for filepath in config.DOCS_DIR.rglob("*"):
        if filepath.is_dir():
            continue
        if filepath.suffix.lower() not in (".md", ".pdf"):
            continue
        rel = _rel_path(filepath)
        current_files.add(rel)

        new_hash = _file_hash(filepath)
        old_hash = hashes.get(rel)

        if old_hash == new_hash:
            continue

        logger.info("完整性检查: 检测到变更 %s", rel)
        if _index_file(filepath):
            reindexed += 1
        else:
            errors += 1

    # 清理已删除的文件
    stale = set(hashes.keys()) - current_files
    for rel in stale:
        logger.info("完整性检查: 清理已删除 %s", rel)
        try:
            abs_path = config.DOCS_DIR.parent / rel
            _remove_file(abs_path)
        except Exception:
            pass
        removed += 1

    _save_hashes(_load_hashes())
    logger.info(
        "完整性检查完成: 检查 %d, 重新索引 %d, 清理 %d, 错误 %d",
        len(current_files), reindexed, removed, errors,
    )
    return {
        "checked": len(current_files),
        "reindexed": reindexed,
        "removed": removed,
        "errors": errors,
    }


# ─── 生命周期 ──────────────────────────────────────────────────────────────


def start_watcher(docs_dir: str | None = None) -> bool:
    """启动文件监控（后台线程）。

    Args:
        docs_dir: 要监控的目录（默认 config.DOCS_DIR）。

    Returns:
        True 如果成功启动，False 如果已在运行或 watchod 未安装。
    """
    global _observer, _running

    with _lock:
        if _running:
            logger.warning("文件监控已在运行")
            return False

        try:
            from watchdog.events import FileSystemEventHandler  # noqa: F811
            from watchdog.observers import Observer  # noqa: F811
        except ImportError:
            logger.error("watchdog 未安装，文件监控不可用。pip install watchdog")
            return False

        watch_dir = Path(docs_dir) if docs_dir else config.DOCS_DIR
        if not watch_dir.exists():
            logger.error("监控目录不存在: %s", watch_dir)
            return False

        handler = _DocsEventHandler()

        class _Handler(FileSystemEventHandler):
            def on_created(self_2, event):
                handler.on_created(event)

            def on_modified(self_2, event):
                handler.on_modified(event)

            def on_deleted(self_2, event):
                handler.on_deleted(event)

            def on_moved(self_2, event):
                handler.on_moved(event)

        _observer = Observer()
        _observer.schedule(_Handler(), str(watch_dir), recursive=True)
        _observer.start()
        _running = True
        logger.info("文件监控已启动: %s", watch_dir)

    return True


def stop_watcher() -> None:
    """停止文件监控。"""
    global _observer, _running, _debounce_timer

    with _lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
            _debounce_timer = None

        if _observer is not None:
            _observer.stop()
            _observer.join(timeout=5)
            _observer = None
        _running = False
        logger.info("文件监控已停止")


def is_running() -> bool:
    """返回监控是否在运行。"""
    return _running


def start_autosync() -> dict:
    """按配置执行启动期重扫并开启监控。

    自动索引属于非关键能力，默认关闭，避免嵌入模型加载失败时连带终止
    Flask/Waitress 主进程。
    """
    if not config.AUTO_INDEX_ENABLED:
        logger.info("RAG 自动索引已关闭（RAG_AUTO_INDEX_ENABLED=false）")
        return {
            "enabled": False,
            "reindexed": None,
            "watcher_started": False,
        }

    reindex_result = reindex_modified()
    return {
        "enabled": True,
        "reindexed": reindex_result,
        "watcher_started": start_watcher(),
    }


def get_watcher_status() -> dict:
    """返回监控状态摘要。"""
    hashes = _load_hashes()
    return {
        "running": _running,
        "auto_index_enabled": config.AUTO_INDEX_ENABLED,
        "watched_dir": str(config.DOCS_DIR),
        "debounce_interval_s": _debounce_interval,
        "hashes_file": str(_HASHES_FILE),
        "tracked_files": len(hashes),
        "pending_changes": len(_pending_changes),
        "pending_deletes": len(_pending_deletes),
    }
