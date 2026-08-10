"""RAG pipeline 编排 — 一键构建索引 + 问答。

将所有 rag 子模块串联为两个入口：
    build_index()  → 加载文档 → 分块 → 嵌入 → 写入 ChromaDB
    query()        → 嵌入问题 → 检索 → 组装上下文 → DeepSeek 生成
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config
from .chunker import chunk_documents
from .document_loader import Document, load_all_documents, load_markdown, load_pdf
from .embedder import embed_documents
from .generator import generate
from .hybrid_search import build_bm25_index, save_bm25_index
from .retriever import build_context, retrieve
from .vector_store import add_chunks, clear_collection, collection_stats, delete_by_source

logger = logging.getLogger(__name__)


def build_index(
    docs_dir: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    batch_size: int = 32,
) -> dict:
    """全量重建知识库索引。

    流程: 加载文档 → 分块 → 嵌入 → 写入向量库。

    Args:
        docs_dir: 文档目录（默认 config.DOCS_DIR）。
        chunk_size: 分块大小。
        chunk_overlap: 块间重叠。
        batch_size: 嵌入批大小（GPU 可加大）。

    Returns:
        {"status": "ok", "documents": N, "chunks": M, "collection_count": K}
    """
    docs_dir_path = Path(docs_dir) if docs_dir else config.DOCS_DIR

    # 1. 加载文档
    documents = load_all_documents(docs_dir_path)
    if not documents:
        return {"status": "empty", "documents": 0, "chunks": 0, "collection_count": 0}

    # 2. 分块
    chunks = chunk_documents(
        documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    if not chunks:
        return {
            "status": "empty",
            "documents": len(documents), "chunks": 0, "collection_count": 0,
        }

    # 3. 嵌入 + 写入（分批，避免 OOM）
    clear_collection()
    texts = [c.text for c in chunks]
    total = len(texts)

    for i in range(0, total, batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_chunks = chunks[i:i + batch_size]
        embeddings = embed_documents(batch_texts)
        add_chunks(batch_chunks, embeddings)
        logger.info("索引进度: %d/%d chunks", min(i + batch_size, total), total)

    # 4. 构建 BM25 关键词索引（混合搜索用）
    logger.info("构建 BM25 索引...")
    chunk_ids = [f"{c.source}:{c.chunk_index}:{c.page}" for c in chunks]
    build_bm25_index(texts, chunk_ids)
    save_bm25_index()

    stats = collection_stats()
    return {
        "status": "ok",
        "documents": len(documents),
        "chunks": total,
        "collection_count": stats["count"],
    }


def query(
    question: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """RAG 问答：检索 + 生成。

    Args:
        question: 用户问题。
        top_k: 检索条数。
        similarity_threshold: 相似度阈值。
        history: 对话历史。

    Returns:
        {"answer": str, "sources": list[dict], "tokens_used": int}
    """
    # 1. 检索
    results = retrieve(
        question, top_k=top_k, similarity_threshold=similarity_threshold,
    )

    # 2. 组装上下文
    context = build_context(results)

    # 3. 生成
    answer, tokens = generate(question, context, history=history)

    # 4. 整理来源
    sources = []
    for r in results:
        meta = r.get("metadata", {})
        text = r.get("text", "")
        sources.append({
            "source": meta.get("source", "未知"),
            "title": meta.get("title", ""),
            "similarity": r.get("similarity", 0),
            "snippet": (text[:200] + "..." if len(text) > 200 else text),
        })

    return {
        "answer": answer,
        "sources": sources,
        "tokens_used": tokens,
        "results_count": len(results),
    }


def index_file(
    filepath: str | Path,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> dict:
    """增量索引单个文件：删旧 chunks → 加载 → 分块 → 嵌入 → 写入。

    用于文件监控检测到新增/修改时调用。

    Args:
        filepath: 文件的绝对路径。
        chunk_size: 分块大小（默认 config 值）。
        chunk_overlap: 块间重叠。

    Returns:
        {"status": "ok"|"skipped"|"error", "chunks": N, "source": "...", "message": "..."}
    """
    filepath = Path(filepath)

    if not filepath.exists():
        return {"status": "error", "chunks": 0, "source": str(filepath), "message": "文件不存在"}

    suffix = filepath.suffix.lower()
    if suffix not in (".md", ".pdf"):
        return {"status": "skipped", "chunks": 0, "source": str(filepath), "message": f"不支持的文件类型: {suffix}"}

    # 相对路径作为 source 标识
    try:
        rel_path = str(filepath.relative_to(config.DOCS_DIR.parent))
    except ValueError:
        rel_path = str(filepath)

    # 1. 删旧
    deleted = delete_by_source(rel_path)
    if deleted > 0:
        logger.info("增量索引: 已清理 %s 的 %d 条旧记录", rel_path, deleted)

    # 2. 加载
    documents: list[Document] = []
    if suffix == ".md":
        doc = load_markdown(filepath)
        if doc.content.strip():
            documents.append(doc)
    elif suffix == ".pdf":
        documents = load_pdf(filepath)

    if not documents:
        return {"status": "skipped", "chunks": 0, "source": rel_path, "message": "无有效内容"}

    # 3. 分块
    chunks = chunk_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return {"status": "skipped", "chunks": 0, "source": rel_path, "message": "分块后无内容"}

    # 4. 嵌入 + 写入
    texts = [c.text for c in chunks]
    embeddings = embed_documents(texts)
    add_chunks(chunks, embeddings)

    logger.info("增量索引完成: %s → %d chunks", rel_path, len(chunks))
    return {
        "status": "ok",
        "chunks": len(chunks),
        "source": rel_path,
        "message": f"已索引 {len(chunks)} 块",
    }


def remove_file(filepath: str | Path) -> dict:
    """从索引中移除指定文件的所有 chunks。

    Args:
        filepath: 文件的绝对路径。

    Returns:
        {"status": "ok"|"skipped", "deleted": N, "source": "..."}
    """
    filepath = Path(filepath)
    try:
        rel_path = str(filepath.relative_to(config.DOCS_DIR.parent))
    except ValueError:
        rel_path = str(filepath)

    deleted = delete_by_source(rel_path)
    if deleted > 0:
        logger.info("已从索引移除: %s (%d 条)", rel_path, deleted)
    return {"status": "ok", "deleted": deleted, "source": rel_path}
