# 项目实时状态 · STATUS

> **本文是项目级 single-source-of-truth dashboard**，任何 session 都该来这看大盘。
> 每次重要进展（PR merge / 任务完成 / 新 blocker）都更新本文。
>
> 最近更新：**2026-05-17**

---

## 🗓️ 时间坐标

```
今天 2026-05-17，距 M1 评审（2026-07-31）剩 75 天

近期硬 ddl：
  ⏰ 5-23   1.2 论文面板入仓最终版（石灵子）
  ⏰ 5-23   1.6 Y 去趋势（Butterworth）— 任务孤儿，待分配
  ⏰ 5-31   1.1 文献综述 finalize（潘妙齐）
  ⏰ 5-31   3.11 域名注册启动（潘妙齐）
  ⏰ 7-25   1.8 Z-score 标准化 + 数据划分（熊鑫）
  ⏰ 7-31   M1 评审：多模态数据集 v1.0
```

---

## 📊 关键指标

| 项 | 数值 |
|---|---|
| 合并 PR | 5 个（#2/#3/#4/#5/#6） |
| 待合并 PR | **1**（#7 · 石灵子 data pipeline） |
| 公开 Issues | 1（#6 · 熊鑫 算法训练）|
| Backend 测试 | 16 个，覆盖率 98% |
| CI 通过率 | 100% |
| 数据资产 | paper_panel_v2 (403×21) + MODIS 11 维 panel + GIS 三级 + CLCD |
| 文档总数 | 11 篇（00–10 + STATUS）|

---

## 👥 全员状态（2026-05-17）

### 🟢 潘妙齐 · 项目负责人 / 后端 / 论文

| 任务 | 状态 | 凭据 |
|---|---|---|
| 后端骨架 + API contract | ✅ DONE | PR #2–#5 全合并 |
| CI 通道 | ✅ DONE | `.github/workflows/ci.yml` |
| 1.1 文献综述 v1.0 草稿 | 🟡 进行中（5/31 ddl） | `docs/09_文献综述_潘妙齐.md`（62KB，38 文献） |
| 3.11 域名 + ICP 备案 | 🟡 进行中（5/31 启动） | `docs/10_域名备案与部署清单_潘妙齐.md` |
| Session 位置 | 🟢 `/home/darcy/DC/pmq`（与石灵子物理隔离） |

### 🟢 石灵子 · 数据工程

| 任务 | 状态 | 凭据 |
|---|---|---|
| 1.2 论文已有数据接入（孤儿接手）| ✅ DONE | `paper_panel_v2.parquet` 403×21 |
| 1.3 MODIS NDVI/LST 下载 + 聚合 | ✅ DONE | 13 年完整，4836 行月度 panel |
| 1.4 GIS 行政区划 + 耕地 | ✅ DONE | 天地图 GS(2024)0650 三级 + CLCD |
| 1.7 时空对齐 | ✅ DONE | 100% 匹配率 |
| 数据质量修复 | ✅ DONE | v2 修了 prec/sun 省会单站 bug |
| PR #7 review/merge | 🔴 等潘 review | 11 commits / +4784 行 / CI ✅ |
| 8 月后角色 | 🟡 待定 | 候选：1.6 接手 / 3.2 数据库 / 4.1 图表 |

### 🟡 熊鑫 · 算法

| 任务 | 状态 | 凭据 |
|---|---|---|
| Issue #6 跟踪 | 🟡 OPEN，0 评论 | 注：本人已开工，只是没在 issue 留言 |
| LSTM 训练脚手架 | ✅ 本地完成（未 commit） | `train_lstm_baseline.py` |
| LSTM 真实基线（2 组）| ✅ 本地完成 | TIMESTEPS=5 → R²=-0.45±0.57；TIMESTEPS=1 → R²=0.16±0.08 |
| **发现 P0 blocker** | 🔴 | Wang 原始 Y 未去趋势 → 任何模型 R² 上限 ~0.5 |
| 5 个交付物 | ✅ 本地完成 | `backend/models/lstm_*` 已就位（gitignored） |
| 对齐消息草稿 | 🟡 待潘决策（A/B/C/D 4 选项） | 4 条 blocker + 5 应对方案 |

### 🔴 周煜楠 · 前端

| 任务 | 状态 | 凭据 |
|---|---|---|
| 前端 UI 设计稿（5 份 HTML）| ⚠️ 状态未知 | 0 commit / 0 PR；`frontend/` 为空 |
| docs/05 任务清单已交付 | ✅ DONE | 5-14 已推送 |

---

## ⚠️ 当前 P0 / P1 风险

### 🔴 P0：Y 时间漂移 = 训练天花板

**症状：** 熊鑫的 2 组 LSTM 基线 R² < 0.2，复现不出论文 0.6619；XGBoost 在同数据上 R²=0.50。

**根因：** Wang 原始 paper_panel 的 Y 未做 Butterworth 去趋势（任务 1.6），导致 Y 含趋势项 → 任何模型的 R² 上限 ~0.5。

**任务归属：** 1.6 是原王天硕任务，王不干活 = 任务孤儿。

**候选承接：**
- **石灵子**（推荐）— 离数据最近，半天加一列 `Y_detrended` 进 `paper_panel_v3`
- 熊鑫 — 训练侧最受益但偏离主线
- 潘 — 算法基础足，但 5-31 撞 2 个 ddl

**ddl 建议：** 5-23（与石灵子的 1.2 同 ddl，便于一并发版 v3）

### 🟡 P1：PR #7 阻塞下游

PR #7 含 paper_panel_v2 + MODIS panel + GIS — **3 个下游任务等它进 main**：
- 熊鑫训练（需要 panel_v2 作训练数据）
- Y 去趋势工作（需要在 v2 基础上加列）
- 后续 MODIS 月度增量更新

**建议：今天 review + merge**。

### 🟡 P1：周煜楠状态未知

5-14 给她任务清单后无音讯。M3 阶段（12 月起）需要她的 5 份 HTML 作 Vue 化的视觉蓝本，**越拖越紧**。

---

## 📥 待处理操作（按优先级）

| 优先 | 动作 | 谁做 | 工作量 |
|---|---|---|---|
| 🔴 P0 | 决定 Y 去趋势归谁 → 开 issue + assign | 潘 | 30 秒 |
| 🔴 P0 | review + merge PR #7 | 潘 | 10 分钟 |
| 🟡 P1 | 熊鑫对齐消息处理（A/B/C/D） | 潘 | 5 分钟决策 |
| 🟡 P1 | ping 周煜楠要状态 | 潘 | 1 分钟 |
| 🟡 P1 | 熊鑫把本地 7 个未 commit 脚本 commit + push | 熊鑫 | 30 分钟 |
| 🟢 P2 | 8 月后石灵子角色（M1 评审后再谈） | 潘+石灵子 | 5 分钟 |
| 🟢 P2 | 设 main 为 Protected branch（强制 PR + CI） | 潘 | 5 分钟（仓库 Settings）|

---

## 🔄 更新机制

- 每次重要进展（PR merge / 任务完成 / 新 blocker / 任务转手）都该 update 本文
- 任何 session 都可以 PR 改本文，commit message 加 `docs(status):` 前缀
- 本文不是"周报"——是**实时大盘**，stale 1 天以上视为过期，需更新
- 跨 session 同步走 git + 本文 + GitHub Issues / PR 评论，**不走 memory**
