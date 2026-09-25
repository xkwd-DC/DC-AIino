"""图谱实体清洗 — 去掉 LLM 抽取带来的机械噪声。

清洗规则按顺序命中，第一个命中即归类，便于在论文里如实报告"每类砍掉多少"：

    太短       单字符（L / ρ / 潘）——变量符号或姓名碎片
    过长       超长描述串
    纯数字或量值 2022 / 4615 kg/ha / 8℃
    路径或文件名 docs\\...md / STATUS.md / docs/_craic/figures/
    版本或占位记号 x2 / v3 / 9NN / B:6
    提及次数不足 可选规则，默认关闭（见下）

关于「提及次数不足」:
    实测 3495 个实体里有 2238 个只出现在 1 个 chunk（64%）。这条规则效果最大，
    但也会误伤只被提到一次的正当术语，所以**默认不启用**（min_chunk_mentions=1），
    由调用方显式开启后作为论文的敏感性分析行，而不是偷偷把图谱改小。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Entity

# 量值（数字与单位之间必须有空格）: "4615 kg/ha" / "500 kg/ha"
# 不写 \s* 是为了不把 "9NN"、"2SLS" 这类记号误判成量值
_QUANTITY = re.compile(r"^[\d.,]+\s+[A-Za-zµμ%/·]+[\d.,\s/]*$")
# 量值（符号单位）: "8℃" / "50%"
_QUANTITY_SYMBOL = re.compile(r"^[\d.,]+\s*[℃°%‰]+$")
# 纯数字（含千分位、百分号）: "2022" / "1,234"
_PURE_NUMBER = re.compile(r"^[\d.,\s%]+$")
# 文件名后缀
_FILE_EXT = re.compile(r"\.(md|pdf|py|json|txt|csv|xlsx|xls|docx|doc|png|jpg|pptx|html)$", re.I)
# 版本/占位记号: "x2" / "v3" —— 只收小写前缀，避免误伤 ERA5 / WGS84 / Vue3
_VERSION_TOKEN = re.compile(r"^[a-z]{1,2}\d{1,2}$")
# 数字开头的占位记号: "9NN" —— 限定大写后缀，避免误伤 2SLS 这类真实方法名
_PLACEHOLDER_TOKEN = re.compile(r"^\d{1,4}[A-Z]{1,2}$")
# 键值占位: "B:6" —— 两侧都必须是短 ASCII，避免误伤"随机8:2划分"这类描述
_KEYED_TOKEN = re.compile(r"^[A-Za-z0-9]{1,3}:[A-Za-z0-9]{1,3}$")

_MAX_EXAMPLES = 10


@dataclass
class CleanPolicy:
    """清洗策略。

    Attributes:
        min_chars: 名字短于该长度即丢弃。
        max_chars: 名字长于该长度即丢弃。
        min_chunk_mentions: 至少出现在多少个不同 chunk 中才保留（默认 1 = 不启用）。
        drop_version_tokens: 是否丢弃版本号/占位记号（x2、v3、9NN、B:6）。
    """

    min_chars: int = 2
    max_chars: int = 80
    min_chunk_mentions: int = 1
    drop_version_tokens: bool = True


@dataclass
class CleanReport:
    """清洗结果统计，用于论文正文与附表的数字。"""

    total_before: int = 0
    total_after: int = 0
    dropped_by_rule: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def dropped_total(self) -> int:
        return self.total_before - self.total_after

    def summary(self) -> str:
        rules = ", ".join(f"{k}={v}" for k, v in self.dropped_by_rule.items())
        return (
            f"实体清洗: {self.total_before} → {self.total_after} "
            f"(丢弃 {self.dropped_total}; {rules})"
        )


def _mentions(entity: Entity) -> int:
    """该实体出现在多少个不同 chunk 中。"""
    return len(set(entity.source_chunks or []))


def _is_path_like(name: str) -> bool:
    """是不是路径/文件名，而不是正常实体名。"""
    if "\\" in name:
        return True
    if name.lower().startswith("docs/"):
        return True
    if name.endswith("/"):
        return True
    return bool(_FILE_EXT.search(name))


def _classify(name: str, policy: CleanPolicy) -> str | None:
    """返回命中的规则名；无需删除时返回 None。"""
    if len(name) < policy.min_chars:
        return "太短"
    if len(name) > policy.max_chars:
        return "过长"
    if _PURE_NUMBER.match(name) or _QUANTITY.match(name) or _QUANTITY_SYMBOL.match(name):
        return "纯数字或量值"
    if _is_path_like(name):
        return "路径或文件名"
    if policy.drop_version_tokens and (_VERSION_TOKEN.match(name) or _PLACEHOLDER_TOKEN.match(name)):
        return "版本或占位记号"
    if _KEYED_TOKEN.match(name):
        return "版本或占位记号"
    return None


def clean_entities(
    entities: list[Entity],
    policy: CleanPolicy | None = None,
) -> tuple[list[Entity], CleanReport]:
    """按策略过滤实体，并返回清洗报告。

    只做过滤，不做合并——实体归并仍由 graph_builder.merge_entities 负责。
    """
    policy = policy or CleanPolicy()
    report = CleanReport(total_before=len(entities))
    kept: list[Entity] = []

    for entity in entities:
        name = (entity.name or "").strip()

        rule = _classify(name, policy)
        if rule is None and _mentions(entity) < policy.min_chunk_mentions:
            rule = "提及次数不足"

        if rule is None:
            kept.append(entity)
            continue

        report.dropped_by_rule[rule] = report.dropped_by_rule.get(rule, 0) + 1
        bucket = report.examples.setdefault(rule, [])
        if len(bucket) < _MAX_EXAMPLES:
            bucket.append(name)

    report.total_after = len(kept)
    return kept, report
