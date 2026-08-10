"""图谱搜索 — 多模式检索：Global / Local / Basic。

搜索模式:
    Global:   用社区摘要回答综述型问题（跨文档综合）
    Local:    从匹配实体出发沿图谱遍历邻居（实体聚焦）
    Basic:    回退到传统向量检索
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

import networkx as nx

from . import config
from .models import Community, Entity, GraphIndex, SearchResult

logger = logging.getLogger(__name__)


def _entity_name_match(query_entity: str, graph_entity: str) -> float:
    """计算查询实体与图谱实体的名称匹配度（0-1）。"""
    q_lower = query_entity.lower()
    g_lower = graph_entity.lower()

    if q_lower == g_lower:
        return 1.0
    if q_lower in g_lower or g_lower in q_lower:
        return 0.9
    return SequenceMatcher(None, q_lower, g_lower).ratio()


def _extract_query_entities(query: str) -> list[str]:
    """使用 LLM 从查询中提取关键实体名。"""
    from .extractor import _get_client as get_extractor_client

    try:
        client = get_extractor_client()
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个实体识别助手。从用户问题中提取关键实体名称。"
                        "实体可能包括：气候因子、作物、地理区域、研究方法、指标名称等。"
                        "只输出实体名称，一行一个，不要编号或额外文字。"
                        "如果问题中没有明确实体，输出 NONE。"
                    ),
                },
                {"role": "user", "content": f"问题：{query}"},
            ],
            max_tokens=200,
            temperature=0.0,
        )
        text = response.choices[0].message.content or ""
        entities = [
            line.strip()
            for line in text.split("\n")
            if line.strip() and line.strip() != "NONE"
        ]
        logger.debug("查询实体提取: %s → %s", query[:60], entities)
        return entities

    except Exception as exc:
        logger.warning("查询实体提取失败: %s", exc)
        return []


def _match_entities_to_graph(
    query_entities: list[str],
    entities: list[Entity],
    top_k: int = 5,
) -> list[Entity]:
    """将查询实体匹配到图谱中的实体，按名称相似度排序。"""
    if not query_entities:
        return []

    scored: list[tuple[float, Entity]] = []
    for ge in entities:
        best_score = 0.0
        for qe in query_entities:
            score = _entity_name_match(qe, ge.name)
            if score > best_score:
                best_score = score
        if best_score > 0.5:
            scored.append((best_score, ge))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


# ─── Global Search ────────────────────────────────────────────────────────

def global_search(
    query: str,
    index: GraphIndex,
    top_k: int | None = None,
) -> list[SearchResult]:
    """全局搜索：基于社区摘要回答综述型问题。

    适用: "当前研究的主要方向有哪些？" "气候变化对粮食生产的主要影响途径？"
    """
    top_k = top_k or config.GRAPH_SEARCH_TOP_K

    if not index.communities:
        logger.warning("无社区摘要可用")
        return []

    query_entities = _extract_query_entities(query)
    entity_set = set(query_entities) if query_entities else set()

    scored: list[tuple[int, Community]] = []
    for c in index.communities:
        if not c.summary or "失败" in c.summary:
            continue

        score = 0
        if entity_set:
            matched = sum(
                1 for e in c.entity_names
                if any(_entity_name_match(qe, e) > 0.6 for qe in query_entities)
            )
            score = matched
        else:
            score = len(c.entity_names)

        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[SearchResult] = []
    for score, c in scored[:top_k]:
        header = (
            f"【知识社区 #{c.community_id}】"
            f"核心实体: {', '.join(c.key_entities[:5])}\n"
        )
        results.append(SearchResult(
            content=header + c.summary,
            source_type="community_summary",
            source_ids=c.entity_names,
            relevance=min(score / max(len(query_entities), 1), 1.0) if query_entities else 0.5,
        ))

    logger.info("Global search: %d 社区结果 (matches=%s)", len(results), query_entities)
    return results


# ─── Local Search ─────────────────────────────────────────────────────────

def local_search(
    query: str,
    index: GraphIndex,
    graph: nx.DiGraph | None = None,
    top_k: int | None = None,
    max_hops: int | None = None,
    max_neighbors: int | None = None,
) -> list[SearchResult]:
    """局部搜索：从匹配实体出发沿图谱遍历获取关联上下文。

    适用: "高温胁迫对华北平原冬小麦产量的影响机制？"
    """
    top_k = top_k or config.GRAPH_SEARCH_TOP_K
    max_hops = max_hops or config.GRAPH_SEARCH_MAX_HOPS
    max_neighbors = max_neighbors or config.GRAPH_SEARCH_MAX_NEIGHBORS

    if graph is None:
        from .graph_builder import index_to_graph
        graph = index_to_graph(index)

    # 匹配查询实体 → 图谱实体
    query_entities = _extract_query_entities(query)
    matched = _match_entities_to_graph(query_entities, index.entities, top_k=top_k)

    if not matched:
        logger.info("Local search: 无匹配实体, 回退 global")
        return global_search(query, index, top_k)

    logger.info("Local search: 匹配 %d 实体: %s", len(matched), [e.name for e in matched])

    # BFS 图谱遍历
    visited: set[str] = set()
    context_parts: list[str] = []
    current_nodes = [e.name for e in matched]

    for hop in range(max_hops + 1):
        next_nodes: list[str] = []

        for node in current_nodes:
            if node in visited:
                continue
            visited.add(node)

            if node in graph.nodes:
                nd = graph.nodes[node]
                context_parts.append(f"[{nd.get('entity_type', '?')}] {node}: {nd.get('description', '')}")

            # 收集带权重的邻居
            neighbors: list[tuple[str, float]] = []
            for _, nb, data in graph.out_edges(node, data=True):
                neighbors.append((nb, data.get("weight", 1.0)))
            for nb, _, data in graph.in_edges(node, data=True):
                neighbors.append((nb, data.get("weight", 1.0)))

            neighbors.sort(key=lambda x: x[1], reverse=True)
            for neighbor, _ in neighbors[:max_neighbors]:
                if neighbor not in visited:
                    edge_desc = ""
                    if graph.has_edge(node, neighbor):
                        edge_desc = graph.edges[node, neighbor].get("description", "")
                    elif graph.has_edge(neighbor, node):
                        edge_desc = graph.edges[neighbor, node].get("description", "")
                    if edge_desc:
                        context_parts.append(f"  → {neighbor}: {edge_desc}")
                    next_nodes.append(neighbor)

        current_nodes = list(set(next_nodes) - visited)
        if not current_nodes:
            break

    context_text = "\n".join(context_parts)
    results = [
        SearchResult(
            content=context_text,
            source_type="entity",
            source_ids=[e.name for e in matched],
            relevance=1.0,
        )
    ]

    logger.info("Local search: %d nodes, %d chars", len(visited), len(context_text))
    return results


# ─── Basic Search ─────────────────────────────────────────────────────────

def basic_search(
    query: str,
    _index: GraphIndex | None = None,
    _graph: nx.DiGraph | None = None,
) -> list[SearchResult]:
    """基础搜索：返回空，由调用方回退向量检索。"""
    logger.info("Basic search: 回退向量检索")
    return []


# ─── 查询路由 ─────────────────────────────────────────────────────────────

_GLOBAL_KEYWORDS = [
    "综述", "总结", "概述", "全面", "整体", "主要方向", "研究现状",
    "有哪些", "什么类型", "分类", "体系", "框架", "全景",
    "overview", "summary", "总结一下", "归纳",
]


def classify_query(query: str) -> str:
    """根据查询内容判断应使用哪种搜索模式。

    Returns:
        "global" | "local" | "basic"
    """
    query_lower = query.lower()

    if any(kw in query_lower for kw in _GLOBAL_KEYWORDS):
        return "global"

    query_entities = _extract_query_entities(query)
    if query_entities:
        return "local"

    return "basic"
