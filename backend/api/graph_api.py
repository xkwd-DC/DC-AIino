"""GraphRAG API — 知识图谱问答端点。

POST /api/graph/query    — 图谱问答
POST /api/graph/rebuild  — 异步重建图谱索引
GET  /api/graph/status   — 图谱索引状态
"""

from __future__ import annotations

import logging
import threading

from flask import Blueprint, request

from api import envelope
from limiter import limiter

logger = logging.getLogger(__name__)

graph_bp = Blueprint("graph", __name__, url_prefix="/api/graph")

# 异步重建状态
_rebuild_status: dict = {"running": False, "progress": "", "error": None}


def _rebuild_async(force: bool = True):
    """后台线程执行图谱重建。"""
    global _rebuild_status
    try:
        _rebuild_status = {"running": True, "progress": "starting", "error": None}

        from graph.pipeline import build_graph_index

        def progress_callback(stage: str, current: int, total: int):
            _rebuild_status["progress"] = f"{stage}: {current}/{total}"

        build_graph_index(force=force, progress_callback=progress_callback)

        _rebuild_status = {"running": False, "progress": "completed", "error": None}

    except Exception as exc:
        logger.exception("图谱重建失败")
        _rebuild_status = {"running": False, "progress": "failed", "error": str(exc)}


@graph_bp.post("/query")
@limiter.limit("50 per hour")
def graph_query():
    """图谱问答：自动路由到 global/local/basic 搜索模式。

    Request:  {"question": "...", "top_k": 5}
    Response: {"answer": "...", "sources": [...], "search_mode": "...", ...}
    """
    body = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()

    if not question:
        return envelope(
            error={"code": 400, "message": "question 不能为空"}, status=400,
        )

    top_k = body.get("top_k")

    try:
        from graph.pipeline import query as graph_query_fn
        result = graph_query_fn(question, top_k=top_k)
        return envelope(data=result)

    except Exception as exc:
        logger.exception("图谱查询失败")
        return envelope(
            error={"code": 500, "message": f"查询失败: {exc}"}, status=500,
        )


@graph_bp.post("/rebuild")
@limiter.limit("5 per hour")
def graph_rebuild():
    """异步重建知识图谱索引。

    Request:  {"force": true}
    Response: {"status": "started" | "already_running"}
    """
    global _rebuild_status

    if _rebuild_status.get("running"):
        return envelope(
            data={
                "status": "already_running",
                "progress": _rebuild_status["progress"],
            }
        )

    force = (request.get_json(silent=True) or {}).get("force", True)

    thread = threading.Thread(target=_rebuild_async, args=(force,), daemon=True)
    thread.start()

    return envelope(data={"status": "started"})


@graph_bp.get("/status")
@limiter.exempt
def graph_status():
    """获取图谱索引状态和重建进度。"""
    global _rebuild_status

    try:
        from graph.pipeline import status as graph_status_fn
        idx_status = graph_status_fn()
    except Exception:
        idx_status = {"built": False, "index": None}

    return envelope(data={
        **idx_status,
        "rebuild": _rebuild_status,
    })
