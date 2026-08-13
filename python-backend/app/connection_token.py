from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .security import configured_token_digest

CONNECTION_TOKEN_FILE_ENV = "QINGJUAN_CONNECTION_TOKEN_FILE"
_CLIENT_TOKEN_KEY = "QINGJUAN_CONNECTION_TOKEN"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{20,512}$")
_MAX_CONNECTION_FILE_BYTES = 4096


@dataclass(frozen=True, slots=True)
class ConnectionTokenState:
    configured: bool
    reveal_available: bool
    masked_token: str | None
    fingerprint: str | None


class ConnectionTokenUnavailable(RuntimeError):
    pass


def get_connection_token_state() -> ConnectionTokenState:
    expected_digest = configured_token_digest()
    if expected_digest is None:
        return ConnectionTokenState(
            configured=False,
            reveal_available=False,
            masked_token=None,
            fingerprint=None,
        )
    try:
        token = read_connection_token()
    except ConnectionTokenUnavailable:
        token = None
    return ConnectionTokenState(
        configured=True,
        reveal_available=token is not None,
        masked_token=_mask_token(token) if token is not None else None,
        fingerprint=expected_digest[:12],
    )


def read_connection_token() -> str:
    expected_digest = configured_token_digest()
    if expected_digest is None:
        raise ConnectionTokenUnavailable("连接 Token 未配置")
    configured_path = os.getenv(CONNECTION_TOKEN_FILE_ENV, "").strip()
    if not configured_path:
        raise ConnectionTokenUnavailable("当前部署不支持显示连接 Token")
    token = _read_token_file(Path(configured_path).expanduser())
    actual_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise ConnectionTokenUnavailable("连接 Token 文件与认证摘要不一致")
    return token


def _read_token_file(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = handle.read(_MAX_CONNECTION_FILE_BYTES + 1)
    except (OSError, UnicodeError) as error:
        raise ConnectionTokenUnavailable("连接 Token 文件不可读取") from error
    if len(payload.encode("utf-8")) > _MAX_CONNECTION_FILE_BYTES:
        raise ConnectionTokenUnavailable("连接 Token 文件格式无效")

    token = ""
    for line in payload.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == _CLIENT_TOKEN_KEY:
            token = value.strip()
            break
    if not token and len(payload.splitlines()) == 1 and "=" not in payload:
        token = payload.strip()
    if not _TOKEN_PATTERN.fullmatch(token):
        raise ConnectionTokenUnavailable("连接 Token 文件格式无效")
    return token


def _mask_token(token: str) -> str:
    return f"{token[:6]}••••••••{token[-6:]}"
