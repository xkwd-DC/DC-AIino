"""实体清洗单测。

测试用的噪声样本全部取自真实的 graph_index.json（2026-07-09 构建），
不是凭空想象的边界情况。
"""
import pytest

from graph.cleaner import CleanPolicy, clean_entities
from graph.models import Entity


def _ent(name: str, chunks: list[str] | None = None) -> Entity:
    return Entity(
        name=name,
        entity_type="其他",
        description="d",
        source_chunks=chunks if chunks is not None else ["c1"],
    )


def _names(entities: list[Entity]) -> set[str]:
    return {e.name for e in entities}


class TestSingleCharacterAndSymbols:
    @pytest.mark.parametrize("name", ["L", "R", "V", "ρ", "σ", "潘", "雪"])
    def test_drops_single_character_names(self, name):
        kept, _ = clean_entities([_ent(name)])

        assert kept == []


class TestNumericNames:
    @pytest.mark.parametrize("name", ["2022", "4615 kg/ha", "500 kg/ha", "8℃"])
    def test_drops_numbers_and_quantities(self, name):
        kept, _ = clean_entities([_ent(name)])

        assert kept == []


class TestPathLikeNames:
    @pytest.mark.parametrize(
        "name",
        [
            r"docs\09_文献综述_潘妙齐.md",
            "docs/03_大创项目_申报书.md",
            "docs/_craic/figures/",
            "STATUS.md",
            "feature_columns.json",
            "spei_province_annual.csv",
            "王天硕总表.xlsx",
        ],
    )
    def test_drops_paths_and_filenames(self, name):
        kept, _ = clean_entities([_ent(name)])

        assert kept == []


class TestShortCodeTokens:
    @pytest.mark.parametrize("name", ["x2", "v3", "9NN", "B:6"])
    def test_drops_terse_code_tokens(self, name):
        kept, _ = clean_entities([_ent(name)])

        assert kept == []


class TestKeepsRealEntities:
    @pytest.mark.parametrize(
        "name",
        [
            "SPEI",
            "AUC",
            "CNN",
            "CDD",
            "CPU",
            "XGBoost",
            "SHAP",
            "XGBoost-SHAP",
            "春旱连续无雨",
            "MODIS NDVI/LST",
            "Sentinel-1/2/3",
            "NOAA/AVHRR数据",
            "旱/水灾面积",
            "RF",
            "F1",
            "ERA5",
            "WGS84",
            "Vue3",
            "2SLS",
            "随机8:2划分",
        ],
    )
    def test_keeps_technical_and_chinese_entities(self, name):
        kept, _ = clean_entities([_ent(name)])

        assert _names(kept) == {name}


class TestChunkMentionPolicy:
    def test_default_keeps_single_mention_entities(self):
        kept, _ = clean_entities([_ent("只出现一次", ["c1"])])

        assert _names(kept) == {"只出现一次"}

    def test_min_chunk_mentions_drops_single_mention_entities(self):
        policy = CleanPolicy(min_chunk_mentions=2)
        entities = [_ent("只出现一次", ["c1"]), _ent("出现两次", ["c1", "c2"])]

        kept, report = clean_entities(entities, policy)

        assert _names(kept) == {"出现两次"}
        assert report.dropped_by_rule["提及次数不足"] == 1

    def test_repeated_chunk_id_counts_as_one_mention(self):
        policy = CleanPolicy(min_chunk_mentions=2)

        kept, _ = clean_entities([_ent("重复同一块", ["c1", "c1"])], policy)

        assert kept == []


class TestReport:
    def test_counts_before_and_after(self):
        entities = [_ent("L"), _ent("SPEI"), _ent("x2")]

        kept, report = clean_entities(entities)

        assert report.total_before == 3
        assert report.total_after == 1
        assert report.dropped_total == 2

    def test_reports_dropped_names_per_rule(self):
        _, report = clean_entities([_ent("L"), _ent("2022")])

        assert report.examples["太短"] == ["L"]
        assert report.examples["纯数字或量值"] == ["2022"]
