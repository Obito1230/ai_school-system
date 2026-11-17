# -*- coding: utf-8 -*-
"""鉴权工具：密码哈希（pbkdf2_hmac，标准库）+ JWT（手写 HS256，零第三方依赖）。"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import SECRET_KEY, TOKEN_EXPIRE_HOURS, JWT_ALGO


# ---------- 密码 ----------
def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100_000)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, salt, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------- JWT（HS256，手写实现避免额外依赖） ----------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int, username: str, role: str) -> str:
    header = {"alg": JWT_ALGO, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "name": username,
        "role": role,
        # 学生端广场用：默认在 GET /orders 中过滤自己发布的单（自己的单不能自己接）；管理员看全量
        "exclude_mine": "true" if role != "admin" else "false",
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRE_HOURS * 3600,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(SECRET_KEY.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def decode_token(token: str) -> dict | None:
    """校验失败返回 None。"""
    try:
        h, p, s = token.split(".")
        expected = hmac.new(SECRET_KEY.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), s):
            return None
        payload = json.loads(_b64url_decode(p))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ---------- FastAPI 依赖 ----------
from fastapi import Depends, HTTPException, status  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """要求已登录，返回 JWT payload。"""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或令牌缺失")
    payload = decode_token(cred.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌无效或已过期")
    return payload


def require_admin(payload: dict = Depends(get_current_user)) -> dict:
    """要求管理员角色。"""
    if payload.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return payload
