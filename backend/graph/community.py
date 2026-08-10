"""社区检测 & 摘要生成 — Louvain 层次聚类 + DeepSeek 社区摘要。

流程:
    NetworkX 图 → Louvain 社区检测 → 层次聚类
    → 每社区 LLM 生成摘要 → Community 对象列表
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import networkx as nx
from networkx.algorithms.community import louvain_communities

from . import config
from .models import Community

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from openai import OpenAI


# ─── 社区摘要 Prompt ──────────────────────────────────────────────────────

_COMMUNITY_SUMMARY_SYSTEM = """你是一个学术研究综合专家，擅长将多个相关概念整合为连贯的概述。

你的任务是：根据一个"知识社区"中的实体和关系，生成一段该社区的综合摘要。
摘要应该：
1. 概述这个社区研究的核心主题
2. 说明社区内关键实体之间的主要关系
3. 突出最重要的发现或结论
4. 中文输出，200-400字"""


def _build_community_prompt(
    community_id: int,
    entity_names: list[str],
    graph: nx.DiGraph,
) -> str:
    """构建社区摘要的 prompt。"""
    entity_info: list[str] = []
    for name in entity_names:
        if name in graph.nodes:
            node = graph.nodes[name]
            entity_info.append(
                f"- {name} [{node.get('entity_type', '未知')}]: "
                f"{node.get('description', '无描述')}"
            )

    relation_info: list[str] = []
    for u, v, data in graph.edges(data=True):
        if u in entity_names and v in entity_names:
            relation_info.append(
                f"- {u} → {v} "
                f"[{data.get('relation_type', '相关')}]: "
                f"{data.get('description', '无描述')}"
            )

    entities_text = "\n".join(entity_info[:30])
    relations_text = "\n".join(relation_info[:50])

    return (
        f"## 社区 #{community_id} 知识图谱摘要\n\n"
        f"### 实体列表（{len(entity_names)} 个）\n{entities_text}\n\n"
        f"### 内部关系（{len(relation_info)} 条）\n{relations_text}\n\n"
        f"请生成该研究社区的综合摘要。"
    )


def _get_client() -> "OpenAI":
    """Lazy init OpenAI 客户端。"""
    from openai import OpenAI
    import httpx

    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=httpx.Timeout(60.0, connect=15.0),
    )


def _summarize_community(
    community_id: int,
    entity_names: list[str],
    graph: nx.DiGraph,
) -> str:
    """使用 LLM 生成单个社区的摘要。"""
    if len(entity_names) < config.COMMUNITY_MIN_SIZE:
        return f"（社区 #{community_id}：实体数量不足，自动跳过）"

    client = _get_client()
    prompt = _build_community_prompt(community_id, entity_names, graph)

    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _COMMUNITY_SUMMARY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=config.SUMMARIZATION_MAX_TOKENS,
            temperature=config.SUMMARIZATION_TEMPERATURE,
        )
        summary = response.choices[0].message.content or ""
        logger.debug("社区 #%d 摘要: %d chars", community_id, len(summary))
        return summary.strip()

    except Exception as exc:
        logger.error("社区 #%d 摘要失败: %s", community_id, exc)
        return f"（社区 #{community_id} 摘要生成失败）"


def _get_key_entities(
    entity_names: list[str],
    graph: nx.DiGraph,
    top_k: int = 5,
) -> list[str]:
    """获取社区内的关键实体（度中心性 top-k）。"""
    subgraph = graph.subgraph(entity_names)
    if subgraph.number_of_nodes() == 0:
        return []

    centrality = nx.degree_centrality(subgraph)
    sorted_entities = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    return [name for name, _ in sorted_entities[:top_k]]


def detect_communities(
    graph: nx.DiGraph,
    min_size: int | None = None,
    max_levels: int | None = None,
) -> list[Community]:
    """使用 Louvain 算法检测图谱社区并生成摘要。

    Args:
        graph: NetworkX 有向图。
        min_size: 最小社区实体数。
        max_levels: 层次聚类最大层级。

    Returns:
        Community 对象列表。
    """
    min_size = min_size or config.COMMUNITY_MIN_SIZE

    if graph.number_of_nodes() == 0:
        logger.warning("图为空，跳过社区检测")
        return []

    undirected = graph.to_undirected()

    logger.info(
        "开始 Louvain 社区检测: |V|=%d, |E|=%d",
        graph.number_of_nodes(), graph.number_of_edges(),
    )

    try:
        communities_iter = louvain_communities(
            undirected, weight="weight", resolution=1.0, seed=42,
        )
        raw_communities = list(communities_iter)
    except Exception as exc:
        logger.error("Louvain 社区检测失败: %s", exc)
        return []

    # 过滤太小的社区
    raw_communities = [list(c) for c in raw_communities if len(c) >= min_size]

    logger.info(
        "社区检测完成: %d 个社区 (min_size=%d)",
        len(raw_communities), min_size,
    )

    # 生成社区摘要
    communities: list[Community] = []
    total = len(raw_communities)

    for i, entity_names in enumerate(raw_communities):
        logger.info("社区摘要 %d/%d (%d 实体)...", i + 1, total, len(entity_names))

        key_entities = _get_key_entities(entity_names, graph)
        summary = _summarize_community(i, entity_names, graph)
        time.sleep(0.3)

        communities.append(Community(
            community_id=i,
            level=0,
            entity_names=entity_names,
            summary=summary,
            key_entities=key_entities,
        ))

    logger.info(
        "社区摘要完成: %d 个, 平均 %.0f 实体/社区",
        len(communities),
        sum(len(c.entity_names) for c in communities) / max(len(communities), 1),
    )
    return communities
