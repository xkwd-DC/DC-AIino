"""科研辅助工作台 API。

目标不是再做一个“预测接口”，而是把研究过程里最容易出错的四件事变成
可查看、可导出、可复核的产品能力：

1. 数据口径：面板、目标、样本量、来源与边界；
2. 模型体检：多协议 CV、混合效应方差分解、归因分歧、尺度混淆；
3. 敏感性：围绕本省基线做单因素扰动，返回响应曲线与排序；
4. 复核：模型卡、指标 JSON、环境版本、数据哈希与复现 README 打包下载。

重要：本模块的 audit 是“模型卡/验证产物的结构化汇总”，不声称在请求时
重新训练模型；敏感性接口只做模型内扰动，不代表因果效应或政策效果。
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, request, send_file

from api import envelope
from limiter import limiter

research_bp = Blueprint("research", __name__, url_prefix="/api/research")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
AUDIT_PATH = BACKEND_DIR / "data" / "research_audit.json"
MODELS_DIR = BACKEND_DIR / "models"

_CARD_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")

_SENS_FEATURES: list[tuple[str, str, str]] = [
    ("irr", "灌溉率", "%"),
    ("flood", "洪涝占比", "%"),
    ("sun", "日照时数", "h"),
    ("temp", "平均气温", "°C"),
    ("spei", "SPEI 干旱指数", ""),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_audit() -> dict[str, Any]:
    with AUDIT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _card_meta(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = next(
        (line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")),
        path.stem,
    )
    return {
        "slug": path.stem,
        "title": title,
        "filename": path.name,
        "size": path.stat().st_size,
        "updated": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).date().isoformat(),
    }


def _model_cards() -> list[dict[str, Any]]:
    if not MODELS_DIR.exists():
        return []
    return [
        _card_meta(p)
        for p in sorted(MODELS_DIR.glob("*.md"), key=lambda item: item.name)
    ]


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _data_manifest() -> list[dict[str, Any]]:
    candidates = [
        BACKEND_DIR / "data" / "grain.db",
        BACKEND_DIR / "data" / "county.db",
        PROJECT_DIR / "data" / "interim" / "paper_panel_v3.parquet",
    ]
    out: list[dict[str, Any]] = []
    for path in candidates:
        out.append(
            {
                "path": str(path.relative_to(PROJECT_DIR)) if path.is_relative_to(PROJECT_DIR) else str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else None,
                "sha256": _sha256(path),
            }
        )
    return out


def _environment() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in ("tensorflow", "xgboost", "shap", "sklearn", "pandas", "numpy", "flask"):
        try:
            module = __import__(name)
            packages[name] = str(getattr(module, "__version__", "unknown"))
        except Exception:
            packages[name] = "not-installed"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "note": "复现包只记录环境与数据哈希，不包含受限原始数据。",
    }


@research_bp.get("/audit")
@limiter.limit("120 per hour")
def get_audit():
    """返回模型体检的结构化摘要。"""
    try:
        audit = _load_audit()
    except Exception as exc:
        return envelope(
            error={"code": 503, "message": f"research audit unavailable: {exc}"},
            status=503,
        )
    audit["cards"] = _model_cards()
    audit["generated_at_runtime"] = _utcnow()
    return envelope(data=audit)


@research_bp.get("/model-cards")
@limiter.limit("120 per hour")
def list_model_cards():
    return envelope(data={"cards": _model_cards()})


@research_bp.get("/model-cards/<slug>")
@limiter.limit("120 per hour")
def get_model_card(slug: str):
    if not _CARD_SLUG.match(slug):
        return envelope(error={"code": 400, "message": "invalid model card slug"}, status=400)
    path = MODELS_DIR / f"{slug}.md"
    if not path.exists():
        return envelope(error={"code": 404, "message": "model card not found"}, status=404)
    return send_file(
        path,
        as_attachment=False,
        download_name=path.name,
        mimetype="text/markdown; charset=utf-8",
    )


@research_bp.get("/repro-bundle")
@limiter.limit("20 per hour")
def repro_bundle():
    """打包模型卡 + 指标 + 环境 + 数据哈希 + README。"""
    buf = io.BytesIO()
    audit = _load_audit()
    audit["cards"] = _model_cards()
    audit["data_manifest"] = _data_manifest()
    audit["environment"] = _environment()
    audit["packaged_at"] = _utcnow()

    readme = f"""# DC 科研复现包

打包时间：{audit["packaged_at"]}
模型口径：{audit["version"]}

## 包含内容

- `model_cards/`：各模型卡 Markdown，记录指标、协议、限制与已知失败模式；
- `research_audit.json`：结构化体检摘要（协议、ICC、归因分歧、消融、尺度、flags）；
- `data_manifest.json`：数据文件是否存在、大小与 SHA-256；
- `environment.json`：Python/平台/关键包版本；
- `feature_columns.json`：训练特征顺序（若本地存在）。

## 不含内容

原始数据、模型权重与受限年份数据不随包分发；请按 `data_manifest.json`
中的路径与哈希在授权环境中取数。

## 使用边界

所有指标属于统计关联与模型内评估，不构成因果结论、政策效果或产量预报。
复现结果若与模型卡数字不一致，先核对数据哈希、特征顺序、随机种子与协议，
再判断是否为版本差异。
"""

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", readme)
        zf.writestr(
            "research_audit.json",
            json.dumps(audit, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "data_manifest.json",
            json.dumps(audit["data_manifest"], ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "environment.json",
            json.dumps(audit["environment"], ensure_ascii=False, indent=2),
        )
        feature_path = BACKEND_DIR / "data" / "feature_columns.json"
        if feature_path.exists():
            zf.write(feature_path, "feature_columns.json")
        for card in MODELS_DIR.glob("*.md"):
            zf.write(card, f"model_cards/{card.name}")

    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="dc_repro_bundle.zip",
        mimetype="application/zip",
    )


@research_bp.post("/sensitivity")
@limiter.limit("60 per hour")
def sensitivity():
    """单因素敏感性：围绕本省基线扰动 5 个可干预/气候因子。

    这是 XGBoost 单模型的 one-at-a-time 情景，不是因果效应估计。
    每个因子的扫描范围截断到 31 省观测范围内，避免把外推当结论。
    """
    body = request.get_json(silent=True) or {}
    province = body.get("province")

    # 延迟导入，避免 blueprint 注册顺序造成循环依赖。
    from api import predict as predict_api
    from services import inference

    if not province or province not in predict_api._PROVINCES:
        return envelope(
            error={"code": 400, "message": f"unknown province: {province!r}"},
            status=400,
        )

    try:
        models = predict_api._get_models()
        baseline_yield = predict_api._baseline_yield_for(province)
        baseline_params = predict_api._fill_from_baseline(province, {})
        baseline_training = inference.to_training_keys(baseline_params)
        baseline_pred = inference.predict_xgb_yield(
            baseline_training,
            xgb=models["xgb"],
            x_scaler=models["xgb_x_scaler"],
        )
        baseline_risk = predict_api._yield_to_risk(baseline_pred, baseline_yield)
    except Exception as exc:
        return envelope(
            error={"code": 503, "message": f"model artifacts unavailable: {exc}"},
            status=503,
        )

    values = {
        feature: [float(p[feature]) for p in predict_api._PROVINCES.values()]
        for feature, _, _ in _SENS_FEATURES
    }

    curves: list[dict[str, Any]] = []
    for feature, label, unit in _SENS_FEATURES:
        observed = values[feature]
        obs_min, obs_max = min(observed), max(observed)
        base = float(baseline_params[feature])
        span = max(obs_max - obs_min, abs(base) * 0.1, 0.1)
        lo = max(obs_min, base - span * 0.25)
        hi = min(obs_max, base + span * 0.25)
        if hi <= lo:
            lo, hi = obs_min, obs_max

        points: list[dict[str, float]] = []
        for i in range(9):
            x = lo + (hi - lo) * i / 8
            params = {**baseline_params, feature: x}
            training = inference.to_training_keys(params)
            try:
                y = inference.predict_xgb_yield(
                    training,
                    xgb=models["xgb"],
                    x_scaler=models["xgb_x_scaler"],
                )
                risk = predict_api._yield_to_risk(y, baseline_yield)
            except Exception:
                continue
            points.append(
                {
                    "x": round(x, 4),
                    "yield_kg_per_ha": round(float(y), 1),
                    "risk": round(float(risk), 6),
                    "delta_risk": round(float(risk - baseline_risk), 6),
                }
            )

        if len(points) >= 2:
            swing = abs(points[-1]["risk"] - points[0]["risk"])
            curves.append(
                {
                    "feature": feature,
                    "label": label,
                    "unit": unit,
                    "baseline": round(base, 4),
                    "observed_range": [round(obs_min, 4), round(obs_max, 4)],
                    "scan_range": [round(lo, 4), round(hi, 4)],
                    "swing": round(swing, 6),
                    "points": points,
                }
            )

    curves.sort(key=lambda item: item["swing"], reverse=True)
    return envelope(
        data={
            "province": province,
            "model": "xgboost",
            "method": "one_at_a_time_xgboost",
            "baseline_yield_kg_per_ha": round(float(baseline_pred), 1),
            "baseline_risk": round(float(baseline_risk), 6),
            "curves": curves,
            "note": (
                "单因素敏感性：固定其他因子，只扰动一个输入；范围截断到 31 省观测区间。"
                "结果是模型内统计关联，不是因果效应、政策效果或产量预报。"
            ),
            "generated_at": _utcnow(),
        }
    )
