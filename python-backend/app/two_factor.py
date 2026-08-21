from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import os
import re
import secrets
import time
from datetime import datetime
from urllib.parse import quote, urlencode

from Crypto.Cipher import AES

TWO_FACTOR_ENCRYPTION_KEY_ENV = "QINGJUAN_2FA_ENCRYPTION_KEY"

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_VALIDATION_WINDOW = 1
TOTP_SECRET_BYTES = 20

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 27

_TOTP_MODULUS = 10**TOTP_DIGITS
_MAX_TOTP_COUNTER = (1 << 64) - 1
_BASE32_PATTERN = re.compile(r"^[A-Z2-7]+$")
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RECOVERY_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_RECOVERY_PATTERN = re.compile(rf"^[{RECOVERY_CODE_ALPHABET}]{{{RECOVERY_CODE_LENGTH}}}$")

_ENCRYPTION_MAGIC = "qj2fa"
_ENCRYPTION_VERSION = "v2"
_ENCRYPTION_AAD = b"qingjuan/two-factor/totp-secret/v1"
_ENCRYPTION_KEY_DOMAIN = b"qingjuan/two-factor/totp-secret-key/v1"
_RECOVERY_KEY_DOMAIN = b"qingjuan/two-factor/recovery-code-key/v1"
_RECOVERY_HASH_PREFIX = "qj2fa-recovery:v2:"


def generate_totp_secret(*, byte_length: int = TOTP_SECRET_BYTES) -> str:
    """Return an unpadded RFC 4648 Base32 secret suitable for TOTP."""

    if not 16 <= byte_length <= 64:
        raise ValueError("TOTP 密钥长度需要在 16 到 64 字节之间")
    return base64.b32encode(secrets.token_bytes(byte_length)).decode("ascii").rstrip("=")


def generate_totp_code(
    secret: str,
    *,
    now: int | float | datetime | None = None,
    counter: int | None = None,
) -> str:
    """Generate a six-digit RFC 6238 HMAC-SHA1 code.

    ``counter`` is exposed for deterministic callers and tests. It is mutually
    exclusive with ``now``; normal callers should pass neither and use the
    current wall-clock time.
    """

    if counter is not None:
        if now is not None:
            raise ValueError("now 与 counter 不能同时指定")
        if not isinstance(counter, int) or isinstance(counter, bool) or not 0 <= counter <= _MAX_TOTP_COUNTER:
            raise ValueError("TOTP 计数器无效")
        accepted_counter = counter
    else:
        accepted_counter = _counter_for_time(now)
    return _code_for_counter(_decode_totp_secret(secret), accepted_counter)


def verify_totp_code(
    secret: str,
    code: str,
    *,
    now: int | float | datetime | None = None,
    last_counter: int | None = None,
    window: int = TOTP_VALIDATION_WINDOW,
) -> int | None:
    """Validate a TOTP code and return its accepted counter.

    By default the current, previous, and next 30-second steps are accepted.
    Supplying the last successfully consumed counter rejects that counter and
    every earlier one, allowing a database caller to prevent replay with an
    atomic compare-and-update.
    """

    if not isinstance(code, str) or len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
        return None
    if not isinstance(window, int) or isinstance(window, bool) or not 0 <= window <= 10:
        raise ValueError("TOTP 校验窗口需要在 0 到 10 之间")
    if last_counter is not None and (
        not isinstance(last_counter, int)
        or isinstance(last_counter, bool)
        or not 0 <= last_counter <= _MAX_TOTP_COUNTER
    ):
        raise ValueError("上次 TOTP 计数器无效")

    key = _decode_totp_secret(secret)
    current_counter = _counter_for_time(now)
    offsets = (0, *(offset for distance in range(1, window + 1) for offset in (-distance, distance)))
    for offset in offsets:
        candidate_counter = current_counter + offset
        if candidate_counter < 0 or (last_counter is not None and candidate_counter <= last_counter):
            continue
        if hmac.compare_digest(_code_for_counter(key, candidate_counter), code):
            return candidate_counter
    return None


def build_totp_uri(secret: str, *, account_name: str, issuer: str = "青卷") -> str:
    """Build an ``otpauth://`` URI for authenticator applications."""

    normalized_secret = _normalize_totp_secret(secret)
    normalized_account = _validate_label(account_name, "账号名称")
    normalized_issuer = _validate_label(issuer, "发行方")
    label = f"{quote(normalized_issuer, safe='')}:{quote(normalized_account, safe='')}"
    query = urlencode(
        {
            "secret": normalized_secret,
            "issuer": normalized_issuer,
            "algorithm": "SHA1",
            "digits": str(TOTP_DIGITS),
            "period": str(TOTP_PERIOD_SECONDS),
        }
    )
    return f"otpauth://totp/{label}?{query}"


def encrypt_totp_secret(secret: str, *, session_secret: str | bytes | None = None) -> str:
    """Encrypt a Base32 TOTP secret into a versioned AES-256-GCM envelope."""

    plaintext = _normalize_totp_secret(secret).encode("ascii")
    key = _derive_key(_ENCRYPTION_KEY_DOMAIN, session_secret)
    nonce = secrets.token_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
    cipher.update(_ENCRYPTION_AAD)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return ":".join(
        (
            _ENCRYPTION_MAGIC,
            _ENCRYPTION_VERSION,
            _base64url_encode(nonce),
            _base64url_encode(ciphertext),
            _base64url_encode(tag),
        )
    )


def decrypt_totp_secret(encrypted: str, *, session_secret: str | bytes | None = None) -> str:
    """Decrypt and authenticate a TOTP secret envelope.

    All malformed, unsupported, wrong-key, and tampered envelopes intentionally
    produce the same error so callers do not expose an authentication oracle.
    """

    error_message = "TOTP 密钥密文无效或已被篡改"
    try:
        magic, version, encoded_nonce, encoded_ciphertext, encoded_tag = encrypted.split(":")
        if magic != _ENCRYPTION_MAGIC or version != _ENCRYPTION_VERSION:
            raise ValueError(error_message)
        nonce = _base64url_decode(encoded_nonce)
        ciphertext = _base64url_decode(encoded_ciphertext)
        tag = _base64url_decode(encoded_tag)
        if len(nonce) != 12 or not ciphertext or len(tag) != 16:
            raise ValueError(error_message)

        key = _derive_key(_ENCRYPTION_KEY_DOMAIN, session_secret)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
        cipher.update(_ENCRYPTION_AAD)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return _normalize_totp_secret(plaintext.decode("ascii"))
    except (AttributeError, binascii.Error, UnicodeError, ValueError) as error:
        raise ValueError(error_message) from error


def generate_recovery_codes() -> list[str]:
    """Generate ten unique, human-readable recovery codes with at least 128 bits each."""

    codes: set[str] = set()
    while len(codes) < RECOVERY_CODE_COUNT:
        compact = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        codes.add("-".join(compact[index : index + 5] for index in range(0, RECOVERY_CODE_LENGTH, 5)))
    return list(codes)


def hash_recovery_code(code: str, *, session_secret: str | bytes | None = None) -> str:
    """Return a versioned keyed SHA-256 digest; the recovery code is not stored."""

    normalized = _normalize_recovery_code(code)
    key = _derive_key(_RECOVERY_KEY_DOMAIN, session_secret)
    digest = hmac.new(key, normalized.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{_RECOVERY_HASH_PREFIX}{digest}"


def hash_recovery_codes(
    codes: list[str] | tuple[str, ...],
    *,
    session_secret: str | bytes | None = None,
) -> list[str]:
    """Hash a newly generated recovery-code set for persistence."""

    return [hash_recovery_code(code, session_secret=session_secret) for code in codes]


def verify_recovery_code(
    code: str,
    stored_hash: str,
    *,
    session_secret: str | bytes | None = None,
) -> bool:
    """Verify a recovery code against its keyed digest."""

    if not isinstance(stored_hash, str) or not stored_hash.startswith(_RECOVERY_HASH_PREFIX):
        return False
    expected = stored_hash.removeprefix(_RECOVERY_HASH_PREFIX)
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        return False
    try:
        actual = hash_recovery_code(code, session_secret=session_secret).removeprefix(_RECOVERY_HASH_PREFIX)
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def _counter_for_time(now: int | float | datetime | None) -> int:
    if now is None:
        timestamp = time.time()
    elif isinstance(now, datetime):
        if now.tzinfo is None:
            raise ValueError("TOTP 时间必须包含时区")
        timestamp = now.timestamp()
    elif isinstance(now, bool):
        raise ValueError("TOTP 时间无效")
    else:
        timestamp = float(now)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("TOTP 时间无效")
    counter = int(timestamp) // TOTP_PERIOD_SECONDS
    if counter > _MAX_TOTP_COUNTER:
        raise ValueError("TOTP 时间无效")
    return counter


def _code_for_counter(key: bytes, counter: int) -> str:
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return f"{truncated % _TOTP_MODULUS:0{TOTP_DIGITS}d}"


def _normalize_totp_secret(secret: str) -> str:
    if not isinstance(secret, str):
        raise TypeError("TOTP 密钥必须是字符串")
    compact = "".join(secret.split()).replace("-", "").rstrip("=").upper()
    if not compact or len(compact) > 104 or _BASE32_PATTERN.fullmatch(compact) is None:
        raise ValueError("TOTP 密钥不是有效的 Base32 字符串")
    _decode_normalized_totp_secret(compact)
    return compact


def _decode_totp_secret(secret: str) -> bytes:
    return _decode_normalized_totp_secret(_normalize_totp_secret(secret))


def _decode_normalized_totp_secret(secret: str) -> bytes:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    try:
        decoded = base64.b32decode(secret + padding, casefold=False)
    except binascii.Error as error:
        raise ValueError("TOTP 密钥不是有效的 Base32 字符串") from error
    if not 10 <= len(decoded) <= 64:
        raise ValueError("TOTP 密钥长度需要在 10 到 64 字节之间")
    return decoded


def _validate_label(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name}必须是字符串")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 254
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValueError(f"{field_name}无效")
    return normalized


def _normalize_recovery_code(code: str) -> str:
    if not isinstance(code, str):
        raise TypeError("恢复码必须是字符串")
    compact = code.strip().replace("-", "").replace(" ", "").upper()
    if _RECOVERY_PATTERN.fullmatch(compact) is None:
        raise ValueError("恢复码格式无效")
    return compact


def _configured_root_secret(session_secret: str | bytes | None) -> bytes:
    value: str | bytes = (
        session_secret if session_secret is not None else os.getenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, "")
    )
    if isinstance(value, bytes):
        if len(value) != 32:
            raise RuntimeError(f"{TWO_FACTOR_ENCRYPTION_KEY_ENV} 必须是 64 位十六进制随机值")
        return value
    if not isinstance(value, str):
        raise TypeError("会话密钥必须是字符串或字节串")
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise RuntimeError(f"{TWO_FACTOR_ENCRYPTION_KEY_ENV} 必须是 64 位十六进制随机值")
    try:
        return bytes.fromhex(normalized)
    except ValueError as error:
        raise RuntimeError(f"{TWO_FACTOR_ENCRYPTION_KEY_ENV} 必须是 64 位十六进制随机值") from error


def validate_two_factor_encryption_key() -> None:
    _configured_root_secret(None)


def _derive_key(domain: bytes, session_secret: str | bytes | None) -> bytes:
    return hmac.new(_configured_root_secret(session_secret), domain, hashlib.sha256).digest()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    if not value or _BASE64URL_PATTERN.fullmatch(value) is None:
        raise ValueError("Base64URL 数据无效")
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)
