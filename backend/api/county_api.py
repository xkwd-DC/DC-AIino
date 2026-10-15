"""县级面板 API — 站点 M07「县级风险地图」的数据端点。

GET /api/counties?year=&unit=&province=   某年县级快照（地图着色 + 点位）
GET /api/counties/meta/summary            覆盖率与元信息（M00 数据卡 / M07 页头）
GET /api/counties/meta/standard           县级口径与协议数字（迁移体检面板）
GET /api/counties/<code>/history          单县 2012-2023 归因轨迹
GET /api/counties/<code>/attribution      单县单年 16 维气候边际贡献（SHAP）

口径提醒（见 backend/models/county_climg_card.md）
=================================================
县级层的模型只吃**气候**特征（CLIMG 16 维，已剔除播种面积/规模与省-年共享常量），
目标仍是 log(粮食总产量)。因此它输出的是「气候条件对该县产量的模型边际贡献」，
**不是**「该县产量水平」，也不是跨县空间外推的精度承诺。
"""

from __future__ import annotations

from flask import Blueprint, request

from api import envelope
from limiter import limiter
from services import county_repo

county_bp = Blueprint("county", __name__, url_prefix="/api/counties")

# 与省级 /api/provinces 同档（静态面板数据，IP 级带宽防护）
_READ_LIMIT = "500 per hour"

_UNAVAILABLE = {
    "code": 503,
    "message": "county panel not loaded (run scripts/data/v9_01_build_county_site_db.py)",
}


@county_bp.get("")
@limiter.limit(_READ_LIMIT)
def list_counties():
    """某年县级快照。缺 year 时用面板最新年。"""
    if not county_repo.is_available():
        return envelope(error=_UNAVAILABLE, status=503)

    try:
        years = county_repo.get_years()
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)

    year_str = request.args.get("year")
    if year_str is None:
        year = years[-1]
    else:
        try:
            year = int(year_str)
        except ValueError:
            return envelope(
                error={"code": 400, "message": f"year must be an integer, got {year_str!r}"},
                status=400,
            )

    unit = request.args.get("unit", "all")
    province = request.args.get("province") or None

    try:
        rows = county_repo.get_counties(year, unit=unit, province=province)
    except county_repo.YearOutOfRange as exc:
        return envelope(error={"code": 400, "message": str(exc)}, status=400)
    except ValueError as exc:
        return envelope(error={"code": 400, "message": str(exc)}, status=400)
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)

    return envelope(data={"year": year, "unit": unit, "count": len(rows), "rows": rows})


@county_bp.get("/meta/summary")
@limiter.limit(_READ_LIMIT)
def county_summary():
    if not county_repo.is_available():
        return envelope(error=_UNAVAILABLE, status=503)
    try:
        return envelope(data=county_repo.get_summary())
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)


@county_bp.get("/meta/standard")
@limiter.limit(_READ_LIMIT)
def county_standard():
    """空间粒度递进与协议数字。前端不写死任何数字，全部读这里。"""
    if not county_repo.is_available():
        return envelope(error=_UNAVAILABLE, status=503)
    try:
        return envelope(data=county_repo.get_standard())
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)


@county_bp.get("/<int:code>/history")
@limiter.limit(_READ_LIMIT)
def county_history(code: int):
    if not county_repo.is_available():
        return envelope(error=_UNAVAILABLE, status=503)
    try:
        return envelope(data=county_repo.get_county_history(code))
    except county_repo.CountyNotFound as exc:
        return envelope(error={"code": 404, "message": str(exc)}, status=404)
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)


@county_bp.get("/<int:code>/attribution")
@limiter.limit(_READ_LIMIT)
def county_attribution(code: int):
    year_str = request.args.get("year")
    if year_str is None:
        return envelope(
            error={"code": 400, "message": "year is required, e.g. ?year=2019"},
            status=400,
        )
    try:
        year = int(year_str)
    except ValueError:
        return envelope(
            error={"code": 400, "message": f"year must be an integer, got {year_str!r}"},
            status=400,
        )

    if not county_repo.is_available():
        return envelope(error=_UNAVAILABLE, status=503)
    try:
        return envelope(data=county_repo.get_attribution(code, year))
    except county_repo.CountyNotFound as exc:
        return envelope(error={"code": 404, "message": str(exc)}, status=404)
    except county_repo.RepoUnavailable as exc:
        return envelope(error={"code": 503, "message": str(exc)}, status=503)
