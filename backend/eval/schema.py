"""评测数据模型 — 题库条目与检索命中。

判定口径（重要）:
    检索器各自的分块粒度不同（图谱 2000 字 / 向量库 800 字），块 ID 无法对齐，
    因此召回一律在**文档级**比较：gold 与命中都经 `normalize_doc()` 归一到文档路径。
    这样四档检索器（向量 / BM25 / 混合 / GraphRAG）才在同一把尺子上比。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

#: 题目类型，与论文里的分层结论一一对应
QUERY_TYPES = ("fact", "relation", "multi_hop")

#: gold 条目的可选前缀（大小写敏感，保持简单）
_GOLD_PREFIXES = ("doc:", "chunk:")


def normalize_doc(source: str) -> str:
    """把任意来源标识归一成文档路径。

    处理三种写法:
        - PDF 块 ID: "docs\\paper\\x.pdf#p11:1:11"      → "docs/paper/x.pdf"
        - PDF 来源:  "docs\\craic\\a.pdf#p1"            → "docs/craic/a.pdf"
        - MD 块 ID:  "docs\\00_项目执行计划.md:0:0"      → "docs/00_项目执行计划.md"
    """
    if not source:
        return ""
    path = source.replace("\\", "/").split("#")[0]
    # 砍掉向量库/图谱拼在末尾的 ":chunk_index:page" 或 ":chunk_index"
    return re.sub(r":\d+(?::\d+)?$", "", path)


def _strip_gold_prefix(entry: str) -> str:
    """去掉 gold 条目的可选前缀（doc: / chunk:）。"""
    for prefix in _GOLD_PREFIXES:
        if entry.startswith(prefix):
            return entry[len(prefix):]
    return entry


@dataclass
class EvalItem:
    """一道评测题。

    Attributes:
        id: 题号，如 "q001"。
        question: 自然语言问题。
        query_type: fact（单文档事实）/ relation（跨实体关系）/ multi_hop（多跳全局）。
        gold: 正确答案所在的来源文档；可带 "doc:" 前缀。
        verified: 是否已人工核对过 gold。自动草拟的题目默认未核对。
        note: 出题依据或待核对提示。
    """

    id: str
    question: str
    query_type: str
    gold: list[str]
    verified: bool = False
    note: str = ""

    @property
    def gold_docs(self) -> set[str]:
        """归一化后的 gold 文档集合。"""
        docs = (normalize_doc(_strip_gold_prefix(g)) for g in self.gold)
        return {d for d in docs if d}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvalItem":
        return cls(
            id=data["id"],
            question=data["question"],
            query_type=data["query_type"],
            gold=list(data.get("gold") or []),
            verified=bool(data.get("verified", False)),
            note=data.get("note", ""),
        )


@dataclass
class RetrievalHit:
    """一条检索命中。

    Attributes:
        chunk_id: 检索器内部标识（沿用各库原有格式）。
        source: 来源标识，可能带 `#page` 后缀。
        score: 检索器自身的相关度分数（不同检索器不可直接比较）。
        text: 命中片段文本。
    """

    chunk_id: str
    source: str
    score: float
    text: str = ""

    @property
    def doc(self) -> str:
        return normalize_doc(self.source)


def rank_docs(hits: list[RetrievalHit]) -> list[str]:
    """把命中列表压成文档排名（保序去重）。

    高频文档可能贡献多个 chunk，只要它排在最前，就算文档排在第一位——
    这正是文档级召回想要的语义，也避免了「同一文档刷榜」。
    """
    seen: set[str] = set()
    ranked: list[str] = []
    for hit in hits:
        doc = hit.doc
        if not doc or doc in seen:
            continue
        seen.add(doc)
        ranked.append(doc)
    return ranked


def load_suite(path: str | Path) -> list[EvalItem]:
    """读取题库 JSON。

    文件结构: {"name": ..., "items": [EvalItem, ...]}

    Raises:
        ValueError: 条目缺 gold，或 query_type 不在 QUERY_TYPES 内。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items: list[EvalItem] = []

    for index, raw in enumerate(data.get("items") or []):
        item = EvalItem.from_dict(raw)

        if not item.gold:
            raise ValueError(f"第 {index + 1} 条（id={item.id}）缺少 gold，无法评分")
        if item.query_type not in QUERY_TYPES:
            raise ValueError(
                f"第 {index + 1} 条（id={item.id}）query_type='{item.query_type}' 非法，"
                f"应为 {QUERY_TYPES} 之一"
            )
        items.append(item)

    return items


def save_suite(path: str | Path, items: list[EvalItem], name: str = "") -> None:
    """写回题库 JSON（保留中文）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "items": [item.to_dict() for item in items]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
