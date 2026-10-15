# deploy/ — 部署配置

## 0. 本地部署（Windows，当前可用的方式）

> ⚠️ **状态更正（2026-10-15）**：`grainrisk.app` **并未注册**，GCP 实例也没开过机。
> 本文 §「部署顺序」以下的 nginx / certbot / Cloudflare 内容属于**未执行的计划**，
> 不要当成"系统已上线"。要跑系统、要录演示视频、要给评委看，一律走本节。

```powershell
# 后台启动（默认 http://127.0.0.1:8000）
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1

# 前台启动（排查用，Ctrl+C 停）
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Foreground

# 局域网访问：同一 WiFi 下的手机/平板可打开（会打印局域网地址）
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Lan

# 换端口 / 查看状态 / 停止
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Port 8081
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Status
powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Stop
```

脚本行为：

1. **预检运行产物，缺什么补什么**（这是本地部署最容易忘的一步）：
   `backend/data/grain.db`（省级 403 行）→ `_build_grain_db.py`；
   `backend/data/county.db` + `frontend/public/maps/counties_10provinces.json`（县级）→ `scripts/data/v9_01_*` + `v9_02_*`；
   `frontend/dist` → `npm ci` + `npm run build`。全都存在则跳过（`-SkipBuild` 则严格校验、不补）。
2. **启动 WSGI 服务**：优先 `waitress`（多线程，Windows 可用；gunicorn 在 Windows 跑不起来），
   没有则退回 Flask 内置服务器。前端 `dist` 与 `/api/*` 由同一个进程提供 —— 前端 axios 用相对路径 `/api`，
   所以**不能只起 vite dev 就想连真数据**。
3. **探活并打印地址**：`/api/health` + 省级/县级两个面板接口各取一次。

运行态文件（PID、日志）写在 `deploy/run/`，已加 `.gitignore`。

> Windows 细节：`serve_local.ps1` 是 **UTF-8 with BOM**。Windows PowerShell 5.1 对无 BOM 的 `.ps1`
> 按系统 ANSI 代码页（本机 GBK）解析，中文会变乱码并报一堆语法错误 —— 以后改这个脚本别把 BOM 弄丢了。

---

## 1. 计划中的公网部署（GCP，未执行）

> 本目录承载 v0.1 上线 GCP `e2-medium asia-east1` 的所有部署资产。
> 上游依赖: `docs/12 §Phase 5`(部署执行计划)+ `docs/10` v2 GCP 路线决策。

## 文件清单

| 文件 | 用途 |
|---|---|
| `nginx.conf` | nginx server block — TLS terminate + 反代 gunicorn + 4 HTTP 安全头 |
| `setup_letsencrypt.sh` | certbot --webroot 一次性证书申请 + 自动续签 hook |
| `README.md` | 本文件 |

未来还会加入 (Phase 5 实施时):

- `systemd/grainrisk.service` — gunicorn 守护
- `systemd/grainrisk-frontend.service` — (若 Vue build 不走 nginx 直服) Node SSR 守护
- `gunicorn.conf.py` — workers / timeout / logging 配置
- `setup.sh` — 一键串起所有步骤的引导脚本

## 部署顺序

```
GCP 实例 (Phase 0)
   │  apt update && apt install -y nginx python3.11 python3.11-venv certbot git
   ▼
clone 仓库到 /opt/grainrisk
   │  git clone <repo> /opt/grainrisk
   │  cd /opt/grainrisk/backend
   │  python3.11 -m venv .venv
   │  source .venv/bin/activate
   │  pip install -r requirements.txt
   ▼
后端
   │  Phase 4 ETL: python scripts/load_panel_to_db.py --reset
   │  pytest (22 tests pass)
   │  gunicorn -w 4 -b 127.0.0.1:5000 app:app --daemon
   ▼
前端
   │  cd /opt/grainrisk/frontend
   │  npm ci
   │  npm run build
   │  sudo cp -r dist /var/www/grainrisk/
   ▼
nginx
   │  sudo cp deploy/nginx.conf /etc/nginx/sites-available/grainrisk.app
   │  sudo ln -s ... /etc/nginx/sites-enabled/
   │  sudo nginx -t && sudo systemctl reload nginx
   ▼
SSL
   │  sudo bash deploy/setup_letsencrypt.sh
   │  sudo systemctl reload nginx
   ▼
✅ https://grainrisk.app 可访问
```

## HTTP 安全头 (Issue #26 HIGH#4)

`nginx.conf` 已默认开启 4 个 `always` 头:

| Header | Value | 防御 |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | 强制 HTTPS,防 SSL stripping |
| `X-Content-Type-Options` | `nosniff` | 防 MIME confusion |
| `X-Frame-Options` | `DENY` | 防 clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | 防 referer 泄露 |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | 关闭浏览器特性 |

**Content-Security-Policy 默认关闭**,理由 + 渐进开启方案见 `nginx.conf` 内注释。

## SSL 评级目标

部署后跑 [ssllabs.com/ssltest](https://www.ssllabs.com/ssltest/),目标 **A+**:
- TLSv1.2 + TLSv1.3 only(老 TLS 已禁)
- HSTS preload 准备就绪(max-age >= 1 year + includeSubDomains)
- OCSP stapling on
- Forward Secrecy (ECDHE) only

## Mozilla SSL Configurator 参照

本 nginx.conf 的 `ssl_*` 部分对齐 Mozilla **intermediate** profile(2026 版),平衡:
- 浏览器兼容性 (95%+ 现代浏览器)
- 安全 (无 RC4/3DES/SHA1)

不用 modern profile 因为某些科研评委可能用旧浏览器/教育内网。

## DNS 配置(Cloudflare)

`grainrisk.app` 注册在 Cloudflare,DNS 记录:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | `<GCP 实例外网 IP>` | DNS only(grey cloud) |
| A | `www` | 同上 | DNS only |

**初期不开 Cloudflare proxy (橙云)**,避免 TLS terminate 在 Cloudflare 端导致 nginx 拿不到 client IP(rate limit 误判)。Phase 5 末期可考虑开 + 配 `set_real_ip_from` 信任 Cloudflare IP 段。

## 日志

| 文件 | 内容 | 轮转 |
|---|---|---|
| `/var/log/nginx/grainrisk.access.log` | 所有请求 | logrotate 默认 daily 14 天 |
| `/var/log/nginx/grainrisk.error.log` | warn+ 错误 | logrotate 默认 daily 14 天 |
| `/var/log/grain-risk/app.log` | (TODO) gunicorn / Flask 应用日志 | 待 systemd 配 |

## 与其他 Issue 联动

- Issue #17 系统开发 Phase 5 — 本目录是 Phase 5 主交付物
- Issue #26 GCP production readiness — HIGH#4 已实装,MEDIUM 部分仍在 backlog
- Issue #25 a11y — 不涉及 deploy,但 nginx HSTS 对评委浏览器警告体验有正向影响

—— 协调中心整夜 loop · [F]
