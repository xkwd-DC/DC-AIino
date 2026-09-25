"""检索器纯函数单测 — RRF 融合 + 图谱展开。

这两块决定了 GraphRAG 档位到底怎么把一个"实体命中"变成"文档命中"，
是四档对照里唯一需要自己定义的部分，所以单独钉住。
"""
from eval.retrievers import graph_expand_docs, rrf_merge
from eval.schema import RetrievalHit
from graph.models import Entity, GraphIndex


def _hit(chunk_id: str, source: str, score: float = 1.0, text: str = "t") -> RetrievalHit:
    return RetrievalHit(chunk_id=chunk_id, source=source, score=score, text=text)


class TestRrfMerge:
    def test_doc_in_both_lists_ranks_first(self):
        first = [_hit("1", "docs/a.md"), _hit("2", "docs/b.md")]
        second = [_hit("3", "docs/b.md"), _hit("4", "docs/c.md")]

        merged = rrf_merge([first, second])

        assert [h.doc for h in merged] == ["docs/b.md", "docs/a.md", "docs/c.md"]

    def test_output_is_deduped_by_document(self):
        first = [_hit("1", "docs/a.md"), _hit("2", "docs/a.md")]

        merged = rrf_merge([first])

        assert [h.doc for h in merged] == ["docs/a.md"]

    def test_keeps_first_non_empty_text_for_a_document(self):
        first = [_hit("1", "docs/a.md", text="第一段")]
        second = [_hit("9", "docs/a.md", text="第二段")]

        merged = rrf_merge([first, second])

        assert merged[0].text == "第一段"

    def test_empty_input_returns_empty(self):
        assert rrf_merge([]) == []
        assert rrf_merge([[], []]) == []


class TestGraphExpandDocs:
    def _index(self) -> GraphIndex:
        return GraphIndex(
            entities=[
                Entity(
                    name="XGBoost-SHAP",
                    entity_type="研究方法",
                    description="d",
                    source_chunks=[r"docs\a.md:1:0", r"docs\a.md:2:0", r"docs\b.md:1:0"],
                ),
                Entity(
                    name="SPEI",
                    entity_type="指标",
                    description="d",
                    source_chunks=[r"docs\c.md:1:0"],
                ),
            ],
        )

    def test_expands_entities_to_documents_in_order(self):
        hits = graph_expand_docs(self._index(), ["XGBoost-SHAP", "SPEI"])

        assert [h.doc for h in hits] == ["docs/a.md", "docs/b.md", "docs/c.md"]

    def test_most_cited_document_comes_first_for_an_entity(self):
        hits = graph_expand_docs(self._index(), ["XGBoost-SHAP"])

        assert hits[0].doc == "docs/a.md"

    def test_unknown_entity_is_skipped(self):
        hits = graph_expand_docs(self._index(), ["不存在的实体"])

        assert hits == []

    def test_matching_is_case_insensitive(self):
        hits = graph_expand_docs(self._index(), ["xgboost-shap"])

        assert hits[0].doc == "docs/a.md"

    def test_empty_entity_list_returns_empty(self):
        assert graph_expand_docs(self._index(), []) == []
