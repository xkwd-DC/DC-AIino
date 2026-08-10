"""文本分块器 — 将文档切分为有重叠的语义块。

中文友好：按段落边界切分（双换行 / 标题行），再合并到目标长度。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from . import config
from .document_loader import Document

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """单个文本块。"""
    text: str
    source: str
    file_type: str
    title: str = ""
    chunk_index: int = 0
    page: int = 0


# ─── 段落分隔 ────────────────────────────────────────────────────────────
# Markdown 标题行 / 空行作为自然段落边界
_PARAGRAPH_SEP = re.compile(r"\n\n|\n(?:#{1,6}\s)|(?<=\n)(?=#{1,6}\s)")


def _split_paragraphs(text: str) -> list[str]:
    """按段落边界切分文本，过滤纯空白段。"""
    parts = _PARAGRAPH_SEP.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """将文档列表切分为有重叠的文本块。

    策略：
    1. 按段落边界切分
    2. 贪心合并段落直到接近 chunk_size
    3. 相邻块 overlap 按 chunk_overlap 个字符复用尾部

    Args:
        documents: 文档列表。
        chunk_size: 目标块大小（字符数）。
        chunk_overlap: 块间重叠字符数。

    Returns:
        Chunk 列表。
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

    all_chunks: list[Chunk] = []

    for doc in documents:
        paragraphs = _split_paragraphs(doc.content)
        if not paragraphs:
            continue

        chunks_for_doc: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 1 <= chunk_size:
                current = (current + "\n\n" + para).strip()
            else:
                if current:
                    chunks_for_doc.append(current)
                # 长段落单独分句（中英文句号 / 换行）
                if len(para) > chunk_size:
                    sub_chunks = _split_long_paragraph(para, chunk_size)
                    chunks_for_doc.extend(sub_chunks)
                    current = ""
                else:
                    current = para

        if current:
            chunks_for_doc.append(current)

        # 添加 overlap
        for i, text in enumerate(chunks_for_doc):
            if i > 0 and chunk_overlap > 0:
                prev = chunks_for_doc[i - 1]
                overlap_text = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
                text = overlap_text + "\n\n" + text

            all_chunks.append(Chunk(
                text=text,
                source=doc.source,
                file_type=doc.file_type,
                title=doc.title,
                chunk_index=i,
                page=doc.page,
            ))

    logger.info("分块完成: %d 个文档 → %d 个 chunk", len(documents), len(all_chunks))
    return all_chunks


def _split_long_paragraph(text: str, max_len: int) -> list[str]:
    """长段落按句子边界进一步切分。"""
    # 按中英文句号、问号、感叹号切分
    sentences = re.split(r"(?<=[。！？.!?\n])(?=\S)", text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) <= max_len:
            current += sent
        else:
            if current:
                chunks.append(current.strip())
            current = sent
    if current:
        chunks.append(current.strip())
    return chunks if chunks else [text]
