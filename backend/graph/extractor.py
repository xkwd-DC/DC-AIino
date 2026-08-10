"""实体/关系提取器 — 使用 DeepSeek LLM 从文本块中提取知识图谱元素。

流程:
    文本块 → LLM 结构化提取 → JSON 解析 → Entity + Relationship 列表

提取策略:
    - 每块独立提取（不跨块合并，避免上下文混淆）
    - 低 temperature (0.1) 保证实体名一致性
    - JSON 输出 + 容错解析（正则兜底）
    - 失败自动重试 + 指数退避
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING

from . import config
from .models import Entity, Relationship

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from openai import OpenAI

_CLIENT: "OpenAI | None" = None


def _get_client() -> "OpenAI":
    """Lazy init OpenAI 客户端（指向 DeepSeek）。"""
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI
        import httpx

        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未设置")

        _CLIENT = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(60.0, connect=15.0),
        )
    return _CLIENT


# ─── 提取 Prompt ──────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """你是一个知识图谱构建专家，专精于从学术文献中提取结构化知识。

你的任务是：从给定的文本片段中，识别出关键实体（entities）和实体之间的关系（relationships）。

## 实体类型
从以下类型中选择最合适的一个：
- 气候因子：温度、降水、干旱、洪涝、极端高温、极端低温、CO2浓度等
- 作物：小麦、水稻、玉米、大豆、棉花等
- 地理区域：华北平原、东北地区、黄淮海地区、长江流域等
- 研究方法：XGBoost、SHAP、LSTM、随机森林、空间杜宾模型、地理探测器等
- 指标：产量、SPEI(标准化降水蒸散指数)、R²、RMSE、NDVI等
- 概念：气候韧性、粮食安全、适应性、脆弱性、暴露度等
- 数据来源：气象站数据、遥感数据、统计年鉴、CMIP6等
- 机构/作者：论文作者、研究机构名称
- 其他：不属于以上类型的实体

## 关系类型
- 影响：A 对 B 产生影响
- 导致：A 直接导致 B
- 测量：A 用来测量/量化 B
- 属于：A 属于 B 类别
- 位于：A 位于 B 区域
- 使用：A 方法/工具应用于 B
- 相关：A 与 B 有相关关系
- 包含：A 包含 B

## 输出格式
严格输出 JSON，不要任何额外文字：
{
  "entities": [
    {"name": "实体名", "type": "实体类型", "description": "一句话描述"}
  ],
  "relationships": [
    {"source": "源实体名", "target": "目标实体名", "type": "关系类型", "description": "关系说明"}
  ]
}

## 规则
1. 实体名要简洁规范（如"高温胁迫"而非"严重的高温胁迫现象"）
2. 只提取文本中明确提到的实体，不推测
3. 每个实体至少出现在一条关系中（孤立实体不提取）
4. 关系描述要具体，说明 A 如何影响/关联 B
5. 如果文本中没有可提取的实体和关系，返回空数组"""


def _build_extraction_prompt(text: str) -> str:
    """构造单块提取的 user prompt。"""
    entity_types_str = "、".join(config.ENTITY_TYPES)
    return (
        f"请从以下学术文献片段中提取实体和关系。"
        f"可用实体类型: {entity_types_str}。\n\n"
        f"## 文本\n{text}\n\n"
        f"请输出 JSON。"
    )


def _parse_extraction_response(response_text: str) -> tuple[list[dict], list[dict]]:
    """解析 LLM 返回的 JSON，容错处理。

    返回: (entities_list, relationships_list)
    """
    text = response_text.strip()

    # 1. 去掉 markdown 代码块包裹 (```json ... ``` 或 ``` ... ```)
    md_stripped = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
    md_stripped = re.sub(r'\n?```\s*$', '', md_stripped, flags=re.MULTILINE)
    if md_stripped != text:
        text = md_stripped.strip()

    # 2. 直接 JSON 解析
    try:
        data = json.loads(text)
        return data.get("entities", []), data.get("relationships", [])
    except json.JSONDecodeError:
        pass

    # 3. 提取最外层 JSON 对象（处理前后多余文字）
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(text[first_brace:last_brace + 1])
            return data.get("entities", []), data.get("relationships", [])
        except json.JSONDecodeError:
            pass

    logger.warning("无法解析 LLM 提取结果，原始响应: %s...", response_text[:200])
    return [], []


def extract_from_chunk(
    text: str,
    chunk_id: str = "",
    max_retries: int | None = None,
) -> tuple[list[Entity], list[Relationship]]:
    """从单个文本块提取实体和关系。

    Args:
        text: 文本内容。
        chunk_id: 块标识（用于溯源）。
        max_retries: 最大重试次数。

    Returns:
        (entities, relationships) 列表。
    """
    max_retries = max_retries if max_retries is not None else config.EXTRACTION_MAX_RETRIES
    client = _get_client()
    prompt = _build_extraction_prompt(text)

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=config.EXTRACTION_MAX_TOKENS,
                temperature=config.EXTRACTION_TEMPERATURE,
            )
            response_text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0

            raw_entities, raw_relations = _parse_extraction_response(response_text)

            entities = [
                Entity(
                    name=e.get("name", "").strip(),
                    entity_type=e.get("type", "其他"),
                    description=e.get("description", "").strip(),
                    source_chunks=[chunk_id] if chunk_id else [],
                )
                for e in raw_entities
                if e.get("name", "").strip()
            ]

            relationships = [
                Relationship(
                    source=r.get("source", "").strip(),
                    target=r.get("target", "").strip(),
                    relation_type=r.get("type", "相关"),
                    description=r.get("description", "").strip(),
                    source_chunk=chunk_id,
                )
                for r in raw_relations
                if r.get("source", "").strip() and r.get("target", "").strip()
            ]

            logger.debug(
                "提取完成: chunk=%s → %d 实体, %d 关系 (tokens=%d)",
                chunk_id[:40], len(entities), len(relationships), tokens,
            )
            return entities, relationships

        except Exception as exc:
            logger.warning(
                "提取失败 (attempt %d/%d, chunk=%s): %s",
                attempt + 1, max_retries + 1, chunk_id[:40], exc,
            )
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.error("提取彻底失败: chunk=%s", chunk_id[:40])

    return [], []


def extract_from_chunks(
    chunks: list[tuple[str, str]],  # [(text, chunk_id), ...]
    batch_size: int | None = None,
    progress_callback=None,
) -> tuple[list[Entity], list[Relationship]]:
    """批量从多个文本块提取实体和关系。

    逐块调用 LLM，带进度回调和速率控制。

    Args:
        chunks: [(text, chunk_id), ...] 文本块列表。
        batch_size: 未使用（逐块提取）。
        progress_callback: 可选回调 (current: int, total: int)。

    Returns:
        (all_entities, all_relationships) 列表。
    """
    all_entities: list[Entity] = []
    all_relationships: list[Relationship] = []
    total = len(chunks)

    logger.info("开始图谱提取: %d 个文本块", total)

    for i, (text, chunk_id) in enumerate(chunks):
        if not text.strip():
            continue

        entities, relationships = extract_from_chunk(text, chunk_id)
        all_entities.extend(entities)
        all_relationships.extend(relationships)

        if progress_callback:
            progress_callback(i + 1, total)

        # 速率控制
        if i < total - 1:
            time.sleep(0.3)

    logger.info(
        "图谱提取完成: %d 实体, %d 关系 (from %d chunks)",
        len(all_entities), len(all_relationships), total,
    )
    return all_entities, all_relationships
