"""评测执行器 — 跑题库、按题型聚合、输出 JSON 与 Markdown 表。

设计要点:
    - 检索器通过参数注入，runner 不关心它背后是向量库、BM25 还是图谱。
    - 单个检索器整体失败（例如索引文件缺失）时记录 error 并继续跑其他档位，
      避免一个环境问题毁掉整轮实验。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from .metrics import aggregate, evaluate_item
from .schema import QUERY_TYPES, EvalItem, rank_docs

logger = logging.getLogger(__name__)


def parse_int_list(value: str) -> list[int]:
    """解析 "5,10" 这类逗号分隔的整数列表（CLI 参数用）。"""
    numbers: list[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        numbers.append(int(chunk))
    return numbers


def run_item(
    item: EvalItem,
    retriever,
    ks: Sequence[int] = (5, 10),
    top_k: int = 10,
) -> dict:
    """跑一道题，返回排名与指标。"""
    started = time.perf_counter()
    hits = retriever.retrieve(item.question, top_k=top_k, query_type=item.query_type)
    latency_ms = (time.perf_counter() - started) * 1000.0

    ranked = rank_docs(hits)
    return {
        "id": item.id,
        "question": item.question,
        "query_type": item.query_type,
        "verified": item.verified,
        "gold_docs": sorted(item.gold_docs),
        "ranked_docs": ranked[:top_k],
        "latency_ms": round(latency_ms, 1),
        "metrics": evaluate_item(item.gold_docs, ranked, ks=ks),
    }


def _summarize(per_item: list[dict]) -> dict:
    return aggregate([entry["metrics"] for entry in per_item])


def run_suite(
    items: Sequence[EvalItem],
    retrievers: Iterable,
    ks: Sequence[int] = (5, 10),
    top_k: int = 10,
    progress=None,
) -> dict:
    """跑一轮完整评测。

    Args:
        items: 题库。
        retrievers: 检索器实例（需带 `name` 属性与 `retrieve()` 方法）。
        ks: 计算哪些 recall/nDCG 截断点。
        top_k: 每次检索取多少条。
        progress: 可选回调 (system_name, done, total)。

    Returns:
        {"ks": [...], "top_k": n, "n_items": n, "systems": {name: {...}}}
    """
    systems: dict[str, dict] = {}

    for retriever in retrievers:
        name = getattr(retriever, "name", retriever.__class__.__name__)
        logger.info("开始评测: %s (%d 题)", name, len(items))

        try:
            per_item = []
            for index, item in enumerate(items):
                per_item.append(run_item(item, retriever, ks=ks, top_k=top_k))
                if progress:
                    progress(name, index + 1, len(items))
        except Exception as exc:  # noqa: BLE001 - 环境问题不该毁掉整轮实验
            logger.error("检索器 %s 评测失败: %s", name, exc)
            systems[name] = {"name": name, "error": f"{type(exc).__name__}: {exc}"}
            continue

        systems[name] = {
            "name": name,
            "overall": _summarize(per_item),
            "by_type": {
                query_type: _summarize([e for e in per_item if e["query_type"] == query_type])
                for query_type in QUERY_TYPES
            },
            "items": per_item,
        }

    return {
        "ks": list(ks),
        "top_k": top_k,
        "n_items": len(items),
        "systems": systems,
    }


def _metric_columns(result: dict) -> list[str]:
    """从结果里推断指标列（保持稳定顺序）。"""
    for system in result["systems"].values():
        if "overall" in system:
            return [k for k in system["overall"] if k != "n_items"]
    return []


def _table(rows: list[tuple[str, dict]], columns: list[str]) -> str:
    header = "| " + " | ".join(["system", *columns]) + " |"
    divider = "|" + "---|" * (len(columns) + 1)
    lines = [header, divider]
    for name, metrics in rows:
        cells = " | ".join(f"{metrics.get(col, 0.0):.3f}" for col in columns)
        lines.append(f"| {name} | {cells} |")
    return "\n".join(lines)


def render_markdown_table(result: dict) -> str:
    """把结果渲染成 Markdown 表格（主表 + 分题型表 + 人工核对子集）。

    人工核对子集单列是必须的：草稿题由图谱机械生成，对 GraphRAG 有结构性偏袒。
    DC 实测中全部 60 题上 GraphRAG 的 recall@5 是 0.821，但在 9 道人工核对题上
    只有 0.259，反而低于纯向量的 0.370——只看总表会得出完全错误的结论。
    """
    columns = _metric_columns(result)
    ok = [(name, s["overall"]) for name, s in result["systems"].items() if "overall" in s]

    blocks = [_table(ok, columns)]

    by_type_rows: list[tuple[str, dict]] = []
    for name, system in result["systems"].items():
        if "overall" not in system:
            continue
        for query_type in QUERY_TYPES:
            by_type_rows.append((f"{name} · {query_type}", system["by_type"][query_type]))
    if by_type_rows:
        blocks.append("")
        blocks.append(_table(by_type_rows, columns))

    verified_rows: list[tuple[str, dict]] = []
    for name, system in result["systems"].items():
        if "overall" not in system:
            continue
        subset = [item for item in system["items"] if item.get("verified")]
        if not subset:
            continue
        metrics = aggregate([item["metrics"] for item in subset])
        verified_rows.append((f"{name} · 仅人工核对 n={len(subset)}", metrics))
    if verified_rows:
        blocks.append("")
        blocks.append(_table(verified_rows, columns))

    failed = [f"{name}: {s['error']}" for name, s in result["systems"].items() if "error" in s]
    if failed:
        blocks.append("")
        blocks.append("失败档位: " + "; ".join(failed))

    return "\n".join(blocks)


def write_report(result: dict, json_path: str | Path, markdown_path: str | Path | None = None) -> None:
    """落盘：JSON（含逐题明细）+ 可选 Markdown 摘要。"""
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if markdown_path:
        markdown_path = Path(markdown_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown_table(result) + "\n", encoding="utf-8")
