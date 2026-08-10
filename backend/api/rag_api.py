"""RAG API — Flask Blueprint。

端点:
    POST /api/rag/query     — RAG 问答
    POST /api/rag/rebuild   — 重建知识库索引（异步）
    GET  /api/rag/status    — 向量库统计 + 重建进度
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, request

from . import envelope
from limiter import limiter
from rag import config as rag_config
from rag.pipeline import build_index, query as rag_query

logger = logging.getLogger(__name__)

rag_bp = Blueprint("rag", __name__)

# ─── 索引重建状态（进程内） ────────────────────────────────────────────────
_rebuild_lock = threading.Lock()
_rebuild_status: dict = {"running": False, "started_at": None, "result": None}


@rag_bp.post("/api/rag/query")
@limiter.limit("50 per hour")
def rag_query_endpoint():
    """RAG 问答。

    Request JSON:
        {
            "question": "极端气候对粮食产量的影响机制？",
            "top_k": 5,          // 可选，1-20
            "history": [          // 可选
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Response (envelope data):
        {
            "answer": "...",
            "sources": [{"source": "...", "title": "...", "similarity": 0.85,
                          "snippet": "..."}],
            "tokens_used": 350,
            "results_count": 5,
            "timestamp": "2026-07-05T..."
        }
    """
    if not rag_config.DEEPSEEK_API_KEY:
        return envelope(
            error={
                "code": 503,
                "message": (
                    "RAG 服务未配置: DEEPSEEK_API_KEY 未设置。"
                    "请在 .env 中添加后重启。"
                ),
            },
            status=503,
        )

    body = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()

    if not question:
        return envelope(
            error={"code": 400, "message": "question 不能为空"},
            status=400,
        )
    if len(question) > 500:
        return envelope(
            error={"code": 400, "message": "question 不能超过 500 字"},
            status=400,
        )

    top_k = body.get("top_k")
    if top_k is not None and (not isinstance(top_k, int) or top_k < 1 or top_k > 20):
        return envelope(
            error={"code": 400, "message": "top_k 必须在 1-20 之间"},
            status=400,
        )

    history = body.get("history")
    if history is not None and not isinstance(history, list):
        return envelope(
            error={"code": 400, "message": "history 必须是数组"},
            status=400,
        )

    try:
        result = rag_query(question, top_k=top_k, history=history)
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return envelope(data=result)
    except Exception as exc:
        logger.exception("RAG 问答失败")
        return envelope(
            error={"code": 500, "message": f"RAG 查询失败: {exc}"},
            status=500,
        )


@rag_bp.post("/api/rag/rebuild")
@limiter.limit("5 per hour")
def rag_rebuild_endpoint():
    """重建知识库索引。异步执行，立即返回。

    Response (envelope data):
        {"status": "started" | "already_running", "message": "...", "started_at": "..."}
    """
    global _rebuild_status

    if _rebuild_status["running"]:
        return envelope(data={
            "status": "already_running",
            "message": "索引重建已在进行中",
            "started_at": _rebuild_status["started_at"],
        })

    def _rebuild():
        global _rebuild_status
        with _rebuild_lock:
            _rebuild_status["running"] = True
            _rebuild_status["started_at"] = datetime.now(timezone.utc).isoformat()
            _rebuild_status["result"] = None

        try:
            result = build_index()
            _rebuild_status["result"] = result
            logger.info("索引重建完成: %s", result)
        except Exception as exc:
            logger.exception("索引重建失败")
            _rebuild_status["result"] = {"status": "error", "message": str(exc)}
        finally:
            _rebuild_status["running"] = False

    thread = threading.Thread(target=_rebuild, daemon=True)
    thread.start()

    return envelope(data={
        "status": "started",
        "message": "索引重建已启动，请稍后查询 /api/rag/status 查看进度",
        "started_at": _rebuild_status["started_at"],
    })


@rag_bp.get("/api/rag/status")
@limiter.exempt
def rag_status_endpoint():
    """查询 RAG 状态：向量库统计 + 重建进度。

    Response (envelope data):
        {
            "collection": {"name": "...", "count": 123, ...},
            "rebuild": {"running": false, "started_at": "...", "result": {...}},
            "config": {"llm_model": "...", "embedding_model": "...", ...}
        }
    """
    from rag.vector_store import collection_stats

    try:
        stats = collection_stats()
    except Exception as exc:
        logger.warning("获取 ChromaDB 状态失败: %s", exc)
        stats = {"error": str(exc)}

    return envelope(data={
        "collection": stats,
        "rebuild": {
            "running": _rebuild_status["running"],
            "started_at": _rebuild_status["started_at"],
            "result": _rebuild_status["result"],
        },
        "watcher": _watcher_status(),
        "config": {
            "llm_model": rag_config.DEEPSEEK_MODEL,
            "embedding_model": rag_config.EMBEDDING_MODEL_NAME,
            "chunk_size": rag_config.CHUNK_SIZE,
            "top_k": rag_config.TOP_K,
        },
    })


def _watcher_status() -> dict:
    """获取文件监控状态（安全调用，缺失时返回 not_available）。"""
    try:
        from rag.watcher import get_watcher_status
        return get_watcher_status()
    except Exception:
        return {"running": False, "error": "watcher module not available"}
