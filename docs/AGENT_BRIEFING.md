# Agent Briefing — 极端气候下粮食生产风险项目

> 所有 subagent 在执行任何任务前必须读完本文件。

---

## 1. 项目一句话

**极端气候下粮食生产风险识别与决策支持系统**（2026 大创 + AI 大赛）。
主仓：`/home/darcy/DC/DC`，main 分支为唯一交付分支。

---

## 2. 环境约束（必须遵守）

| 约束 | 说明 |
|------|------|
| 文件读取 | `sudo bash -c '...'` 可读 `/home/xxfql` 等队员 home（owner-only 750），不要用 `sudo sh` |
| Python 包安装 | **只能装到 `/tmp/dc-*`**，例：`python3.10 -m venv /tmp/dc-env && pip install --no-cache-dir ...` |
| 训练二进制 | `backend/models/*.{pkl,h5}` 已加白名单进 git（见 commit fb58981），不要加 LFS |
| 严禁 push | **只做 local commit**，commit 完报告 hash，由 orchestrator 决定是否 push |
| 严禁越权 | 队员 home 只能读，不能改；`darcy` 有 google-sudoers 权限，但 harness 会拒绝越权写操作 |

---

## 3. 模型选择原则（省 token）

| 任务类型 | 使用模型 |
|----------|---------|
| 只读 / grep / git status / 简单检查 | `haiku` |
| 代码生成 / 文档写作 / 数据处理 | `sonnet`（默认） |
| 架构分析 / 复杂规划（Plan Mode） | `opus` |

---

## 4. 【关键】模型稳健性事实（对外叙事必须遵守）

来源：`backend/models/strict_cv_v3_card.md`，`docs/_craic/robustness_summary_2026-05-22.md`

| 指标 | 数字 | 结论 |
|------|------|------|
| random 8:2 R² | 0.907 | 论文协议，可引用 |
| leave-year-out R² | 0.8943 | 时序泛化可用 |
| **leave-province-out 中位 R²** | **-16.83，31 省仅 1 省 R²>0** | **空间外推完全失败** |
| NDVI 移除后 R² 变化 | -0.003 | NDVI 贡献≈0% |

**❌ 绝对不能写/说的话：**
- "climate → yield 高精度预测"
- "R²=0.91 证明跨省预测能力"
- "SHAP × Attention 一致性验证"
- "NDVI 是核心驱动因子"

**✅ 必须用的诚实表述：**
- "省内风险因子相对重要性识别"
- "random 8:2 协议 R²=0.91（论文协议）；严格 leave-province-out 退化至中位 -16.83，反映 N=403/31 截面数据上限"
- "SHAP 与 Attention 双视角互补（非一致性验证）"
- "**决策支持系统**是核心交付，不依赖模型空间外推能力"

---

## 5. 团队与账号

| 人 | 角色 | Linux 账号 | GitHub |
|----|------|-----------|--------|
| 潘妙齐（orchestrator） | 项目负责人 / 后端 / 部署 | `darcy` | `15934110986pmq-debug` |
| 熊鑫 | 算法：XGBoost-SHAP / LSTM / Attention | `xxfql` | `xxxx9939` |
| 石灵子 | 数据：MODIS / GIS / 时空对齐 | — | — |
| 常宇璇 | 新入：docs / 可视化 / AI 大赛材料 | `cyx67` | — |

不涉及王天硕、张嘉越、周煜楠（已淡出）。

---

## 6. 标准交付要求

- **完成后报告**：`git log --oneline -3`（hash + 描述）
- **不要 push**：只 local commit
- **不要创建新 GitHub Issue**：由 orchestrator 统一创建
- **不要改 main 以外的配置文件**（CI/deploy 相关）
- 若遇到阻塞，在输出里写 `BLOCKED: <原因>`，不要静默跳过

---

## 7. 关键参考文件

| 用途 | 路径 |
|------|------|
| 稳健性完整报告 | `docs/_craic/robustness_summary_2026-05-22.md` |
| 项目状态 | `docs/STATUS.md` |
| 系统执行计划 | `docs/12_系统开发执行计划.md` |
| 模型训练任务 | `docs/07_模型训练任务_算法组.md` |
