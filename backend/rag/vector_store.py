"""向量存储 — ChromaDB 持久化 + 增删查。

集合名: dc_knowledge
持久化目录: backend/chroma_db/
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import config
from .chunker import Chunk

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import chromadb

_CLIENT: "chromadb.PersistentClient | None" = None
_COLLECTIONS: dict[str, "chromadb.Collection"] = {}


def _get_client() -> "chromadb.PersistentClient":
    """Lazy init ChromaDB 持久化客户端。"""
    global _CLIENT
    if _CLIENT is None:
        import chromadb  # noqa: import-not-at-top
        config.CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
        _CLIENT = chromadb.PersistentClient(
            path=str(config.CHROMA_DB_DIR),
        )
        logger.info("ChromaDB 客户端初始化: %s", config.CHROMA_DB_DIR)
    return _CLIENT


def _get_collection(collection_name: str | None = None) -> "chromadb.Collection":
    """获取或创建集合（按名称隔离，支持全库与论文独立收藏）。"""
    global _COLLECTIONS
    collection_name = collection_name or config.COLLECTION_NAME
    if collection_name not in _COLLECTIONS:
        client = _get_client()
        _COLLECTIONS[collection_name] = client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": "DC 项目知识库 — 极端气候粮食生产风险",
                "embedding_model": config.EMBEDDING_MODEL_NAME,
                "hnsw:space": "cosine",
            },
        )
        logger.info(
            "ChromaDB 集合 '%s' 就绪，当前 %d 条",
            collection_name, _COLLECTIONS[collection_name].count(),
        )
    return _COLLECTIONS[collection_name]


def add_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    collection_name: str | None = None,
) -> None:
    """批量添加 chunk 及其嵌入向量到向量库。

    Args:
        chunks: Chunk 对象列表。
        embeddings: 对应的嵌入向量列表。
    """
    if not chunks:
        return

    collection = _get_collection(collection_name)

    ids = [f"{c.source}:{c.chunk_index}:{c.page}" for c in chunks]
    metadatas = [
        {
            "source": c.source,
            "title": c.title,
            "file_type": c.file_type,
            "chunk_index": c.chunk_index,
            "page": c.page,
        }
        for c in chunks
    ]
    documents = [c.text for c in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,  # type: ignore[arg-type]
        documents=documents,
    )
    logger.info("向量库写入 %d 条记录", len(chunks))


def query(
    query_embedding: list[float],
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    collection_name: str | None = None,
) -> list[dict]:
    """语义检索 top-k 相关文档块。

    Args:
        query_embedding: 查询嵌入向量。
        top_k: 返回条数（默认 config.TOP_K）。
        similarity_threshold: 余弦相似度阈值（默认 config.SIMILARITY_THRESHOLD）。

    Returns:
        list[dict]，每项含 id, text, metadata, similarity。
    """
    top_k = top_k or config.TOP_K
    threshold = similarity_threshold or config.SIMILARITY_THRESHOLD

    collection = _get_collection(collection_name)
    if collection.count() == 0:
        logger.warning("向量库为空，检索无结果")
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    items = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 1.0
            # ChromaDB cosine distance → similarity = 1 - distance
            if distance <= 1.0:
                similarity = 1.0 - distance
            else:
                similarity = 1.0 / (1.0 + distance)  # ip fallback

            if similarity < threshold:
                continue

            items.append({
                "id": doc_id,
                "text": (results["documents"][0][i] if results["documents"] else ""),
                "metadata": (results["metadatas"][0][i] if results["metadatas"] else {}),
                "similarity": round(similarity, 4),
            })

    return items


def collection_stats(collection_name: str | None = None) -> dict:
    """返回向量库统计信息。"""
    collection = _get_collection(collection_name)
    return {
        "name": collection_name or config.COLLECTION_NAME,
        "count": collection.count(),
        "embedding_model": config.EMBEDDING_MODEL_NAME,
        "storage_path": str(config.CHROMA_DB_DIR),
    }


def delete_by_source(source_prefix: str, collection_name: str | None = None) -> int:
    """删除指定 source 前缀的所有 chunk。

    用于增量索引：更新某文件前先删旧 chunks，再写入新 chunks。

    Args:
        source_prefix: source 路径前缀（如 "docs/papers/paper.pdf"），
                       匹配所有以此开头的 chunk ID。

    Returns:
        删除的 chunk 数量。
    """
    collection = _get_collection(collection_name)
    if collection.count() == 0:
        return 0

    try:
        existing = collection.get(
            include=["metadatas"],
        )
    except Exception:
        logger.warning("获取现有 chunks 失败，跳过删除")
        return 0

    if not existing["ids"]:
        return 0

    # 匹配 source 字段以 source_prefix 开头的所有 chunks
    ids_to_delete: list[str] = []
    for i, doc_id in enumerate(existing["ids"]):
        meta = existing["metadatas"][i] if existing["metadatas"] else {}
        src = meta.get("source", "")
        if src == source_prefix or src.startswith(source_prefix):
            ids_to_delete.append(doc_id)

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        logger.info(
            "已删除 source='%s' 的 %d 条旧 chunks", source_prefix, len(ids_to_delete),
        )

    return len(ids_to_delete)


def clear_collection(collection_name: str | None = None) -> None:
    """清空集合并重建。用于 re-index。"""
    global _COLLECTIONS
    collection_name = collection_name or config.COLLECTION_NAME
    client = _get_client()
    try:
        client.delete_collection(collection_name)
        logger.info("已删除集合 '%s'", collection_name)
    except Exception:
        pass
    _COLLECTIONS.pop(collection_name, None)
    _get_collection(collection_name)
    logger.info("集合 '%s' 已重建（空）", collection_name)
