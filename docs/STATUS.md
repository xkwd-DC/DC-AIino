# 项目实时状态 · STATUS

> **本文是项目级 single-source-of-truth dashboard**，任何 session 都该来这看大盘。
> 每次重要进展（PR merge / 任务完成 / 新 blocker）都更新本文。
>
> 最近更新：**2026-05-17 下半天**（协调中心：`cwd=/home/darcy/DC`）

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
今天 2026-05-17，距 M1 评审（2026-07-31）剩 75 天

近期硬 ddl：
  ⏰ 5-23   docs/09_数据集说明_v1 草案（石灵子，Issue #9）
  ⏰ 5-31   1.1 文献综述 finalize（潘）
  ⏰ 5-31   3.11 域名注册启动（潘）
  ⏰ 7-25   1.8 Z-score 标准化 + 数据划分（熊鑫）
  ⏰ 7-31   M1 评审：多模态数据集 v1.0
```

---

## 📊 关键指标

| 项 | 数值 |
|---|---|
| 合并 PR | **7 个**（#2/#3/#4/#5/#6/#7/#8） |
| 待合并 PR | 0（待熊鑫开新 PR：v3 诊断脚本） |
| 公开 Issues | **3**（#6 熊鑫 / #9 石灵子 / #10 路线决策） |
| Backend 测试 | 16 个，覆盖率 98% |
| CI 通过率 | 100% |
| 数据资产 | paper_panel_v3 (403×27, y_detrended 完美) + MODIS 11 维 panel + GIS 三级 + CLCD |
| 文档总数 | 12 篇（00–10 + STATUS）|

---

## 👥 全员状态（2026-05-17 17:00）

### 🟢 潘妙齐 · 项目负责人 / 协调中心 / 后端 / 论文

- 协调中心 = **cwd=/home/darcy/DC**（此会话），_NOT_ `/home/darcy/DC/pmq`（pmq session 转个人 dev）
- ✅ docs/09 文献综述 v1.0 草稿（62KB，38 文献）
- ✅ docs/10 域名 + ICP 备案清单
- 🟡 综述 v1.0 → v1.1 校对（5/31 ddl）
- 🟡 域名注册启动（5/31 ddl）
- 🟡 申报书重写（Issue #10，与全员协作）

### 🟢 石灵子 · 数据工程（M1 实质完成）

- ✅ 1.2 论文数据接入（孤儿接手）→ `paper_panel_v2.parquet` 403×21
- ✅ 1.3 MODIS NDVI/LST 月度聚合 → 4836 行
- ✅ 1.4 GIS 三级（天地图 GS(2024)0650）+ CLCD 耕地
- ✅ 1.6 **Y 去趋势 Butterworth** → `paper_panel_v3.parquet` 403×27（y_linear mean=0, slope=0）
- ✅ 1.7 时空对齐 100% 匹配率
- 🟡 下一轮：docs/09 数据集说明 v1（[Issue #9](../../issues/9) D5）+ MODIS/POWER 月度可行性查询（D7）

### 🟡 熊鑫 · 算法（今天大量进展 + 关键发现）

- ✅ LSTM 训练脚手架 `train_lstm_baseline.py`
- ✅ XGB R² 0.4962 → **0.5647** 用 v2（10 种子均值）
- ✅ Butterworth 完整跑通 + 4 个诊断脚本（参数扫描 7 cutoff × 3 poly）
- ✅ 5 个 LSTM 交付物到 `backend/models/`（gitignored）
- 🔴 **发现 R² 上限**：去趋势后任意配置 R²≈0 → 路线转向（已决策）
- 🟡 下一轮：[Issue #6](../../issues/6) 新评论的 P0 任务（v3 诊断脚本新 PR + backend/models 重训 + 路线 memory）

### 🔴 周煜楠 · 前端

- 仍无 commit / 0 PR / `frontend/` 为空
- docs/05 任务清单已 5-14 交付
- **建议：今天群里 ping 状态**（5-14 至今 3 天无音）

---

## 📦 已 merge PR（今天）

| PR | 标题 | 何时 |
|---|---|---|
| **#7** | feat(data) 石灵子 data pipeline + Y 去趋势（14 commits） | 2026-05-17 |
| **#8** | docs(status) 加入项目实时状态 dashboard | 2026-05-17 |

---

## ⚠️ 当前 P0 / P1 风险

### 🟢 P0：R² 路线已决策（不再是 blocker）

之前的"Y 漂移阻塞训练"已通过 PI 拍板务实路线解除。熊鑫开干新 PR。

### 🟡 P1：周煜楠状态未知

5-14 给她 docs/05 任务清单后 3 天无音讯。M3 阶段（12 月起）等她的 5 份 HTML 视觉蓝本。**今天群里 ping 一次**。

### 🟢 P2：申报书重写工程量

Issue #10 列出的章节重写约 1–2 天工作量，潘负责。可与 M1 评审材料一起做。

---

## 📥 待处理操作

| 优先 | 动作 | 谁做 | 何时 |
|---|---|---|---|
| 🔴 P0 | docs/09 数据集说明 v1 草案 | 石灵子（Issue #9）| 今天/明天 |
| 🔴 P0 | MODIS / POWER 月度数据可行性 | 石灵子（Issue #9）| 30 分钟内回复 |
| 🔴 P0 | v3 诊断脚本新 PR + backend/models 重训 | 熊鑫（Issue #6）| 今天/明天 |
| 🟡 P1 | 群里 ping 周煜楠状态 | 潘 | 1 分钟 |
| 🟡 P1 | 申报书 §2.3/§3/§5 重写 | 潘（Issue #10）| 5/31 前 |
| 🟢 P2 | 设 main 为 Protected branch | 潘 | 5 分钟（Settings → Branches）|
| 🟢 P2 | M1 评审材料启动 | 潘 + 全员 | 6 月起 |

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
