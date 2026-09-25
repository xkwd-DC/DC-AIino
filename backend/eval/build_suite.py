"""题库草拟器 — 从图谱索引机械推出候选题目与 gold。

为什么是"草拟":
    gold 必须能追溯到语料，所以这里全部靠机械推导：
        事实型   只取**恰好一个来源文档**的实体 → gold = 那个文档（确保单文档可答）
        关系型   取两端实体都存在的关系 → gold = 两端实体的来源文档并集
        多跳型   取有摘要且有核心实体的社区 → gold = 核心实体的来源文档并集
    这样 gold 一定"确实包含答案"，不会凭空捏造；但**问法**是模板化的，
    需要人工改写得更自然，并把 verified 打开。

已知偏差（写论文时要如实披露）:
    候选实体/关系/社区来自图谱本身，对 GraphRAG 档位存在结构性偏袒。
    人工复核时应尽量保留那些"用向量检索也能答"的题目，并单独统计来源构成。

用法:
    python -m eval.build_suite --per-type 20 --out eval/suites/dc_rag_v1.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .schema import EvalItem, normalize_doc, save_suite

if TYPE_CHECKING:
    from graph.models import GraphIndex

logger = logging.getLogger(__name__)

#: 多跳题问法里最多点几个核心实体
_MAX_ENTITIES_IN_QUESTION = 3

#: gold 文档数上限。像"R²"这种无处不在的实体能牵出 40+ 篇文档，
#: gold 一大，任何一篇命中都算召回，指标会虚高，所以直接剔除这类题。
_MAX_GOLD_DOCS = 5

#: 人工核对过的题目（可选），与生成题合并
SEEDS_FILE = Path(__file__).resolve().parent / "suites" / "seeds_verified.json"


def _entity_docs(entity) -> list[str]:
    """实体来源文档（保序去重）。"""
    docs: list[str] = []
    for chunk in entity.source_chunks or []:
        doc = normalize_doc(chunk)
        if doc and doc not in docs:
            docs.append(doc)
    return docs


def draft_fact_items(index: "GraphIndex", per_type: int = 20) -> list[EvalItem]:
    """事实型：单文档可答的实体定义题。"""
    items: list[EvalItem] = []

    for entity in sorted(index.entities, key=lambda e: e.name):
        if len(items) >= per_type:
            break
        if not (entity.name or "").strip():
            continue

        docs = _entity_docs(entity)
        if len(docs) != 1:
            continue

        items.append(
            EvalItem(
                id="",
                question=f"{entity.name} 是什么？请根据知识库给出定义或说明。",
                query_type="fact",
                gold=[f"doc:{docs[0]}"],
                note=f"由实体「{entity.name}」机械生成，gold 为其唯一来源文档，待人工复核问法",
            )
        )

    return items


def draft_relation_items(
    index: "GraphIndex",
    per_type: int = 20,
    max_gold_docs: int = _MAX_GOLD_DOCS,
) -> list[EvalItem]:
    """关系型：两端实体都在图谱里的关系题。"""
    by_name = {(e.name or "").strip().lower(): e for e in index.entities}
    items: list[EvalItem] = []
    seen: set[tuple[str, str]] = set()

    for relation in index.relationships:
        if len(items) >= per_type:
            break

        source = (relation.source or "").strip()
        target = (relation.target or "").strip()
        if not source or not target:
            continue

        pair = (source.lower(), target.lower())
        if pair in seen:
            continue

        source_entity = by_name.get(pair[0])
        target_entity = by_name.get(pair[1])
        if source_entity is None or target_entity is None:
            continue

        docs = _entity_docs(source_entity) + _entity_docs(target_entity)
        docs = list(dict.fromkeys(docs))
        if not docs or len(docs) > max_gold_docs:
            continue

        seen.add(pair)
        items.append(
            EvalItem(
                id="",
                question=f"{source} 与 {target} 之间是什么关系？",
                query_type="relation",
                gold=[f"doc:{d}" for d in docs],
                note=f"由关系「{source} → {target}」机械生成，gold 为两端实体来源文档并集",
            )
        )

    return items


def draft_multi_hop_items(
    index: "GraphIndex",
    per_type: int = 20,
    max_gold_docs: int = _MAX_GOLD_DOCS,
) -> list[EvalItem]:
    """多跳型：社区级综述题。"""
    by_name = {(e.name or "").strip().lower(): e for e in index.entities}
    items: list[EvalItem] = []

    ordered = sorted(index.communities, key=lambda c: (-len(c.key_entities or []), c.community_id))

    for community in ordered:
        if len(items) >= per_type:
            break

        key_entities = [n for n in (community.key_entities or []) if (n or "").strip()]
        if not key_entities or not (community.summary or "").strip():
            continue

        docs: list[str] = []
        for name in key_entities:
            entity = by_name.get(name.strip().lower())
            if entity is not None:
                docs.extend(_entity_docs(entity))
        docs = list(dict.fromkeys(docs))
        if not docs or len(docs) > max_gold_docs:
            continue

        shown = key_entities[:_MAX_ENTITIES_IN_QUESTION]
        items.append(
            EvalItem(
                id="",
                question=f"围绕 {'、'.join(shown)} 等主题，知识库中有哪些主要结论？",
                query_type="multi_hop",
                gold=[f"doc:{d}" for d in docs],
                note=f"由社区 #{community.community_id} 机械生成，gold 为核心实体来源文档并集",
            )
        )

    return items


def build_draft(index: "GraphIndex", per_type: int = 20) -> list[EvalItem]:
    """三类各草拟 per_type 题，统一编号。"""
    drafts: list[EvalItem] = []
    drafts.extend(draft_fact_items(index, per_type))
    drafts.extend(draft_relation_items(index, per_type))
    drafts.extend(draft_multi_hop_items(index, per_type))

    for number, item in enumerate(drafts, start=1):
        item.id = f"q{number:03d}"

    return drafts


def load_seeds(path: Path = SEEDS_FILE) -> list[EvalItem]:
    """读取人工核对过的种子题（不存在则返回空）。"""
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for raw in data.get("items") or []:
        item = EvalItem.from_dict(raw)
        item.verified = True
        items.append(item)
    return items


def merge(seeds: list[EvalItem], drafts: list[EvalItem], per_type: int = 20) -> list[EvalItem]:
    """种子题优先占位，生成题补足每类配额，按问题文本去重。"""
    merged: list[EvalItem] = []
    seen_questions: set[str] = set()
    counts = {"fact": 0, "relation": 0, "multi_hop": 0}

    for item in seeds + drafts:
        if counts.get(item.query_type, 0) >= per_type:
            continue
        key = item.question.strip()
        if not key or key in seen_questions:
            continue
        seen_questions.add(key)
        counts[item.query_type] = counts.get(item.query_type, 0) + 1
        merged.append(item)

    for number, item in enumerate(merged, start=1):
        item.id = f"q{number:03d}"

    return merged


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval.build_suite", description="草拟检索评测题库")
    parser.add_argument("--per-type", type=int, default=20, help="每类题目数量（默认 20）")
    parser.add_argument("--out", default="eval/suites/dc_rag_v1.json", help="输出路径")
    parser.add_argument("--clean-min-mentions", type=int, default=1, help="实体清洗的最小提及次数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from graph.cleaner import CleanPolicy, clean_entities
    from graph.graph_builder import load_index

    index = load_index()
    kept, report = clean_entities(index.entities, CleanPolicy(min_chunk_mentions=args.clean_min_mentions))
    logger.info(report.summary())
    index.entities = kept

    seeds = load_seeds()
    drafts = build_draft(index, per_type=args.per_type)
    items = merge(seeds, drafts, per_type=args.per_type)

    out = Path(args.out)
    save_suite(out, items, name="dc_rag_v1")

    verified = sum(1 for i in items if i.verified)
    logger.info(
        "题库已写出: %s（共 %d 题，已核对 %d 题，待核对 %d 题）",
        out, len(items), verified, len(items) - verified,
    )


if __name__ == "__main__":
    main()
