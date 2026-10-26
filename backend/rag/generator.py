"""LLM 生成器 — 调用 DeepSeek API 基于检索上下文生成回答。

DeepSeek API 与 OpenAI SDK 兼容，base_url 指向 https://api.deepseek.com。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from openai import OpenAI

_CLIENT: "OpenAI | None" = None


def _get_client() -> "OpenAI":
    """Lazy init OpenAI 客户端（指向 DeepSeek）。"""
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI  # noqa: import-not-at-top

        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError(
                "DEEPSEEK_API_KEY 未设置。请在 .env 中配置后重启。"
            )

        _CLIENT = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
        logger.info(
            "DeepSeek 客户端初始化: model=%s base_url=%s",
            config.DEEPSEEK_MODEL, config.DEEPSEEK_BASE_URL,
        )
    return _CLIENT


# ─── 系统提示词 ──────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """你是"稷韧云图"知识助手，专精于极端气候下粮食生产风险分析。

你的知识来源于 DC 项目的文档库，涵盖：
- 学术文献笔记（气候韧性、极端气候、粮食产量、SHAP 归因等）
- 项目模型卡（XGBoost-SHAP, LSTM, Attention-LSTM）
- 数据集说明、方法论文档、实验报告

回答规则：
1. 仅基于提供的上下文信息回答，不要编造未在上下文中出现的数据或结论。
2. 如果上下文不足以回答问题，诚实说明"当前知识库中未找到相关信息"。
3. 回答用中文，学术风格但易于理解。
4. 引用来源时标注【来源 N】。
5. 回答控制在 500 字以内，重点突出。
6. 本系统输出属于统计关联与模型内情景，不得表述为因果结论、政策效果
   或产量预报。遇到“导致 / 证明 / 必然 / 能增产多少”这类问题，必须
   明确说明证据边界，并建议结合农学机理、田间试验和专家研判。"""


def generate(
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, int]:
    """调用 DeepSeek API 生成回答。

    Args:
        question: 用户问题。
        context: 检索到的上下文。
        history: 可选对话历史 [{"role": "user", "content": "..."}, ...]。

    Returns:
        (answer_text, tokens_used)。
    """
    client = _get_client()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]

    user_message = (
        f"请根据以下参考信息回答用户问题。\n\n"
        f"## 参考信息\n{context}\n\n"
        f"## 用户问题\n{question}"
    )
    if history:
        messages.extend(history[-12:])  # 最多 6 轮对话

    messages.append({"role": "user", "content": user_message})

    logger.info(
        "调用 DeepSeek API: model=%s question='%s'",
        config.DEEPSEEK_MODEL, question[:80],
    )

    try:
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=config.DEEPSEEK_MAX_TOKENS,
            temperature=config.DEEPSEEK_TEMPERATURE,
        )
    except Exception as exc:
        logger.error("DeepSeek API 调用失败: %s", exc)
        raise

    answer = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0

    logger.info("DeepSeek 返回: %d chars, %d tokens", len(answer), tokens)
    return answer.strip(), tokens


def generate_stream(
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
):
    """流式调用 DeepSeek API，逐 token yield。

    用法:
        for chunk in generate_stream(q, ctx):
            yield chunk
    """
    client = _get_client()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    user_message = (
        f"请根据以下参考信息回答用户问题。\n\n"
        f"## 参考信息\n{context}\n\n"
        f"## 用户问题\n{question}"
    )
    if history:
        messages.extend(history[-12:])
    messages.append({"role": "user", "content": user_message})

    try:
        stream = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=config.DEEPSEEK_MAX_TOKENS,
            temperature=config.DEEPSEEK_TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:
        logger.error("DeepSeek 流式调用失败: %s", exc)
        yield f"\n[生成中断: {exc}]"
