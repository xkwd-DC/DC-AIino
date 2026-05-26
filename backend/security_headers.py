"""HTTP 安全响应头中间件 — Issue #26 HIGH#4。

设计目的
========
nginx 反代层 (deploy/nginx.conf) 已配置 4 个安全头 (HSTS / X-Frame-Options /
X-Content-Type-Options / Referrer-Policy)。本中间件在 Flask app 层兜底:

  1. dev / pytest / 直连 gunicorn 场景没有 nginx 时也合规
  2. nginx 配置漂移 / 部分路由绕过 location block 时仍生效
  3. CSP / Permissions-Policy 在 app 层统一管理,nginx 渐进开启可单独控制

参考: ~/.claude/rules/ecc/web/security.md

启用方式
========
backend/app.py 顶部:

    from security_headers import apply_security_headers
    apply_security_headers(app)

env 控制 (可选)
==============
- SECURITY_HEADERS_ENABLED=0 → 关闭注入 (dev 排错用,生产禁用)
- SECURITY_HEADERS_CSP=relaxed → 用 'unsafe-inline' (ECharts 需要),
  否则默认 strict CSP (default-src 'self', script-src 'self' 'unsafe-inline'
  保持与 Vue dev / ECharts 兼容)

—— Issue #26 HIGH#4 · 协调中心 Wave 2
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask, Response


# Strict CSP — script-src 留 'unsafe-inline' 给 Vue 3 hydration boundary,
# style-src 留 'unsafe-inline' 给 ECharts inline tooltip。
# 如未来重构 ECharts extraCssText + Vue 用 nonce,可切换到更严格策略。
_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'"
)

# 完整安全头集合 — 与 deploy/nginx.conf 对齐 + Permissions-Policy + CSP 补全
_SECURITY_HEADERS: dict[str, str] = {
    # HSTS: 1 年, includeSubDomains;preload 留给运维显式 opt-in (避免误开)
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # 禁止 MIME sniffing — 防 .json 被当 .html 执行
    "X-Content-Type-Options": "nosniff",
    # 拒绝任何 frame 嵌入 — 防 clickjacking
    "X-Frame-Options": "DENY",
    # 跨域只暴露 origin 不暴露 path / query
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # 禁用敏感浏览器特性 — 与 nginx 对齐
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    ),
    # CSP — 默认 strict,可由 SECURITY_HEADERS_CSP=relaxed 切换
    "Content-Security-Policy": _DEFAULT_CSP,
}


def _is_enabled() -> bool:
    """SECURITY_HEADERS_ENABLED=0 时禁用(仅 dev 排错用)。"""
    return os.getenv("SECURITY_HEADERS_ENABLED", "1") != "0"


def _build_headers() -> dict[str, str]:
    """根据 env 构建实际生效的头集合。"""
    headers = dict(_SECURITY_HEADERS)
    # 当前默认策略已是 relaxed (含 'unsafe-inline'),保留 hook 以后续收紧 CSP
    return headers


def apply_security_headers(app: "Flask") -> None:
    """在 Flask app 上注册 after_request hook,所有响应自动带安全头。

    幂等:多次调用不会重复注册(用 app.config flag 守护)。
    """
    if app.config.get("_SECURITY_HEADERS_APPLIED"):
        return

    if not _is_enabled():
        return

    headers = _build_headers()

    @app.after_request
    def _inject_security_headers(response: "Response") -> "Response":
        for name, value in headers.items():
            # 不覆盖上游(nginx / 中间件)已设的同名头
            response.headers.setdefault(name, value)
        return response

    app.config["_SECURITY_HEADERS_APPLIED"] = True


__all__ = ["apply_security_headers"]
