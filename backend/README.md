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
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                       # 开发：http://localhost:5000
gunicorn -w 2 -b 0.0.0.0:5000 app:app   # 生产
```

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/provinces` | 31 省基线数据（当前为 mock） |
