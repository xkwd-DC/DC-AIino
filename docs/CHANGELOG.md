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

## 2026-05-22(全天硬战果 + 协调中心 5 agent 评审 + CRAIC 递交)

### 进展

#### 凌晨(00:00-01:30 UTC,~08:00-09:30 台湾)
- PR #16 协调二周目 merge(`f4be983`)
- PR #18 路线 E 收尾 merge(`a55bc46`)→ Issue #6 自动关闭
- PR #19 STATUS 凌晨同步 merge(`aa7dbf4`)

#### 上午(凌晨续到中午)— 熊鑫 SHAP v3 重生成
- `scripts/plot_shap_v3.py` 初版 + 2 fix patch
  - 列名映射 `flood_r` → `flood` + Keras `compile=False`
  - 字体 DejaVu Sans + 标题全英文化
- 5 张 PNG 入 `docs/figures/`:`fig4_shap_bar` / `fig5_shap_beeswarm` / `fig6_shap_interaction` / `fig9_attlstm_attention` / `fig_consistency`
- `shap_v3_summary.json` JSON summary
- **关键发现**: 双模型 Top-3 仅 Temp 重合(1/3)
  - XGB SHAP Top-3 = `[NDVI, Prec, Temp]`
  - Att-LSTM Att Top-3 = `[Drou_A, SPEI, Temp]`
  - `NDVI` XGB #1 → Att-LSTM #4
  - `SPEI` XGB 倒数#1 → Att-LSTM #2
  - `Drou_A` XGB #9 → Att-LSTM #1
- **PR #21 OPEN**(等 merge,5 commits)
- Issue #22 跟 plot_shap_v3 任务(等 merge 关)
- Issue #23 数据红旗:sun/prec/flood_a 单位漂移 30-54%(P1,石灵子)
- Issue #24 CRAIC §7 全面重写 — Top-3 重合 1/3,"双模型一致性"叙事不成立(已落 §7 章节级方案)

#### 下午(13:00-16:00 UTC)— 潘 4 view Vue 化 + 2 security 修
- M01 风险时空地图 Vue 化(`578fbab`):ECharts 中国地图 + 时间滑块 + Top10 + 明细卡 + 对比抽屉
- M04 韧性路径推荐 Vue 化(`8d894b1`):11 规则引擎 + 三阶段时间线 + stagger 入场动画 + jsPDF 导出
- M02 SHAP 看板 + M03 情景模拟 Vue 化(`1943381`)
- Security fix:Flask debug 默认 OFF + host 默认 127.0.0.1(`b87e667`)
- Security fix:CORS 默认收窄 + DOMPurify 包装 v-html(`5915084`)
- **PR #20 OPEN**(等 merge,5 commits,~540 行)

#### 晚间(15:30+ UTC)— 协调中心 5 agent 并发评审
- code-reviewer:WARN — 3 HIGH(GeoJSON CDN 无 fallback / province 选择双重 / console.error)+ 3 MEDIUM + 2 LOW
- typescript-reviewer:WARN — 3 HIGH(`as never` 类型擦除 / WaterfallStep 强断言 / watch deep 无 debounce)+ 5 MEDIUM
- security-reviewer:WARN — 4 HIGH(app.py 部署陷阱 / .env.example wildcard / 无 rate limit / 无安全头)+ 3 MEDIUM
- a11y-architect:**FAILS WCAG 2.2 AA** — 7+ CRITICAL + 10+ HIGH(所有 chart canvas 无 aria / 5 滑块无标签 / outline:none 无替换 / Top10 无键盘)
- planner:Phase 0 (GCP 12 步 2.5h) + Phase 4 (SQLite Day1+2) 完整可执行 runbook
- PR #20 综合 review 评论已贴
- Issue #25 a11y 修复(P1,7/31 前必修)开
- Issue #26 GCP production readiness(P1,6/25 前必修)开
- Issue #17 评论加 Phase 0+4 runbook
- Issue #12 评论 CRAIC 5/23 提交路径锁定

#### 夜间(台湾 23:00+)— CRAIC 三份材料最终递交
- CRAIC 5/23 09:00 提交 caairobot.com ✅
- 三份递交版入仓 `docs/craic/2026-05-23/`:
  - `01_报名表.docx` (116 KB)
  - `02_项目研究报告.docx` (4.7 MB)
  - `03_查新报告.docx` (26 KB)
- 团队:**稷韧云图**(潘 + 熊 + 常宇璇,指导徐苗)
- 常宇璇资料已在打印版完善

### 遇到问题

- **`.env` 本地凭据风险** — security agent 在审计时读了本地 `.env`(NASA Earthdata / Tianditu / geodata.cn 三组),agent transcript 被写到 `/tmp/claude-1002/.../tasks/<id>.output`。
  - 验证:`.env` 从未进 git history(`git log --all --full-history -- .env` 空 + `.gitignore:79-80` 早就忽略 `.env`/`.env.*`)
  - 缓解:删 agent transcript 文件 + 视情况轮换 3 组凭据(密码模式 `937276412@Pmq`)
  - 修:`backend/.env.example:8` `CORS_ORIGINS=*` 应改为占位 prod 域名
- **PR #21 git am 冲突** — 熊鑫 patch 0003 base 为 5/17 STATUS,与 origin/main 不同 → `git am --3way` 解 4 hunks 后 continue 成功

### 全天指标

| 维度 | 5/21 末 → 5/22 末 |
|---|---|
| 合并 PR | 9 → 12 (+3:#16/#18/#19) |
| 待合并 PR | 0 → 2 (#20/#21) |
| 开放 Issues | 6 → 6 (+#22/#23/#24/#25/#26,-#6 关) |
| Vue 业务模块 | 0/4 → **4/4 ✅** |
| 模型 R² | XGB 0.91 + LSTM 0.89 → +Att-LSTM 0.82 |
| SHAP/Attention 实测图 | 旧 → **5 新图全英文版** |
| 文档总数 | 16 → 17 + 3 CRAIC docx |
| CRAIC 三份材料 | 文本 95-100% → **✅ 完整递交** |

### 明天计划(5/23)

- 潘:CRAIC 已交可休息;接 PR #20+#21 merge + HIGH 8 项修
- 5/24 早晨:Phase 0 GCP 开机(2.5h 实操,planner 已给详 12 步)
- 协调中心:5/22 晚间 loop 推进 docs/papers 入仓 + Phase 4 schema 等独立工作(分独立分支)

---
