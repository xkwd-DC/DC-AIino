# DC-AIino 项目文件清单

> 给独立 Claude 的完整项目导读 & 面试技术点索引

---

## 项目概述

**DC-AIino** 是一个面向全国大学生创新竞赛（大创）的农业粮食安全风险预测系统，包含：
- 多模型 ML 训练流水线（XGBoost / LSTM / Attention-LSTM）
- Flask 3 REST API 后端（含 SHAP 可解释性）
- Vue 3 + ECharts 前端（6 模块仪表盘）
- 完整数据工程管线（NASA POWER / MODIS / EPS 多源融合，v1→v5 演进）
- GCP + nginx + Let's Encrypt 生产部署方案

---

## 一、根目录

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `.env.example` | 环境变量模板 | 12-factor App 配置管理 |
| `.gitignore` | 排除规则（含模型 artifact 保留策略） | Git LFS 策略 / 数据版本管理 |
| `.python-version` | pyenv 锁定 Python 3.10 | Python 版本管理工具链 |
| `README.md` | 中文项目概览（竞赛背景） | 项目文档规范 |
| `EVAL_BRIEFING.md` | AI 评测摘要；主动披露鲁棒性缺陷 | 诚实的模型验证 / 模型卡片 |
| `compare_data_versions.py` | v3/v4/v5 面板数据对比工具 | 数据版本 diff / ETL 校验 |
| `diagnose_v2.py` / `diagnose_y_trend.py` / `inspect_data.py` | 数据诊断与趋势分析 | EDA / 探索性数据分析 |
| `retest_with_real_yield.py` | 用真实产量数据重测模型 | 数据科学迭代流程 |
| `train_xgb_baseline.py` | XGBoost 10 seed 基线训练（含 SHAP） | XGBoost / 随机种子评估 / SHAP |
| `train_lstm_baseline.py` | LSTM 基线训练 | Keras 时序建模 / 归一化 |
| `train_att_lstm_baseline.py` | Attention-LSTM 训练 | Self-Attention / 可解释性 |
| `train_xgb_compare.py` | 多模型横向比较 | 模型选择 / 对比实验 |
| `train_xgb_y_butter_ablation.py` | 目标变量消融研究 | 消融实验 / 特征工程 |
| `verify_env.py` | 依赖环境自检 | DevOps / 可复现性 |
| `.github/workflows/ci.yml` | GitHub Actions CI（pytest + coverage） | CI/CD / 自动化测试 |

---

## 二、后端 `backend/`

### 2.1 主应用

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `app.py` | Flask 3 入口；CORS、限速、安全头、SPA 路由 | Flask 应用工厂 / Gunicorn 部署 / HSTS / CSP / X-Frame-Options |
| `requirements.txt` | 生产依赖（版本冻结） | tensorflow-cpu 2.18 / xgboost 2.1.1 / flask-limiter / shap 0.46 / Flask 3 |
| `requirements-dev.txt` | 测试依赖 | pytest / 测试自动化 |
| `pyproject.toml` | 包元数据 | Python 构建系统 |
| `limiter.py` | flask-limiter 封装；缺失时无操作降级 | 限流设计 / 优雅降级 / 装饰器模式 |
| `security_headers.py` | HTTP 安全头中间件 | HSTS / CSP / Referrer-Policy / Permissions-Policy / OWASP |

### 2.2 API 层 `backend/api/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `__init__.py` | 统一响应信封 `{"success", "data", "error"}` | API 设计规范 / 错误处理标准化 |
| `predict.py` | POST /api/predict；产量→风险映射 + SHAP + 内存 trace | 模型推理管线 / SHAP 可解释性 / Ring Buffer |
| `shap_api.py` | SHAP 特征重要性端点（子集聚合） | Tree SHAP / 特征归因 |
| `province.py` | GET /api/provinces（31省）+ 历史数据 | Repository 模式 / SQLite / REST 设计 |

### 2.3 服务层 `backend/services/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `inference.py` | ModelInferer Protocol stub；Keras 兼容垫片 | 深度学习推理 / 模型序列化 / Protocol ABC |
| `panel_repo.py` | SQLite 仓库；省份查询、年份过滤、只读模式 | 数据库抽象 / SQL 参数化查询 / 防注入 |

### 2.4 测试 `backend/tests/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `conftest.py` | pytest fixtures（client、smoke skip） | pytest fixture / 测试配置 |
| `test_api.py` | 22 个端点测试（health/provinces/predict 合约） | AAA 测试模式 / Mock 数据验证 |
| `test_panel_endpoints.py` | 面板数据 & 历史端点测试 | 集成测试 / 年份范围验证 |
| `test_predict_real.py` | 真实模型推理测试（11 特征 / 双模型） | 模型集成测试 |

### 2.5 数据与模型 `backend/data/` `backend/models/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `data/provinces_baseline.json` | 31省基线数据（fallback） | Mock Data / 兜底策略 |
| `models/xgb_model.pkl` (408 KB) | 训练好的 XGBoost 回归器 | scikit-learn pickle 序列化 |
| `models/lstm_model.h5` / `att_lstm_model.h5` | Keras LSTM / Attention-LSTM | TensorFlow h5 格式 / 循环神经网络 |
| `models/*_scaler.pkl` / `*_y_scaler.pkl` | 特征/目标标准化器 | ML 预处理管线 / StandardScaler |
| `models/*_feature_columns.json` | 11 维特征名映射 | Schema 声明 / 特征工程 |
| `models/*_seeds_results.json` | 10-seed R² 统计（均值±标准差） | 交叉验证 / 模型稳定性评估 |
| `models/strict_cv_v3_card.md` | 鲁棒性报告：留省验证 R²=-16.83 诚实披露 | 模型卡片 / 过拟合诊断 / 数据泄露防范 |
| `models/mixed_effects_v1_*` | 混合效应模型 POC（省份随机截距） | 层次/多级建模 / statsmodels |

---

## 三、前端 `frontend/`

### 3.1 构建与配置

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `package.json` | Vue 3 + Vite 前端；axios / echarts / pinia / vue-router / dompurify | SPA 技术选型 / 依赖管理 |
| `vite.config.ts` | Vite 开发服务器；/api 代理到 :5000；Cloudflare tunnel 白名单 | 构建工具 / 代理配置 / 跨域处理 |
| `tsconfig.json` | TypeScript 严格模式 / 路径别名 @/ / Vue DOM 类型 | 前端类型安全 / 工程化 |

### 3.2 应用核心 `frontend/src/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `main.ts` | Vue 应用启动（挂载 Pinia + router） | SPA 初始化流程 |
| `App.vue` | 6-tab 导航（M00-M05）+ 健康状态指示器 | 组件树根节点 / 无障碍（WCAG 2.2 AA） |
| `router/index.ts` | 路由定义；懒加载 6 个模块 | vue-router / 代码分割 / 懒加载 |

### 3.3 状态管理 `frontend/src/stores/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `useProvinceStore.ts` | Pinia 全局状态；31省选择、API 加载/错误、fallback | Pinia store / 响应式数据绑定 / 单一数据源 |

### 3.4 API 层 `frontend/src/api/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `http.ts` | axios 封装；响应信封拆包 / 统一错误处理 | HTTP 抽象层 / axios interceptors |
| `predict.ts` | POST /api/predict TypeScript 类型 + debounce 封装 | API 类型契约 / 防抖函数 |
| `shap.ts` | SHAP 子集聚合（北方/南方/主产区） | 特征重要性 API |
| `province.ts` | 省份列表 + 历史数据获取 | 面板数据请求 |
| `health.ts` | GET /api/health 存活探针 | Liveness Probe / 系统监控 |

### 3.5 视图模块 `frontend/src/views/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `Overview.vue` (M00) | 系统首页；统计卡片 + 模型说明 | 仪表盘布局 / 信息层次 |
| `RiskMap.vue` (M01) | ECharts 31省 choropleth 地图 + 年份时间轴滑块 | 数据可视化 / 地理空间渲染 / 交互设计 |
| `ShapDashboard.vue` (M02) | SHAP 特征重要性柱图 + 子集切换 + 双模型对比 | 可解释 AI / 对比分析 |
| `ScenarioSim.vue` (M03) | 5 参数滑块；实时 /api/predict（debounce） | 交互模拟 / 用户反馈 / 防抖优化 |
| `ResiliencePath.vue` (M04) | 11 规则韧性引擎；政策建议按优先级排序 | 规则引擎 / 政策生成 |
| `InferenceTrace.vue` (M05) | 最近 50 次 /api/predict 调用 Ring Buffer 可视化 | 可观测性 / 调试工具 |

### 3.6 工具与数据 `frontend/src/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `data/mockProvinces.ts` | 31省 Mock 基线；RANGES / YEARS 常量 / 风险色映射 | 骨架屏 / Fallback 策略 |
| `data/recommendation.ts` | M04 11 规则引擎（省份画像 / 预算估算 / 行动优先级） | 业务逻辑 / 决策树 |
| `data/a11y.ts` | WCAG 2.2 AA 助手（prefersReducedMotion / SR-only） | 无障碍合规 |
| `styles/tokens.css` | 设计 Token（颜色 / 字体 / 间距 / 动画 / 暗色模式就绪） | 设计系统 / CSS 变量 |
| `styles/global.css` | 全局 Reset + 响应式断点（≤900px 平板适配） | CSS 工程化 / 响应式设计 |

### 3.7 静态资源 `frontend/public/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `maps/china.json` | GeoJSON 中国省界（61 KB，自托管避免 CDN 单点） | 地理空间数据 / 自托管策略 |
| `deck/` | Slidev 幻灯片资产（非主应用） | Markdown 驱动演示 |

---

## 四、数据目录 `data/`

### 4.1 原始数据 `data/raw/`

| 文件/目录 | 作用 | 面试技术点 |
|---|---|---|
| `paper_panel/wang_tianshuo_original/*.xlsx` | 11 份 Excel（气候/产量/灌溉/化肥/灾害） | 多源数据整合 / 省级面板统计（2000-2024） |
| `gis_province/` | GeoJSON 省界（天地图） | 地理空间参考数据 |
| `eps_yield/eps_city_yield_*.csv` | EPS 地级市产量（6省真实数据） | 空间降尺度 / v5 扩展 |

### 4.2 中间数据 `data/interim/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `paper_panel_v3.parquet` | v3 最终版（403 行×27 列，31省×13年 2011-2023） | Parquet 格式 / 面板数据特征矩阵 |
| `paper_panel_v4.parquet` | v4（+CLCD 耕地比 / +灾害粒度） | 特征工程扩展 |
| `modis_province_monthly.parquet` | MODIS NDVI/LST（月→年聚合） | 遥感数据 / 空间聚合 |
| `nasa_power_annual.csv` | NASA POWER 气候 API（温度/降水/SPEI） | 气候数据 API 集成 |
| `spei_province_annual.csv` | SPEI 干旱指数（年化聚合） | 干旱指数计算 |

---

## 五、脚本目录 `scripts/`

### 5.1 数据管线 `scripts/data/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `00_ingest_paper_panel.py` | 11 份 Excel → Parquet (v1) | 数据摄取 / pandas ETL |
| `00a_fetch_stats_gov_cn_local.py` | 统计局数据爬取 | Web 爬虫 / 数据采集 |
| `00b_fetch_nasa_power.py` | NASA POWER API 拉取 | REST API 集成 / 气候数据 |
| `00c_fetch_spei.py` | SPEI 数据获取 | 气象指数 / 时序数据 |
| `00z_merge_panel.py` | 11 维数据对齐合并 | ETL / Schema 对齐 |
| `01_download_cropland.py` | CLCD 中国土地覆盖数据集获取 | 遥感 / 地理空间数据 |
| `03-04_request/poll_appeears.py` | MODIS AppEEARS API 异步任务管理 | 遥感数据编排 / 任务轮询 |
| `05_aggregate_modis_to_province.py` | MODIS 像素→省份空间聚合（耕地掩膜） | 栅格→矢量 / 空间聚合 |
| `05b_*` (7 个变体) | CLCD 比率 & 耕地加权迭代优化 | 特征工程 / 消融实验 |
| `07_fix_panel_v2.py` | 数据清洗 | 缺失值处理 / 数据质量 |
| `08_detrend_y.py` | 产量去趋势 | 时序预处理 / 趋势分离 |
| `v5_01-03_*.py` | v5 地级市扩展（MODIS/CLCD/NASA POWER → 市级） | 空间降尺度 / 面板扩展 |

### 5.2 模型训练与部署

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `retrain_all.sh` | 主重训脚本（顺序调用三模型） | ML 管线编排 / Bash 脚本 |
| `serve_demo.sh` | 快速启动（后端+前端 dev server） | 本地开发启动器 |
| `load_panel_to_db.py` | Parquet → SQLite ETL（grain.db） | 数据库初始化 |
| `mixed_effects_poc.py` | 混合效应模型 POC | statsmodels / 层次回归 |
| `plot_shap_v3.py` | SHAP 汇总图可视化 | SHAP 可视化 |

---

## 六、部署目录 `deploy/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `nginx.conf` | 反向代理（TLS 终止 / 4 安全头 / CORS） | nginx 生产配置 / 服务端安全加固 |
| `setup_letsencrypt.sh` | Certbot 自动化（一次性申请 + 自动续期） | SSL/TLS 自动化 / ACME 协议 |
| `README.md` | GCP 部署手册（nginx / SSL / HSTS / Cloudflare DNS） | 云部署 / DevOps Runbook |

---

## 七、文档目录 `docs/`

| 文件 | 作用 | 面试技术点 |
|---|---|---|
| `STATUS.md` | 实时项目状态追踪（里程碑 / Action Items） | 项目管理 |
| `CHANGELOG.md` | 版本历史 | 语义化版本管理 |
| `00_项目执行计划.md` | 执行计划（4 人 / 10 万预算 / 3 模型 / SQLite→GCP） | 项目范围规划 |
| `07_模型训练任务_算法组.md` | ML 团队 spec（11 artifact / 河南 2022 验证样本） | 模型需求文档 |
| `12_系统开发执行计划.md` | 系统构建分阶段路线图（Phase 0-5） | 系统设计 / 迭代规划 |
| `15_训练复现指南.md` | 可复现性指南（依赖冻结版本 / artifact checksum） | ML 可复现性 / MLOps |
| `17_韧性规则引擎说明.md` | 11 规则引擎透明度说明（M04 政策建议） | 规则引擎 / 可解释 AI |
| `23_软著申请材料指南.md` | 软件著作权注册指南（9/30 截止 / 5K 行门槛） | 知识产权策略 |

---

## 技术栈汇总（面试速查）

### 后端
| 层次 | 技术 |
|---|---|
| Web 框架 | Flask 3 + Gunicorn |
| 安全 | CORS / flask-limiter / HSTS / CSP / X-Frame-Options |
| ML 推理 | XGBoost (sklearn) / LSTM & Attention-LSTM (TensorFlow 2.18 Keras) |
| 可解释性 | SHAP TreeExplainer |
| 数据库 | SQLite（演示） → PostgreSQL（生产）|
| 数据处理 | Pandas / NumPy / scikit-learn / joblib |
| 测试 | pytest + coverage（GitHub Actions CI） |

### 前端
| 层次 | 技术 |
|---|---|
| 框架 | Vue 3 + TypeScript + Vite |
| 路由 | vue-router（懒加载） |
| 状态管理 | Pinia |
| 可视化 | ECharts 5.5.1（choropleth / 柱图） |
| HTTP | axios（自定义信封拆包） |
| 安全 | DOMPurify（XSS 防护） |
| 无障碍 | WCAG 2.2 AA（a11y 工具集） |
| 样式 | CSS 变量设计 Token / 响应式断点 |

### 数据工程
| 层次 | 技术 |
|---|---|
| 数据源 | NASA POWER API / MODIS AppEEARS / EPS / 省级统计局 Excel |
| 存储格式 | Parquet（中间层） / SQLite（服务层） / JSON（配置/基线） |
| 地理空间 | GeoJSON / rasterio / CLCD 耕地掩膜 |
| 数据版本 | v1→v5 面板演进（省级→地级市空间降尺度） |

### ML 核心概念
| 概念 | 说明 |
|---|---|
| 验证策略 | 10-seed 随机 8:2 / 留省验证（R²=-16.83，主动披露） / 留年验证 |
| 可解释性 | SHAP TreeExplainer + Attention 权重 |
| 特征工程 | 11 维（气候 / 灌溉 / 灾害 / 遥感 NDVI） |
| 归一化 | StandardScaler（特征 + 目标双路归一化） |
| 消融实验 | NDVI 移除研究 / XGB vs LSTM 分歧分析 |

### 部署与基础设施
| 层次 | 技术 |
|---|---|
| 云平台 | GCP e2-medium |
| Web 服务器 | nginx 反向代理（TLS 终止） |
| SSL | Let's Encrypt + Certbot 自动续期 |
| DNS | Cloudflare |
| CI/CD | GitHub Actions（pytest） |

---

*生成时间：2026-06-22 | 覆盖文件数：100+*
