"""API 包。所有 Blueprint 在此目录下；envelope 是统一响应壳。"""
from flask import jsonify


def envelope(data=None, error=None, status=None):
    """统一响应壳：{success, data, error}。

    error 形如 {"code": int, "message": str}。
    status 可选；若提供则返回 (response, status) 元组。
    """
    resp = jsonify(success=error is None, data=data, error=error)
    return (resp, status) if status is not None else resp
