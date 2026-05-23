"""pytest 公共 fixture：用 Flask test_client 避免真启 HTTP 服务。"""
import pytest

from app import app as flask_app
from limiter import FLASK_LIMITER_AVAILABLE, limiter


@pytest.fixture(autouse=True)
def _disable_rate_limit():
    """每个测试关 rate limit + reset 计数，避免 429 污染 400/200 断言。

    CI runner 用 in-memory storage 共享状态，/api/predict 10/min 在测试链
    中会越限触发 429，遮蔽真实的 400/200 校验。
    """
    flask_app.config["RATELIMIT_ENABLED"] = False
    if FLASK_LIMITER_AVAILABLE:
        try:
            limiter.reset()
        except Exception:
            pass
    yield


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()
