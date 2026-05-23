# 8 PR 合并指引 · 2026-05-23 早间

> 早间应处理 **10 个 OPEN PR**(协调中心整夜新增 8 + 潘的 #20 + 熊鑫的 #21 + 5/22 晚间 #27)。
> 推荐合并顺序如下,按"依赖最少 → 依赖最多"梯度安排。

## 全景 OPEN PR 矩阵

| PR | 分支 | own | 大小 | 风险 | 是否独立? |
|---|---|---|---|---|---|
| #20 | feat/m01-risk-map | 潘 | ~540 行 / 5 commits | review WARN 0C/8H,有 followup | ✅ |
| #21 | feat/shap-v3-runbook | 熊鑫 | 5 commits + 5 PNG | 无 | ✅ Closes #22 |
| #27 | docs/coord-2026-05-22-evening | 协调中心 | CRAIC 3 docx + STATUS + CHANGELOG | 无 | ✅ |
| #28 | feat/phase4-schema | 协调中心 | +236 schema+README | 无 | ✅ |
| #29 | feat/phase4-etl | 协调中心 | +426 ETL | **依赖 #28** | ⚠️ |
| #30 | feat/phase4-repo | 协调中心 | +278/-2 Repo+endpoints | **依赖 #28**(schema 在 repo 内) | ⚠️ |
| #31 | feat/phase4-tests | 协调中心 | +230 6 pytest | **依赖 #30**(skipif) | ⚠️ |
| #32 | fix/gcp-readiness-p1 | 协调中心 | +91/-4 | 无 | ✅ |
| #33 | deploy/nginx-conf | 协调中心 | +458 nginx+Let's Encrypt | 无 | ✅ |
| #34 | feat/local-geojson | 协调中心 | +96 china.json+README | 无 | ✅ |
| #35 | docs/coord-2026-05-23-morning | 协调中心 | (本 PR) | 无 | ✅ |

## 推荐合并顺序

### Step 1: 独立 PR 并行 squash(可任意顺序,无依赖)

```bash
# CRAIC docs(零依赖,最快)
gh pr merge 27 --squash --auto

# 熊鑫 SHAP — 注意 squash message 后缀加 Closes #22
gh pr merge 21 --squash --subject "feat(scripts): plot_shap_v3.py + 5 PNG (Closes #22)" --body "..."

# 潘 4 view + security(squash 即可,8 HIGH followup 由潘起 fix/pr20-followup 分支)
gh pr merge 20 --squash

# GCP readiness 三连
gh pr merge 32 --squash
gh pr merge 33 --squash
gh pr merge 34 --squash
```

完成后 main 上有:
- CRAIC docx 入仓 + STATUS 5/22 晚间版 + CHANGELOG 5/22 entry
- 4 view Vue 业务模块
- 熊鑫 SHAP 5 PNG + plot_shap_v3.py
- backend docstring/env/limiter fix + nginx + China GeoJSON 自托管

### Step 2: Phase 4 链式合并(必须按序)

依赖关系:
```
#28 schema 提供 backend/data/schema.sql
   ↓
#29 ETL import schema.sql 跑 ETL → grain.db
   ↓
#30 Repo + endpoints 读 grain.db
   ↓
#31 tests 测 endpoints + Repository
```

`#29` / `#30` 都依赖 `#28`(schema.sql 文件存在);`#31` 用 `skipif` 检测 `panel_repo` 模块,理论上 `#30` 合后自动启用。但 PR 是基于 main 的,所以:

```bash
# 强制按顺序合
gh pr merge 28 --squash --auto && \
  gh pr merge 29 --squash --auto && \
  gh pr merge 30 --squash --auto && \
  gh pr merge 31 --squash --auto
```

合完后跑:
```bash
cd backend && .venv/bin/python -m pytest -v
# 应见 16 现有 + 6 新 phase4_db fixture = 22 passed
```

### Step 3: 本 PR(早间总结)

```bash
gh pr merge 35 --squash
```

完整生态收尾。

## 合并后状态

| 项 | merge 前 | merge 后 |
|---|---|---|
| 合并 PR 总数 | 12 | **22** |
| 待合并 PR | 10 | 0 |
| pytest 测试数 | 16 | **22** |
| Vue 业务模块 | 0/4 | 4/4 ✅ |
| 模型 R² | 三模型 ready | 三模型 ready |
| Phase 4 持久层 | 不存在 | schema + ETL + Repo + endpoints + tests ✅ |
| GCP production readiness | 0% | 4 HIGH 全过 ✅ |
| nginx + Let's Encrypt | 不存在 | 完整配置 ✅ |
| China GeoJSON | CDN | 自托管 ✅ |
| Issue 完成 | #6 | + 可关 #12 / #22 / #24 / #26 |

## 风险提示

### PR #20 8 HIGH followup

潘起一个新 `fix/pr20-followup` 分支修 8 HIGH(协调中心 PR #20 review 评论列出),~2-3h 工作量:
- RiskMap.vue:18 fetch URL 改 `/maps/china.json`(PR #34 已铺好)
- RiskMap.vue:226 删 console.error
- RiskMap.vue:210 `as never` → 具体类型
- ShapDashboard.vue:225-258 改 discriminated union
- ScenarioSim.vue:230 加 debounce + flush:'post'
- ScenarioSim/ResiliencePath 抽 `useProvinceStore` Pinia
- backend/app.py:62 改 `app.run(host="127.0.0.1", debug=False)` 默认(b87e667 commit 内容)
- backend/.env.example 注释强化 CORS 警告

### Phase 4 ETL 真跑

潘 5/27 在 GCP venv 装齐:
```bash
cd ~/grain/backend
source .venv/bin/activate
pip install -r requirements.txt  # 含 flask-limiter + pandas + scipy
cd ..
python scripts/load_panel_to_db.py --reset
# 期望 SUMMARY: 31 provinces / 403 rows / 2011..2023
pytest backend/tests -v  # 22 passed
```

### a11y Issue #25

7/31 评审前必修(约半天工作量),不阻塞 6/25 上线。

### Issue #26 完结

PR #32 + #33 + #34 全部 merge 后,Issue #26 4 HIGH + MEDIUM#5 完成,可关 Issue。剩 MEDIUM#6 (silent JSON) + MEDIUM#7 (`_mock` 字段) 可单开 sub-issue 或留 backlog。

## 不应做的事

- ❌ 不要直接 push main(squash via gh pr merge 才安全)
- ❌ 不要 force-push 任何分支
- ❌ 不要在 squash message 里漏 `Closes #xx`(自动关 Issue 依赖此)
- ❌ 不要让 Phase 4 4 PR 顺序错乱(尤其 #28 必须先合)

## 命令汇总(顺序版)

```bash
cd /home/darcy/DC/DC
git fetch origin --quiet

# Step 1: 独立 PR 并行
gh pr merge 27 --squash --auto
gh pr merge 21 --squash --auto    # 在 squash dialog 加 Closes #22
gh pr merge 20 --squash --auto
gh pr merge 32 --squash --auto
gh pr merge 33 --squash --auto
gh pr merge 34 --squash --auto

# Step 2: Phase 4 串行
gh pr merge 28 --squash --auto && \
  gh pr merge 29 --squash --auto && \
  gh pr merge 30 --squash --auto && \
  gh pr merge 31 --squash --auto

# Step 3: 本 PR
gh pr merge 35 --squash --auto

# 验证
git checkout main && git pull
cd backend && .venv/bin/python -m pytest -v
# expect: 22 passed
```

—— 协调中心整夜 loop · 2026-05-23 早间收尾
