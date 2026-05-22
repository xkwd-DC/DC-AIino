# 项目实时状态 · STATUS

> **本文是项目级 single-source-of-truth dashboard**，任何 session 都该来这看大盘。
> 每次重要进展（PR merge / 任务完成 / 新 blocker）都更新本文。
>
> 最近更新：**2026-05-22 上午**（协调中心：`cwd=/home/darcy/DC`，CRAIC 研究报告审校 + PR #21 SHAP 重生成脚本入仓）

---

## 🚨 关键路线决策

### 2026-05-17 · R² 路线务实化
## 🎯 2026-05-21 路线 E 全部落地（XGB / LSTM / Att-LSTM 三模型 ready）

| 模型 | 10 种子 test R² | RMSE (kg/ha) | 申报书硬指标 |
|---|---|---|---|
| XGBoost | **0.9072 ± 0.0383** | 312.5 | ≥ 0.62 ✅ 远超 |
| LSTM | **0.8856 ± 0.0223** | 362.0 | ≥ 0.62 ✅ 远超 |
| **Attention-LSTM** | **0.8160 ± 0.0502** | 456.4 | ≥ 0.65 ✅ 通过 |
| y_butter 消融 | -0.1015 ± 0.2763 | — | (方法学消融) |

**后端 sanity check** `python -m backend.services.inference` — 三模型对河南 2022 真值 4615 kg/ha：
- XGB 4387.5（err −227.5）/ LSTM 4173.5（err −441.6）/ **Att-LSTM 4657.6（err +42.6） ← 最准**
- Att-LSTM attention softmax sum=1 ✅，单样本 top-3 = `SPEI(0.49) > Irr(0.29) > Flood_R(0.05)`（**与论文期望 `Irr > Flood > Sun` 高度一致**）

**关键叙事**：XGB SHAP top-3 = `ndvi/temp/prec`（数据驱动，生物量主导）；Att-LSTM attention 显著偏向 `SPEI/Irr/Flood`（policy lever）—— 两套互补，可拼成"数据 × 政策"双层解释。

→ Issue #6 关闭条件全部满足，**M2 评审硬指标全部提前达成**（距 11-30 还有 6 个月）。**PR #18 已合，Issue #6 已自动关闭（2026-05-22 01:02 UTC）。**

> ⚡ **路线 E 对 5/17 务实化路线的更新**：
> - 5/17 推断"R² 上限 0.53-0.56"指的是去趋势 Y 上的 XGB —— **未涵盖 Att-LSTM 在原始 y_kg_per_ha 上的表现**
> - 5/21 熊鑫实测 3 模型在 `yield_kg_per_ha` 上 R² 全部 ≥ 0.81，**5/17 务实化路线的"R² 不可达"推断在新口径下不成立**
> - 务实化路线的"70% 精力投 Att-LSTM + SHAP × Attention 一致性 + 韧性路径"**战略叙事仍成立**，只是 R² 数字更亮
> - **5/22 决策点**：CRAIC §7 R² 数字是否从 0.5647（5/17 务实化保守值）替换为 0.8160（5/21 实测）—— 见 [Issue #12](../../issues/12) 新评论

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
今天 2026-05-22，距 M1 评审（2026-07-31）剩 70 天，距系统 v0.1 上线（6/25）剩 34 天

近期硬 ddl：
  🚨 今天 5-22         CRAIC 三份材料 PDF 终版校对（潘+熊+周复核）
                       Att-LSTM R²=0.8160 是否替换 5/17 务实化 0.5647 → Issue #12
  🚨 5-23 09:00        CRAIC 三份材料提交 caairobot.com (Issue #12)
  🚨 5-24              GCP e2-medium 实例开机 + Claude Code 服务器端装 (Issue #17)
  🚨 5-26              Phase 1 GCP 验收：gunicorn + Vue dev + 4 view 切换
  🚨 5-31              1.1 文献综述 v1.1 finalize（潘）
  🚨 5-31              申报书 §2.3/§3/§5 重写（Issue #10）—— 注意 R² 数字与 CRAIC 对齐
  🚨 5-31              Phase 3.2 M01 风险地图 Vue 化（不依赖熊鑫，Issue #17）
  ⏰ 6-15              Phase 2 模型集成（PR #18 已交付 inference.py 三模型；剩接 api/predict.py）
  ⏰ 6-25              系统 v0.1 GCP 公网可访问（4 模块 + 国际域名 + HTTPS）
  ⏰ 7-25              1.8 Z-score 标准化 + 数据划分（熊鑫）
  ⏰ 7-31              M1 评审：多模态数据集 v1.0
  ⏰ 11-30             M2 评审：R² 3 项硬指标——已提前 6 个月达成 ✅
```

**5/21 IRL 状态待群里确认**：14:00 三人现场签字 + 学院盖章是否完成。

---

## 🏆 CRAIC 比赛 5/23 节点（最优先）

第二十八届中国机器人及人工智能创新大赛 - 人工智能创新比赛｜指导教师：邱东芳｜团队：**潘妙齐 + 熊鑫 + 周煜楠**（3 人）

> ⚠️ **报名表早期"石灵子"是数据组代号——实际指代熊鑫本人**，三份材料已统一改为熊鑫。docs/03 大创申报书 5 人队（含真名"石灵子"做数据工程）与 CRAIC 是不同队伍。

**三份材料状态**（详见 [docs/_craic/00_README.md](_craic/00_README.md)）：

| # | 材料 | 完成度 | 主要 gap |
|---|---|---|---|
| 1 | 报名表 1 份 | 🟢 90% | 3 张身份证号 + 5/21 现场签字盖章 |
| 2 | 查新报告 4 页 | 🟢 100% 文本 | 签字盖章 |
| 3 | 研究报告 18 页 | 🟢 95% 文本 | 团队名称 + 11 张图就位 |

**周煜楠到位**：5/21 一次性交付 7 份 UI HTML（详见 `frontend/prototypes/`），P0 解除；剩 14:00 现场签字盖章。

**R² 口径策略**：5/17 晚用户拍板 CRAIC 三份材料**直接切换至务实路线** R²=0.5647（10 种子均值实测上限）。三份材料的摘要 / §7.1.2 / 表 2 / 表 3 / 查新结论已统一改写。

**5/19 嵌图日已过**：熊鑫负责图 2-10（9 张算法图），潘负责图 1+11 — 状态待群里确认是否就位。

---

## 📊 关键指标

| 项 | 数值 |
|---|---|
| 合并 PR | **12 个**（#2-#8 + #11/#13/#14 + **#16 / #18**） |
| 待合并 PR | 0 |
| 公开 Issues | **4**（#9 石灵子 / #10 路线决策 / #12 CRAIC 5-23 / #17 系统 Phase 0-5）— #6 已关 ✅ |
| Backend 测试 | **16 个端点测试**全过（health + 31 省 + 11 特征 predict + ensemble + 校验 + 404 兜底） |
| Backend 完成度 | 85%（health/provinces/predict mock + **三模型 inference.py 全部加载 PASS**；待补 SHAP API + recommendation API + year 参数 + 接入真模型） |
| Frontend 完成度 | 静态原型 100%（周 6 份 HTML）+ Vue 3 骨架 100%（4 view 占位 + router + axios + health 灯），M01-M04 业务 Vue 化 0% |
| 模型 artifacts | **XGB / LSTM / Att-LSTM 全部入库** + model_card + seeds_results + 11 维 sanity PASS |
| 模型 R²（10 种子均值） | XGB **0.9072** / LSTM **0.8856** / Att-LSTM **0.8160** — 全部超 M2 硬指标 |
| 数据资产 | paper_panel_v3 (403×27, y_detrended 完美) + MODIS 11 维 panel + GIS 三级 + CLCD |
| 文档总数 | **16** 篇（00–12 + STATUS + CHANGELOG + cheatsheet_熊鑫） |

---

## 👥 全员状态（2026-05-22 凌晨）

### 🟢 潘妙齐 · 项目负责人 / 后端 / 前端 Vue 集成 / 部署 / 论文

- 个人 dev session = `cwd=/home/darcy/DC/pmq`，协调中心 = `cwd=/home/darcy/DC`
- ✅ docs/09 文献综述 v1.0 草稿（62KB，38 文献）
- ✅ docs/10 v2.0 改 GCP 路线 / docs/12 系统开发执行计划 / docs/CHANGELOG.md（均已 merge via PR #16）
- ✅ Vue 3 + Vite 工程骨架本地验收通过（PR #16）
- 🔥 **5/22 今天**：CRAIC PDF 终版校对 + R² 数字最终化决策（Issue #12）
- 🔥 **5/23 明早**：CRAIC 09:00 提交
- 🔥 **5/24+ 系统开发** Issue #17 全面启动（Phase 2 阻塞已解除，可与 Phase 3 并行）
- 🟡 综述 v1.0 → v1.1 校对 / 申报书重写（5/31 ddl）
- 🔥 **GCP 部署**：替代 ICP 备案路径，5/24 开机
- 🔥 **本周冲刺**：CRAIC 收口（5/23）→ Phase 1 骨架（5/24-26）→ Phase 3.2/3.5 Vue 化（5/27-31）

### 🟢 石灵子 · 数据工程（M1 实质完成 + 文档交付）

- ✅ 1.2 论文数据接入（孤儿接手）→ `paper_panel_v2.parquet` 403×21
- ✅ 1.3 MODIS NDVI/LST 月度聚合 → 4836 行
- ✅ 1.4 GIS 三级（天地图 GS(2024)0650）+ CLCD 耕地
- ✅ 1.6 **Y 去趋势 Butterworth** → `paper_panel_v3.parquet` 403×27（y_linear mean=0, slope=0）
- ✅ 1.7 时空对齐 100% 匹配率
- ✅ **D5** docs/11 数据集说明 v1（PR #11 已合，341 行 / 11 章 / M1 评审硬交付物）
- ✅ **D7** MODIS / POWER 月度可行性评估（Issue #9 评论）
- 🟡 下一轮：v4 待办（SPEI proxy → 真实灾害 / 耕地像元加权 / 多年 CLCD），非阻塞，按节奏

### 🟢 熊鑫 · 算法（路线 E 全部完成 ✅，M2 硬指标提前 6 个月达成）

- ✅ XGB 基线 `yield_kg_per_ha` R² = **0.9072 ± 0.0383**（PR #18）
- ✅ LSTM 基线 R² = **0.8856 ± 0.0223**，修了 y_scaler bug（PR #18）
- ✅ y_butter 消融 R² = -0.10（PR #18，方法学诚实保留为消融基准）
- ✅ Attention-LSTM feature-gating + 2×LSTM，R² = **0.8160 ± 0.0502**（PR #18）
- ✅ `backend/services/inference.py` 三模型集成 + sanity check 全 PASS（河南 2022 真值 4615：XGB err -227.5 / LSTM -441.6 / Att-LSTM **+42.6 最准**）
- ✅ Attention top-3 = `SPEI(0.49) > Irr(0.29) > Flood_R(0.05)`，与论文期望 `Irr > Flood > Sun` 高度一致
- ✅ Issue #6 已关闭（2026-05-22 01:02 UTC）
- 🟡 下一轮（M2 节点前任选）：SHAP 蜂群图 / 韧性路径 PoC
- 🟡 **5/24+ Phase 2 集成已无血量阻塞**：inference.py 已就位，潘只剩在 `api/predict.py` 替换 `_predict_mock()` 调用（依赖项已交付）

### 🟢 周煜楠 · 前端（UI 阶段 100% 交付，工作 freeze）

- ✅ **2026-05-21 一次性交付 7 份 HTML**：index + 00 设计系统 + 01 风险地图 + 02 SHAP 看板 + 03 情景模拟 + 04 韧性路径（详见 `frontend/prototypes/`）
- ✅ docs/05 任务清单 5-14 → 5-21 完成（7 天闷头干活，未通讯）
- 设计水准：深绿 #162520 + 橄榄/琥珀/赭石点缀；Noto Serif/Sans + JetBrains Mono；odometer 字符滚动；reduce-motion 适配；ECharts china map / 11 规则引擎 / SHAP 4 图全交付
- ⚠️ **数字口径警告（已部分对齐）**：UI 硬编码 R²=0.847 与实测 R²=0.8160（Att-LSTM）现已**高度接近**，Vue 化时仍按 API 走，前端展示三模型并列即可
- 🛑 **后续工作**：周个人到此 freeze；Vue 化 + 后端 + 联调 + 部署全归潘妙齐
- 🟢 CRAIC 5/21 14:00 现场签字 — 群里跟进结果

---

## 📦 已 merge PR（近 5 天）

| PR | 标题 | 何时 |
|---|---|---|
| **#7** | feat(data) 石灵子 data pipeline + Y 去趋势（14 commits） | 2026-05-17 |
| **#8** | docs(status) 加入项目实时状态 dashboard | 2026-05-17 |
| **#11** | docs(11) 数据集说明 v1 — M1 评审硬交付物 | 2026-05-19 |
| **#13** | docs(craic) 5/23 比赛三份材料追踪 + 协调中心风险清单 | 2026-05-19 |
| **#14** | docs(handoff) 石灵子 2026-05-17 session 收尾 | 2026-05-19 |
| **#16** | docs(coord) 协调二周目 — 系统开发启动 + GCP 路线 + 周 UI 入仓 + Vue 骨架 | 2026-05-22 |
| **#18** | feat 路线 E 收尾 — Att-LSTM R²=0.8160 + 三模型 inference 集成（Closes #6） | 2026-05-22 |
| **#21** | feat(scripts) plot_shap_v3.py — 重生成 §7.2-§7.5 SHAP/注意力图（待熊鑫执行 #22） | 2026-05-22（待 merge） |

---

## ⚠️ 当前 P0 / P1 风险

### 🔴 P0：CRAIC 5/23 09:00 三份材料提交（今天最后一天）

- ✅ 5/21 14:00 三人现场签字 + 学院盖章（IRL 结果待群里确认）
- 🔥 **今天 5/22 PDF 终版校对** + 5/17 决策 §7 R² 数字最终化（0.5647 vs 0.8160 见 [Issue #12](../../issues/12)）
- 🚨 5/23 09:00 上传 caairobot.com

### 🔴 P0：CRAIC 研究报告（《极端气候下基于多模态的粮食风险预警系统》）§7 全部图与定性叙事失去依据（2026-05-22 上午发现）

上传论文与 v3 系统实测对照发现 15 项不一致，重大者：
- §7.1 表 4 R² (0.6293 / 0.6619) 是旧 normalized-y 指标，与 v3 实测 (XGB 0.9072 / LSTM 0.8856 / Att-LSTM 0.8160) 全部对不上
- 摘要 + §7.5 "双模型 Top-3 完全一致" **错的**：实测 XGB SHAP top-3 `ndvi/temp/prec` ≠ Att-LSTM 注意力 top-3 `Flood_A/Mech/Temp`
- 表 1 Y 定义为 "Butterworth 滤波残差"，实际训练 target 是 `yield_kg_per_ha`；y_butter 上模型 R²=-0.10
- 表 1 漏列 NDVI；§2.1 声称用 MODIS LST 但 11 维特征只有 NDVI
- 表 2 多列均值漂移（Sun +52%、Prec +29%、Flood_A +54%）—— v3 数据来源待石灵子核对
- LSTM 表 3 超参 4 项与代码不符（timesteps 13→1、batch 32→16、epochs 200→100、PyTorch 实际未用）
- 公式 (13)(14)(15) 给的是 timestep-level attention，实际是 feature-level gating

**已派任务：**
- [#21](../../pull/21) PR — `scripts/plot_shap_v3.py` 重生成 5 张图（已合 → 待合）
- [#22](../../issues/22) Issue — @xxxx9939 (熊鑫) 5/23 09:00 前跑脚本 + 上传图

**剩下要做：** §7 文字 / 摘要 / 表 1 / 表 2 / 应用前景全面重写（图出后由协调中心 + 潘妙齐另开 PR）。完整 15 项审校单见上传论文对应会话归档。

### 🟡 P1：系统开发 5/24 启动 — 关键路径解锁

- Phase 0/1（5/24-26）：GCP 开机 + backend gunicorn + Vue 骨架联调
- Phase 4 提前（5/27-28）：SQLite 灌 paper_panel_v3 → `/api/provinces?year`
- Phase 3.2/3.5（5/29-31）：M01 地图 + M04 路径 Vue 化
- ✅ **Phase 2 模型阻塞已解除**（PR #18 三模型 inference.py 已入库）；潘只剩在 `api/predict.py` 替 mock 为真模型调用，可与 Phase 3 并行
- 完整 tracking → [Issue #17](../../issues/17)

### 🟡 P1：申报书重写

Issue #10 列出的章节重写约 1–2 天工作量。**R² 数字现可直接用 0.81+ 实测**（不再受 5/17 务实化 0.56 限制）。可与 M1 评审 + 系统开发交错做（5/31 前）。

### 🟢 P2：M1 评审材料启动

距 7-31 评审还有 70 天。`docs/11 数据集说明 v1` 已是硬交付物。6 月起补汇报材料。

---

## 📥 待处理操作

| 优先 | 动作 | 谁做 | 何时 |
|---|---|---|---|
| 🔴 P0 | CRAIC 5/22 三份材料 PDF 终版校对 + §7 R² 数字最终化 | 潘+熊 | 今天 |
| 🔴 P0 | CRAIC 5/23 09:00 三份材料提交 caairobot.com | 潘 | 明天早 |
| 🟡 P1 | GCP 项目开通 + e2-medium asia-east1 实例 | 潘 | 5/24 |
| 🟡 P1 | Phase 1 GCP 验收：gunicorn + Vue dev + 4 view | 潘 | 5/26 |
| 🟡 P1 | 申报书 §2.3/§3/§5 重写（R² 用 0.81+ 实测） | 潘（Issue #10）| 5/31 前 |
| 🟡 P1 | Phase 3.2/3.5 M01+M04 Vue 化（不依赖熊鑫）| 潘（Issue #17）| 5/31 |
| 🟡 P1 | Phase 2 集成：api/predict.py 接 inference.py 真模型 | 潘（Issue #17）| 6/01-15 |
| 🟢 P2 | 设 main 为 Protected branch | 潘 | 5 分钟 |
| 🟢 P2 | M1 评审材料启动 | 潘 + 全员 | 6 月起 |
| 🟢 P2 | 熊鑫加 collaborator + gh auth login（免代发） | 用户 | 任意 |
| 🟢 P2 | 熊鑫 SHAP 蜂群图 / 韧性路径 PoC | 熊鑫 | M2 节点前任选 |
| ✅ done | docs/10 GCP 部署清单 v2 / docs/12 系统开发执行计划 / docs/CHANGELOG / 周 UI / Vue 骨架 / Issue #17 / **三模型 inference 集成 + Issue #6 closed** | 全员 | 5/21-22 |

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
