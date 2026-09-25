"""华北数据闸门探测脚本单测 — 只管可复现的解析与判定逻辑。
"""
import pytest

from scripts.climate_probe.probe_yearbooks import (
    YearbookSource,
    classify_year,
    extract_table_ids,
    toc_candidates,
)


class TestExtractTableIds:
    def test_pulls_table_ids_from_relative_image_links(self):
        html = """
        <a href="html/note.jpg">说明</a>
        <a href="html/01-01.jpg">1-1</a>
        <a href="html/20-14.jpg">20-14</a>
        """

        assert extract_table_ids(html) == ["01-01", "20-14"]

    def test_pulls_ids_from_pdf_links_too(self):
        html = '<a href="html/sm01.pdf">说明</a><a href="html/12-03.pdf">表</a>'

        assert extract_table_ids(html) == ["12-03"]

    def test_supports_platform_variant_without_hyphen(self):
        """河南年鉴的表号是 0101.jpg（无连字符），山西是 01-01.jpg。"""
        html = '<a href="html/0101.jpg">1-1</a><a href="html/2014.jpg">20-14</a>'

        assert extract_table_ids(html) == ["0101", "2014"]

    def test_ignores_hyphenless_asset_names(self):
        html = '<a href="html/ge01.jpg">地理</a><a href="html/note.jpg">说明</a>'

        assert extract_table_ids(html) == []

    def test_ignores_non_table_assets(self):
        html = '<a href="indexce.htm">目录</a><a href="html/board.jpg">板</a>'

        assert extract_table_ids(html) == []

    def test_deduplicates_and_sorts(self):
        html = '<a href="html/20-14.jpg">a</a><a href="html/01-01.jpg">b</a><a href="html/20-14.jpg">c</a>'

        assert extract_table_ids(html) == ["01-01", "20-14"]

    def test_returns_empty_for_html_without_tables(self):
        assert extract_table_ids("<html><body>无</body></html>") == []


class TestClassifyYear:
    @pytest.mark.parametrize("probed", [12, 1])
    def test_any_xls_hit_means_machine_readable(self, probed):
        assert classify_year(xls_hits=probed, image_tables=50, toc_status="ok") == "可机读"

    def test_no_xls_but_images_means_scan_only(self):
        assert classify_year(xls_hits=0, image_tables=50, toc_status="ok") == "仅图片或PDF"

    def test_empty_toc_is_reported_separately(self):
        assert classify_year(xls_hits=0, image_tables=0, toc_status="ok") == "目录为空"

    def test_network_failure_is_not_confused_with_wrong_path(self):
        assert classify_year(xls_hits=0, image_tables=0, toc_status="network") == "站点不可达"

    def test_missing_toc_reports_path_template_mismatch(self):
        assert classify_year(xls_hits=0, image_tables=0, toc_status="missing") == "目录不存在"

    def test_forbidden_site(self):
        assert classify_year(xls_hits=0, image_tables=0, toc_status="forbidden") == "站点拒绝访问"


class TestTocCandidates:
    def test_expands_year_placeholder(self):
        source = YearbookSource(
            province="测试",
            toc_templates=("http://x/{year}/left.htm",),
            xls_templates=("http://x/{year}/html/{table}.xls",),
        )

        assert toc_candidates(source, 2023) == [("http://x/2023/left.htm", "http://x/2023/html/{table}.xls")]

    def test_returns_variants_in_declared_order(self):
        """河南的年鉴有的年份带 nj 后缀、有的不带，必须能按序回退。"""
        source = YearbookSource(
            province="测试",
            toc_templates=("http://x/{year}nj/left.htm", "http://x/{year}/left.htm"),
            xls_templates=("http://x/{year}nj/html/{table}.xls", "http://x/{year}/html/{table}.xls"),
        )

        pairs = toc_candidates(source, 2022)

        assert [p[0] for p in pairs] == ["http://x/2022nj/left.htm", "http://x/2022/left.htm"]
