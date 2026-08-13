from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

ADMIN_PASSWORD_HASH_ENV = "QINGJUAN_ADMIN_PASSWORD_HASH"
ADMIN_SESSION_SECRET_ENV = "QINGJUAN_ADMIN_SESSION_SECRET"
ADMIN_SESSION_COOKIE = "qingjuan_admin_session"
ADMIN_CSRF_HEADER = "X-QingJuan-CSRF"
ADMIN_SESSION_TTL_SECONDS = 12 * 60 * 60
TRUST_LOCAL_ADMIN_ENV = "QINGJUAN_TRUST_LOCAL_ADMIN"
PASSWORD_HASH_ITERATIONS = 600_000

_PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
_SESSION_VERSION = "v1"
_SESSION_SECRET_PATTERN_LENGTH = 64
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_LOCAL_ADMIN_CSRF_TOKEN = secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class AdminSession:
    token: str
    issued_at: int
    expires_at: int
    csrf_token: str


def generate_admin_password() -> str:
    """Generate a high-entropy password that remains easy to paste in a browser."""

    return secrets.token_urlsafe(24)


def validate_admin_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("管理密码至少需要 12 个字符")
    if len(password) > 256:
        raise ValueError("管理密码不能超过 256 个字符")
    if not password.strip():
        raise ValueError("管理密码不能只包含空白字符")
    if any(ord(character) < 32 or ord(character) == 127 for character in password):
        raise ValueError("管理密码不能包含控制字符")


def hash_admin_password(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = PASSWORD_HASH_ITERATIONS,
) -> str:
    validate_admin_password(password)
    if iterations < 100_000:
        raise ValueError("密码哈希迭代次数过低")
    password_salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt,
        iterations,
    )
    return ":".join(
        (
            _PASSWORD_HASH_ALGORITHM,
            str(iterations),
            password_salt.hex(),
            derived.hex(),
        )
    )


def configured_admin_password_hash() -> str | None:
    value = os.getenv(ADMIN_PASSWORD_HASH_ENV, "").strip()
    if not value:
        return None
    _parse_password_hash(value)
    return value


def configured_admin_session_secret() -> bytes | None:
    value = os.getenv(ADMIN_SESSION_SECRET_ENV, "").strip().lower()
    if not value:
        return None
    if len(value) != _SESSION_SECRET_PATTERN_LENGTH:
        raise RuntimeError(f"{ADMIN_SESSION_SECRET_ENV} 必须是 64 位十六进制随机值")
    try:
        secret = bytes.fromhex(value)
    except ValueError as error:
        raise RuntimeError(f"{ADMIN_SESSION_SECRET_ENV} 必须是 64 位十六进制随机值") from error
    return secret


def validate_admin_auth_configuration() -> bool:
    password_hash = configured_admin_password_hash()
    session_secret = configured_admin_session_secret()
    if (password_hash is None) != (session_secret is None):
        raise RuntimeError(
            f"{ADMIN_PASSWORD_HASH_ENV} 与 {ADMIN_SESSION_SECRET_ENV} 必须同时配置"
        )
    return password_hash is not None


def verify_admin_password(password: str) -> bool:
    configured = configured_admin_password_hash()
    if configured is None:
        return False
    try:
        algorithm, iterations, salt, expected = _parse_password_hash(configured)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
    except (UnicodeError, ValueError):
        return False
    return algorithm == _PASSWORD_HASH_ALGORITHM and hmac.compare_digest(actual, expected)


def create_admin_session(*, now: int | None = None) -> AdminSession:
    secret = _required_session_secret()
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + ADMIN_SESSION_TTL_SECONDS
    nonce = _base64url_encode(secrets.token_bytes(24))
    unsigned = f"{_SESSION_VERSION}.{issued_at}.{expires_at}.{nonce}"
    signature = _sign(secret, unsigned)
    token = f"{unsigned}.{signature}"
    return AdminSession(
        token=token,
        issued_at=issued_at,
        expires_at=expires_at,
        csrf_token=_csrf_token(secret, token),
    )


def read_admin_session(request: Request, *, now: int | None = None) -> AdminSession | None:
    local_session = _trusted_local_admin_session(request, now=now)
    if local_session is not None:
        return local_session
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "").strip()
    if not token:
        return None
    return parse_admin_session(token, now=now)


def parse_admin_session(token: str, *, now: int | None = None) -> AdminSession | None:
    if len(token) > 256 or not token.isascii():
        return None
    try:
        version, issued_raw, expires_raw, nonce, signature = token.split(".")
        issued_at = int(issued_raw)
        expires_at = int(expires_raw)
    except (TypeError, ValueError):
        return None
    if (
        version != _SESSION_VERSION
        or not _BASE64URL_PATTERN.fullmatch(nonce)
        or not _BASE64URL_PATTERN.fullmatch(signature)
        or issued_at > expires_at
    ):
        return None

    current_time = int(time.time() if now is None else now)
    if issued_at > current_time + 60 or expires_at <= current_time:
        return None

    secret = configured_admin_session_secret()
    if secret is None:
        return None
    unsigned = f"{version}.{issued_at}.{expires_at}.{nonce}"
    if not hmac.compare_digest(signature, _sign(secret, unsigned)):
        return None
    return AdminSession(
        token=token,
        issued_at=issued_at,
        expires_at=expires_at,
        csrf_token=_csrf_token(secret, token),
    )


def require_admin_session(request: Request, *, require_csrf: bool = False) -> AdminSession:
    session = read_admin_session(request)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理会话已失效，请重新登录",
        )
    if require_csrf:
        submitted = request.headers.get(ADMIN_CSRF_HEADER, "")
        if not submitted or not hmac.compare_digest(submitted, session.csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="页面安全凭据已失效，请刷新后重试",
            )
    return session


def _trusted_local_admin_session(
    request: Request,
    *,
    now: int | None = None,
) -> AdminSession | None:
    if os.getenv(TRUST_LOCAL_ADMIN_ENV, "").strip() != "1":
        return None
    client = request.client
    if client is None:
        return None
    if not _is_loopback_address(client.host) or not _is_loopback_address(
        request.url.hostname or ""
    ):
        return None
    issued_at = int(time.time() if now is None else now)
    return AdminSession(
        token="local-desktop",
        issued_at=issued_at,
        expires_at=issued_at + ADMIN_SESSION_TTL_SECONDS,
        csrf_token=_LOCAL_ADMIN_CSRF_TOKEN,
    )


def _is_loopback_address(value: str) -> bool:
    host = value.strip().strip("[]")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def admin_cookie_secure(request: Request) -> bool:
    public_url = os.getenv("QINGJUAN_PUBLIC_URL", "").strip()
    return request.url.scheme == "https" or urlsplit(public_url).scheme == "https"


def _parse_password_hash(value: str) -> tuple[str, int, bytes, bytes]:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = value.split(":")
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_raw)
        digest = bytes.fromhex(digest_raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{ADMIN_PASSWORD_HASH_ENV} 格式无效") from error
    if (
        algorithm != _PASSWORD_HASH_ALGORITHM
        or iterations < 100_000
        or len(salt) < 16
        or len(digest) != hashlib.sha256().digest_size
    ):
        raise RuntimeError(f"{ADMIN_PASSWORD_HASH_ENV} 格式无效")
    return algorithm, iterations, salt, digest


def _required_session_secret() -> bytes:
    secret = configured_admin_session_secret()
    if secret is None:
        raise RuntimeError("管理界面认证尚未配置")
    return secret


def _sign(secret: bytes, value: str) -> str:
    return _base64url_encode(hmac.digest(secret, value.encode("ascii"), "sha256"))


def _csrf_token(secret: bytes, session_token: str) -> str:
    return _base64url_encode(
        hmac.digest(secret, f"csrf:{session_token}".encode("ascii"), "sha256")
    )


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
