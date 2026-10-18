"""M03「玉米长势」情景 API。

GET  /api/growth/counties   玉米主产区县级基线（前端下拉 + 初始值）
POST /api/growth/simulate   给定县 + 情景参数，返回相对长势指数 GSI

口径
====
- 作物固定为玉米，按种植制度分东北春玉米 / 黄淮海夏玉米 / 西南春玉米。
- 输出是「相对长势指数」：该县常年基线 = 100，不是产量预测。
- 模型为积温–水分–热害限制因子响应面，不是 DSSAT 机理模型。
- 数据来自 `maize_growth_baseline.json`（由 scripts/data/v11_01 生成）；
  文件缺失时端点返 503，不影响其他模块。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from api import envelope
from limiter import limiter

growth_bp = Blueprint("growth", __name__, url_prefix="/api/growth")

_DATA = Path(__file__).resolve().parent.parent / "data" / "maize_growth_baseline.json"

_ZONES: dict[str, dict[str, Any]] = {}
_ROWS: list[dict[str, Any]] = []
_BY_CODE: dict[int, dict[str, Any]] = {}
_BASELINE_SORTED: list[float] = []
_META: dict[str, Any] = {}

try:
    with _DATA.open(encoding="utf-8") as f:
        _PAYLOAD = json.load(f)
    _META = _PAYLOAD.get("meta", {})
    _ZONES = {z["key"]: z for z in _PAYLOAD["zones"]}
    _ROWS = _PAYLOAD["rows"]
    _BY_CODE = {r["code"]: r for r in _ROWS}
    _BASELINE_SORTED = sorted(r["baseline_gsi"] for r in _ROWS)
except (OSError, KeyError, ValueError):  # 数据未生成：不影响其余模块启动
    _AVAILABLE = False
else:
    _AVAILABLE = True

_UNAVAILABLE = {
    "code": 503,
    "message": "maize growth baseline not loaded (run scripts/data/v11_01_build_maize_growth_baseline.py)",
}

# 前端滑块会高频触发，限额放宽；仍保留 DoS 兜底。
_SIM_LIMIT = "6000 per hour"
_READ_LIMIT = "600 per hour"

LIMIT_LABELS = {
    "gdd": "积温不足",
    "water": "水分亏缺",
    "heat": "抽雄期热害",
    "none": "无明显限制",
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _factors(
    row: dict[str, Any],
    zone: dict[str, Any],
    d_temp: float,
    d_prec_pct: float,
    d_heat_days: float,
    irrigation: float,
) -> dict[str, Any]:
    """积温–水分–热害三因子。d_temp 单位 ℃，d_prec_pct 单位 %。"""
    gdd = row["gdd"] + d_temp * zone["season_days"]
    f_gdd = _clamp(gdd / zone["req_gdd"], 0.0, 1.0)

    # gs_pet 是 4–9 月参考蒸散；按玉米实际占用季长折算后再乘 Kc。
    # 升温抬高潜在蒸散（约 4%/℃），降水按百分比缩放。
    pet = row["pet"] * zone.get("pet_fraction", 1.0) * (1.0 + 0.04 * d_temp)
    ppt = max(0.0, row["ppt"] * (1.0 + d_prec_pct / 100.0))
    etc = zone["kc"] * pet
    irr = _clamp(irrigation, 0.0, 1.0)
    supply = irr * etc + (1.0 - irr) * 0.75 * ppt
    f_water = 1.0 - 0.6 * max(0.0, (etc - supply) / etc) if etc > 0 else 0.25
    f_water = _clamp(f_water, 0.25, 1.0)

    # 全季 ≥35℃ 日数按 1/4 折算到抽雄吐丝期；基线热害在相对 GSI 里约掉，
    # 所以这里保留绝对热害负担，滑块才有连续响应。
    heat_days = max(0.0, row["heat_mean"] + d_heat_days)
    critical_heat = 0.25 * heat_days
    f_heat = _clamp(1.0 - 0.015 * critical_heat, 0.60, 1.0)

    deficits = {"gdd": 1.0 - f_gdd, "water": 1.0 - f_water, "heat": 1.0 - f_heat}
    limiting = max(deficits, key=deficits.get)
    if deficits[limiting] < 0.02:
        limiting = "none"

    gsi_abs = 100.0 * min(f_gdd, f_water) * f_heat
    return {
        "gsi_abs": round(gsi_abs, 1),
        "gdd": round(gdd, 1),
        "ppt": round(ppt, 1),
        "pet": round(pet, 1),
        "etc": round(etc, 1),
        "heat_days": round(heat_days, 1),
        "critical_heat": round(critical_heat, 2),
        "f_gdd": round(f_gdd, 3),
        "f_water": round(f_water, 3),
        "f_heat": round(f_heat, 3),
        "limiting": limiting,
        "limiting_label": LIMIT_LABELS[limiting],
    }


@growth_bp.get("/counties")
@limiter.limit(_READ_LIMIT)
def list_maize_counties():
    if not _AVAILABLE:
        return envelope(error=_UNAVAILABLE, status=503)
    return envelope(
        data={
            "meta": _META,
            "zones": list(_ZONES.values()),
            "count": len(_ROWS),
            "rows": _ROWS,
        }
    )


@growth_bp.post("/simulate")
@limiter.limit(_SIM_LIMIT)
def simulate_maize():
    if not _AVAILABLE:
        return envelope(error=_UNAVAILABLE, status=503)

    body = request.get_json(silent=True) or {}
    try:
        code = int(body["county_code"])
    except (KeyError, TypeError, ValueError):
        return envelope(
            error={"code": 400, "message": "county_code is required and must be an integer"},
            status=400,
        )

    row = _BY_CODE.get(code)
    if row is None:
        return envelope(
            error={"code": 404, "message": f"county {code} is not in the maize panel"},
            status=404,
        )
    zone = _ZONES[row["zone"]]

    try:
        d_temp = float(body.get("d_temp", 0.0))
        d_prec_pct = float(body.get("d_prec_pct", 0.0))
        d_heat_days = float(body.get("d_heat_days", 0.0))
        irrigation = float(body.get("irrigation", row["irr"]))
    except (TypeError, ValueError):
        return envelope(
            error={"code": 400, "message": "scenario parameters must be numeric"},
            status=400,
        )

    if not (-2.0 <= d_temp <= 4.0):
        return envelope(error={"code": 400, "message": "d_temp must be within [-2, 4]"}, status=400)
    if not (-40.0 <= d_prec_pct <= 40.0):
        return envelope(error={"code": 400, "message": "d_prec_pct must be within [-40, 40]"}, status=400)
    if not (0.0 <= d_heat_days <= 30.0):
        return envelope(error={"code": 400, "message": "d_heat_days must be within [0, 30]"}, status=400)
    if not (0.0 <= irrigation <= 1.0):
        return envelope(error={"code": 400, "message": "irrigation must be within [0, 1]"}, status=400)

    # 前端滑块按整数百分比回传；与县基线相差不到 0.6 个百分点时视为基线，
    # 避免默认状态下出现 +0.2% 这类数值噪声。
    if abs(irrigation - row["irr"]) <= 0.006:
        irrigation = row["irr"]

    base = _factors(row, zone, 0.0, 0.0, 0.0, row["irr"])
    scen = _factors(row, zone, d_temp, d_prec_pct, d_heat_days, irrigation)
    gsi_rel = 100.0 * scen["gsi_abs"] / base["gsi_abs"] if base["gsi_abs"] > 0 else 100.0
    gsi_rel = round(_clamp(gsi_rel, 40.0, 130.0), 1)
    delta_pct = round(gsi_rel - 100.0, 1)

    # 情景绝对 GSI 在主产区基线分布中的分位
    below = sum(1 for v in _BASELINE_SORTED if v <= scen["gsi_abs"])
    percentile = round(100.0 * below / len(_BASELINE_SORTED), 0) if _BASELINE_SORTED else 50.0

    trend = "上升" if delta_pct > 0 else ("下降" if delta_pct < 0 else "持平")
    interpretation = (
        f"{row['name']}（{zone['name']}）情景长势 {gsi_rel:.1f}，较常年{trend} "
        f"{abs(delta_pct):.1f}%；主要限制因子：{scen['limiting_label']}。"
    )

    return envelope(
        data={
            "county": {
                "code": row["code"],
                "name": row["name"],
                "province": row["province"],
                "city": row["city"],
                "lon": row["lon"],
                "lat": row["lat"],
                "zone": row["zone"],
                "zone_name": zone["name"],
                "sowing": zone["sowing"],
                "req_gdd": zone["req_gdd"],
            },
            "params": {
                "d_temp": d_temp,
                "d_prec_pct": d_prec_pct,
                "d_heat_days": d_heat_days,
                "irrigation": round(irrigation, 4),
            },
            "baseline": base,
            "scenario": scen,
            "gsi": gsi_rel,
            "delta_pct": delta_pct,
            "percentile": percentile,
            "limiting": scen["limiting"],
            "limiting_label": scen["limiting_label"],
            "interpretation": interpretation,
            "metric_note": "相对长势指数（常年=100），非产量预测；限制因子响应面模型",
        }
    )
