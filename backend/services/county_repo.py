"""backend/services/county_repo.py — 县级面板（county.db）只读查询层。

定位
====
与 `panel_repo.py`（省级 grain.db，31 省 × 13 年 = 403 行）**并列的第二套读路径**，
服务站点新增的县级模块（M07 县级风险地图）。两套口径独立，数字不可混用：

| 层 | 面板 | 模型 | 对外可报的泛化能力 |
|---|---|---|---|
| 省级（M01-M04） | v3 403 行 × 11 维 | XGB / LSTM / Att-LSTM | random 8:2 R²=0.907；leave-province-out 中位 −16.83 |
| 县级（M07） | v7 14388 行 × 16 维气候 | CLIMG XGB + SHAP | LCO R²=+0.4489；时间外推 +0.3644（5 种子） |

县级层的特征是**剔除规模与省-年常量后的纯气候 16 维**，所以它的 R² 是"气候解释力"，
不是"产量预测力"。详见 `backend/models/county_climg_card.md`。

设计要点（沿用 panel_repo 的约定）
=================================
1. 不在 import 时打开 db；每次方法调用临时连接 + 关闭；
2. read-only URI 连接（`?mode=ro`），SQLite 层面拒绝写；
3. 参数化查询 + `sqlite3.Row`；
4. 显式异常，让 api 层返 400 / 404 / 503。

依赖
====
- backend/data/county.db（由 `scripts/data/v9_01_build_county_site_db.py`
  + `scripts/data/v9_02_train_county_climg.py` 生成，可重建）
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "county.db"

# 气候特征名 → (中文名, 单位, 是否为"生长季/极端指数"族)
# 前端归因面板直接用这份字典渲染，避免在 TypeScript 里再抄一遍口径。
FEATURE_DICT: dict[str, tuple[str, str, str]] = {
    "temp": ("年均气温", "℃", "annual"),
    "prec": ("年降水量", "mm", "annual"),
    "sun": ("年均太阳辐射", "W/m²", "annual"),
    "spei_annual_mean": ("年均 SPEI", "—", "annual"),
    "spei_growing_season_mean": ("生长季 SPEI", "—", "seasonal"),
    "gs_tmax_mean": ("生长季最高气温均值", "℃", "seasonal"),
    "gs_tmin_mean": ("生长季最低气温均值", "℃", "seasonal"),
    "gs_ppt": ("生长季降水量", "mm", "seasonal"),
    "gs_srad": ("生长季太阳辐射", "W/m²", "seasonal"),
    "gs_pet": ("生长季潜在蒸散", "mm", "seasonal"),
    "gdd10": ("生长季 ≥10℃ 积温", "℃·d", "seasonal"),
    "gs_aridity": ("生长季干燥度", "—", "seasonal"),
    "prec_cv": ("降水变异系数", "—", "seasonal"),
    "gs_prec_share": ("生长季降水集中度", "—", "seasonal"),
    "winter_temp": ("冬季气温", "℃", "seasonal"),
    "seasonal_temp_range": ("季节温差", "℃", "seasonal"),
}

# 空间粒度递进：省级两行是权威来源里已公开的数字，这里只登记其出处，不重算。
PROVINCE_ROW = {
    "level": "省级（M01–M04）",
    "scope": "31 省 × 13 年 = 403 行 × 11 维",
    "lco_r2": "−16.83（中位，31 省仅 1 省 > 0）",
    "time_r2": "+0.894 ± 0.104（leave-year-out）",
    "reading": "省-年常量主导（ICC = 0.9710），跨省空间外推不成立",
    "source": "backend/models/strict_cv_v3_card.md",
}


class RepoError(Exception):
    """Repository 基类异常。"""


class RepoUnavailable(RepoError):
    """county.db 不存在 / 不可读。"""


class CountyNotFound(RepoError):
    def __init__(self, code: int) -> None:
        super().__init__(f"county_code not in panel: {code}")
        self.code = code


class YearOutOfRange(RepoError):
    def __init__(self, year: int, lo: int, hi: int) -> None:
        super().__init__(f"year {year} not in [{lo}, {hi}]")
        self.year = year


def _open_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise RepoUnavailable(f"county.db not found at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def is_available(db_path: Optional[Path] = None) -> bool:
    return (db_path or DEFAULT_DB_PATH).exists()


def get_metadata(db_path: Optional[Path] = None) -> dict[str, str]:
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM metadata")}


def get_years(db_path: Optional[Path] = None) -> list[int]:
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        rows = conn.execute("SELECT DISTINCT year FROM county_model_out ORDER BY year").fetchall()
        if not rows:
            raise RepoUnavailable("county_model_out 表无数据")
        return [int(r["year"]) for r in rows]


def _validate_year(year: int, db_path: Optional[Path]) -> None:
    years = get_years(db_path)
    if year not in years:
        raise YearOutOfRange(year, years[0], years[-1])


def get_counties(
    year: int,
    unit: str = "all",
    province: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """某年县级快照，供 M07 地图着色与点位。

    Args:
        year: 面板年份
        unit: "all" 全部单元 / "farm" 仅粮食产量 ≥ 1 万吨的主产单元
        province: 可选，中文省名过滤（如 "四川省"）

    Returns:
        每行含 map_key（与前端 geojson 的 properties.name 同口径）/ 风险等级 /
        气候异常 / 当年总产量 / 主产单元标记。
        一年约 1,200 行，故此处只返回地图与清单需要的字段；单县的完整轨迹与
        16 维归因分别走 get_county_history / get_attribution。
    """
    _validate_year(year, db_path)
    if unit not in ("all", "farm"):
        raise ValueError(f"unit must be 'all' or 'farm', got {unit!r}")

    sql = """
        SELECT m.county_code, m.county, m.province, m.map_key, m.on_map,
               o.risk_level, o.risk_pct, o.clim_anomaly, o.unit_type,
               p.grain_output_t
        FROM county_model_out o
        JOIN county_meta m ON m.county_code = o.county_code
        LEFT JOIN county_panel p
               ON p.county_code = o.county_code AND p.year = o.year
        WHERE o.year = ?
    """
    params: list = [year]
    if unit == "farm":
        sql += " AND o.unit_type = 'farm'"
    if province:
        sql += " AND m.province = ?"
        params.append(province)
    sql += " ORDER BY o.risk_level DESC, m.county_code"

    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["on_map"] = bool(d["on_map"])
        out.append(d)
    return out


def get_county_history(code: int, db_path: Optional[Path] = None) -> dict:
    """单县县级面板时间序列 + 归因轨迹。"""
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        meta = conn.execute(
            "SELECT * FROM county_meta WHERE county_code = ?", (code,)
        ).fetchone()
        if meta is None:
            raise CountyNotFound(code)
        rows = conn.execute(
            """
            SELECT o.year, o.y_true, o.y_pred, o.clim_contrib, o.clim_anomaly,
                   o.risk_level, o.risk_pct, o.contrib_pct,
                   o.unit_type, p.grain_output_t, p.sown_kha, p.temp, p.prec, p.sun,
                   p.gs_tmax_mean, p.gs_ppt, p.gs_prec_share, p.spei_growing_season_mean
            FROM county_model_out o
            LEFT JOIN county_panel p
                   ON p.county_code = o.county_code AND p.year = o.year
            WHERE o.county_code = ?
            ORDER BY o.year
            """,
            (code,),
        ).fetchall()
    info = dict(meta)
    info["on_map"] = bool(info["on_map"])
    return {"county": info, "series": [dict(r) for r in rows]}


def get_attribution(code: int, year: int, db_path: Optional[Path] = None) -> dict:
    """单县单年的 16 维气候边际贡献（SHAP），按绝对值排序。"""
    path = db_path or DEFAULT_DB_PATH
    cols = list(FEATURE_DICT)
    select = ", ".join(f'o."shap_{c}" AS "shap__{c}"' for c in cols)
    value_cols = ", ".join(f'p."{c}" AS "val__{c}"' for c in cols)

    with _open_ro(path) as conn:
        meta = conn.execute(
            "SELECT * FROM county_meta WHERE county_code = ?", (code,)
        ).fetchone()
        if meta is None:
            raise CountyNotFound(code)
        row = conn.execute(
            f"""
            SELECT o.year, o.y_true, o.y_pred, o.clim_contrib, o.clim_anomaly,
                   o.risk_level, o.risk_pct, o.contrib_pct, o.unit_type,
                   {select}, {value_cols}
            FROM county_model_out o
            LEFT JOIN county_panel p
                   ON p.county_code = o.county_code AND p.year = o.year
            WHERE o.county_code = ? AND o.year = ?
            """,
            (code, year),
        ).fetchone()
        if row is None:
            return {"county": dict(meta), "year": year, "available": False, "items": []}
        directions = {
            r["feature"]: bool(r["same_sign"])
            for r in conn.execute("SELECT * FROM feature_direction")
        }

    d = dict(row)
    items = []
    for c in cols:
        label, unit, family = FEATURE_DICT[c]
        items.append(
            {
                "feature": c,
                "label": label,
                "unit": unit,
                "family": family,
                "shap": d.get(f"shap__{c}"),
                "value": d.get(f"val__{c}"),
                "direction_stable": directions.get(c),
            }
        )
    items.sort(key=lambda x: -abs(x["shap"] or 0.0))

    info = dict(meta)
    info["on_map"] = bool(info["on_map"])
    return {
        "county": info,
        "year": d["year"],
        "available": True,
        "summary": {
            "clim_contrib": d["clim_contrib"],
            "clim_anomaly": d["clim_anomaly"],
            "y_pred": d["y_pred"],
            "y_true": d["y_true"],
            "risk_level": d["risk_level"],
            "risk_pct": d["risk_pct"],
            "contrib_pct": d["contrib_pct"],
            "unit_type": d["unit_type"],
        },
        "items": items,
    }


def _standard_map(db_path: Optional[Path] = None) -> dict[str, list[dict]]:
    path = db_path or DEFAULT_DB_PATH
    with _open_ro(path) as conn:
        rows = conn.execute(
            "SELECT group_name, item, value FROM county_standard ORDER BY group_name, item"
        ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["group_name"], []).append(
            {"item": r["item"], "value": r["value"]}
        )
    return grouped


def _n_feat(grouped: dict[str, list[dict]], group: str, config: str) -> str:
    """从 <config>|<n_feat>|... 形态的键里取维数（维数是键的一部分，不是单独条目）。"""
    for e in grouped.get(group, []):
        parts = e["item"].split("|")
        if len(parts) >= 2 and parts[0] == config:
            return parts[1]
    return "—"


def _pick(grouped: dict[str, list[dict]], group: str, config: str, metric: str) -> Optional[str]:
    """从 county_standard 的 <config>|<n_feat>|<seed>|<metric> 键里取指定 config 的值。"""
    for e in grouped.get(group, []):
        parts = e["item"].split("|")
        if len(parts) < 2 or parts[0] != config:
            continue
        if parts[-1] == metric:
            return e["value"]
    return None


def _mean_std(grouped: dict[str, list[dict]], group: str, config: str, metric: str) -> str:
    vals = [
        float(e["value"])
        for e in grouped.get(group, [])
        if len(e["item"].split("|")) >= 3
        and e["item"].split("|")[0] == config
        and e["item"].split("|")[-1] == metric
    ]
    if not vals:
        return "—"
    n = len(vals)
    mean = sum(vals) / n
    if n < 2:
        return f"{mean:+.4f}"
    std = (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5
    return f"{mean:+.4f} ± {std:.4f}"


def get_standard(db_path: Optional[Path] = None) -> dict:
    """县级层的口径与协议数字（供前端"迁移体检"面板直读，前端不写死任何数字）。"""
    grouped = _standard_map(db_path)
    null_by_cfg = {
        cfg: _pick(grouped, "null_permutation", cfg, "null_mean")
        for cfg in ("CLIM3", "CLIM5", "CLIMG")
    }
    configs = [
        ("CLIM3", "纯县级年均气候 3 维", "口径下限：只给气温/降水/辐射"),
        ("CLIM5", "CLIM3 + 县级 SPEI ×2", "加入干旱强度"),
        ("CLIMG", "CLIM5 + 生长季/极端/季节指数 11 维", "站点主口径"),
    ]
    ladder = [PROVINCE_ROW]
    for cfg, meaning, note in configs:
        n_feat = _n_feat(grouped, "transfer_5seed", cfg)
        ladder.append(
            {
                "level": f"县级 · {cfg}（{n_feat} 维）",
                "scope": f"{meaning}｜{note}",
                "lco_r2": _mean_std(grouped, "transfer_5seed", cfg, "lco_r2")
                + f"（null {null_by_cfg[cfg] or '—'}）",
                "time_r2": _mean_std(grouped, "transfer_5seed", cfg, "time_r2"),
                "reading": "",
                "source": "reports/v6_12_climate_transfer_results.csv, reports/v6_13_null_results.csv",
            }
        )
    single = _mean_std(grouped, "single_yield_lco", "CLIMG", "lco_r2")
    ladder.append(
        {
            "level": "县级 · CLIMG（单产口径对照）",
            "scope": "目标换成 log(单产)，天然剥离规模；样本 4693 行 / 627 县（仅 60% 覆盖）",
            "lco_r2": f"{single}（null −0.0336）",
            "time_r2": "不报（2020-22 每年仅约 200 县，时间外推样本过小会误导）",
            "reading": "",
            "source": "reports/v6_13_single_yield_lco.csv",
        }
    )
    scale = _mean_std(grouped, "transfer_5seed", "CLIMG+S", "lco_r2")
    scale_t = _mean_std(grouped, "transfer_5seed", "CLIMG+S", "time_r2")
    ladder.append(
        {
            "level": "县级 · CLIMG+播种面积（对照，不对外报）",
            "scope": "把规模放回特征，用于验证「前面的 R² 是不是规模背的」",
            "lco_r2": scale,
            "time_r2": scale_t,
            "reading": "比 CLIMG 高 0.2 左右 —— 差额即规模贡献，故站点口径不含规模",
            "source": "reports/v6_12_climate_transfer_results.csv",
        }
    )

    boot_txt = {e["item"].split("|")[-1]: e["value"] for e in grouped.get("bootstrap_delta", [])}

    nulls = [
        {
            "config": cfg,
            "n_feat": _n_feat(grouped, "null_permutation", cfg),
            "true_mean": _pick(grouped, "null_permutation", cfg, "true_mean"),
            "null_mean": _pick(grouped, "null_permutation", cfg, "null_mean"),
            "excess": _pick(grouped, "null_permutation", cfg, "excess_true_over_null"),
            "frac_true_gt_null": _pick(grouped, "null_permutation", cfg, "frac_true_gt_null"),
        }
        for cfg in ("CLIM3", "CLIM5", "CLIMG")
    ]

    scale = {e["item"]: e["value"] for e in grouped.get("scope_diagnosis", [])}
    scale_note = scale.pop("note", None)

    return {
        "ladder": ladder,
        "nulls": nulls,
        "scale_diagnosis": scale,
        "scale_note": scale_note,
        "bootstrap": boot_txt,
        "note": (
            "省级与县级是两套独立口径，连验证协议都不同：省级是随机 8:2 / 留一年 / 留一省三协议，"
            "县级是按县分组的 10 折 LCO 与 ≤2019→2020-22 时间外推。"
            "省级 R² 来自省-年常量（ICC 0.9710），县级 CLIMG 已剔除规模与省-年常量，"
            "报告的是气候变量本身的可迁移解释力 —— 两列数字不可相加、不可互相替代。"
        ),
    }


def get_summary(db_path: Optional[Path] = None) -> dict:
    """县级层的覆盖率与元信息，供 M00 数据卡与 M07 页头。"""
    path = db_path or DEFAULT_DB_PATH
    meta = get_metadata(path)
    with _open_ro(path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n_rows,
                   COUNT(DISTINCT county_code) AS n_counties,
                   SUM(CASE WHEN unit_type = 'farm' THEN 1 ELSE 0 END) AS n_farm_rows,
                   SUM(CASE WHEN y_true IS NOT NULL THEN 1 ELSE 0 END) AS n_truth,
                   SUM(CASE WHEN unit_type IS NULL THEN 1 ELSE 0 END) AS n_unscored
            FROM county_model_out
            """
        ).fetchone()
        prov = conn.execute(
            "SELECT province, COUNT(*) AS n FROM county_meta GROUP BY province ORDER BY n DESC"
        ).fetchall()
        coverage = conn.execute(
            """
            SELECT year,
                   COUNT(*) AS scored,
                   SUM(CASE WHEN y_true IS NOT NULL THEN 1 ELSE 0 END) AS truth
            FROM county_model_out GROUP BY year ORDER BY year
            """
        ).fetchall()
    return {
        "scored_rows": row["n_rows"],
        "truth_rows": row["n_truth"],
        "unscored_rows": row["n_unscored"],
        "farm_rows": row["n_farm_rows"],
        "counties": row["n_counties"],
        "years": get_years(path),
        "provinces": [dict(r) for r in prov],
        "year_coverage": [dict(r) for r in coverage],
        "meta": {
            k: meta.get(k)
            for k in ("data_version", "source_parquet_md5", "built_at",
                      "n_climate_features", "model_trained_at", "model_scope_note")
        },
        "climate_features": json.loads(meta.get("climate_features", "[]")),
        "agri_output_threshold_t": int(meta.get("agri_output_threshold_t", 0) or 0),
        "risk_index_definition": meta.get("risk_index_definition"),
    }
