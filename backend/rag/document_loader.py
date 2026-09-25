"""文档加载器 — 遍历 docs/ 目录，加载 .md 和 .pdf 文件。

PDF 提取依赖 pymupdf (fitz)；缺失时跳过 PDF 并记录警告。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """单个文档的完整表示。"""
    content: str
    source: str          # 相对路径，如 "docs/papers/v1_draft.md"
    file_type: str       # "md" | "pdf"
    title: str = ""      # 从文件名推断的标题
    page: int = 0        # PDF 页码（md 文件为 0）


def _extract_title(filepath: Path) -> str:
    """从文件名推断标题：去掉扩展名，`_` → 空格。"""
    stem = filepath.stem
    # 尝试取 markdown 第一行 # 标题
    if filepath.suffix == ".md":
        try:
            first_line = filepath.read_text(encoding="utf-8").split("\n", 1)[0]
            if first_line.startswith("# "):
                return first_line[2:].strip()
        except Exception:
            pass
    return stem.replace("_", " ")


def _read_text(filepath: Path) -> str:
    """读取文本文件，UTF-8 优先，GBK 兜底（Windows 中文编码兼容）。"""
    try:
        return filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return filepath.read_text(encoding="gbk", errors="replace")


def _rel_source(filepath: Path) -> str:
    """计算文档 source：相对项目根；不在项目内时退回绝对路径。"""
    try:
        return str(filepath.relative_to(config.DOCS_DIR.parent))
    except ValueError:
        return str(filepath)


def load_markdown(filepath: Path) -> Document:
    """加载单个 .md 文件。"""
    text = _read_text(filepath)
    return Document(
        content=text,
        source=_rel_source(filepath),
        file_type="md",
        title=_extract_title(filepath),
    )


def load_txt(filepath: Path) -> Document:
    """加载单个 .txt 文件（论文全文、导出文本等）。"""
    text = _read_text(filepath)
    return Document(
        content=text,
        source=_rel_source(filepath),
        file_type="txt",
        title=_extract_title(filepath),
    )


def load_pdf(filepath: Path) -> list[Document]:
    """加载单个 .pdf 文件，按页返回 Document 列表。

    使用 pymupdf (fitz) 提取文字；不可用时返回空列表。
    """
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("pymupdf 未安装，跳过 PDF: %s", filepath.name)
        return []

    docs = []
    try:
        with fitz.open(str(filepath)) as pdf:
            title = _extract_title(filepath)
            for page_num, page in enumerate(pdf, start=1):
                text = page.get_text()
                if not text.strip():
                    continue
                docs.append(Document(
                    content=text.strip(),
                    source=f"{_rel_source(filepath)}#p{page_num}",
                    file_type="pdf",
                    title=title,
                    page=page_num,
                ))
    except Exception as exc:
        logger.warning("PDF 解析失败 %s: %s", filepath.name, exc)
        return []

    return docs


def load_all_documents(
    docs_dir: Path | None = None,
    file_types: tuple[str, ...] = config.FILE_TYPES,
) -> list[Document]:
    """递归加载 docs_dir 下所有支持的文件。

    Args:
        docs_dir: 文档根目录，默认 config.DOCS_DIR。
        file_types: 要加载的扩展名（默认 .md/.txt/.pdf）。

    Returns:
        Document 列表（已去空内容）。
    """
    docs_dir = docs_dir or config.DOCS_DIR
    if not docs_dir.exists():
        logger.warning("文档目录不存在: %s", docs_dir)
        return []

    documents: list[Document] = []
    counts: dict[str, int] = {}

    for filepath in sorted(docs_dir.rglob("*")):
        if filepath.is_dir():
            continue
        suffix = filepath.suffix.lower()
        if suffix not in file_types:
            continue

        if suffix == ".md":
            doc = load_markdown(filepath)
            if doc.content.strip():
                documents.append(doc)
                counts[".md"] = counts.get(".md", 0) + 1
        elif suffix == ".txt":
            doc = load_txt(filepath)
            if doc.content.strip():
                documents.append(doc)
                counts[".txt"] = counts.get(".txt", 0) + 1
        elif suffix == ".pdf":
            pdf_docs = load_pdf(filepath)
            documents.extend(pdf_docs)
            counts[".pdf"] = counts.get(".pdf", 0) + len(pdf_docs)

    logger.info(
        "文档加载完成: %s = %d 个文档单元",
        ", ".join(f"{k}×{v}" for k, v in counts.items()) or "空",
        len(documents),
    )
    return documents
