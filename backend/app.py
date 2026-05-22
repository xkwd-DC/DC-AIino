"""Flask 入口：健康检查 + 31 省 mock 数据 + CORS。

开发：  python app.py
生产：  gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS

from api import envelope
from api.predict import predict_bp
from services import panel_repo

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 启动时一次性加载 mock，避免每次请求读盘。后续切 DB 时替换为查询。
with (DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    PROVINCES_BASELINE = json.load(f)

app = Flask(__name__)
app.json.ensure_ascii = False  # 直接输出中文，便于 curl 调试；浏览器/前端两种都能解析

# CORS：demo 阶段默认 *，部署时用 .env 的 CORS_ORIGINS 收窄到具体域名（逗号分隔）。
cors_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = "*" if cors_env.strip() == "*" else [o.strip() for o in cors_env.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": cors_origins}})

app.register_blueprint(predict_bp)


@app.get("/api/health")
def health():
    return envelope(
        data={
            "status": "ok",
            "service": "grain-risk-api",
            "version": "0.1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/api/provinces")
def list_provinces():
    """31 省面板数据。

    无 query: 返最新年的 31 省(grain.db 存在则查 db,否则 fallback 到 mock baseline)
    ?year=YYYY: 返指定年的 31 省(必须 db 存在,否则 503)
    """
    year_str = request.args.get("year")

    # 无 year 参数 — 向后兼容,Phase 1 行为不变(fallback baseline json)
    if year_str is None:
        if panel_repo.is_available():
            try:
                latest = panel_repo.get_latest_year()
                return envelope(data=panel_repo.get_panel_by_year(latest))
            except panel_repo.RepoUnavailable:
                pass  # fall through to baseline
        return envelope(data=PROVINCES_BASELINE)

    # 带 year — Phase 4 后才有效
    try:
        year = int(year_str)
    except ValueError:
        return envelope(
            error={"code": 400, "message": f"year must be an integer, got {year_str!r}"},
            status=400,
        )

    if not panel_repo.is_available():
        return envelope(
            error={"code": 503, "message": "panel data not loaded (run scripts/load_panel_to_db.py)"},
            status=503,
        )

    try:
        return envelope(data=panel_repo.get_panel_by_year(year))
    except panel_repo.YearOutOfRange as e:
        return envelope(error={"code": 400, "message": str(e)}, status=400)
    except panel_repo.RepoUnavailable as e:
        return envelope(error={"code": 503, "message": str(e)}, status=503)


@app.get("/api/provinces/<string:province>/history")
def province_history(province):
    """某省 2011-2023 时间序列。Phase 4 后可用。

    Flask 自动 URL decode 中文省名 (UTF-8 路径)。
    """
    if not panel_repo.is_available():
        return envelope(
            error={"code": 503, "message": "panel data not loaded (run scripts/load_panel_to_db.py)"},
            status=503,
        )

    try:
        return envelope(data=panel_repo.get_history(province))
    except panel_repo.ProvinceNotFound as e:
        return envelope(error={"code": 404, "message": str(e)}, status=404)
    except panel_repo.RepoUnavailable as e:
        return envelope(error={"code": 503, "message": str(e)}, status=503)


@app.errorhandler(404)
def not_found(_):
    return envelope(error={"code": 404, "message": "endpoint not found"}, status=404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
