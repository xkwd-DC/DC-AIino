# Backend — 粮食生产风险可视化系统

Flask + Gunicorn 后端，承担模型推理、SHAP 解释、省份数据三类 API。

## 技术栈

- Python 3.10
- Flask 3 + Flask-CORS
- Gunicorn（生产）
- XGBoost (.pkl) + Keras LSTM (.h5) + SHAP
- SQLite（demo）→ PostgreSQL（部署）

## 目录

```
backend/
├── app.py            # Flask 入口与路由注册
├── api/              # 路由层（薄）
│   ├── predict.py    # /api/predict        模型推理
│   ├── shap_api.py   # /api/shap           SHAP 解释
│   └── province.py   # /api/provinces 等   省份数据
├── services/         # 业务逻辑层
├── models/           # 训练产物（.pkl/.h5，不入库）
├── data/             # API 用到的 CSV
└── requirements.txt
```

## 本地启动

```bash
cd backend

# 推荐：uv 自动拉 Python 3.10
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 或：本机已有 python3.10
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

.venv/bin/python app.py                       # 开发：http://localhost:5000
.venv/bin/gunicorn -w 6 -b 0.0.0.0:5000 app:app   # 生产（c2-standard-8）
```

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/api/health`    | 健康检查 |
| GET  | `/api/provinces` | 31 省基线数据（mock） |
| POST | `/api/predict`   | 风险预测（mock；M2 节点后接真模型） |

统一响应壳：`{"success": bool, "data": ..., "error": null | {"code", "message"}}`

### `POST /api/predict` 契约

**请求体**：

```json
{
  "province": "河南",
  "year": 2026,
  "params": {
    "irr":   65.4,   // 灌溉率 %
    "flood":  4.2,   // 洪涝占比 %
    "sun":  2240,    // 日照时数 h
    "temp":  14.2,   // 平均气温 °C
    "spei":  -0.2    // SPEI 干旱指数
  },
  "model": "ensemble"  // "xgboost" | "lstm" | "ensemble"，可选，默认 ensemble
}
```

**响应体（成功）**：

```json
{
  "success": true,
  "data": {
    "province": "河南",
    "year": 2026,
    "model": "ensemble",
    "risk_score": 0.024696,
    "baseline": 0.026,
    "delta": -0.001304,
    "confidence": 0.78,
    "shap_top": [
      {"feature": "洪涝占比", "value": 0.002113, "direction": "harm"},
      {"feature": "灌溉率",   "value": -0.001001, "direction": "protect"}
    ],
    "recommendations": [
      {"action": "...", "factor": "洪涝占比", "expected_delta": -0.002113, "priority": "high"}
    ],
    "_mock": true
  },
  "error": null
}
```

**错误（HTTP 400）**：`province` 未知 / `params` 缺字段 / 字段非数值 / `model` 不在白名单。
`_mock: true` 字段会在 M2 节点接入真模型后移除。

## 测试

```bash
# 装开发依赖（仅一次）
uv pip install --python .venv/bin/python -r requirements-dev.txt

# 跑全部测试 + 覆盖率
.venv/bin/pytest -v --cov=. --cov-report=term-missing
```

当前 15 个测试，覆盖率 99%（唯一未覆盖：`app.run()` 入口块，按设计不走测试）。

## 配置

复制 `.env.example` 为 `.env`：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | `5000` | dev 模式监听端口 |
| `CORS_ORIGINS` | `*` | 允许跨域来源，多个用逗号分隔，部署时收窄 |

## 常见问题

| 环境 | 现象 | 解法 |
|---|---|---|
| Mac M1/M2 | TF 装慢但能装 | 耐心等 2–5 分钟 |
| Windows | `python3.10` 命令找不到 | 用 `py -3.10`，或装 uv 走推荐路径 |
| Windows | 路径含中文 | 把仓库 clone 到纯英文路径（`C:\Code\`） |
| 任意 | pip 装到一半超时 | 加镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 任意 | TF 提示 AVX2/AVX512 not enabled | 信息性提示，可忽略；想消静音设 `TF_CPP_MIN_LOG_LEVEL=2` |
| Ubuntu 24.04+ | 系统 Python 是 3.12，没 3.10 | 用 uv（推荐）或 `deadsnakes` PPA 装 3.10 |
