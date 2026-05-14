"""Flask 入口：健康检查 + 31 省 mock 数据 + CORS。

开发：  python app.py
生产：  gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 启动时一次性加载 mock，避免每次请求读盘。后续切 DB 时替换为查询。
with (DATA_DIR / "provinces_baseline.json").open(encoding="utf-8") as f:
    PROVINCES_BASELINE = json.load(f)

app = Flask(__name__)

# CORS：demo 阶段默认 *，部署时用 .env 的 CORS_ORIGINS 收窄到具体域名（逗号分隔）。
cors_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = "*" if cors_env.strip() == "*" else [o.strip() for o in cors_env.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": cors_origins}})


def envelope(data=None, error=None):
    """统一响应壳：{success, data, error}。"""
    return jsonify(success=error is None, data=data, error=error)


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
    return envelope(data=PROVINCES_BASELINE)


@app.errorhandler(404)
def not_found(_):
    return envelope(error={"code": 404, "message": "endpoint not found"}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
