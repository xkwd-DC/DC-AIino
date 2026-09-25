"""题库草拟单测 — 只钉住"gold 怎么推出来"。

措辞可以人工改，但 gold 必须是从语料机械推出的、可复核的，不能凭印象写。
"""
from eval.build_suite import draft_fact_items, draft_multi_hop_items, draft_relation_items
from graph.models import Community, Entity, GraphIndex, Relationship


def _index() -> GraphIndex:
    return GraphIndex(
        entities=[
            Entity("SPEI", "指标", "标准化降水蒸散指数", [r"docs\a.md:1:0", r"docs\a.md:2:0"]),
            Entity("春旱", "气候因子", "春季连续无雨", [r"docs\b.md:1:0"]),
            Entity("冬小麦", "作物", "北方主要口粮作物", [r"docs\c.md:1:0", r"docs\d.md:1:0"]),
            Entity("嘈杂节点", "其他", "", []),
        ],
        relationships=[
            Relationship("春旱", "冬小麦", "影响", "春旱压低冬小麦单产", r"docs\c.md:1:0"),
            Relationship("SPEI", "冬小麦", "测量", "用 SPEI 量化干旱强度", r"docs\a.md:1:0"),
            Relationship("春旱", "不存在的实体", "相关", "dangling", r"docs\x.md:1:0"),
        ],
        communities=[
            Community(
                community_id=0,
                entity_names=["SPEI", "春旱", "冬小麦"],
                summary="干旱指标体系与冬小麦产量响应",
                key_entities=["SPEI", "春旱", "冬小麦"],
            )
        ],
    )


class TestFactItems:
    def test_gold_is_the_single_document_that_supports_the_entity(self):
        items = draft_fact_items(_index(), per_type=10)

        by_question = {i.question: i for i in items}
        item = next(i for i in items if "春旱" in i.question)
        assert item.gold_docs == {"docs/b.md"}
        assert item.query_type == "fact"
        assert item.verified is False
        assert by_question  # 非空

    def test_skips_entities_without_source_documents(self):
        items = draft_fact_items(_index(), per_type=10)

        assert all("嘈杂节点" not in i.question for i in items)

    def test_respects_the_requested_count(self):
        assert len(draft_fact_items(_index(), per_type=1)) == 1


class TestRelationItems:
    def test_gold_covers_both_endpoints(self):
        items = draft_relation_items(_index(), per_type=10)

        item = next(i for i in items if "春旱" in i.question and "冬小麦" in i.question)
        assert item.gold_docs == {"docs/b.md", "docs/c.md", "docs/d.md"}
        assert item.query_type == "relation"

    def test_skips_relationships_with_dangling_endpoints(self):
        items = draft_relation_items(_index(), per_type=10)

        assert all("不存在的实体" not in i.question for i in items)

    def test_skips_relations_whose_gold_set_is_too_large(self):
        """gold 过大（如"R²"这种无处不在的实体）会让召回虚高，必须剔除。"""
        index = _index()
        index.entities.append(
            Entity("弥漫实体", "其他", "d", [f"docs/z{i}.md:1:0" for i in range(10)])
        )
        index.relationships.append(
            Relationship("弥漫实体", "冬小麦", "影响", "d", r"docs\z0.md:1:0")
        )

        items = draft_relation_items(index, per_type=10)

        assert all("弥漫实体" not in i.question for i in items)
        assert any("春旱" in i.question for i in items)


class TestMultiHopItems:
    def test_gold_covers_the_community_key_entities(self):
        items = draft_multi_hop_items(_index(), per_type=10)

        assert len(items) == 1
        assert items[0].gold_docs == {"docs/a.md", "docs/b.md", "docs/c.md", "docs/d.md"}
        assert items[0].query_type == "multi_hop"

    def test_skips_communities_without_key_entities(self):
        index = _index()
        index.communities.append(Community(community_id=1, entity_names=[], summary="s"))

        assert len(draft_multi_hop_items(index, per_type=10)) == 1

    def test_skips_communities_whose_gold_set_is_too_large(self):
        index = _index()
        index.entities.append(
            Entity("弥漫实体", "其他", "d", [f"docs/z{i}.md:1:0" for i in range(10)])
        )
        index.communities.append(
            Community(
                community_id=2,
                entity_names=["弥漫实体"],
                summary="s",
                key_entities=["弥漫实体"],
            )
        )

        items = draft_multi_hop_items(index, per_type=10)

        assert len(items) == 1
