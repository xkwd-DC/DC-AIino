# 项目实时状态 · STATUS

> **本文是项目级 single-source-of-truth dashboard**，任何 session 都该来这看大盘。
> 每次重要进展（PR merge / 任务完成 / 新 blocker）都更新本文。
>
> 最近更新：**2026-05-21 下午**（潘妙齐 session：`cwd=/home/darcy/DC/pmq`）

---

## 🚨 关键路线决策

### 2026-05-17 · R² 路线务实化

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
今天 2026-05-21，距 M1 评审（2026-07-31）剩 71 天，距系统 v0.1 上线（6/25）剩 35 天

近期硬 ddl：
  🚨 今天 5-21 14:00  CRAIC 三人现场签字 + 学院盖章
  🚨 5-23 09:00       CRAIC 三份材料提交 caairobot.com (Issue #12)
  🟢 5-22             周 UI 入仓 PR + STATUS 同步（潘）
  🚨 5-24             GCP e2-medium 实例 + Claude Code 服务器端装
  🚨 5-26             Phase 1 验收：backend /api/health + Vue 骨架 4 view 切换
  🚨 5-31             1.1 文献综述 finalize（潘）
  🚨 5-31             申报书 §2.3/§3/§5 重写（Issue #10）
  🚨 5-31             Phase 3.2 M01 风险地图 Vue 化（不依赖熊鑫）
  ⏰ 6-15             Phase 2 模型集成（依赖熊鑫导出 5 文件）
  ⏰ 6-25             系统 v0.1 GCP 公网可访问（4 模块 + 国际域名 + HTTPS）
  ⏰ 7-25             1.8 Z-score 标准化 + 数据划分（熊鑫）
  ⏰ 7-31             M1 评审：多模态数据集 v1.0
```

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
| 合并 PR | **10 个**（#2-#8 + #11/#13/#14） |
| 待合并 PR | 0（待潘开 PR：周 UI 入仓 + Phase 1 骨架 + 路线决策） |
| 公开 Issues | **5**（#6 熊鑫 / #9 石灵子 / #10 路线决策 / #12 CRAIC 5-23 / #17 M3 系统开发 Phase 0-5）|
| Backend 测试 | **16 个端点测试**（health + 31 省 + 11 特征 predict + ensemble + 校验 + 404 兜底），全过 |
| Backend 完成度 | 80%（health/provinces/predict mock 完整；待补 SHAP API + recommendation API + year 参数） |
| Frontend 完成度 | 静态原型 100%（周 6 份 HTML）+ Vue 3 骨架 100%（4 view 占位 + router + axios + health 灯），M01-M04 业务 Vue 化 0% |
| 数据资产 | paper_panel_v3 (403×27, y_detrended 完美) + MODIS 11 维 panel + GIS 三级 + CLCD |
| 文档总数 | **15** 篇（00–12 + STATUS + CHANGELOG） |

---

## 👥 全员状态（2026-05-21 下午）

### 🟢 潘妙齐 · 项目负责人 / 后端 / 前端 Vue 集成 / 部署 / 论文

- 个人 dev session = **cwd=/home/darcy/DC/pmq**（此会话），协调中心见 `/home/darcy/DC`
- ✅ docs/09 文献综述 v1.0 草稿（62KB，38 文献）
- ✅ docs/10 v2.0 重写：取消 ICP 备案 → GCP `e2-medium asia-east1` 海外部署
- ✅ docs/12 系统开发执行计划 v1 落档（35 天，5/21 → 6/25 上线）
- ✅ docs/CHANGELOG.md 启动（系统开发日志，答辩"过程性材料"来源）
- 🟡 综述 v1.0 → v1.1 校对（5/31 ddl）
- 🟡 申报书重写（Issue #10）
- 🔥 **系统开发启动**：周 UI 已到位，5/24 起 Phase 1（详见 `docs/12_系统开发执行计划.md`）
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

### 🟡 熊鑫 · 算法（CRAIC 收口 + 系统 Phase 2 准备）

- ✅ LSTM 训练脚手架 `train_lstm_baseline.py`
- ✅ XGB R² 0.4962 → **0.5647** 用 v2（10 种子均值）
- ✅ Butterworth 完整跑通 + 4 个诊断脚本
- ✅ 5 个 LSTM 交付物到 `backend/models/`（gitignored，未入仓）
- 🔴 **CRAIC 5/19 嵌图 + Att-LSTM R² 实测**：状态待群里确认
- 🟡 **5/24+ 系统 Phase 2 准备**：按 docs/07 §3.3 接口契约导出 5 文件入仓（xgb_model.pkl / lstm_model.h5 / scaler.pkl / feature_columns.json + inference 示例），潘的 backend Phase 2 集成依赖此

### 🟢 周煜楠 · 前端（UI 阶段 100% 交付，工作 freeze）

- ✅ **2026-05-21 一次性交付 7 份 HTML**：index + 00 设计系统 + 01 风险地图 + 02 SHAP 看板 + 03 情景模拟 + 04 韧性路径（详见 `frontend/prototypes/`）
- ✅ docs/05 任务清单 5-14 → 5-21 完成（7 天闷头干活，未通讯）
- 设计水准：深绿 #162520 + 橄榄/琥珀/赭石点缀；Noto Serif/Sans + JetBrains Mono；odometer 字符滚动；reduce-motion 适配；ECharts china map / 11 规则引擎 / SHAP 4 图全交付
- ⚠️ **数字口径警告**：UI 内硬编码 R²=0.847 / 11 特征 / NASA POWER 等 mock 数字与务实路线不符——Vue 化时全部走 API，等熊鑫真数字回填
- 🛑 **后续工作**：周个人到此 freeze；Vue 化 + 后端 + 联调 + 部署全归潘妙齐
- 🟢 CRAIC 5/21 14:00 签字到场风险**待群里确认**（人已到位，剩下是是否能 14:00 现场签字）

---

## 📦 已 merge PR（近 3 天）

| PR | 标题 | 何时 |
|---|---|---|
| **#7** | feat(data) 石灵子 data pipeline + Y 去趋势（14 commits） | 2026-05-17 |
| **#8** | docs(status) 加入项目实时状态 dashboard | 2026-05-17 |
| **#11** | docs(11) 数据集说明 v1 — M1 评审硬交付物 | 2026-05-19 |
| **#13** | docs(craic) 5/23 比赛三份材料追踪 + 协调中心风险清单 | 2026-05-19 |
| **#14** | docs(handoff) 石灵子 2026-05-17 session 收尾 | 2026-05-19 |

---

## ⚠️ 当前 P0 / P1 风险

### 🔴 P0：CRAIC 5/23 09:00 三份材料提交

- 5/21 14:00 三人现场签字 + 学院盖章（潘+熊+周）— **周到位待群确认**
- 5/22 三份材料 PDF 终版校对
- 5/23 09:00 上传 caairobot.com
- 风险：熊鑫的务实路线 Att-LSTM R² 实测数字是否嵌入研究报告 §7（5/17 决策要求）

### 🟡 P1：系统开发 5/24 启动 — 关键路径

- Phase 0/1（5/24-26）：GCP 开机 + backend 启动验证 + Vue 骨架
- Phase 4 提前（5/27-28）：SQLite 灌 paper_panel_v3 → /api/provinces?year
- Phase 3.2/3.5（5/29-31）：M01 地图 + M04 路径 Vue 化（不依赖熊鑫）
- 阻塞：等熊鑫 CRAIC 后（5/24+）按 docs/07 §3.3 导出 5 个模型文件，才能做 Phase 2 + Phase 3.3/3.4

### 🟡 P1：申报书重写

Issue #10 列出的章节重写约 1–2 天工作量。可与 M1 评审材料 + 系统开发交错做（5/31 前）。

### 🟢 P2：M1 评审材料启动

距 7-31 评审还有 71 天。`docs/11 数据集说明 v1` 已是硬交付物。6 月起补汇报材料。

---

## 📥 待处理操作

| 优先 | 动作 | 谁做 | 何时 |
|---|---|---|---|
| 🔴 P0 | CRAIC 5/21 14:00 三人现场签字到场 | 潘+熊+周 | 今天 |
| 🔴 P0 | CRAIC 5/23 09:00 三份材料提交 caairobot.com | 潘 | D+2 |
| 🟡 P1 | GCP 项目开通 + e2-medium asia-east1 实例 | 潘 | 5/24 |
| 🟡 P1 | Phase 1 验收：backend 启动 + Vue 骨架 | 潘 | 5/26 |
| 🟡 P1 | 申报书 §2.3/§3/§5 重写 | 潘（Issue #10）| 5/31 前 |
| 🟡 P1 | Phase 3.2/3.5 M01+M04 Vue 化（不依赖熊鑫）| 潘 | 5/31 |
| 🟡 P1 | 熊鑫 5/24+ 按 docs/07 §3.3 导出 5 模型文件 | 熊鑫（Issue #6）| 5/24+ |
| 🟡 P1 | 开 PR `feat/system-skeleton`：Vue 骨架 + 后端验收 + GIS/POWER 数据 | 潘 | 5/22 |
| 🟢 P2 | 设 main 为 Protected branch | 潘 | 5 分钟 |
| 🟢 P2 | M1 评审材料启动 | 潘 + 全员 | 6 月起 |
| ✅ done | docs/10 改写 GCP 部署清单 v2 | 潘 | 完成于 5/21 |
| ✅ done | docs/12 系统开发执行计划落档 | 潘 | 完成于 5/21 |
| ✅ done | docs/CHANGELOG.md 启动 | 潘 | 完成于 5/21 |
| ✅ done | 周煜楠 6 份 UI 原型入仓 `frontend/prototypes/` | 协调中心 | 完成于 5/21 |
| ✅ done | Vue 3 + Vite 工程骨架（4 view + router + axios + health 灯）| 潘 | 完成于 5/21 |
| ✅ done | 系统开发 Phase 0-5 tracking Issue #17 | 协调中心 | 完成于 5/21 |

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
