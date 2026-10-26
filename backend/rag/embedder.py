"""嵌入模型封装 — BGE-M3 GPU 本地推理，自动 GPU/CPU 检测。

模型: BAAI/bge-m3 (1024-dim, 多语言, 中文 C-MTEB SOTA)
    - 相比旧 BGE-small-zh (512-dim): 检索精度显著提升
    - GPU 推理比 CPU 快 10-50x
    - 自动检测 CUDA/MPS，可用时默认 GPU；否则回退 CPU

Lazy load: 首次调用时加载本地缓存模型 (~2.2GB)，进程内缓存。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

from . import config

logger = logging.getLogger(__name__)

# Windows 上 transformers 探测 tensorflow 会因 Keras3 兼容问题 import 失败。
# 在导入 sentence_transformers 之前禁用 TF 分支（wiki 已记录该坑）。
os.environ.setdefault("USE_TF", "0")

if TYPE_CHECKING:
    import numpy as np

_MODEL: "SentenceTransformer | None" = None  # type: ignore[name-defined]
_MODEL_DEVICE: str = ""
_MODEL_LOCK = threading.Lock()


def _available_memory_mb() -> int | None:
    """Windows 同时检查物理内存和提交额度，防止 native 分配失败退出进程。"""
    if os.name != "nt":
        return None
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in (
                "total_phys", "avail_phys", "total_page", "avail_page",
                "total_virtual", "avail_virtual", "avail_extended",
            )
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return min(status.avail_phys, status.avail_page) // (1024 * 1024)


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
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL

        available_mb = _available_memory_mb()
        if available_mb is not None and available_mb < config.EMBEDDING_MIN_FREE_MB:
            raise MemoryError(f"BGE-M3 加载内存不足：可用 {available_mb} MB")

        from sentence_transformers import SentenceTransformer
        import torch

        device = _detect_device()
        logger.info(
            "加载 %s (device=%s)...", config.EMBEDDING_MODEL_NAME, device,
        )
        model = None
        try:
            model = SentenceTransformer(
                config.EMBEDDING_MODEL_NAME,
                device=device,
                local_files_only=config.EMBEDDING_LOCAL_ONLY,
            )
        except torch.cuda.OutOfMemoryError:
            if not device.startswith("cuda"):
                raise
            logger.warning("BGE-M3 CUDA 内存分配失败，改用 CPU")
            device = "cpu"

        # 离开 except 后再加载，释放异常 traceback 持有的部分 GPU 模型。
        if model is None:
            torch.cuda.empty_cache()
            model = SentenceTransformer(
                config.EMBEDDING_MODEL_NAME,
                device="cpu",
                local_files_only=config.EMBEDDING_LOCAL_ONLY,
            )
        if hasattr(model, "max_seq_length"):
            model.max_seq_length = 1024
        _MODEL_DEVICE = device
        _MODEL = model
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

    保留调用方指定的 batch_size，避免小显存机器上强制扩批。
    """
    model = _get_model()

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
