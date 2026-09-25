"""评测指标单测 — Recall@k / MRR / nDCG@k。

这些是纯函数，是整篇论文实验表格的算数基础，所以先把定义钉死。
"""
import math

import pytest

from eval.metrics import (
    aggregate,
    evaluate_item,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestRecallAtK:
    def test_all_gold_within_top_k(self):
        assert recall_at_k({"a", "b"}, ["a", "b", "c"], k=5) == 1.0

    def test_half_of_gold_within_top_k(self):
        assert recall_at_k({"a", "b"}, ["a", "x", "y"], k=5) == 0.5

    def test_gold_beyond_k_is_not_counted(self):
        assert recall_at_k({"a"}, ["x", "y", "z", "w", "v", "a"], k=5) == 0.0

    def test_duplicate_hits_count_once(self):
        assert recall_at_k({"a", "b"}, ["a", "a", "a", "b"], k=5) == 1.0

    def test_no_hits_returns_zero(self):
        assert recall_at_k({"a"}, ["x", "y"], k=5) == 0.0

    def test_empty_gold_returns_zero(self):
        assert recall_at_k(set(), ["a", "b"], k=5) == 0.0


class TestReciprocalRank:
    def test_first_position_hit(self):
        assert reciprocal_rank({"a"}, ["a", "b"]) == 1.0

    def test_third_position_hit(self):
        assert reciprocal_rank({"a"}, ["x", "y", "a"]) == pytest.approx(1 / 3)

    def test_no_hit_returns_zero(self):
        assert reciprocal_rank({"a"}, ["x", "y"]) == 0.0

    def test_uses_highest_ranked_gold(self):
        assert reciprocal_rank({"a", "b"}, ["x", "b", "a"]) == pytest.approx(0.5)


class TestNdcgAtK:
    def test_single_gold_at_first_position(self):
        assert ndcg_at_k({"a"}, ["a"], k=1) == pytest.approx(1.0)

    def test_single_gold_at_second_position(self):
        expected = 1 / math.log2(3)
        assert ndcg_at_k({"a"}, ["x", "a"], k=2) == pytest.approx(expected)

    def test_gold_beyond_k_yields_zero(self):
        assert ndcg_at_k({"a"}, ["x", "y", "a"], k=2) == 0.0

    def test_perfect_ranking_of_two_gold(self):
        assert ndcg_at_k({"a", "b"}, ["a", "b", "x"], k=3) == pytest.approx(1.0)

    def test_empty_gold_returns_zero(self):
        assert ndcg_at_k(set(), ["a"], k=5) == 0.0


class TestEvaluateItem:
    def test_reports_every_metric_for_each_k(self):
        metrics = evaluate_item(gold={"a"}, ranked=["a", "b"], ks=(5, 10))

        assert metrics["recall@5"] == 1.0
        assert metrics["recall@10"] == 1.0
        assert metrics["ndcg@5"] == pytest.approx(1.0)
        assert metrics["ndcg@10"] == pytest.approx(1.0)
        assert metrics["mrr"] == pytest.approx(1.0)

    def test_miss_produces_all_zero_metrics(self):
        metrics = evaluate_item(gold={"a"}, ranked=["x", "y"], ks=(5,))

        assert metrics == {"recall@5": 0.0, "ndcg@5": 0.0, "mrr": 0.0}


class TestAggregate:
    def test_averages_each_metric_and_reports_n(self):
        per_item = [
            {"recall@5": 1.0, "mrr": 1.0},
            {"recall@5": 0.0, "mrr": 0.0},
        ]

        result = aggregate(per_item)

        assert result["recall@5"] == pytest.approx(0.5)
        assert result["mrr"] == pytest.approx(0.5)
        assert result["n_items"] == 2

    def test_empty_input_reports_zero_items(self):
        assert aggregate([])["n_items"] == 0
