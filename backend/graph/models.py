"""GraphRAG 数据模型 — 实体、关系、社区、图谱索引。

数据类定义，用于 graph 模块内部传递结构化数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Entity:
    """知识图谱中的实体节点。

    Attributes:
        name: 实体名称（规范化后）。
        entity_type: 实体类型标签（气候因子/作物/方法/区域/指标/概念/数据/其他）。
        description: 实体描述，从原文提取。
        source_chunks: 该实体出现的源文档 chunk ID 列表。
        frequency: 实体在语料中的出现频次。
    """

    name: str
    entity_type: str
    description: str = ""
    source_chunks: list[str] = field(default_factory=list)
    frequency: int = 1


@dataclass
class Relationship:
    """知识图谱中的关系边。

    Attributes:
        source: 源实体名称。
        target: 目标实体名称。
        relation_type: 关系类型（影响/测量/属于/位于/相关/使用/导致/包含）。
        description: 关系描述。
        source_chunk: 提取该关系的 chunk ID。
        weight: 关系权重（同类型关系被多次提取时累加）。
    """

    source: str
    target: str
    relation_type: str
    description: str = ""
    source_chunk: str = ""
    weight: float = 1.0


@dataclass
class Community:
    """图谱社区（通过 Louvain 检测得到）。

    Attributes:
        community_id: 社区编号。
        level: 层级（0 = 最底层, 越高越聚合）。
        entity_names: 社区内实体名称列表。
        summary: LLM 生成的社区摘要。
        key_entities: 社区中的核心实体（度中心性 top-N）。
    """

    community_id: int
    level: int = 0
    entity_names: list[str] = field(default_factory=list)
    summary: str = ""
    key_entities: list[str] = field(default_factory=list)


@dataclass
class GraphIndex:
    """完整的图谱索引结构，可序列化到磁盘。

    持久化文件: graph_data/graph_index.json
    """

    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    communities: list[Community] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    entity_count: int = 0
    relation_count: int = 0
    community_count: int = 0
    version: str = "0.1.0"

    def summary(self) -> str:
        return (
            f"GraphIndex(v{self.version}): "
            f"{self.entity_count} entities, "
            f"{self.relation_count} relationships, "
            f"{self.community_count} communities, "
            f"{len(self.source_files)} source files"
        )


@dataclass
class SearchResult:
    """图谱搜索结果。

    Attributes:
        content: LLM 可用的文本内容。
        source_type: 来源类型（community_summary/entity/relationship/chunk）。
        source_ids: 关联的实体或 chunk ID。
        relevance: 相关度分数（0-1）。
    """

    content: str
    source_type: str
    source_ids: list[str] = field(default_factory=list)
    relevance: float = 0.0
