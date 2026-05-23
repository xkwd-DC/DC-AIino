# 常宇璇 onboarding — 粮食风险风险预测项目

> 2026-05-23 创建。覆盖:服务器登录后到第一次提交 PR 的全流程。
> 协调中心:潘妙齐(账号 `darcy`,GitHub admin)。本文档由协调中心整理。

---

## 0. 你目前的位置

- **角色**:开发团队第 4 人,接替原前端位置;团队还有潘妙齐(后端/部署/协调)、熊鑫(算法)、石灵子(数据)。
- **当前阶段目标**:准备**人工智能大赛**(具体赛项与 deadline 由潘对接通知;6/25 还有系统 v0.1 上线、5/31 还有申报书 deadline,你的任务优先级会按这些 deadline 给)。
- **服务器**:你已经 SSH 上 GCP `imback.asia-east1-b`(Ubuntu 26.04),账号 `cyx67`,公钥已就位。
- **磁盘**:服务器只剩 ~2.7 GB,**严格按本文档的安装步骤来,不要乱装东西**。

---

## 1. 第一次登入做的事(~10 分钟)

### 1.1 确认登入成功

```bash
whoami     # 应输出: cyx67
pwd        # 应输出: /home/cyx67
uname -a   # 看到 Linux ... 26.04 即对
```

### 1.2 配置基础信息

```bash
# Git 身份(用真名 + 邮箱,提交记录会留下来)
git config --global user.name "常宇璇"
git config --global user.email "你的邮箱@example.com"
git config --global init.defaultBranch main
git config --global pull.ff only          # 防止意外 merge commit
git config --global push.default current  # 只 push 当前分支
```

### 1.3 生成 SSH key(给 GitHub 用)

```bash
ssh-keygen -t ed25519 -C "cyx67-grainrisk-$(date +%Y%m%d)" -f ~/.ssh/id_ed25519
# 一路回车,passphrase 留空(本机自用)
cat ~/.ssh/id_ed25519.pub
# 把整行复制下来,发给潘妙齐
```

发完之后等潘:
1. 把你的 GitHub username 加为仓库 collaborator(read 权限)
2. 你收到 GitHub 邀请邮件 → 点接受

---

## 2. 拉取项目(~5 分钟)

### 2.1 测试 GitHub SSH 通了

```bash
ssh -T git@github.com
# 第一次会问 known_hosts,输入 yes
# 成功提示: Hi <你的用户名>! You've successfully authenticated...
```

### 2.2 克隆项目

```bash
cd ~
git clone git@github.com:xkwd-DC/DC-AIino.git DC
cd ~/DC
git log --oneline -5   # 验证拿到最新主干
```

**项目体积**:源码 ~30 MB。不要在 `~/DC` 之外建项目副本,**不要 git clone 第二份**(磁盘紧)。

---

## 3. 项目地图(2 分钟扫一眼)

```
~/DC/
├── docs/
│   ├── STATUS.md              ← 项目当前状态总览,每次开工先看
│   ├── CHANGELOG.md           ← 按日变更日志
│   ├── coord/                 ← 协调中心(潘)产出的阶段性总结
│   ├── onboarding/            ← 你正在看的目录
│   └── craic/                 ← CRAIC 比赛已提交材料归档
├── backend/                   ← Flask API (Python 3.10+)
│   ├── app.py                 ← 入口
│   ├── api/                   ← 路由 (predict / provinces)
│   ├── services/              ← 业务层 (panel_repo)
│   └── tests/                 ← pytest (22 个测试,全过)
├── frontend/                  ← Vue 3 + Vite + TS + ECharts (4 个 view 已完成)
│   ├── src/views/             ← RiskMap / ShapDashboard / ScenarioSim / ResiliencePath
│   ├── src/stores/            ← Pinia (useProvinceStore)
│   └── public/maps/           ← 自托管 china.json
├── scripts/                   ← 数据处理脚本(load_panel_to_db / plot_shap 等)
├── data/                      ← .gitignore 已排除 raw/中间数据
└── deploy/                    ← nginx.conf + Let's Encrypt 脚本(GCP 上线用)
```

**先看的两个文件**:
1. `docs/STATUS.md` — 项目"早报",当前进度、谁在干什么、风险点
2. `docs/coord/2026-05-23-morning/SUMMARY.md` — 最近一份阶段总结

---

## 4. 工作流(必读)

### 4.1 单源真理:GitHub Issues + PRs

- **任务**:协调中心(潘)在 GitHub 起 Issue,assign 给你
- **沟通**:Issue / PR 评论留痕,口头讨论后要在 Issue 里补一句结论
- **不要直接 push 到 main**:你 collaborator 是 read 权限,push 不进去,改用 PR

### 4.2 分支命名

```
feat/cyx-<功能>           # 例: feat/cyx-pitch-deck
fix/cyx-<bug>             # 例: fix/cyx-typo-readme
docs/cyx-<文档>           # 例: docs/cyx-competition-notes
```

### 4.3 Commit message 格式

```
<类型>: <50字以内描述>

[可选正文,解释为什么这么改]
```

类型 = `feat | fix | refactor | docs | test | chore | perf | ci`

### 4.4 提交 PR 流程

```bash
git checkout -b docs/cyx-第一次提交     # 起新分支
# ... 改文件 ...
git status
git diff
git add <具体文件>                       # 不要 git add . 避免误提交
git commit -m "docs: 改了 xxx"
git push -u origin docs/cyx-第一次提交   # -u 第一次需要
gh pr create --base main --title "..." --body "..."
# (gh CLI 已装,首次用需 gh auth login,告诉潘)
```

潘会 review + squash merge。**不要自己强制合并 PR**。

---

## 5. 当前任务(占位,潘给你具体派活前先准备)

5/23 早上协调中心已经把 11 个 PR 全合主干。**主干现状**:
- 11 PR 全合(后端 Phase 4 持久层 + nginx/SSL 部署就绪 + Vue 4 view 完成 + 凭据安全收紧)
- 6 个 open issue 全是 tracking 类型,无 blocker

**你可以在等派活时做的轻量准备工作**:

1. **熟悉项目** — 读 `docs/STATUS.md` + `docs/coord/` 最近 3 份总结(15 min)
2. **跑一遍 demo** — 看前端长什么样:
   ```bash
   cd ~/DC/frontend
   pnpm install         # 占 143 MB,需要 ~3 分钟
   pnpm dev             # 起本地 5173,浏览器看 4 个 view
   ```
3. **运行测试看后端** — 验证你环境通:
   ```bash
   cd ~/DC/backend
   python -m venv venv  # ~30 MB
   source venv/bin/activate
   pip install -r requirements.txt   # ~500 MB-1 GB,看磁盘!
   pytest -v             # 应该 22/22 pass
   ```
   ⚠️ **装 backend 前先 `df -h /` 看一眼**,可用空间 <1 GB 就**别装**,先问潘扩盘。
4. **看 AI 大赛规则**(潘把赛项告诉你后) — 把要求贴一份到 `docs/competition/<赛名>/rules.md`

---

## 6. 磁盘约束(重要)

服务器 `/dev/root` 38 GB 总量,目前 93% 用,可用空间紧。

**不要**:
- 不要在 `~/cyx67` 之外建工作目录
- 不要 git clone 第二份
- 不要装 conda(占 4+ GB)
- 不要下载训练好的模型 .pkl/.h5 到 home(用 `/tmp` 临时跑然后清)
- 不要 npm install global

**建议**:
- 大文件挂 `/tmp`(7.9 GB tmpfs,重启清空)
- 装完 `pnpm install` 如果暂时不用,可以删 `frontend/node_modules`,需要时再装
- 任何下载前先 `df -h /`

---

## 7. 与协调中心同步

- 你做了什么 → 写在 PR description 或 Issue comment 里
- 卡住了 → 在 Issue 上 @ 潘的 GitHub(`@15934110986pmq-debug`)
- 大改方向 → 私聊潘,确认后再开 PR
- 紧急联系 → 微信/电话(从潘那里要)

**不要**:
- 不要 push 到 main(权限上也不行)
- 不要直接改 `docs/STATUS.md`(那是协调中心维护的)
- 不要删别人的分支
- 不要 force push

---

## 8. 常见问题

**Q: `pnpm` 命令找不到?**
```bash
npm install -g pnpm   # 装全局有可能权限不够,改:
corepack enable       # Node 16+ 内置 corepack 启用 pnpm
```

**Q: `pytest` 全 skipped?**
说明 `panel_repo` 模块没装好,确认在 `backend/` 目录 + `source venv/bin/activate` 后再跑。

**Q: 前端 `china.json` 加载失败?**
确认 `frontend/public/maps/china.json` 存在(61 KB)。

**Q: GitHub SSH 拒了?**
key 还没贴到 GitHub,或潘还没加你 collaborator。先发 pub key 给潘。

**Q: 把代码改了但 git status 看不到?**
你可能在 `/home/darcy/DC/DC` 里改了 — 那是潘的目录,你没权写。回 `~/DC`(即 `/home/cyx67/DC`)。

---

## 9. 这份 onboarding 还缺什么?

读完执行完之后,**告诉潘**:
- 哪一步卡住、文档不清
- 你的 GitHub username + 邮箱(还没给过潘的话)
- 你想做的方向(具体 view / docs / 数据 / 算法分析 / 其他)

潘会:
- 把你加 GitHub collaborator + 在 GitHub 起一个 issue assign 给你
- 把 AI 大赛具体赛项 / deadline / 你的工作模块告诉你
- 把微信群 / 沟通方式同步给你

欢迎入队 🌾
