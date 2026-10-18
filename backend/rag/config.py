"""RAG 模块配置 — 路径、模型参数、ChromaDB、混合搜索、重排序。

所有可调参数集中管理；运行时敏感值从环境变量读取。
"""

from __future__ import annotations

import os
from pathlib import Path

# ─── 项目根路径 ──────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
_PROJECT_DIR = _BACKEND_DIR.parent                      # DC-AIino/

# ─── 文档路径 ────────────────────────────────────────────────────────────
DOCS_DIR = _PROJECT_DIR / "docs"
DOCS_PAPERS_DIR = DOCS_DIR / "papers"

# 支持的文件类型（.md / .txt / .pdf）
FILE_TYPES = (".md", ".txt", ".pdf")
# ChromaDB 持久化目录：默认 backend/chroma_db，可用环境变量 DC_CHROMA_DIR 覆盖。
# 为什么要这个开关：ChromaDB 的 Rust 层在**非 ASCII 路径**下加载 HNSW 索引会失败
# （实测报 "Error loading hnsw index"；同一份数据换到纯 ASCII 路径立刻正常）。
# 便携包一旦被放进中文目录，启动器就把向量库同步到 ASCII 临时目录，再用这个变量指过来。
CHROMA_DB_DIR = Path(os.getenv("DC_CHROMA_DIR") or (_BACKEND_DIR / "chroma_db"))

# ─── 分块参数 ────────────────────────────────────────────────────────────
CHUNK_SIZE = 800       # 每块最大字符数
CHUNK_OVERLAP = 100    # 块间重叠字符数

# ─── 嵌入模型 ────────────────────────────────────────────────────────────
# BGE-M3: 1024 维，Dense+Sparse 双模式，中文 C-MTEB SOTA
# "auto" 自动检测 cuda > mps > cpu
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DEVICE = os.getenv("RAG_EMBEDDING_DEVICE", "auto")

# ─── 检索参数 ────────────────────────────────────────────────────────────
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.3"))

# ─── 混合搜索 (BM25 + Vector, RRF 融合) ──────────────────────────────────
HYBRID_BM25_WEIGHT = float(os.getenv("RAG_BM25_WEIGHT", "0.3"))
RRF_K = int(os.getenv("RAG_RRF_K", "60"))

# ─── 重排序 (Cross-Encoder Reranker) ─────────────────────────────────────
RERANKER_MODEL_NAME = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_ENABLED = os.getenv("RAG_RERANKER_ENABLED", "true").lower() == "true"
RERANKER_TOP_N = int(os.getenv("RAG_RERANKER_TOP_N", "5"))

# ─── DeepSeek API ────────────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_MAX_TOKENS = int(os.getenv("RAG_MAX_TOKENS", "1500"))
DEEPSEEK_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.3"))

# ─── ChromaDB 集合名 ─────────────────────────────────────────────────────
COLLECTION_NAME = "dc_knowledge"
PAPERS_COLLECTION_NAME = "dc_papers"

# ─── 启动验证 ────────────────────────────────────────────────────────────
def validate() -> list[str]:
    """启动时校验配置。返回缺失项列表；空 = 通过。"""
    issues = []
    if not DEEPSEEK_API_KEY:
        issues.append("DEEPSEEK_API_KEY 未设置，RAG 问答不可用")
    if not DOCS_DIR.exists():
        issues.append(f"文档目录不存在: {DOCS_DIR}")
    return issues
