"""嵌入模型封装 — BGE-M3 GPU 本地推理，自动 GPU/CPU 检测。

模型: BAAI/bge-m3 (1024-dim, 多语言, 中文 C-MTEB SOTA)
    - 相比旧 BGE-small-zh (512-dim): 检索精度显著提升
    - GPU 推理比 CPU 快 10-50x
    - 自动检测 CUDA/MPS，可用时默认 GPU；否则回退 CPU

Lazy load: 首次调用时下载/加载模型 (~2.2GB)，进程内缓存。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import numpy as np

_MODEL: "SentenceTransformer | None" = None  # type: ignore[name-defined]
_MODEL_DEVICE: str = ""


def _detect_device() -> str:
    """自动检测最佳推理设备: cuda > mps > cpu。"""
    device = config.EMBEDDING_DEVICE
    if device and device != "auto":
        return device

    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    except ImportError:
        device = "cpu"

    logger.info("嵌入设备: %s", device.upper())
    return device


def _get_model() -> "SentenceTransformer":  # type: ignore[name-defined]
    """Lazy load BGE-M3 嵌入模型（~2.2GB）。"""
    global _MODEL, _MODEL_DEVICE
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL_DEVICE = _detect_device()
        logger.info(
            "加载 %s (device=%s)...", config.EMBEDDING_MODEL_NAME, _MODEL_DEVICE,
        )
        _MODEL = SentenceTransformer(
            config.EMBEDDING_MODEL_NAME,
            device=_MODEL_DEVICE,
        )
        if hasattr(_MODEL, "max_seq_length"):
            _MODEL.max_seq_length = 1024
        logger.info(
            "嵌入模型就绪: %d-dim, device=%s",
            _MODEL.get_sentence_embedding_dimension(), _MODEL_DEVICE,
        )
    return _MODEL


def get_device() -> str:
    """返回当前推理设备。"""
    global _MODEL_DEVICE
    if not _MODEL_DEVICE:
        _MODEL_DEVICE = _detect_device()
    return _MODEL_DEVICE


def embed_documents(texts: list[str], batch_size: int = 64) -> "list[list[float]]":
    """批量嵌入文档文本为 Dense 向量 (1024-dim)。

    GPU 模式自动调大 batch_size。
    """
    model = _get_model()

    if _MODEL_DEVICE == "cuda":
        batch_size = max(batch_size, 128)

    embeddings: "np.ndarray" = model.encode(  # type: ignore[assignment]
        texts,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 30,
        batch_size=batch_size,
    )
    return embeddings.tolist()


def embed_query(query: str) -> "list[float]":
    """嵌入查询文本为 Dense 向量 (1024-dim)。"""
    model = _get_model()
    instruction = "为这个句子生成表示以用于检索相关文章："
    embedding: "np.ndarray" = model.encode(  # type: ignore[assignment]
        instruction + query,
        normalize_embeddings=True,
    )
    return embedding.tolist()


def embed_dim() -> int:
    """返回嵌入向量维度（BGE-M3: 1024）。"""
    return _get_model().get_sentence_embedding_dimension()
