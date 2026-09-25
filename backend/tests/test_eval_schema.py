"""评测数据模型单测 — 文档级判定口径 + 题库读写。

判定口径是全篇实验的地基：图谱索引用 2000 字分块、向量库用 800 字分块，
块 ID 根本对不上，所以召回一律在**文档级**比较（gold 与命中都归一到文档路径）。
"""
import json

import pytest

from eval.schema import EvalItem, RetrievalHit, load_suite, normalize_doc, rank_docs


class TestNormalizeDoc:
    def test_strips_pdf_page_suffix(self):
        assert normalize_doc(r"docs\paper\x.pdf#p11:1:11") == "docs/paper/x.pdf"

    def test_strips_page_suffix_from_vector_store_id(self):
        assert normalize_doc(r"docs\craic\a.pdf#p1") == "docs/craic/a.pdf"

    def test_converts_backslashes(self):
        assert normalize_doc(r"docs\national\19_结题验收要求.md") == "docs/national/19_结题验收要求.md"

    def test_leaves_clean_path_untouched(self):
        assert normalize_doc("docs/09_文献综述_潘妙齐.md") == "docs/09_文献综述_潘妙齐.md"

    def test_strips_markdown_chunk_suffix(self):
        assert normalize_doc(r"docs\00_项目执行计划.md:0:0") == "docs/00_项目执行计划.md"

    def test_strips_pdf_chunk_suffix_after_page(self):
        assert normalize_doc(r"docs\craic\x.pdf#p1:3:1") == "docs/craic/x.pdf"

    def test_empty_input(self):
        assert normalize_doc("") == ""


class TestEvalItem:
    def test_gold_docs_normalizes_every_entry(self):
        item = EvalItem(
            id="q001",
            question="XGBoost-SHAP 是什么？",
            query_type="fact",
            gold=[r"doc:docs\papers\x.txt", "docs/09_文献综述_潘妙齐.md"],
        )

        assert item.gold_docs == {"docs/papers/x.txt", "docs/09_文献综述_潘妙齐.md"}

    def test_defaults_to_unverified(self):
        item = EvalItem(id="q002", question="q", query_type="fact", gold=["doc:a.md"])

        assert item.verified is False

    def test_round_trips_through_dict(self):
        item = EvalItem(
            id="q003",
            question="q",
            query_type="multi_hop",
            gold=["doc:a.md"],
            verified=True,
            note="已核对",
        )

        assert EvalItem.from_dict(item.to_dict()) == item


class TestRetrievalHit:
    def test_doc_is_normalized(self):
        hit = RetrievalHit(chunk_id="x:1:0", source=r"docs\paper\y.pdf#p2", score=0.5, text="t")

        assert hit.doc == "docs/paper/y.pdf"


class TestRankDocs:
    def test_dedups_keeping_first_occurrence(self):
        hits = [
            RetrievalHit("a1", "docs/a.md", 0.9, "t"),
            RetrievalHit("a2", "docs/a.md", 0.8, "t"),
            RetrievalHit("b1", r"docs\b.md#p3", 0.7, "t"),
        ]

        assert rank_docs(hits) == ["docs/a.md", "docs/b.md"]


class TestLoadSuite:
    def test_loads_items_from_json(self, tmp_path):
        path = tmp_path / "suite.json"
        path.write_text(
            json.dumps(
                {
                    "name": "demo",
                    "items": [
                        {
                            "id": "q001",
                            "question": "问题",
                            "query_type": "fact",
                            "gold": ["doc:a.md"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        items = load_suite(path)

        assert len(items) == 1
        assert items[0].id == "q001"

    def test_rejects_item_without_gold(self, tmp_path):
        path = tmp_path / "suite.json"
        path.write_text(
            json.dumps(
                {"items": [{"id": "q1", "question": "q", "query_type": "fact", "gold": []}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="gold"):
            load_suite(path)

    def test_rejects_unknown_query_type(self, tmp_path):
        path = tmp_path / "suite.json"
        path.write_text(
            json.dumps(
                {"items": [{"id": "q1", "question": "q", "query_type": "vibes", "gold": ["doc:a.md"]}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="query_type"):
            load_suite(path)
