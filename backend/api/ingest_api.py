"""M08 数据整备 API —— 上传 / 映射 / 质检 / 导出。

设计约束
========
- 只读沙盒：本模块不写 county.db，也不调用任何模型。
- 会话状态全部落盘（backend/data/ingest/<sid>/），多 worker 下不会丢。
- 上传文件按 uuid 目录隔离，24 小时自动清理。

端点
====
POST /api/ingest/sessions                 上传统计表（+ 可选地理文件）
POST /api/ingest/sessions/<sid>/run       按映射与单位执行清洗
GET  /api/ingest/sessions/<sid>           会话元信息与上次结果摘要
GET  /api/ingest/sessions/<sid>/export/<kind>   csv | report | script
"""

from __future__ import annotations

import json
import math
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Blueprint, request, send_file

from api import envelope
from limiter import limiter
from services import panel_cleaner

ingest_bp = Blueprint("ingest", __name__, url_prefix="/api/ingest")

BACKEND_DIR = Path(__file__).resolve().parents[1]
INGEST_DIR = BACKEND_DIR / "data" / "ingest"

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 200_000
MAX_COLS = 200
SESSION_TTL_SECONDS = 24 * 3600

STATS_EXT = {".csv", ".txt", ".tsv", ".xlsx", ".xlsm"}
GEO_EXT = {".json", ".geojson"}
SID_RE = re.compile(r"^[0-9a-f]{32}$")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _session_dir(sid: str) -> Path:
    if not SID_RE.match(sid or ""):
        raise panel_cleaner.CleanError("无效的会话编号")
    return INGEST_DIR / sid


def _cleanup_expired() -> None:
    """删除超过 24 小时的会话目录。"""
    if not INGEST_DIR.exists():
        return
    now = time.time()
    for child in INGEST_DIR.iterdir():
        if not child.is_dir() or not SID_RE.match(child.name):
            continue
        try:
            if now - child.stat().st_mtime > SESSION_TTL_SECONDS:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def _records(df: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    """把 DataFrame 前若干行转成可 JSON 化的记录。"""
    head = df.head(limit).astype(object)
    out: list[dict[str, Any]] = []
    for row in head.to_dict(orient="records"):
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if value is None or (isinstance(value, float) and math.isnan(value)):
                clean[str(key)] = None
            elif isinstance(value, (pd.Timestamp, datetime)):
                clean[str(key)] = str(value)
            else:
                clean[str(key)] = value
        out.append(clean)
    return out


def _load_meta(sid: str) -> dict[str, Any]:
    meta_path = _session_dir(sid) / "meta.json"
    if not meta_path.exists():
        raise panel_cleaner.CleanError("会话不存在或已过期")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _save_meta(sid: str, meta: dict[str, Any]) -> None:
    (_session_dir(sid) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@ingest_bp.post("/sessions")
@limiter.limit("30 per hour")
def create_session():
    _cleanup_expired()

    mode = (request.form.get("mode") or "china").strip().lower()
    if mode not in ("china", "custom"):
        return envelope(
            error={"code": 400, "message": "mode 只能是 china 或 custom"}, status=400
        )

    stats = request.files.get("stats")
    if stats is None or not stats.filename:
        return envelope(
            error={"code": 400, "message": "请上传统计表（字段名 stats）"}, status=400
        )

    stats_ext = _safe_ext(stats.filename)
    if stats_ext not in STATS_EXT:
        return envelope(
            error={"code": 400, "message": f"统计表只支持 {sorted(STATS_EXT)}"}, status=400
        )

    geo = request.files.get("geo")
    if geo is not None and geo.filename:
        if mode != "custom":
            return envelope(
                error={"code": 400, "message": "中国模式不需要地理文件；跨国数据请选 custom"}, status=400
            )
        if _safe_ext(geo.filename) not in GEO_EXT:
            return envelope(
                error={"code": 400, "message": "地理文件只支持 .json / .geojson"}, status=400
            )
    elif mode == "custom":
        return envelope(
            error={"code": 400, "message": "国外模式必须上传地理文件（GeoJSON）"}, status=400
        )

    sid = uuid.uuid4().hex
    session = _session_dir(sid)
    (session / "input").mkdir(parents=True, exist_ok=True)
    (session / "output").mkdir(parents=True, exist_ok=True)

    stats_path = session / "input" / f"stats{stats_ext}"
    stats.save(stats_path)
    if stats_path.stat().st_size > MAX_BYTES:
        shutil.rmtree(session, ignore_errors=True)
        return envelope(
            error={"code": 413, "message": "文件超过 10 MB 上限"}, status=413
        )

    geo_path: Path | None = None
    if geo is not None and geo.filename:
        geo_path = session / "input" / "geo.geojson"
        geo.save(geo_path)

    try:
        sheet = request.form.get("sheet") or None
        df = panel_cleaner.read_table(
            stats_path, sheet=int(sheet) if sheet and sheet.isdigit() else None
        )
    except panel_cleaner.CleanError as exc:
        shutil.rmtree(session, ignore_errors=True)
        return envelope(error={"code": 400, "message": str(exc)}, status=400)
    except Exception as exc:  # 解析失败不把堆栈甩给前端
        shutil.rmtree(session, ignore_errors=True)
        return envelope(
            error={"code": 400, "message": f"文件解析失败：{exc}"}, status=400
        )

    if len(df) == 0:
        shutil.rmtree(session, ignore_errors=True)
        return envelope(error={"code": 400, "message": "表里没有数据行"}, status=400)
    if len(df) > MAX_ROWS:
        shutil.rmtree(session, ignore_errors=True)
        return envelope(
            error={"code": 413, "message": f"行数超过 {MAX_ROWS} 上限"}, status=413
        )
    if len(df.columns) > MAX_COLS:
        shutil.rmtree(session, ignore_errors=True)
        return envelope(
            error={"code": 413, "message": f"列数超过 {MAX_COLS} 上限"}, status=413
        )

    columns = [str(c) for c in df.columns]
    mapping = panel_cleaner.guess_mapping(columns)
    inferred = panel_cleaner.infer_units(df, mapping)
    chosen_units = {
        field: info["suggested"] for field, info in inferred.items()
    }
    years: list[int] = []
    year_col = mapping.get("year", {}).get("column")
    if year_col and year_col in df.columns:
        year_values = panel_cleaner.parse_number(df[year_col]).dropna()
        years = sorted({int(y) for y in year_values if 1900 <= y <= 2100})

    meta = {
        "session_id": sid,
        "mode": mode,
        "created_at": _utcnow(),
        "source_file": Path(stats.filename).name,
        "stats_path": str(stats_path),
        "geo_path": str(geo_path) if geo_path else None,
        "rows": int(len(df)),
        "columns": columns,
        "years": years,
        "mapping": mapping,
        "units": chosen_units,
    }
    _save_meta(sid, meta)

    return envelope(
        data={
            "session_id": sid,
            "mode": mode,
            "source_file": meta["source_file"],
            "rows": meta["rows"],
            "columns": columns,
            "years": years,
            "mapping": mapping,
            "units": {"chosen": chosen_units, "inferred": inferred},
            "field_specs": [
                {
                    "key": s["key"],
                    "label": s["label"],
                    "kind": s["kind"],
                    "required": s["required"],
                }
                for s in panel_cleaner.FIELD_SPECS
            ],
            "unit_options": panel_cleaner.UNIT_FACTORS,
            "preview": _records(df, 8),
        }
    )


@ingest_bp.post("/sessions/<sid>/run")
@limiter.limit("60 per hour")
def run_session(sid: str):
    try:
        session = _session_dir(sid)
        meta = _load_meta(sid)
    except panel_cleaner.CleanError as exc:
        return envelope(error={"code": 404, "message": str(exc)}, status=404)

    payload = request.get_json(silent=True) or {}
    mapping = payload.get("mapping") or meta["mapping"]
    units = {**meta.get("units", {}), **(payload.get("units") or {})}

    ok, missing = panel_cleaner.mapping_complete(mapping)
    if not ok:
        return envelope(
            error={"code": 400, "message": "缺少必需字段：" + "、".join(missing)},
            status=400,
        )

    try:
        raw = panel_cleaner.read_table(Path(meta["stats_path"]))
        clean = panel_cleaner.apply_mapping(raw, mapping, units)
    except panel_cleaner.CleanError as exc:
        return envelope(error={"code": 400, "message": str(exc)}, status=400)

    inferred = panel_cleaner.infer_units(raw, mapping)
    findings = panel_cleaner.check_basic(clean)
    findings += panel_cleaner.check_units(units, inferred)

    if meta["mode"] == "china":
        matched, region_stats = panel_cleaner.match_china(clean)
        findings += panel_cleaner.check_regions(matched, region_stats)
        result, climate_stats = panel_cleaner.attach_climate_china(matched)
        findings += panel_cleaner.check_climate(result, climate_stats)
        summary_extra = {
            "matched": region_stats["matched"],
            "match_rate": region_stats["match_rate"],
            "match_method": region_stats["by_method"],
            "climate_covered": climate_stats.get("covered", 0),
            "climate_rate": climate_stats.get("rate", 0.0),
        }
    else:
        from services import geo_climate

        geo_path = meta.get("geo_path")
        if not geo_path:
            return envelope(
                error={"code": 400, "message": "国外模式缺少地理文件"}, status=400
            )
        try:
            result, region_stats = geo_climate.attach_climate_custom(
                clean, Path(geo_path)
            )
            window_years = geo_climate.available_years()
            window = (
                (window_years[0], window_years[-1]) if window_years else (0, 0)
            )
        except panel_cleaner.CleanError as exc:
            return envelope(error={"code": 400, "message": str(exc)}, status=400)
        findings += panel_cleaner.check_regions(result, region_stats)
        findings += panel_cleaner.check_climate(
            result, region_stats, window=window, region="custom"
        )
        summary_extra = {
            "matched": region_stats["matched"],
            "match_rate": region_stats["match_rate"],
            "match_method": region_stats["by_method"],
            "climate_covered": region_stats.get("covered", 0),
            "climate_rate": region_stats.get("rate", 0.0),
            "geo_units": region_stats.get("units", 0),
        }

    # 把原始表里未被标准化的列一起带出来
    extra_cols = [c for c in raw.columns if c not in result.columns]
    if extra_cols:
        result = pd.concat(
            [result, raw[extra_cols].reset_index(drop=True)], axis=1
        )

    output_cols = panel_cleaner.export_columns(result)
    output = result[output_cols]
    out_dir = session / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    output.to_csv(out_dir / "cleaned_panel.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": _utcnow(),
        "source_file": meta.get("source_file", ""),
        "input_rows": int(len(raw)),
        "output_rows": int(len(output)),
        "mode": meta["mode"],
        **summary_extra,
    }
    report = panel_cleaner.build_report(findings, summary, mapping, units)
    (out_dir / "qc_report.md").write_text(report, encoding="utf-8")

    sha = panel_cleaner.sha256_of(Path(meta["stats_path"]))
    script = panel_cleaner.build_repro_script(mapping, units, sha)
    (out_dir / "run_pipeline.py").write_text(script, encoding="utf-8")

    meta["mapping"] = mapping
    meta["units"] = units
    meta["last_run"] = summary
    _save_meta(sid, meta)

    blocked = any(f["level"] == "blocker" for f in findings)
    return envelope(
        data={
            "session_id": sid,
            "summary": summary,
            "findings": findings,
            "blocked": blocked,
            "columns": output_cols,
            "preview": _records(output, 20),
            "exports": [
                {"kind": "csv", "label": "清洗后面板 CSV", "hint": f"{len(output)} 行"},
                {"kind": "report", "label": "质检报告 Markdown", "hint": f"{len(findings)} 条"},
                {"kind": "script", "label": "复现脚本 Python", "hint": "同参数重跑"},
            ],
        }
    )


@ingest_bp.get("/sessions/<sid>")
@limiter.limit("120 per hour")
def get_session(sid: str):
    try:
        meta = _load_meta(sid)
    except panel_cleaner.CleanError as exc:
        return envelope(error={"code": 404, "message": str(exc)}, status=404)
    return envelope(
        data={
            "session_id": meta["session_id"],
            "mode": meta["mode"],
            "created_at": meta["created_at"],
            "source_file": meta["source_file"],
            "rows": meta["rows"],
            "columns": meta["columns"],
            "years": meta.get("years", []),
            "last_run": meta.get("last_run"),
        }
    )


@ingest_bp.get("/sessions/<sid>/export/<kind>")
@limiter.limit("120 per hour")
def export_session(sid: str, kind: str):
    try:
        session = _session_dir(sid)
        meta = _load_meta(sid)
    except panel_cleaner.CleanError as exc:
        return envelope(error={"code": 404, "message": str(exc)}, status=404)

    files = {
        "csv": (session / "output" / "cleaned_panel.csv", "cleaned_panel.csv"),
        "report": (session / "output" / "qc_report.md", "qc_report.md"),
        "script": (session / "output" / "run_pipeline.py", "run_pipeline.py"),
    }
    if kind not in files:
        return envelope(error={"code": 404, "message": "未知导出类型"}, status=404)
    path, name = files[kind]
    if not path.exists():
        return envelope(
            error={"code": 404, "message": "尚未生成，请先执行清洗"}, status=404
        )
    stem = Path(meta.get("source_file", "panel")).stem
    return send_file(
        path, as_attachment=True, download_name=f"{stem}_{name}", mimetype="application/octet-stream"
    )


@ingest_bp.errorhandler(413)
def too_large(_error):
    return envelope(error={"code": 413, "message": "文件超过 10 MB 上限"}, status=413)
