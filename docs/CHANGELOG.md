# 系统开发日志

> 每个开发日落一段。格式：日期 → 进展 / 遇到问题 / 明天计划。
> 答辩材料的"过程性材料"来源。

---

## 2026-05-21（系统开发启动日）

### 进展

- **周煜楠 UI 100% 到位**：一次性交付 6 份 HTML（index + 00 设计系统 + 01-04 模块原型），入仓 `frontend/prototypes/`
- **路线决策 v2**：取消 ICP 备案，改 GCP `e2-medium asia-east1` + 国际域名直接上线；详见 `docs/10` 已重写
- **docs/12 系统开发执行计划落档**：3 周时间表本地化为 35 天（5/21→6/25）
- **Phase 1 后端验收**：
  - 16/16 pytest 通过（health + 31 省 provinces + 11 特征 predict + ensemble + 校验 + 404 兜底）
  - 后端 server 启动正常，curl `/api/health` 200 OK
  - mock 数据 `provinces_baseline.json` 31 省 11 特征完整
- **Phase 1 前端骨架建好**：
  - Vue 3 + Vite + TypeScript + vue-router + pinia + ECharts + axios
  - 4 个 view 占位（RiskMap / ShapDashboard / ScenarioSim / ResiliencePath）
  - App.vue：顶部 tab 导航 + health 状态灯（绿/红/黄三态）
  - vite proxy `/api` → `:5000`
  - 设计 tokens.css 从 prototypes/00-design-system.html 提取

### 遇到问题

- **Python 3.14 + numpy<2.1 不兼容**：requirements.txt 锁定 numpy<2.1 是为 SHAP 0.46 配合，但 Python 3.14 上 numpy 1.x 没预编译 wheel
  - **方案 A**：本地 venv 只装 Flask 栈（mock 阶段不需要 numpy/tf），跑通 Phase 1
  - **方案 B**：GCP 服务器装 Python 3.11，Phase 2 时再装全栈
- **STATUS.md 部分 Edit 被中英文括号差异拒**：file 用全角 `（）` 但首轮 old_string 用半角 `()`，重 Edit 修复

### 明天计划（5/22）

- 开 PR `feat/system-skeleton`：周 UI 入仓 + Phase 1 骨架 + docs/10 v2 + docs/12
- CRAIC 5/23 提交准备
- 群里发：路线 v2 通告 + 系统开发启动公告

---

## 2026-05-21（接续 · 晚间本地联调验收）

### 进展

- **backend venv 建好**：`backend/.venv`（Python 3.14），装 mock 阶段最小依赖（flask 3.1.3 / flask-cors 6.0.2 / python-dotenv / pytest）；numpy/tf 暂不装，Phase 2 时切 GCP Python 3.11 venv
- **backend pytest**：`.venv/bin/python -m pytest` **16 通过 / 0.03s**；之前 STATUS 写"17 个"是 inflate，按实际 16 修正
- **backend 启动**：`python app.py` → 0.0.0.0:5000；curl `/api/health` 返 200 OK + service=grain-risk-api + version=0.1.0；curl `/api/provinces` 返 31 省 11 特征 JSON
- **frontend tsconfig 修复**：`@vue/tsconfig@0.5.1` 包内不存在 `tsconfig.node.json`（只有 dom/lib/json）→ `tsconfig.node.json` 改为 self-contained（不再 extends 缺失文件）；装 `@types/node` 给 `vite.config.ts` 的 `node:url` import
- **frontend build**：`vue-tsc --noEmit && vite build` 100 modules transformed，输出 142.51 KB（gzipped 55.6 KB），远低于 web rules "App page < 300KB gzip" 预算
- **frontend dev**：`npm run dev` → 5173 OK；vite proxy `/api/*` → `:5000` 工作；浏览器 `/` 200，4 view 各自单独 chunk
- **Phase 1 本地验收 ✅**：前端骨架 + 后端 health + proxy 联通全部通过

### 遇到问题

- 系统 `python` 命令不存在，只有 `python3`；改用 venv 后无影响
- 一次 parallel Bash 调用因为 inline `__version__` 探测脚本对 `python-dotenv` 报 AttributeError（dotenv 没这个属性）触发 exit 1，连带 cancel 了同批的 npm install——补跑就好，不是真问题

### 明天计划（5/22）

- 把今日所有变更分批 commit 推 `feat/system-skeleton` PR
- 群里发：路线 v2 通告 + Phase 1 本地验收通过 + CRAIC 5/23 倒计时
- CRAIC 三份材料 PDF 终版校对
- memory 落档：deployment_route_v2（GCP 路线决策）+ session_role 更新（Vue 集成归潘）

---
