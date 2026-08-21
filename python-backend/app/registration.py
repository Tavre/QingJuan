from __future__ import annotations

import hashlib
import re
import secrets
import smtplib
import sqlite3
import ssl
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .admin_auth import hash_admin_password, verify_password_hash
from .db import get_connection

EMAIL_CODE_TTL_SECONDS = 10 * 60
EMAIL_CODE_RESEND_SECONDS = 60
EMAIL_CODE_MAX_ATTEMPTS = 5
EMAIL_CODE_ITERATIONS = 150_000

SmtpSecurity = Literal["none", "starttls", "ssl"]
SecretAction = Literal["keep", "replace", "clear"]


class RegistrationPolicy(BaseModel):
    emailRequired: bool = True
    emailVerificationRequired: bool
    identityBadgeRequired: bool
    githubLoginEnabled: bool


class RegistrationRequirementsView(BaseModel):
    emailRequired: bool = True
    emailVerificationRequired: bool
    identityBadgeRequired: bool
    identityBadgeConfigured: bool


class SmtpSettingsView(BaseModel):
    host: str
    port: int
    security: SmtpSecurity
    username: str
    fromAddress: str
    fromName: str
    passwordConfigured: bool
    configured: bool


class GitHubSettingsView(BaseModel):
    enabled: bool
    clientId: str
    configured: bool


class RegistrationSettingsView(BaseModel):
    registration: RegistrationRequirementsView
    smtp: SmtpSettingsView
    github: GitHubSettingsView


class GitHubSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    clientId: str = Field(default="", max_length=128)


class SmtpSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="", max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    security: SmtpSecurity = "starttls"
    username: str = Field(default="", max_length=254)
    fromAddress: str = Field(default="", max_length=254)
    fromName: str = Field(default="青卷", max_length=128)


class RegistrationSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emailVerificationRequired: bool
    identityBadgeRequired: bool
    smtp: SmtpSettingsPayload
    smtpPasswordAction: SecretAction = "keep"
    smtpPassword: SecretStr | None = Field(default=None, max_length=1024)
    identityBadgeAction: SecretAction = "keep"
    identityBadge: SecretStr | None = Field(default=None, max_length=128)
    github: GitHubSettingsPayload | None = None


@dataclass(frozen=True, slots=True)
class StoredRegistrationSettings:
    email_verification_required: bool
    identity_badge_required: bool
    smtp_host: str
    smtp_port: int
    smtp_security: SmtpSecurity
    smtp_username: str
    smtp_password: str
    smtp_from_address: str
    smtp_from_name: str
    identity_badge_hash: str
    github_enabled: bool = False
    github_client_id: str = ""
    github_config_revision: int = 0

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self.smtp_host and self.smtp_from_address and (not self.smtp_username or self.smtp_password)
        )


class EmailCodeRateLimited(ValueError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("验证码发送过于频繁，请稍后再试")
        self.retry_after = max(1, retry_after)


def normalize_email(value: str) -> tuple[str, str]:
    email = unicodedata.normalize("NFKC", value).strip()
    if not email or len(email) > 254 or email.count("@") != 1:
        raise ValueError("请输入有效的邮箱地址")
    local, domain = email.rsplit("@", 1)
    if not local or len(local) > 64 or not domain:
        raise ValueError("请输入有效的邮箱地址")
    if local[0] == "." or local[-1] == "." or ".." in local:
        raise ValueError("请输入有效的邮箱地址")
    forbidden_local = frozenset('()<>[]:;,\\"')
    if any(
        character.isspace() or not character.isprintable() or character in forbidden_local
        for character in local
    ):
        raise ValueError("请输入有效的邮箱地址")
    try:
        ascii_domain = domain.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("请输入有效的邮箱地址") from error
    labels = ascii_domain.split(".")
    if (
        not ascii_domain
        or len(ascii_domain) > 253
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or any(not (character.isalnum() or character == "-") for character in label)
            for label in labels
        )
    ):
        raise ValueError("请输入有效的邮箱地址")
    normalized = f"{local}@{ascii_domain}"
    return normalized, normalized.casefold()


def load_registration_settings() -> StoredRegistrationSettings:
    with get_connection() as conn:
        row = _select_registration_settings(conn)
    if row is None:
        raise RuntimeError("注册设置尚未初始化")
    return _stored_settings_from_row(row)


def _select_registration_settings(conn: sqlite3.Connection) -> tuple[object, ...] | None:
    return conn.execute(
        """
        SELECT email_verification_required, identity_badge_required,
               smtp_host, smtp_port, smtp_security, smtp_username,
               smtp_password, smtp_from_address, smtp_from_name,
               identity_badge_hash, github_enabled, github_client_id,
               github_config_revision
        FROM registration_settings
        WHERE id = 1
        """
    ).fetchone()


def _stored_settings_from_row(row: tuple[object, ...]) -> StoredRegistrationSettings:
    security = str(row[4])
    if security not in {"none", "starttls", "ssl"}:
        security = "starttls"
    return StoredRegistrationSettings(
        email_verification_required=bool(row[0]),
        identity_badge_required=bool(row[1]),
        smtp_host=str(row[2] or ""),
        smtp_port=int(row[3] or 587),
        smtp_security=security,  # type: ignore[arg-type]
        smtp_username=str(row[5] or ""),
        smtp_password=str(row[6] or ""),
        smtp_from_address=str(row[7] or ""),
        smtp_from_name=str(row[8] or "青卷"),
        identity_badge_hash=str(row[9] or ""),
        github_enabled=bool(row[10]),
        github_client_id=str(row[11] or ""),
        github_config_revision=int(row[12] or 0),
    )


def registration_policy() -> RegistrationPolicy:
    settings = load_registration_settings()
    return RegistrationPolicy(
        emailVerificationRequired=settings.email_verification_required,
        identityBadgeRequired=settings.identity_badge_required,
        githubLoginEnabled=settings.github_enabled and bool(settings.github_client_id),
    )


def registration_settings_view(
    settings: StoredRegistrationSettings | None = None,
) -> RegistrationSettingsView:
    current = settings or load_registration_settings()
    return RegistrationSettingsView(
        registration=RegistrationRequirementsView(
            emailVerificationRequired=current.email_verification_required,
            identityBadgeRequired=current.identity_badge_required,
            identityBadgeConfigured=bool(current.identity_badge_hash),
        ),
        smtp=SmtpSettingsView(
            host=current.smtp_host,
            port=current.smtp_port,
            security=current.smtp_security,
            username=current.smtp_username,
            fromAddress=current.smtp_from_address,
            fromName=current.smtp_from_name,
            passwordConfigured=bool(current.smtp_password),
            configured=current.smtp_configured,
        ),
        github=GitHubSettingsView(
            enabled=current.github_enabled,
            clientId=current.github_client_id,
            configured=bool(current.github_client_id),
        ),
    )


def update_registration_settings(payload: RegistrationSettingsPayload) -> RegistrationSettingsView:
    smtp = payload.smtp
    host = _safe_header_value(smtp.host, field_name="SMTP 主机", allow_empty=True)
    username = _safe_header_value(smtp.username, field_name="SMTP 用户名", allow_empty=True)
    from_name = _safe_header_value(smtp.fromName, field_name="发件人名称", allow_empty=True)
    from_address = ""
    if smtp.fromAddress.strip():
        from_address, _ = normalize_email(smtp.fromAddress)
    if smtp.security == "none" and (username or payload.smtpPasswordAction == "replace"):
        raise ValueError("明文 SMTP 不允许使用用户名或密码认证，请使用 TLS 或无认证本地中继")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _select_registration_settings(conn)
        if row is None:
            raise RuntimeError("注册设置尚未初始化")
        current = _stored_settings_from_row(row)
        if payload.github is None:
            github_enabled = current.github_enabled
            github_client_id = current.github_client_id
        else:
            github_enabled = payload.github.enabled
            github_client_id = payload.github.clientId.strip()
            if github_client_id and re.fullmatch(r"[A-Za-z0-9._-]{10,128}", github_client_id) is None:
                raise ValueError("GitHub Client ID 格式无效")
            if github_enabled and not github_client_id:
                raise ValueError("启用 GitHub 登录前，请先配置 Client ID")
        github_config_revision = current.github_config_revision
        if github_enabled != current.github_enabled or github_client_id != current.github_client_id:
            github_config_revision += 1
        smtp_password = _updated_secret(
            current.smtp_password,
            action=payload.smtpPasswordAction,
            supplied=payload.smtpPassword,
            field_name="SMTP 密码",
            minimum_length=1,
            maximum_length=1024,
            normalize=False,
        )
        identity_badge = _updated_secret(
            "",
            action=payload.identityBadgeAction,
            supplied=payload.identityBadge,
            field_name="身份牌",
            minimum_length=8,
            maximum_length=128,
            keep_value=None,
            invalid_message="身份牌长度需要在 8 到 128 个字符之间，且不能包含控制字符",
        )
        if payload.identityBadgeAction == "keep":
            identity_badge_hash = current.identity_badge_hash
        elif payload.identityBadgeAction == "clear":
            identity_badge_hash = ""
        else:
            identity_badge_hash = _hash_identity_badge(identity_badge)

        next_settings = StoredRegistrationSettings(
            email_verification_required=payload.emailVerificationRequired,
            identity_badge_required=payload.identityBadgeRequired,
            smtp_host=host,
            smtp_port=smtp.port,
            smtp_security=smtp.security,
            smtp_username=username,
            smtp_password=smtp_password,
            smtp_from_address=from_address,
            smtp_from_name=from_name or "青卷",
            identity_badge_hash=identity_badge_hash,
            github_enabled=github_enabled,
            github_client_id=github_client_id,
            github_config_revision=github_config_revision,
        )
        if next_settings.email_verification_required and not next_settings.smtp_configured:
            raise ValueError("启用邮箱验证码注册前，请完整配置 SMTP 服务")
        if next_settings.identity_badge_required and not next_settings.identity_badge_hash:
            raise ValueError("启用身份牌注册前，请先设置身份牌")
        conn.execute(
            """
            UPDATE registration_settings
            SET email_verification_required = ?, identity_badge_required = ?,
                smtp_host = ?, smtp_port = ?, smtp_security = ?,
                smtp_username = ?, smtp_password = ?, smtp_from_address = ?,
                smtp_from_name = ?, identity_badge_hash = ?, updated_at = ?,
                github_enabled = ?, github_client_id = ?, github_config_revision = ?
            WHERE id = 1
            """,
            (
                int(next_settings.email_verification_required),
                int(next_settings.identity_badge_required),
                next_settings.smtp_host,
                next_settings.smtp_port,
                next_settings.smtp_security,
                next_settings.smtp_username,
                next_settings.smtp_password,
                next_settings.smtp_from_address,
                next_settings.smtp_from_name,
                next_settings.identity_badge_hash,
                _datetime_text(datetime.now(UTC)),
                int(next_settings.github_enabled),
                next_settings.github_client_id,
                next_settings.github_config_revision,
            ),
        )
    return registration_settings_view(next_settings)


def verify_identity_badge(candidate: str, settings: StoredRegistrationSettings) -> bool:
    normalized = unicodedata.normalize("NFKC", candidate).strip()
    if (
        not settings.identity_badge_hash
        or not 8 <= len(normalized) <= 128
        or any(not character.isprintable() for character in normalized)
    ):
        return False
    return verify_password_hash(f"identity-badge:{normalized}", settings.identity_badge_hash)


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def reserve_email_code(email_key: str, code: str, *, now: datetime | None = None) -> str:
    sent_at = (now or datetime.now(UTC)).astimezone(UTC)
    salt = secrets.token_bytes(16)
    code_hash = _email_code_hash(code, salt)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM email_verification_codes WHERE expires_at <= ?",
            (_datetime_text(sent_at),),
        )
        existing = conn.execute(
            "SELECT last_sent_at FROM email_verification_codes WHERE email_key = ?",
            (email_key,),
        ).fetchone()
        if existing is not None:
            elapsed = (sent_at - _parse_datetime(str(existing[0]))).total_seconds()
            if elapsed < EMAIL_CODE_RESEND_SECONDS:
                raise EmailCodeRateLimited(int(EMAIL_CODE_RESEND_SECONDS - elapsed + 0.999))
        conn.execute(
            """
            INSERT INTO email_verification_codes (
                email_key, code_hash, code_salt, expires_at,
                attempts_remaining, last_sent_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(email_key) DO UPDATE SET
                code_hash = excluded.code_hash,
                code_salt = excluded.code_salt,
                expires_at = excluded.expires_at,
                attempts_remaining = excluded.attempts_remaining,
                last_sent_at = excluded.last_sent_at,
                active = 0
            """,
            (
                email_key,
                code_hash,
                salt.hex(),
                _datetime_text(sent_at + timedelta(seconds=EMAIL_CODE_TTL_SECONDS)),
                EMAIL_CODE_MAX_ATTEMPTS,
                _datetime_text(sent_at),
            ),
        )
    return code_hash


def activate_email_code(email_key: str, code_hash: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE email_verification_codes SET active = 1 WHERE email_key = ? AND code_hash = ?",
            (email_key, code_hash),
        )
    return cursor.rowcount == 1


def discard_email_code(email_key: str, code_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM email_verification_codes WHERE email_key = ? AND code_hash = ?",
            (email_key, code_hash),
        )


def verify_email_code(
    email_key: str,
    candidate: str,
    *,
    now: datetime | None = None,
) -> str | None:
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT code_hash, code_salt, expires_at, attempts_remaining, active
            FROM email_verification_codes
            WHERE email_key = ?
            """,
            (email_key,),
        ).fetchone()
        if row is None or not bool(row[4]):
            return None
        if _parse_datetime(str(row[2])) <= checked_at:
            conn.execute("DELETE FROM email_verification_codes WHERE email_key = ?", (email_key,))
            return None
        expected_hash = str(row[0])
        try:
            salt = bytes.fromhex(str(row[1]))
        except ValueError:
            conn.execute("DELETE FROM email_verification_codes WHERE email_key = ?", (email_key,))
            return None
        candidate_hash = _email_code_hash(candidate, salt)
        if secrets.compare_digest(expected_hash, candidate_hash):
            return expected_hash
        attempts_remaining = int(row[3]) - 1
        if attempts_remaining <= 0:
            conn.execute("DELETE FROM email_verification_codes WHERE email_key = ?", (email_key,))
        else:
            conn.execute(
                "UPDATE email_verification_codes SET attempts_remaining = ? WHERE email_key = ?",
                (attempts_remaining, email_key),
            )
        return None


def consume_email_code(email_key: str, code_hash: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM email_verification_codes WHERE email_key = ? AND code_hash = ? AND active = 1",
            (email_key, code_hash),
        )
    return cursor.rowcount == 1


def send_verification_email(
    settings: StoredRegistrationSettings,
    *,
    recipient: str,
    code: str,
) -> None:
    if not settings.smtp_configured:
        raise RuntimeError("SMTP 服务尚未完整配置")
    message = EmailMessage()
    message["Subject"] = "青卷注册验证码"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
    message["To"] = recipient
    message.set_content(
        f"您的青卷注册验证码是：{code}\n\n"
        f"验证码 {EMAIL_CODE_TTL_SECONDS // 60} 分钟内有效。"
        "如非本人操作，请忽略此邮件。"
    )
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=15,
            context=context,
        ) as client:
            _smtp_deliver(client, settings, message)
        return
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.ehlo()
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
            client.ehlo()
        _smtp_deliver(client, settings, message)


def _smtp_deliver(
    client: smtplib.SMTP,
    settings: StoredRegistrationSettings,
    message: EmailMessage,
) -> None:
    if settings.smtp_username:
        client.login(settings.smtp_username, settings.smtp_password)
    client.send_message(message)


def _safe_header_value(value: str, *, field_name: str, allow_empty: bool) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized and allow_empty:
        return ""
    if not normalized or any(not character.isprintable() for character in normalized):
        raise ValueError(f"{field_name}无效")
    return normalized


def _updated_secret(
    current: str,
    *,
    action: SecretAction,
    supplied: SecretStr | None,
    field_name: str,
    minimum_length: int,
    maximum_length: int,
    keep_value: str | None = "current",
    normalize: bool = True,
    invalid_message: str | None = None,
) -> str:
    value = supplied.get_secret_value() if supplied is not None else None
    if action == "keep":
        if value is not None:
            raise ValueError(f"{field_name}操作为 keep 时不应提交新值")
        return current if keep_value is not None else ""
    if action == "clear":
        if value is not None:
            raise ValueError(f"{field_name}操作为 clear 时不应提交新值")
        return ""
    if value is None:
        raise ValueError(f"{field_name}操作为 replace 时必须提交新值")
    normalized = unicodedata.normalize("NFKC", value).strip() if normalize else value
    if not minimum_length <= len(normalized) <= maximum_length or any(
        not character.isprintable() for character in normalized
    ):
        raise ValueError(invalid_message or f"{field_name}无效")
    return normalized


def _email_code_hash(code: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt,
        EMAIL_CODE_ITERATIONS,
    ).hex()


def _hash_identity_badge(value: str) -> str:
    return hash_admin_password(f"identity-badge:{value}")


def _datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
