# 极端气候下粮食生产风险智能分析 · 前端

Vue 3 + Vite + TypeScript + ECharts + Pinia + vue-router。

## 目录

```
frontend/
├── prototypes/        # 周煜楠 5/21 交付的 6 份 HTML 静态原型（保留参考）
├── public/
│   └── maps/          # ECharts 中国地图 JSON（Phase 3.2 下载）
├── src/
│   ├── api/           # axios 封装 + 各端点
│   ├── components/    # 通用组件（Phase 3 后填充）
│   ├── router/        # 路由
│   ├── stores/        # Pinia
│   ├── styles/        # tokens.css + global.css
│   ├── utils/
│   ├── views/         # 4 个模块视图
│   ├── App.vue        # 顶部 tab + health 状态灯
│   └── main.ts
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 开发

```bash
npm install
npm run dev   # http://localhost:5173 (前端) → proxy 到 :5000 (后端)
```

后端需同时运行：

```bash
cd ../backend
source ../.venv/bin/activate
python app.py
```

## 进度

| 模块 | 阶段 | 状态 | ddl |
|---|---|---|---|
| App.vue 框架 + 健康状态灯 | Phase 1 | ✅ | 5/26 |
| M01 风险时空地图 | Phase 3.2 | 🟡 占位 | 5/31 |
| M04 韧性路径推荐 | Phase 3.5 | 🟡 占位 | 5/31 |
| M02 SHAP 看板 | Phase 3.3 | ⏸️ 等熊鑫 | 6/10 |
| M03 情景模拟 | Phase 3.4 | ⏸️ 等熊鑫 | 6/12 |

## 设计来源

设计 tokens / 视觉风格 / 交互范式严格沿用 `prototypes/` 下周煜楠的 6 份 HTML。

⚠️ **数字口径警告**：prototypes 内硬编码 R²=0.847 / 11 特征 / NASA POWER 等数字与务实路线（R²=0.5647）不符——Vue 化时全部走 `/api/*`，**不照搬数字到代码**。
