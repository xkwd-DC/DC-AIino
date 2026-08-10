"""知识图谱构建 — 实体合并去重、关系聚合、NetworkX 图构建与 JSON 持久化。

流程:
    原始 Entity/Relationship 列表 → 实体合并（名称相似度）
    → 关系聚合 → NetworkX 有向图 → JSON 序列化到 graph_data/
"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path

import networkx as nx

from . import config
from .models import Community, Entity, GraphIndex, Relationship

logger = logging.getLogger(__name__)


def _name_similarity(a: str, b: str) -> float:
    """计算两个实体名的字符串相似度（0-1）。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def merge_entities(entities: list[Entity], threshold: float = 0.85) -> list[Entity]:
    """合并名称相似的实体（归一化 + 去重）。

    策略:
        1. 按频次降序排列，高频实体优先保留名称
        2. 若候选实体与已保留实体名称相似 > threshold 或互为子串，则合并
        3. 合并时保留高频名，聚合 source_chunks，取最长的描述

    Args:
        entities: 原始实体列表。
        threshold: 名称相似度阈值。

    Returns:
        去重合并后的实体列表。
    """
    if not entities:
        return []

    sorted_entities = sorted(entities, key=lambda e: e.frequency, reverse=True)
    merged: list[Entity] = []

    for candidate in sorted_entities:
        found = False
        for existing in merged:
            sim = _name_similarity(candidate.name, existing.name)
            is_substring = (
                candidate.name in existing.name
                or existing.name in candidate.name
            )
            if sim >= threshold or (is_substring and sim >= 0.7):
                existing.source_chunks = list(
                    set(existing.source_chunks + candidate.source_chunks)
                )
                existing.frequency += candidate.frequency
                if len(candidate.description) > len(existing.description):
                    existing.description = candidate.description
                found = True
                break

        if not found:
            merged.append(candidate)

    logger.info(
        "实体合并: %d → %d (threshold=%.2f)",
        len(entities), len(merged), threshold,
    )
    return merged


def aggregate_relationships(
    relationships: list[Relationship],
    entity_names: set[str],
) -> list[Relationship]:
    """聚合关系：同 (source, target, type) 合并权重，过滤无效关系。

    Args:
        relationships: 原始关系列表。
        entity_names: 有效实体名集合。

    Returns:
        聚合后的关系列表。
    """
    valid = [
        r for r in relationships
        if r.source in entity_names and r.target in entity_names
    ]

    key_to_rel: dict[tuple[str, str, str], Relationship] = {}
    for r in valid:
        key = (r.source, r.target, r.relation_type)
        if key in key_to_rel:
            key_to_rel[key].weight += r.weight
            if len(r.description) > len(key_to_rel[key].description):
                key_to_rel[key].description = r.description
        else:
            key_to_rel[key] = Relationship(
                source=r.source,
                target=r.target,
                relation_type=r.relation_type,
                description=r.description,
                source_chunk=r.source_chunk,
                weight=r.weight,
            )

    result = list(key_to_rel.values())
    logger.info(
        "关系聚合: %d → %d valid → %d unique",
        len(relationships), len(valid), len(result),
    )
    return result


def build_graph(
    entities: list[Entity],
    relationships: list[Relationship],
) -> nx.DiGraph:
    """从实体和关系列表构建 NetworkX 有向图。

    Args:
        entities: 合并后的实体列表。
        relationships: 聚合后的关系列表。

    Returns:
        NetworkX DiGraph。
    """
    graph = nx.DiGraph()

    for e in entities:
        graph.add_node(
            e.name,
            entity_type=e.entity_type,
            description=e.description,
            frequency=e.frequency,
            source_chunks=e.source_chunks,
        )

    for r in relationships:
        if graph.has_edge(r.source, r.target):
            existing = graph.edges[r.source, r.target]
            existing["weight"] = existing.get("weight", 1.0) + r.weight
            existing["relation_types"] = existing.get("relation_types", []) + [
                r.relation_type
            ]
        else:
            graph.add_edge(
                r.source,
                r.target,
                relation_type=r.relation_type,
                relation_types=[r.relation_type],
                description=r.description,
                weight=r.weight,
            )

    logger.info(
        "图谱构建完成: |V|=%d, |E|=%d",
        graph.number_of_nodes(), graph.number_of_edges(),
    )
    return graph


def graph_to_index(
    graph: nx.DiGraph,
    entities: list[Entity],
    relationships: list[Relationship],
    source_files: list[str],
    communities: list[Community] | None = None,
) -> GraphIndex:
    """将图谱打包为 GraphIndex 对象。

    Args:
        graph: NetworkX 图。
        entities: 实体列表。
        relationships: 关系列表。
        source_files: 源文件列表。
        communities: 社区列表。

    Returns:
        GraphIndex 对象。
    """
    return GraphIndex(
        entities=entities,
        relationships=relationships,
        communities=communities or [],
        source_files=source_files,
        entity_count=graph.number_of_nodes(),
        relation_count=graph.number_of_edges(),
        community_count=len(communities) if communities else 0,
    )


def save_index(index: GraphIndex, filepath: Path | None = None) -> Path:
    """将 GraphIndex 序列化为 JSON 文件。

    Args:
        index: 图谱索引。
        filepath: 保存路径。

    Returns:
        实际保存的文件路径。
    """
    filepath = Path(filepath) if filepath else config.GRAPH_INDEX_FILE
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": index.version,
        "source_files": index.source_files,
        "entity_count": index.entity_count,
        "relation_count": index.relation_count,
        "community_count": index.community_count,
        "entities": [
            {
                "name": e.name,
                "entity_type": e.entity_type,
                "description": e.description,
                "source_chunks": e.source_chunks,
                "frequency": e.frequency,
            }
            for e in index.entities
        ],
        "relationships": [
            {
                "source": r.source,
                "target": r.target,
                "relation_type": r.relation_type,
                "description": r.description,
                "source_chunk": r.source_chunk,
                "weight": r.weight,
            }
            for r in index.relationships
        ],
        "communities": [
            {
                "community_id": c.community_id,
                "level": c.level,
                "entity_names": c.entity_names,
                "summary": c.summary,
                "key_entities": c.key_entities,
            }
            for c in index.communities
        ],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("图谱索引已保存: %s (%.1f KB)", filepath, filepath.stat().st_size / 1024)
    return filepath


def load_index(filepath: Path | None = None) -> GraphIndex | None:
    """从 JSON 文件加载 GraphIndex。

    Args:
        filepath: 文件路径。

    Returns:
        GraphIndex 或 None。
    """
    filepath = Path(filepath) if filepath else config.GRAPH_INDEX_FILE

    if not filepath.exists():
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        entities = [
            Entity(
                name=e["name"],
                entity_type=e.get("entity_type", "其他"),
                description=e.get("description", ""),
                source_chunks=e.get("source_chunks", []),
                frequency=e.get("frequency", 1),
            )
            for e in data.get("entities", [])
        ]

        relationships = [
            Relationship(
                source=r["source"],
                target=r["target"],
                relation_type=r.get("relation_type", "相关"),
                description=r.get("description", ""),
                source_chunk=r.get("source_chunk", ""),
                weight=r.get("weight", 1.0),
            )
            for r in data.get("relationships", [])
        ]

        communities = [
            Community(
                community_id=c["community_id"],
                level=c.get("level", 0),
                entity_names=c.get("entity_names", []),
                summary=c.get("summary", ""),
                key_entities=c.get("key_entities", []),
            )
            for c in data.get("communities", [])
        ]

        index = GraphIndex(
            entities=entities,
            relationships=relationships,
            communities=communities,
            source_files=data.get("source_files", []),
            entity_count=data.get("entity_count", len(entities)),
            relation_count=data.get("relation_count", len(relationships)),
            community_count=data.get("community_count", len(communities)),
            version=data.get("version", "0.1.0"),
        )

        logger.info("图谱索引已加载: %s", index.summary())
        return index

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("图谱索引加载失败: %s", exc)
        return None


def index_to_graph(index: GraphIndex) -> nx.DiGraph:
    """从 GraphIndex 重建 NetworkX 图（用于社区检测和搜索）。

    Args:
        index: 图谱索引。

    Returns:
        NetworkX DiGraph。
    """
    graph = nx.DiGraph()

    for e in index.entities:
        graph.add_node(
            e.name,
            entity_type=e.entity_type,
            description=e.description,
            frequency=e.frequency,
        )

    for r in index.relationships:
        graph.add_edge(
            r.source,
            r.target,
            relation_type=r.relation_type,
            description=r.description,
            weight=r.weight,
        )

    return graph
