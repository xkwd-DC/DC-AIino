"""评测 runner 单测 — 用假检索器注入，不加载任何模型。"""
import pytest

from eval.runner import parse_int_list, render_markdown_table, run_suite
from eval.schema import EvalItem, RetrievalHit


class FakeRetriever:
    """按预置答案返回文档，用于验证 runner 的聚合逻辑。"""

    def __init__(self, name, mapping):
        self.name = name
        self.mapping = mapping
        self.calls = []

    def retrieve(self, question, top_k=10, query_type=None):
        self.calls.append((question, top_k, query_type))
        return [
            RetrievalHit(chunk_id=f"{doc}:0:0", source=doc, score=1.0, text="t")
            for doc in self.mapping.get(question, [])
        ]


class BoomRetriever:
    name = "boom"

    def retrieve(self, question, top_k=10, query_type=None):
        raise RuntimeError("索引缺失")


def _items():
    return [
        EvalItem("q1", "问题一", "fact", ["doc:docs/a.md"]),
        EvalItem("q2", "问题二", "multi_hop", ["doc:docs/b.md"]),
    ]


class TestRunSuite:
    def test_hit_scores_one_and_miss_scores_zero(self):
        retriever = FakeRetriever("hit_only_q1", {"问题一": ["docs/a.md"], "问题二": ["docs/x.md"]})

        result = run_suite(_items(), [retriever], ks=(5,), top_k=5)

        overall = result["systems"]["hit_only_q1"]["overall"]
        assert overall["recall@5"] == pytest.approx(0.5)
        assert overall["n_items"] == 2

    def test_splits_metrics_by_query_type(self):
        retriever = FakeRetriever("split", {"问题一": ["docs/a.md"], "问题二": ["docs/x.md"]})

        result = run_suite(_items(), [retriever], ks=(5,), top_k=5)

        by_type = result["systems"]["split"]["by_type"]
        assert by_type["fact"]["recall@5"] == pytest.approx(1.0)
        assert by_type["multi_hop"]["recall@5"] == pytest.approx(0.0)

    def test_passes_query_type_to_retriever(self):
        retriever = FakeRetriever("router", {"问题二": ["docs/b.md"]})

        run_suite(_items(), [retriever], ks=(5,), top_k=5)

        assert ("问题二", 5, "multi_hop") in retriever.calls

    def test_records_ranked_docs_and_latency(self):
        retriever = FakeRetriever("detail", {"问题一": ["docs/a.md", "docs/z.md"]})

        item = run_suite(_items(), [retriever], ks=(5,), top_k=5)["systems"]["detail"]["items"][0]

        assert item["ranked_docs"] == ["docs/a.md", "docs/z.md"]
        assert item["latency_ms"] >= 0

    def test_dedups_documents_from_the_same_source(self):
        class DupRetriever:
            name = "dup"

            def retrieve(self, question, top_k=10, query_type=None):
                return [
                    RetrievalHit("b", "docs/a.md", 0.9, "t"),
                    RetrievalHit("a", "docs/a.md", 0.8, "t"),
                ]

        item = run_suite(_items()[:1], [DupRetriever()], ks=(5,), top_k=5)["systems"]["dup"]["items"][0]

        assert item["ranked_docs"] == ["docs/a.md"]

    def test_failing_retriever_is_reported_not_raised(self):
        result = run_suite(_items(), [BoomRetriever()], ks=(5,), top_k=5)

        system = result["systems"]["boom"]
        assert "索引缺失" in system["error"]
        assert "overall" not in system

    def test_other_systems_still_run_when_one_fails(self):
        good = FakeRetriever("good", {"问题一": ["docs/a.md"]})

        result = run_suite(_items(), [BoomRetriever(), good], ks=(5,), top_k=5)

        assert result["systems"]["good"]["overall"]["recall@5"] == pytest.approx(0.5)


class TestRenderMarkdownTable:
    def test_renders_one_row_per_system(self):
        retriever = FakeRetriever("vector", {"问题一": ["docs/a.md"]})
        result = run_suite(_items(), [retriever], ks=(5,), top_k=5)

        table = render_markdown_table(result)

        assert "| vector |" in table
        assert "recall@5" in table
        assert table.startswith("|")

    def test_separates_verified_items_from_generated_drafts(self):
        """草稿题是从图谱生成的，对 GraphRAG 有结构性偏袒，必须单列。"""
        items = [
            EvalItem("q1", "核对题", "fact", ["doc:docs/a.md"], verified=True),
            EvalItem("q2", "草稿题", "fact", ["doc:docs/b.md"], verified=False),
        ]
        retriever = FakeRetriever("vector", {"核对题": ["docs/a.md"], "草稿题": ["docs/x.md"]})
        result = run_suite(items, [retriever], ks=(5,), top_k=5)

        table = render_markdown_table(result)

        assert "仅人工核对" in table
        main_block, verified_block = table.split("仅人工核对", 1)
        # 全部题上只命中一半，人工核对子集上是满分
        assert "| vector | 0.500 |" in main_block
        assert "| 1.000 |" in verified_block

    def test_omits_verified_block_when_nothing_is_verified(self):
        retriever = FakeRetriever("vector", {"问题一": ["docs/a.md"]})
        result = run_suite(_items(), [retriever], ks=(5,), top_k=5)

        assert "仅人工核对" not in render_markdown_table(result)


class TestParseIntList:
    def test_parses_comma_separated_values(self):
        assert parse_int_list("5,10") == [5, 10]

    def test_ignores_whitespace(self):
        assert parse_int_list(" 5 , 10 , 20 ") == [5, 10, 20]

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            parse_int_list("5,abc")
