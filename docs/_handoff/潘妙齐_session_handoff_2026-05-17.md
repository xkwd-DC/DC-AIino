# 潘妙齐 session handoff · 2026-05-17

> 上一轮 Claude session 结束前的 handoff 笔记。
> 下次开新 Claude session 时第一件事：读本文 + `git pull` + `cat docs/STATUS.md`。

---

## 角色定位（新会话开局必读）

- **本 cwd**：`/home/darcy/DC/pmq` = **潘妙齐个人 dev**——干实质活（论文 / 后端 / 系统 / 部署）
- **协调中心不在这里**：是 `cwd=/home/darcy/DC` 那个 session（石灵子 cwd）在做整合 + STATUS.md + Issue/PR 分发
- **跨 session 同步**：走 git + `docs/STATUS.md` + GitHub Issues/PR，**不走 memory**
- Memory 文件 `session_role_panmiaoqi.md` 已正确标注潘妙齐席位，**不需要改**

## 今天的关键路线决策（必须知道）

- 实证发现：**R² ≥ 0.62 在去趋势 Y 上数学不可达**
  - 任何模型在去趋势 Y 上 R²≈0
  - 原始 Y 上限 0.53–0.56（熊鑫实测 XGB 0.5647）
  - 论文 R²=0.6619 是模型把"年份"当因子，趋势伪相关
- PI 拍板务实路线：**30% 冲原始 Y R²（承认上限）+ 70% 投 Attention-LSTM + SHAP×Attention 一致性 + 韧性路径系统**
- **影响**：申报书 §2.3/§3/§5 + 文献综述结论段 + 论文摘要 — 所有 R² 表述都要改

## 潘妙齐当下待办（STATUS.md 派下来）

| 优先 | 任务 | ddl |
|---|---|---|
| 🟡 P1 | `docs/09` 文献综述 v1.0 → v1.1 校对 | 5/31 |
| 🟡 P1 | 申报书 §2.3/§3/§5 重写（**Issue #10**）| 5/31 前 |
| 🟢 P2 | M1 评审材料启动 | 6 月起 |

## 已交付（最近 commit，不重复）

- `docs/09` 文献综述 v1.0 草稿（62KB / 38 文献）
- `docs/10` 域名 + ICP 备案清单
- M3.3 Flask 后端 scaffold + `/api/predict` mock + 15 pytest + CI + ensemble 接口
- 算法组训练任务交接给熊鑫（`docs/07`）+ inference Protocol stub
- 周煜楠前端 UI 任务清单（`docs/05`）

## 潘本人要做（Claude 帮不上）

- 群里 ping 周煜楠（5-14 至今 3 天无音）
- 5/31 前阿里云域名注册 + ICP 备案（线下操作）
- 设 main 为 Protected branch（GitHub Settings → Branches）

## 上轮建议但未启动的下一步

**先吃 Issue #10**——申报书重写和文献综述校对都涉及 R² 表述，一并改省一轮。具体动作：

```bash
gh issue view 10
# 扫 docs/03 申报书 + docs/02 论文 + docs/09 综述里所有 R² 段落
# 出 diff plan
```

## 新会话起手白话

> 我是潘妙齐席位（cwd=/home/darcy/DC/pmq，个人 dev），刚 git pull 完。
> 请读 docs/STATUS.md + docs/_handoff/潘妙齐_session_handoff_2026-05-17.md，
> 然后帮我开干 Issue #10（申报书重写）+ docs/09 文献综述 v1.1 校对——
> R² 路线已变更为 30/70 务实路线。
