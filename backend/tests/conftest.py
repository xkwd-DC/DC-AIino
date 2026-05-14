"""pytest 公共 fixture：用 Flask test_client 避免真启 HTTP 服务。"""
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()
