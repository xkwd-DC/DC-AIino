# 项目实时状态 · STATUS

> **本文是项目级 single-source-of-truth dashboard**，任何 session 都该来这看大盘。
> 每次重要进展（PR merge / 任务完成 / 新 blocker）都更新本文。
>
> 最近更新：**2026-05-26 深夜**（🚀 docs/13 国家级执行规划 v1 落定 + v6 叙事基线化 + T6/T7/T2 三 agent 战果 push;邮件汇报 + T8 onboarding + 教务处咨询邮件草稿已就位)

---

## 🚨 关键路线决策

### 🚀 2026-05-26 深夜 · T1-T8 执行规划落定 + 3 agent 战果

- **`docs/13_国家级升级执行规划_2026-05-26.md` v1 落定**:三主线(论文主推 / 软著同步 / AI 大赛 upside)+ 12 月时间表 + 8 件本周事 + GCP 5 步详细
- **v6 叙事基线化**:`_craic/04_*.md` header 从"草稿"升级"叙事基线(已批准)";`docs/03` 加 banner 指向 v6 基线(**已交版 v5 保留快照, 不动**)
- **`docs/00_项目执行计划.md` v2 同步**(T2,commit `a9e355a`):1 万经费 + 4 人队 + 三模型互补 + GCP/SQLite + §5 三主线
- **3 个 opus agent 并发完成 + push main**:

  | Agent | commit | 主产出 |
  |---|---|---|
  | T7 论文 outline | `a6f3680` | `docs/papers/v1_outline.md`(278 行)— §3/§5/§6/§7 outline + 5 期刊候选 + 投稿优先级 |
  | T2 执行计划 v2 | `a9e355a` | `docs/00` 全文同步(+284/-165) |
  | T6 训练复现指南 | `abc8e76` | `docs/15`(539 行)+ `scripts/retrain_all.sh`(192 行)+ requirements frozen + `.python-version` |

- **叙事 spot check**:3 个新 doc 中"禁用叙事"关键词出现 8 处, **全部为反向引用**(❌ 不写 X / 主动反驳 X), 无 1 处实际使用;"leave-province / -16.83" 出现 24 次, 诚实披露到位
- **决策同步**(用户 5/26 晚拍板):
  - ✅ 主推:论文 + 软著同步, AI 大赛 in 准备
  - ✅ 不延期(12 月不变)
  - ✅ 经费 1 万维持,不申请追加,选低版面费期刊
  - ✅ 申报书 v5 已交不动, v6 仅作后续材料基线
- **邮件汇报**:T6+T7+T2 战果 + T8 石灵子 onboarding prompt 已通过 msmtp 发到 `sakura93777@163.com`(2026-05-26 09:42 UTC,smtpstatus=250)
- **教务处咨询邮件草稿**:`docs/coord/2026-05-26_教务处咨询邮件草稿.md` 已起(中检 / 经费 / 结题硬指标 3 问),等用户补收件人后发

### 🎉 2026-05-26 · 项目升级国家级大创

- 原省级大创已批准 → **学院推荐为国家级大学生创新创业训练计划**
- 经费 / 中期检查时间 / 结题硬指标具体要求 **待教务处通知**(占位,user 另起 session 安排)
- **叙事影响**:国家级评审更严格,v6 leave-province-out 诚实披露口径 **不能回滚**到"R²=0.91 高精度预测"
- **结题硬指标**(典型国家级要求软著 / 论文 / 获奖至少一项):
  - 软著(决策支持系统)~ 3 个月下来,**兜底产出**
  - 论文(SCI 4 区或核心期刊 1 篇)~ 6-9 个月,**主推产出**
  - 获奖(AI 大赛 + 互联网+ + 挑战杯 三选一)~ 进行中
- 行动 milestone:`国家级升级` 涵盖 #10 / #40-#43

### 🏁 2026-05-22 · CRAIC 三份材料最终递交 ✅

| 文件 | 入仓路径 | 大小 |
|---|---|---|
| 报名表 | `docs/craic/2026-05-23/01_报名表.docx` | 116 KB |
| 项目研究报告 | `docs/craic/2026-05-23/02_项目研究报告.docx` | 4.7 MB |
| 查新报告 | `docs/craic/2026-05-23/03_查新报告.docx` | 26 KB |

- 团队：**稷韧云图**(潘妙齐 / 熊鑫 / 常宇璇),指导:徐苗
- 作品:极端气候下基于多模态的粮食风险预警系统
- 查新日期:2026.5.22
- 常宇璇资料已在打印版完善
- 5/23 09:00 提交 caairobot.com → ✅ 已交,**Issue #12 可关**

### 🎯 2026-05-22 全天大事

| 工作 | 负责 | 状态 |
|---|---|---|
| CRAIC 三份材料 PDF 终版 + 5/23 提交 | 潘+熊 | ✅ |
| M01 风险时空地图 Vue 化 | 潘 | ✅ commit 578fbab |
| M04 韧性路径推荐 Vue 化(11 规则引擎) | 潘 | ✅ commit 8d894b1 |
| M02+M03 SHAP 看板 + 情景模拟 Vue 化 | 潘 | ✅ commit 1943381 |
| Security fix:Flask debug + host + CORS + DOMPurify | 潘 | ✅ commit b87e667 / 5915084 |
| SHAP v3 plot_shap_v3.py + 5 张 PNG (PR #21) | 熊鑫 | ✅ 等 merge |
| 协调中心 5 agent 并发 review | 协调中心 | ✅ PR #20 review + Issue #25 #26 |

**4 个 Vue 业务模块 5/22 一天全做完**(原计划 Phase 3.2/3.3/3.4/3.5 是 5/29-31 + 6/01-15 完成)→ **系统开发进度领先约 3 周**。

### 2026-05-21 路线 E 全部落地(XGB / LSTM / Att-LSTM 三模型 ready)

| 模型 | 10 种子 test R² | RMSE (kg/ha) | 申报书硬指标 |
|---|---|---|---|
| XGBoost | **0.9072 ± 0.0383** | 312.5 | ≥ 0.62 ✅ 远超 |
| LSTM | **0.8856 ± 0.0223** | 362.0 | ≥ 0.62 ✅ 远超 |
| **Attention-LSTM** | **0.8160 ± 0.0502** | 456.4 | ≥ 0.65 ✅ 通过 |
| y_butter 消融 | -0.1015 ± 0.2763 | — | (方法学消融) |

**后端 sanity check** `python -m backend.services.inference` — 三模型对河南 2022 真值 4615 kg/ha：
- XGB 4387.5（err −227.5）/ LSTM 4173.5（err −441.6）/ **Att-LSTM 4657.6（err +42.6） ← 最准**
- Att-LSTM attention softmax sum=1 ✅，单样本 top-3 = `SPEI(0.49) > Irr(0.29) > Flood_R(0.05)`（**与论文期望 `Irr > Flood > Sun` 高度一致**）

**关键叙事 v2 (PR #21 + 5/22 实测后)**:
- XGB SHAP Top-3 = `[NDVI, Prec, Temp]`(数据驱动,生物量主导)
- Att-LSTM Att Top-3 = `[Drou_A, SPEI, Temp]`(灾害响应,policy lever)
- **仅 Temp 1/3 重合**,**§7.5 叙事从"一致性"改"互补而非一致"**(见 Issue #24)
- 极端反差: `NDVI` XGB #1 → Att-LSTM #4 / `SPEI` XGB 倒数#1 → Att-LSTM #2 / `Drou_A` XGB #9 → Att-LSTM #1

→ Issue #6 关闭条件全部满足,**M2 评审硬指标全部提前达成**(距 11-30 还有 6 个月)。**PR #18 已合,Issue #6 已自动关闭(2026-05-22 01:02 UTC)。**

> ⚡ **路线 E 对 5/17 务实化路线的更新**:
> - 5/17 推断"R² 上限 0.53-0.56"指的是去趋势 Y 上的 XGB —— **未涵盖 Att-LSTM 在原始 y_kg_per_ha 上的表现**
> - 5/21 熊鑫实测 3 模型在 `yield_kg_per_ha` 上 R² 全部 ≥ 0.81,**5/17 务实化路线的"R² 不可达"推断在新口径下不成立**
> - 务实化路线的"70% 精力投 Att-LSTM + SHAP × Attention 一致性 + 韧性路径"战略叙事**部分成立** — Att-LSTM 仍是主推,但"一致性"叙事被 PR #21 实测反证 → 改"互补"

---

## 🚨 2026-05-17 关键路线决策

**实证发现：R² ≥ 0.62 在去趋势 Y 上数学不可达。**

- 论文 R²=0.6619 是模型把"年份"当因子，趋势伪相关
- 任何模型在去趋势 Y 上 R² ≈ 0
- 原始 Y 上模型上限 0.53–0.56（熊鑫实测 XGB 0.5647）

**PI 拍板务实路线：**
- 30% 精力做 R²（原始 Y 冲 0.6+，承认是上限）
- 70% 精力投 Attention-LSTM + SHAP × Attention 一致性 + 韧性路径系统
- 报告时坦诚说"工程实现完成，残差不可预测"

**申报书重写动作清单 → [Issue #10](../../issues/10)**

---

## 🗓️ 时间坐标

```
今天 2026-05-22 晚,距 M1 评审(2026-07-31) 70 天,距系统 v0.1 上线(6/25) 34 天

近期硬 ddl:
  ✅ 5-22              CRAIC 三份材料最终递交 + 4 个 Vue 业务模块全部完成
  ✅ 5-23 09:00        CRAIC 提交 caairobot.com (已交,Issue #12 可关)
  🟡 5-24              GCP e2-medium 实例开机 + 域名 grainrisk.app 注册 (Issue #17)
  🟡 5-26              Phase 1 GCP 验收: gunicorn + Vue 联调
  🟡 5-27-28           Phase 4 SQLite 灌 paper_panel_v3 + /api/provinces?year (Issue #17)
  🟡 5-31              1.1 文献综述 v1.1 finalize (潘)
  🟡 5-31              申报书 §2.3/§3/§5 重写 (Issue #10) — R² 用 0.81+ 实测
  🟡 6-03              Phase 2 提前完成 — api/predict.py 接 inference.py 真模型 (从 6-15 提前)
  🟡 6-25              系统 v0.1 GCP 公网可访问 — 含 Issue #26 production readiness
  🟡 7-25              1.8 Z-score 标准化 + 数据划分 (熊鑫)
  🚨 7-31              M1 评审 — **Issue #25 a11y WCAG 2.2 AA 必修(~半天)**
  ✅ 11-30             M2 评审: R² 3 项硬指标已提前 6 个月达成
```

---

## 🏆 CRAIC 比赛 5/23 节点 ✅ 已交付

第二十八届中国机器人及人工智能创新大赛 - 人工智能创新比赛｜指导教师:徐苗(报名表显示)｜团队:**稷韧云图**(潘妙齐 + 熊鑫 + 常宇璇,3 人)

> 📝 团队最终为 3 人(潘 + 熊 + 常宇璇),石灵子在 docs/03 大创申报 5 人队但**不在 CRAIC 队伍**。常宇璇资料已在打印版完善。

**三份材料最终递交版** — 入仓 `docs/craic/2026-05-23/`:

| # | 文件 | 入仓路径 | 大小 |
|---|---|---|---|
| 1 | 报名表 | `01_报名表.docx` | 116 KB |
| 2 | 项目研究报告 | `02_项目研究报告.docx` | 4.7 MB |
| 3 | 查新报告 | `03_查新报告.docx` | 26 KB |

5/23 09:00 提交 caairobot.com ✅ 完成。**Issue #12 可关。**

---

## 📊 关键指标

| 项 | 数值 |
|---|---|
| 合并 PR | **12 个**(#2-#8 + #11/#13/#14 + #16 / #18 / #19) |
| **待合并 PR** | **2 个**(#20 M01-M04 + security / #21 SHAP plot_shap_v3 + 5 PNG) |
| 公开 Issues | **6**(#9 石灵子 / #10 路线决策 / #17 系统 Phase / #23 数据红旗 / **#25 a11y** / **#26 GCP readiness**)— #6 已关 ✅,#12 #22 #24 等 user 关 |
| Backend 测试 | **16 个端点测试**全过 |
| Backend 完成度 | 85%(待补 Phase 4 SQLite + Phase 2 真模型接入 + Phase 5 nginx) |
| Frontend 完成度 | **静态原型 + 4 view Vue 化 全部 100% ✅**(M01 风险地图 / M02 SHAP / M03 情景 / M04 韧性路径) |
| 模型 artifacts | XGB / LSTM / Att-LSTM 全部入库 + model_card + seeds_results + 11 维 sanity PASS |
| 模型 R² (10 种子均值) | XGB **0.9072** / LSTM **0.8856** / Att-LSTM **0.8160** ✅ |
| SHAP 重生成 (PR #21 等 merge) | 5 张 PNG 全英文版 + `shap_v3_summary.json` 在 `docs/figures/` |
| 数据资产 | paper_panel_v3 (403×27) + MODIS 11 维 + GIS 三级 + CLCD |
| 文档总数 | **17** 篇(原 16 + CHANGELOG 5/22 末) + CRAIC 3 docx |
| **代码质量** | 5 agent 评审 PR #20 → 8 HIGH 已派 + WCAG 2.2 AA 不过(Issue #25) + GCP readiness 4 HIGH(Issue #26) |

---

## 👥 全员状态（2026-05-22 凌晨）

### 🟢 潘妙齐 · 项目负责人 / 后端 / 前端 Vue 集成 / 部署 / 论文

- 个人 dev session = `cwd=/home/darcy/DC/pmq`,协调中心 = `cwd=/home/darcy/DC`
- ✅ docs/09 文献综述 v1.0 / docs/10 v2.0 GCP 路线 / docs/12 系统开发执行计划 / Vue 3 工程骨架
- ✅ **5/22 全天硬战果** ([CRAIC + M01 + M04 + M02+M03 + 2 security] 一日全做):
  - CRAIC 三份材料 PDF 终版 + 5/23 提交 ✅
  - M01 风险时空地图 Vue 化 (ECharts 中国地图 + 时间滑块 + Top10 + 明细卡)
  - M04 韧性路径推荐 Vue 化 (11 规则引擎 + 三阶段时间线 + stagger 动画)
  - M02 SHAP 看板 + M03 情景模拟 Vue 化
  - Flask debug + host + CORS 三处 security fix + DOMPurify 包装 v-html
  - 待 merge:**PR #20** (5 commits)
- 🟡 接下来 5/22 晚-5/24 早:**PR #20 review HIGH 8 项修** + PR #21 squash merge(熊鑫)
- 🟡 5/24+ Phase 0 GCP 开机 → Phase 4 SQLite (5/27-28) → 真模型集成(可提前到 6/03)
- 🟡 5/31 申报书重写 (Issue #10) + 7/31 评审 a11y 修(Issue #25)
- 🟡 6/25 v0.1 上线前 production readiness (Issue #26)

### 🟢 石灵子 · 数据工程（M1 实质完成 + 文档交付）

- ✅ 1.2 论文数据接入（孤儿接手）→ `paper_panel_v2.parquet` 403×21
- ✅ 1.3 MODIS NDVI/LST 月度聚合 → 4836 行
- ✅ 1.4 GIS 三级（天地图 GS(2024)0650）+ CLCD 耕地
- ✅ 1.6 **Y 去趋势 Butterworth** → `paper_panel_v3.parquet` 403×27（y_linear mean=0, slope=0）
- ✅ 1.7 时空对齐 100% 匹配率
- ✅ **D5** docs/11 数据集说明 v1（PR #11 已合，341 行 / 11 章 / M1 评审硬交付物）
- ✅ **D7** MODIS / POWER 月度可行性评估（Issue #9 评论）
- 🟡 下一轮：v4 待办（SPEI proxy → 真实灾害 / 耕地像元加权 / 多年 CLCD），非阻塞，按节奏

### 🟢 熊鑫 · 算法(路线 E + SHAP v3 全部完成 ✅)

- ✅ XGB / LSTM / Att-LSTM 三模型 R² 全部超硬指标(0.9072 / 0.8856 / 0.8160)
- ✅ `backend/services/inference.py` 三模型集成 + sanity check 全 PASS(PR #18)
- ✅ Issue #6 已关闭(2026-05-22 01:02 UTC)
- ✅ **5/22 SHAP v3 重生成** (PR #21,等 merge):
  - `scripts/plot_shap_v3.py` 修两 bug (列名映射 + Keras compile=False) + 字体英文化
  - 5 张 PNG (`docs/figures/`) + `shap_v3_summary.json`
  - **关键发现**: 双模型 Top-3 仅 1/3 重合 → §7.5 叙事从"一致性"改"互补"
  - Issue #24 已开 — §7 章节级重写方案完整,CRAIC 提交版已落
- 🟡 下一轮 (M2 节点前任选): 韧性路径 PoC 联调
- 🟡 长期: 加 GitHub collaborator + gh auth 免代发 (Issue 标注 P2)

### 🟢 周煜楠 · 前端(UI 阶段 100% 交付,工作 freeze)

- ✅ **2026-05-21 一次性交付 7 份 HTML** 在 `frontend/prototypes/`
- ✅ 设计 tokens.css 已被 Vue 化吸收,4 view 视觉严格按 prototypes
- 🛑 周个人 freeze;Vue 化 + 后端 + 联调 + 部署全归潘
- 📝 不在 CRAIC 三人队;CRAIC 团队为潘 + 熊 + 常宇璇

---

## 📦 已 merge PR (近 5 天)

| PR | 标题 | 何时 |
|---|---|---|
| **#7** | feat(data) 石灵子 data pipeline + Y 去趋势 | 2026-05-17 |
| **#8** | docs(status) 加入项目实时状态 dashboard | 2026-05-17 |
| **#11** | docs(11) 数据集说明 v1 — M1 评审硬交付物 | 2026-05-19 |
| **#13** | docs(craic) 5/23 比赛三份材料追踪 + 协调中心风险清单 | 2026-05-19 |
| **#14** | docs(handoff) 石灵子 2026-05-17 session 收尾 | 2026-05-19 |
| **#16** | docs(coord) 协调二周目 — 系统开发启动 + GCP 路线 + 周 UI 入仓 + Vue 骨架 | 2026-05-22 |
| **#18** | feat 路线 E 收尾 — Att-LSTM R²=0.8160 + 三模型 inference (Closes #6) | 2026-05-22 |
| **#19** | docs(status) 2026-05-22 凌晨同步 | 2026-05-22 |

## 🟡 待合并 PR

| PR | 标题 | 状态 |
|---|---|---|
| **#20** | feat(M01-M04): 4 view Vue 化 + 2 security 修 (潘 5/22 全天) | review 完成,8 HIGH 列在评论,可 squash & merge |
| **#21** | feat(scripts): plot_shap_v3.py + 5 PNG (Closes #22) (熊鑫) | 5 commits ready,可 squash & merge |

---

## ⚠️ 当前 P0 / P1 风险

### ✅ CRAIC 5/23 已交,Issue #12 可关

### 🟡 P1: PR #20 + #21 等 merge

- PR #20 5 agent review 完成,**0 仓库级 CRITICAL**,8 HIGH 应 merge 后 follow-up 修
- PR #21 SHAP v3 5 PNG 已就位,等 squash & merge(message 加 `Closes #22`)
- 推荐顺序: #21 先 merge(无依赖) → #20 merge(下面所有工作的基础)

### 🟡 P1: 系统开发 5/24 启动 — Phase 0 GCP 开机

- Phase 0 (5/23-24, 0.5 day) → Phase 1 GCP 验收 (5/26) → Phase 4 SQLite (5/27-28) → Phase 5 部署 (6/25)
- Phase 3.2/3.3/3.4/3.5 (M01-M04 Vue 化) **5/22 全部完成** → 节奏领先 3 周
- Phase 2 模型集成可**提前到 6/03**(PR #18 inference.py 已就位)
- Issue #17 评论加了详细 Phase 0+4 runbook (planner agent 完整输出)

### 🟡 P1: Issue #25 a11y WCAG 2.2 AA — 7/31 评审前必修

5 个 CRITICAL + 10+ HIGH:全部 ECharts canvas 缺 text alt / 5 滑块缺 aria-label / 健康状态色单一信息 / `outline:none` 无替换 / Top10 行无键盘。~半天工作量。

### 🟡 P1: Issue #26 GCP production readiness — 6/25 上线前必修

backend/app.py:4 docstring 部署陷阱 + .env.example wildcard + 无 rate limit + 无 HTTP 安全头(CSP/HSTS/XFO)。

### 🟡 P1: 申报书重写

Issue #10 列出约 1-2 天工作量。R² 数字现可用 0.81+ 实测。可 5/31 前完成。

### 🟢 P2: M1 评审材料启动 + 熊鑫 collaborator + main protected branch

---

## 📥 待处理操作

| 优先 | 动作 | 谁做 | 何时 |
|---|---|---|---|
| 🟡 P1 | PR #21 squash & merge (message 加 `Closes #22`) | 潘 | 5/22 晚 / 5/23 早 |
| 🟡 P1 | PR #20 squash & merge | 潘 | 同上 |
| 🟡 P1 | PR #20 HIGH 8 项修 (fix/pr20-followup 分支) | 潘 | merge 后 ~3h |
| 🟡 P1 | CRAIC §7 重写在仓内 docs/ 同步 (Issue #24) | 潘 | 任意 (CRAIC 提交版已交) |
| 🟡 P1 | GCP 项目开通 + e2-medium + 域名 grainrisk.app | 潘 (Issue #17) | 5/24 |
| 🟡 P1 | Phase 1 GCP 验收 | 潘 (Issue #17) | 5/26 |
| 🟡 P1 | Phase 4 SQLite + /api/provinces?year + history | 潘 (Issue #17) | 5/27-28 |
| 🟡 P1 | 申报书 §2.3/§3/§5 重写 (R² 用 0.81+) | 潘 (Issue #10) | 5/31 前 |
| 🟡 P1 | Phase 2 集成 — api/predict.py 接 inference.py | 潘 (Issue #17) | 6/03 (从 6/15 提前) |
| 🟡 P1 | Issue #25 a11y WCAG 2.2 AA 修复 (~半天) | 潘 | 7/31 前 |
| 🟡 P1 | Issue #26 GCP production readiness (rate limit + 安全头 + docstring + .env.example) | 潘 | 6/25 前 |
| 🟢 P2 | Issue #23 数据红旗 sun/prec/flood_a 单位核对 | 石灵子 | CRAIC 后 |
| 🟢 P2 | 设 main 为 Protected branch | 潘 | 5 min |
| 🟢 P2 | M1 评审材料启动 | 全员 | 6 月起 |
| 🟢 P2 | 熊鑫加 collaborator + gh auth login | user | 任意 |
| ✅ done | CRAIC 三份材料递交 + 4 view Vue 化 + SHAP v3 重生成 + 5 agent 评审 | 全员 | 5/22 |

---

## 🔄 协调中心工作流

```
队员 Claude × N → 自总结（schema：✅完成 / 🟡进行中 / 🔴卡点 / ❓问题）
                ↓
            用户中转（贴给本会话）
                ↓
            协调中心整合
                ↓
   ┌─ 更新 STATUS.md
   ├─ Issue / PR 评论分发任务
   ├─ 开新 Issue 给新任务
   └─ push 到 GitHub
                ↓
            队员下次 turn 自己 git pull + gh issue view 拿活
```

### 协调中心已永久授权（user `~/.claude/settings.json`）
- `Bash(gh issue comment:*)`
- `Bash(gh issue create:*)`
- `Bash(gh pr comment:*)`
- `Bash(gh pr review:*)`

---

## 🔧 更新机制

- 每次重要进展（PR merge / 任务完成 / 新 blocker / 任务转手 / 决策）都该 update 本文
- 任何 session 都可以 PR 改本文，commit message 加 `docs(status):` 前缀
- 本文不是"周报"——是**实时大盘**，stale 1 天以上视为过期，需更新
- 跨 session 同步走 git + 本文 + GitHub Issues / PR 评论，**不走 memory**
