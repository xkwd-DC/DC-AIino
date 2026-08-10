"""GraphRAG 配置 — 路径、提取参数、社区检测、搜索设置。

所有可调参数集中管理；运行时敏感值从环境变量读取。
"""

from __future__ import annotations

import os
from pathlib import Path

# ─── 项目根路径 ──────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
_PROJECT_DIR = _BACKEND_DIR.parent                      # DC-AIino/

# ─── 数据路径 ────────────────────────────────────────────────────────────
DOCS_DIR = _PROJECT_DIR / "docs"
GRAPH_DATA_DIR = _BACKEND_DIR / "graph_data"
GRAPH_INDEX_FILE = GRAPH_DATA_DIR / "graph_index.json"

# ─── 文档分块（图谱提取用更大的 chunk 以获取完整语义）────────────────────
GRAPH_CHUNK_SIZE = 2000       # 图谱提取用大块，保证实体上下文完整
GRAPH_CHUNK_OVERLAP = 200

# ─── 实体提取 ────────────────────────────────────────────────────────────
# 实体类型定义（用于 LLM prompt）
ENTITY_TYPES = [
    "气候因子",   # 温度、降水、干旱、洪涝、极端事件...
    "作物",       # 小麦、水稻、玉米、大豆...
    "地理区域",   # 华北平原、东北、黄淮海...
    "研究方法",   # XGBoost、SHAP、LSTM、SMM...
    "指标",       # 产量、SPEI、R²、NDVI...
    "概念",       # 气候韧性、粮食安全、适应性...
    "数据来源",   # 气象站、遥感、统计年鉴、CMIP6...
    "机构/作者",  # 论文作者、研究机构
    "其他",
]

# 关系类型定义
RELATION_TYPES = [
    "影响",   # A 影响 B（因果或统计关联）
    "导致",   # A 导致 B（直接因果）
    "测量",   # A 用来测量/量化 B
    "属于",   # A 属于 B 类别
    "位于",   # A 位于 B 区域
    "使用",   # A 方法应用于 B
    "相关",   # A 与 B 相关
    "包含",   # A 包含 B
]

# LLM 提取参数
EXTRACTION_BATCH_SIZE = 5      # 每批处理的 chunk 数
EXTRACTION_MAX_RETRIES = 2     # 单 chunk 提取失败重试次数

# ─── DeepSeek API（复用 rag 模块的配置）───────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 提取用模型参数（需要较大输出空间）
# 2000 → 4096：部分 chunk 实体/关系较多时 JSON 易被截断导致解析失败
EXTRACTION_MAX_TOKENS = 4096
EXTRACTION_TEMPERATURE = 0.1   # 实体提取需要低温度保证一致性

# 摘要用模型参数
SUMMARIZATION_MAX_TOKENS = 800
SUMMARIZATION_TEMPERATURE = 0.3

# ─── 社区检测 ────────────────────────────────────────────────────────────
COMMUNITY_MIN_SIZE = 3          # 最小社区实体数
COMMUNITY_MAX_LEVELS = 2        # 层次聚类最大层级

# ─── 图谱搜索 ────────────────────────────────────────────────────────────
GRAPH_SEARCH_TOP_K = 5          # 实体匹配 top-k
GRAPH_SEARCH_MAX_HOPS = 2       # 图谱遍历最大跳数
GRAPH_SEARCH_MAX_NEIGHBORS = 8  # 每跳最多遍历邻居数

# ─── 启动验证 ────────────────────────────────────────────────────────────
def validate() -> list[str]:
    """启动时校验配置。返回缺失项列表；空 = 通过。"""
    issues = []
    if not DEEPSEEK_API_KEY:
        issues.append("DEEPSEEK_API_KEY 未设置，GraphRAG 不可用")
    if not DOCS_DIR.exists():
        issues.append(f"文档目录不存在: {DOCS_DIR}")
    return issues
