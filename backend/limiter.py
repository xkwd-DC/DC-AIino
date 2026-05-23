"""Optional flask-limiter wrapper — graceful no-op when package missing.

设计目的
========
本机 dev/test 环境可能没装 flask-limiter (mock 阶段最小依赖),需保证 pytest 不破。
production 环境装齐后 limiter 自动生效。

用法
====
1. 在 backend/app.py 内: `from limiter import limiter; limiter.init_app(app)`
2. 在 endpoint 内: `@limiter.limit("10 per minute")` 紧贴在 route decorator 内层

存储后端
========
- 默认: in-memory (单进程 dev/test OK)
- 多 worker (gunicorn -w >1): 必须配 RATELIMIT_STORAGE_URI=redis://...
  否则各 worker 计数相互独立,实际 rate = N × 配置值

—— Issue #26 HIGH#3 · 协调中心整夜 loop [E]
"""

from __future__ import annotations

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    # 全局默认 100/min, 单 endpoint 用 @limiter.limit("...") 覆盖
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100 per minute"],
        # storage_uri 走 env var RATELIMIT_STORAGE_URI (flask-limiter 自动读)
        # 不传则默认 in-memory
    )
    FLASK_LIMITER_AVAILABLE = True

except ImportError:
    FLASK_LIMITER_AVAILABLE = False

    class _NoOpLimiter:
        """Fallback when flask-limiter is not installed.

        所有 method 都是 no-op,decorator 透传 callable,使现有路由代码可直接装饰
        而不必判断 limiter 是否真存在。
        """

        def limit(self, _spec, **_kwargs):  # noqa: ARG002 — 签名匹配 flask-limiter
            def decorator(fn):
                return fn
            return decorator

        def shared_limit(self, _spec, **_kwargs):  # noqa: ARG002
            def decorator(fn):
                return fn
            return decorator

        def init_app(self, _app):
            """flask-limiter 真版本通过 init_app 绑定;no-op 接口对齐。"""
            pass

        def exempt(self, fn):
            """flask-limiter 的 @exempt 也得有同名 method,no-op。"""
            return fn

    limiter = _NoOpLimiter()


__all__ = ["limiter", "FLASK_LIMITER_AVAILABLE"]
