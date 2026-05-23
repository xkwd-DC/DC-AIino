#!/usr/bin/env bash
# deploy/setup_letsencrypt.sh
# 粮食风险预测系统 v0.1 · Phase 5 GCP 部署 (6/16-25)
#
# 一次性 SSL 证书申请脚本 (certbot --webroot 模式)。
# 跑前提:
#   1. nginx 已安装且本目录的 nginx.conf 已部署 + reload (HTTP→HTTPS 跳转 + .well-known/ 路径就位)
#   2. grainrisk.app 与 www.grainrisk.app 的 DNS A 记录已指向本 GCP 实例外网 IP
#   3. 防火墙开 80/443 (gcloud compute firewall-rules create 已做, 见 docs/12 Phase 0)
#
# 用法:
#   sudo bash deploy/setup_letsencrypt.sh
#
# 跑完会:
#   - 安装 certbot (若缺失)
#   - 创建 /var/www/certbot/ webroot
#   - 拉取 + 安装证书到 /etc/letsencrypt/live/grainrisk.app/
#   - 装 systemd timer 做自动续签 (90 天周期, 30 天前续)
#
# 失败排查:
#   - DNS 未传播 → dig grainrisk.app 检查 A 记录是否对
#   - 80 端口不通 → curl http://grainrisk.app/.well-known/acme-challenge/test
#   - 限速 → Let's Encrypt 5 次/小时/域名,失败要等
#
# —— 协调中心整夜 loop · [F]

set -euo pipefail

# === 配置 (改这里) ===
DOMAIN_MAIN="grainrisk.app"
DOMAIN_ALT="www.grainrisk.app"
EMAIL="${LETSENCRYPT_EMAIL:-admin@grainrisk.app}"   # 接 ACME 通知用
WEBROOT="/var/www/certbot"
STAGING="${STAGING:-0}"                              # 1 = 用 staging 服务器测试(免限速)
# =====================

log() {
    echo "[setup_letsencrypt] $*"
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log "FATAL: must run as root (sudo bash $0)"
        exit 1
    fi
}

ensure_certbot() {
    if command -v certbot >/dev/null 2>&1; then
        log "certbot already installed: $(certbot --version 2>&1)"
        return
    fi
    log "installing certbot via apt"
    apt-get update -qq
    apt-get install -y certbot
}

ensure_webroot() {
    if [ ! -d "${WEBROOT}" ]; then
        log "creating webroot at ${WEBROOT}"
        mkdir -p "${WEBROOT}"
        chown -R www-data:www-data "${WEBROOT}"
    fi
}

ensure_nginx_reloaded() {
    if ! command -v nginx >/dev/null 2>&1; then
        log "FATAL: nginx not installed. Run 'sudo apt install -y nginx' first."
        exit 1
    fi
    if ! nginx -t 2>&1 | grep -q "syntax is ok"; then
        log "FATAL: nginx config invalid. Run 'sudo nginx -t' to see error."
        exit 1
    fi
    systemctl reload nginx
    log "nginx reloaded OK"
}

dns_sanity_check() {
    log "DNS sanity for ${DOMAIN_MAIN}:"
    dig +short A "${DOMAIN_MAIN}" || true
    log "DNS sanity for ${DOMAIN_ALT}:"
    dig +short A "${DOMAIN_ALT}" || true
    log "(若上面输出为空, 等 DNS 传播 5-30 min, 用 dnschecker.org 确认全球传播状态)"
}

issue_cert() {
    local staging_flag=""
    if [ "${STAGING}" = "1" ]; then
        staging_flag="--staging"
        log "STAGING=1 — 用 Let's Encrypt 测试服务器(证书不被浏览器信任,但不撞限速)"
    fi

    log "申请 ${DOMAIN_MAIN} + ${DOMAIN_ALT} 证书"
    certbot certonly \
        --webroot \
        --webroot-path "${WEBROOT}" \
        --email "${EMAIL}" \
        --agree-tos \
        --no-eff-email \
        --keep-until-expiring \
        --non-interactive \
        ${staging_flag} \
        -d "${DOMAIN_MAIN}" \
        -d "${DOMAIN_ALT}"
}

ensure_renewal_timer() {
    # certbot apt 包默认装了 /etc/cron.d/certbot 或 systemd timer
    # 这里只 verify + 重启 nginx 钩子
    local hook_dir="/etc/letsencrypt/renewal-hooks/deploy"
    mkdir -p "${hook_dir}"
    cat > "${hook_dir}/reload-nginx.sh" <<'EOF'
#!/usr/bin/env bash
# 续签后自动 reload nginx 让新证书生效
systemctl reload nginx
EOF
    chmod +x "${hook_dir}/reload-nginx.sh"
    log "deploy hook installed: ${hook_dir}/reload-nginx.sh"

    log "verify cron / timer (随机一项即可):"
    systemctl list-timers | grep -i certbot || true
    cat /etc/cron.d/certbot 2>/dev/null || true
}

main() {
    require_root
    log "目标域名: ${DOMAIN_MAIN} + ${DOMAIN_ALT}"
    log "邮箱: ${EMAIL}"
    log "webroot: ${WEBROOT}"
    log "STAGING: ${STAGING}"

    ensure_certbot
    ensure_webroot
    ensure_nginx_reloaded
    dns_sanity_check
    issue_cert
    ensure_renewal_timer

    log "证书已签发"
    log "  /etc/letsencrypt/live/${DOMAIN_MAIN}/fullchain.pem"
    log "  /etc/letsencrypt/live/${DOMAIN_MAIN}/privkey.pem"
    log ""
    log "下一步:"
    log "  1. systemctl reload nginx  # 加载证书"
    log "  2. 浏览器打开 https://${DOMAIN_MAIN}  应见 padlock 图标"
    log "  3. ssllabs.com/ssltest/ 跑 A+ 评级测试"
}

main "$@"
