from __future__ import annotations

import hashlib
import hmac
import os
import re

from fastapi import HTTPException, Request, status

from .admin_auth import read_admin_session, require_admin_session
from .device_registry import register_request_device

API_PREFIX = "/api/v1"
API_VERSION = "1"
TOKEN_DIGEST_ENV = "QINGJUAN_AUTH_TOKEN_SHA256"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def configured_token_digest() -> str | None:
    value = os.getenv(TOKEN_DIGEST_ENV, "").strip().lower()
    if not value:
        return None
    if not _SHA256_PATTERN.fullmatch(value):
        raise RuntimeError(f"{TOKEN_DIGEST_ENV} 必须是 64 位小写 SHA-256 十六进制摘要")
    return value


def authentication_enabled() -> bool:
    return configured_token_digest() is not None


async def require_api_authentication(request: Request) -> None:
    expected = configured_token_digest()
    if expected is None:
        return

    authorization = request.headers.get("Authorization", "")
    if not authorization:
        session = read_admin_session(request)
        if session is None:
            raise _unauthorized()
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            require_admin_session(request, require_csrf=True)
        return

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized()

    actual = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise _unauthorized()
    await register_request_device(request)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="连接凭据无效",
        headers={"WWW-Authenticate": "Bearer"},
    )
