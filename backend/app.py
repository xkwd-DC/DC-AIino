"""Flask 入口：健康检查 + 31 省面板数据 + 模型推理 + CORS / Rate-Limit / 安全头。

启动方式
========
开发：  python app.py                                  # 默认 host=127.0.0.1, debug=0
生产：  gunicorn -w 4 -b 127.0.0.1:5000 app:app        # 必须通过 nginx 反代,勿用 0.0.0.0

生产防御层 (Issue #26)
====================
1. CORS 收窄到 env CORS_ORIGINS (默认 dev localhost;生产必须显式设)
2. Rate limit (flask-limiter, 见 limiter.py + 各路由 @limiter.limit)
3. HTTP 安全头 (security_headers.py — HSTS / CSP / X-Frame-Options / nosniff / Referrer / Permissions)
4. nginx 反代终止 TLS (deploy/nginx.conf, Let's Encrypt)

绝不能在生产做的事
==================
- gunicorn `-b 0.0.0.0:5000` (绕过 nginx,直接对外暴露 5000)
- FLASK_DEBUG=1 (Werkzeug debugger 是 RCE 向量)
- CORS_ORIGINS=* (任意源跨域读 API)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS

from api import envelope
from api.predict import predict_bp, run_startup_smoke_check
from limiter import limiter
from security_headers import apply_security_headers
from services import panel_repo

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 启动时一次性加载 mock，避免每次请求读盘。后续切 DB 时替换为查询。
with (DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    PROVINCES_BASELINE = json.load(f)

app = Flask(__name__)
app.json.ensure_ascii = False  # 直接输出中文，便于 curl 调试；浏览器/前端两种都能解析

# SECURITY: CORS 默认收窄到 dev localhost 端口，**不再** allow all origins。
# 生产部署必须显式设 CORS_ORIGINS=https://yourdomain.com,...
# 历史教训：默认 * 在部署人忘设环境变量时会让任何恶意网站跨域读 API。
_DEV_DEFAULT_ORIGINS = (
    "http://localhost:5173,http://localhost:5174,"
    "http://127.0.0.1:5173,http://127.0.0.1:5174"
)
cors_env = os.getenv("CORS_ORIGINS", _DEV_DEFAULT_ORIGINS)
if cors_env.strip() == "*":
    # 显式 opt-in 允许全部（不推荐生产用）。日志告警提醒。
    import warnings
    warnings.warn("CORS_ORIGINS=* — 允许任何源跨域，仅限开发/排障", stacklevel=1)
    cors_origins: list[str] | str = "*"
else:
    cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": cors_origins}})

app.register_blueprint(predict_bp)

# Rate limiting — flask-limiter 真装时启用,缺失时 no-op (见 limiter.py)
# /api/predict   → 100/hour (CPU-heavy 真模型,DoS 防护,见 api/predict.py)
# /api/provinces → 500/hour (静态面板数据,带宽防护)
# /api/health    → 不限速 (Cloud Run / GCP load balancer 健康探针)
limiter.init_app(app)

# HTTP 安全头中间件 — Issue #26 HIGH#4
# nginx 已在 deploy/nginx.conf 配 HSTS / X-Frame-Options 等,
# 但 app 层兜底保证:
#   (a) dev/test 直连 Flask 时也有头
#   (b) nginx 配置漂移 / 单测试环境也合规
# 顺序: 在 blueprint 注册之后,limiter 之后 — 用 @app.after_request 注入响应头。
apply_security_headers(app)

# Issue #39: 启动期模型 smoke check (Henan 2022 XGB yield ≈ 4615 ± 1370)。
# 失败 → raise → fail-fast,绝不静默 fallback 到 mock。
# 测试场景设 DC_SKIP_MODEL_SMOKE=1 跳过(see conftest.py)。
run_startup_smoke_check()


@app.get("/api/health")
@limiter.exempt  # Issue #26 HIGH#3 - 健康探针不走 rate limit (GCP LB / Cloud Run 高频探测)
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
@limiter.limit("500 per hour")  # Issue #26 HIGH#3 - 静态面板数据,IP 级带宽防护
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
@limiter.limit("500 per hour")  # Issue #26 HIGH#3 - 与 /api/provinces 同档,统一带宽防护
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
    # SECURITY: debug 默认 OFF。Werkzeug debugger 在公网暴露 = 潜在 RCE。
    # 本地开发需要 reloader/traceback 时显式 `FLASK_DEBUG=1 python app.py`。
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    # SECURITY: host 默认 127.0.0.1。需要公网/局域网访问由 reverse proxy（Nginx）转发，
    # 或显式 `FLASK_HOST=0.0.0.0 python app.py`（不推荐直接对公网）。
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=debug)
