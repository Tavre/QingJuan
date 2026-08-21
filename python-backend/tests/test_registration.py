from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app import registration as registration_service
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
    verify_password_hash,
)
from app.api import auth as auth_api
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.application import create_application
from app.security import API_PREFIX

ADMIN_PASSWORD = "correct-admin-password"
USER_PASSWORD = "correct-user-password"


@pytest.fixture
def registration_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "1")
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(ADMIN_PASSWORD, salt=b"0123456789abcdef", iterations=100_000),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "77" * 32)
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    monkeypatch.setattr(db, "_SITE_PLUGIN_STATE_CACHE", None)
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db.init_db()
    return data_dir


def _application():
    return create_application(
        routers=[auth_router],
        public_routers=[admin_router],
        api_prefix=API_PREFIX,
    )


def _admin_csrf(client: TestClient) -> dict[str, str]:
    response = client.post("/admin/api/login", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200
    return {ADMIN_CSRF_HEADER: response.json()["csrfToken"]}


def _settings_payload(
    *,
    email_required: bool = False,
    badge_required: bool = False,
    smtp_password_action: str = "keep",
    smtp_password: str | None = None,
    badge_action: str = "keep",
    badge: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "emailVerificationRequired": email_required,
        "identityBadgeRequired": badge_required,
        "smtp": {
            "host": "smtp.example.test",
            "port": 587,
            "security": "starttls",
            "username": "mailer",
            "fromAddress": "noreply@example.test",
            "fromName": "青卷测试",
        },
        "smtpPasswordAction": smtp_password_action,
        "identityBadgeAction": badge_action,
    }
    if smtp_password is not None:
        payload["smtpPassword"] = smtp_password
    if badge is not None:
        payload["identityBadge"] = badge
    return payload


def test_public_policy_and_self_registration_require_unique_email(
    registration_database: Path,
) -> None:
    with TestClient(_application()) as client:
        policy = client.get(f"{API_PREFIX}/auth/registration-policy")
        assert policy.status_code == 200
        assert policy.json() == {
            "emailRequired": True,
            "emailVerificationRequired": False,
            "identityBadgeRequired": False,
            "githubLoginEnabled": False,
        }
        assert policy.headers["cache-control"] == "no-store"

        missing = client.post(
            f"{API_PREFIX}/auth/register",
            json={"username": "reader_one", "password": USER_PASSWORD},
        )
        assert missing.status_code == 422

        created = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "reader_one",
                "email": "Reader@One.Example",
                "password": USER_PASSWORD,
            },
        )
        assert created.status_code == 201
        assert created.json()["user"]["email"] == "Reader@one.example"

        duplicate = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "reader_two",
                "email": "reader@ONE.example",
                "password": USER_PASSWORD,
            },
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"] == "邮箱已被注册"


def test_registration_session_uses_creation_epoch_snapshot(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = Event()
    release = Event()
    original_issue_session = auth_api.issue_user_session
    replacement_hash = hash_admin_password(
        "replacement-user-password",
        salt=b"fedcba9876543210",
        iterations=100_000,
    )

    def blocking_issue_session(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_issue_session(*args, **kwargs)

    monkeypatch.setattr(auth_api, "issue_user_session", blocking_issue_session)
    with TestClient(_application()) as client, ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.post,
            f"{API_PREFIX}/auth/register",
            json={
                "username": "racing_reader",
                "email": "racing_reader@example.test",
                "password": USER_PASSWORD,
            },
        )
        assert entered.wait(timeout=5)
        created = db.get_user_by_email_key("racing_reader@example.test")
        assert created is not None
        assert db.update_user_password(
            created.id,
            replacement_hash,
            revoke_sessions=True,
        )
        release.set()
        response = future.result(timeout=5)

    assert response.status_code == 409, response.text
    with db.get_connection() as conn:
        session_count = conn.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id = ?",
            (created.id,),
        ).fetchone()[0]
    assert session_count == 0


def test_admin_settings_require_session_csrf_and_never_echo_secrets(
    registration_database: Path,
) -> None:
    application = _application()
    with TestClient(application) as client:
        assert client.get("/admin/api/registration-settings").status_code == 401
        headers = _admin_csrf(client)
        assert (
            client.put(
                "/admin/api/registration-settings",
                json=_settings_payload(),
            ).status_code
            == 403
        )
        response = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                badge_required=True,
                smtp_password_action="replace",
                smtp_password="smtp-super-secret",
                badge_action="replace",
                badge="fixed-badge-secret",
            ),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["registration"] == {
            "emailRequired": True,
            "emailVerificationRequired": True,
            "identityBadgeRequired": True,
            "identityBadgeConfigured": True,
        }
        assert body["smtp"]["passwordConfigured"] is True
        assert body["smtp"]["configured"] is True
        assert "smtp-super-secret" not in response.text
        assert "fixed-badge-secret" not in response.text

        fetched = client.get("/admin/api/registration-settings")
        assert fetched.status_code == 200
        assert "smtp-super-secret" not in fetched.text
        assert "fixed-badge-secret" not in fetched.text

        whitespace_password = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                badge_required=True,
                smtp_password_action="replace",
                smtp_password="  SMTP password with spaces  ",
            ),
        )
        assert whitespace_password.status_code == 200
        assert "SMTP password" not in whitespace_password.text

    with sqlite3.connect(db.DB_PATH) as connection:
        smtp_password, badge_hash = connection.execute(
            "SELECT smtp_password, identity_badge_hash FROM registration_settings WHERE id = 1"
        ).fetchone()
    assert smtp_password == "  SMTP password with spaces  "
    assert badge_hash != "fixed-badge-secret"
    assert verify_password_hash("identity-badge:fixed-badge-secret", badge_hash)


def test_enabling_requirements_rejects_incomplete_configuration(
    registration_database: Path,
) -> None:
    with TestClient(_application()) as client:
        headers = _admin_csrf(client)
        missing_smtp = _settings_payload(email_required=True)
        missing_smtp["smtp"] = {
            "host": "",
            "port": 587,
            "security": "starttls",
            "username": "",
            "fromAddress": "",
            "fromName": "青卷",
        }
        smtp_rejected = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=missing_smtp,
        )
        assert smtp_rejected.status_code == 400

        badge_rejected = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(badge_required=True),
        )
        assert badge_rejected.status_code == 400

        header_injection = _settings_payload()
        header_injection["smtp"] = {
            **header_injection["smtp"],  # type: ignore[dict-item]
            "fromName": "sender\r\nBcc: victim@example.test",
        }
        injected = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=header_injection,
        )
        assert injected.status_code == 400

        leaked_secret = "secret-that-must-never-be-reflected"
        invalid_secret = _settings_payload(
            smtp_password_action="replace",
            smtp_password=leaked_secret,
        )
        invalid_secret["emailVerificationRequired"] = "not-a-boolean"
        validation = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=invalid_secret,
        )
        assert validation.status_code == 422
        assert leaked_secret not in validation.text

        short_badge = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                badge_action="replace",
                badge="short",
            ),
        )
        assert short_badge.status_code == 400
        assert "8 到 128" in short_badge.json()["detail"]

        plaintext_auth = _settings_payload(
            smtp_password_action="replace",
            smtp_password="smtp-password",
        )
        plaintext_auth["smtp"] = {
            **plaintext_auth["smtp"],  # type: ignore[dict-item]
            "security": "none",
        }
        plaintext_rejected = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=plaintext_auth,
        )
        assert plaintext_rejected.status_code == 400
        assert "明文 SMTP" in plaintext_rejected.json()["detail"]


def test_secret_keep_merge_is_atomic_across_concurrent_admin_updates(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = registration_service.RegistrationSettingsPayload.model_validate(
        _settings_payload(
            smtp_password_action="replace",
            smtp_password="initial-smtp-password",
            badge_action="replace",
            badge="initial-badge",
        )
    )
    registration_service.update_registration_settings(initial)

    # A transactional implementation must read the current secrets on the same connection
    # used for its UPDATE; the old pre-transaction loader must never be consulted.
    monkeypatch.setattr(
        registration_service,
        "load_registration_settings",
        lambda: (_ for _ in ()).throw(AssertionError("stale settings read")),
    )
    replace_smtp = registration_service.RegistrationSettingsPayload.model_validate(
        _settings_payload(
            smtp_password_action="replace",
            smtp_password="concurrent-smtp-password",
        )
    )
    replace_badge = registration_service.RegistrationSettingsPayload.model_validate(
        _settings_payload(
            badge_action="replace",
            badge="concurrent-badge",
        )
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                registration_service.update_registration_settings,
                (replace_smtp, replace_badge),
            )
        )
    assert len(results) == 2

    with sqlite3.connect(db.DB_PATH) as connection:
        smtp_password, badge_hash = connection.execute(
            "SELECT smtp_password, identity_badge_hash FROM registration_settings WHERE id = 1"
        ).fetchone()
    assert smtp_password == "concurrent-smtp-password"
    assert verify_password_hash("identity-badge:concurrent-badge", badge_hash)


def test_email_code_and_identity_badge_are_combined_and_code_is_one_time(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[tuple[str, str]] = []

    def capture_email(settings, *, recipient: str, code: str) -> None:
        assert settings.smtp_password == "smtp-password"
        delivered.append((recipient, code))

    monkeypatch.setattr(auth_api, "send_verification_email", capture_email)
    with TestClient(_application()) as client:
        headers = _admin_csrf(client)
        configured = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                badge_required=True,
                smtp_password_action="replace",
                smtp_password="smtp-password",
                badge_action="replace",
                badge="access-badge",
            ),
        )
        assert configured.status_code == 200

        sent = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "reader@example.test"},
        )
        assert sent.status_code == 202
        assert sent.json()["expiresInSeconds"] == 600
        assert len(delivered) == 1
        recipient, code = delivered[0]
        assert recipient == "reader@example.test"
        assert len(code) == 6 and code.isdigit()

        wrong_badge = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "reader_one",
                "email": recipient,
                "password": USER_PASSWORD,
                "emailCode": code,
                "identityBadge": "wrong-badge",
            },
        )
        assert wrong_badge.status_code == 400
        assert wrong_badge.json()["detail"] == "身份牌验证失败"

        created = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "reader_one",
                "email": recipient,
                "password": USER_PASSWORD,
                "emailCode": code,
                "identityBadge": "access-badge",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["user"]["email"] == recipient

    with sqlite3.connect(db.DB_PATH) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM email_verification_codes WHERE email_key = ?",
            (recipient,),
        ).fetchone()[0]
    assert remaining == 0


def test_email_code_is_bound_to_email_limited_and_not_activated_on_send_failure(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: dict[str, str] = {}

    def capture_email(settings, *, recipient: str, code: str) -> None:
        delivered[recipient] = code

    monkeypatch.setattr(auth_api, "send_verification_email", capture_email)
    with TestClient(_application()) as client:
        headers = _admin_csrf(client)
        configured = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                smtp_password_action="replace",
                smtp_password="smtp-password",
            ),
        )
        assert configured.status_code == 200
        assert (
            client.post(
                f"{API_PREFIX}/auth/email-code",
                json={"email": "first@example.test"},
            ).status_code
            == 202
        )
        repeated = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "first@example.test"},
        )
        assert repeated.status_code == 429
        assert int(repeated.headers["retry-after"]) > 0

        wrong_email = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "wrong_email",
                "email": "second@example.test",
                "password": USER_PASSWORD,
                "emailCode": delivered["first@example.test"],
            },
        )
        assert wrong_email.status_code == 400
        assert "验证码" in wrong_email.json()["detail"]

    def fail_send(settings, *, recipient: str, code: str) -> None:
        raise OSError("smtp password and internal hostname must not escape")

    monkeypatch.setattr(auth_api, "send_verification_email", fail_send)
    with TestClient(_application()) as client:
        failed = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "failed@example.test"},
        )
        assert failed.status_code == 503
        assert "internal hostname" not in failed.text
        with sqlite3.connect(db.DB_PATH) as connection:
            stored = connection.execute(
                "SELECT active FROM email_verification_codes WHERE email_key = ?",
                ("failed@example.test",),
            ).fetchone()
        assert stored is None


def test_email_code_does_not_reveal_registered_email_or_send_to_it(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[str] = []

    def capture_email(settings, *, recipient: str, code: str) -> None:
        delivered.append(recipient)

    monkeypatch.setattr(auth_api, "send_verification_email", capture_email)
    with TestClient(_application()) as client:
        created = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "existing_reader",
                "email": "existing@example.test",
                "password": USER_PASSWORD,
            },
        )
        assert created.status_code == 201
        headers = _admin_csrf(client)
        configured = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                smtp_password_action="replace",
                smtp_password="smtp-password",
            ),
        )
        assert configured.status_code == 200

        existing = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "EXISTING@example.test"},
        )
        fresh = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "fresh@example.test"},
        )
        assert existing.status_code == fresh.status_code == 202
        assert existing.json() == fresh.json()
        assert delivered == ["fresh@example.test"]

        repeated_existing = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "existing@example.test"},
        )
        assert repeated_existing.status_code == 429

    with sqlite3.connect(db.DB_PATH) as connection:
        active = connection.execute(
            "SELECT active FROM email_verification_codes WHERE email_key = ?",
            ("existing@example.test",),
        ).fetchone()[0]
    assert active == 0


def test_email_code_wrong_attempt_limit_and_ip_limit(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: dict[str, str] = {}

    def capture_email(settings, *, recipient: str, code: str) -> None:
        delivered[recipient] = code

    monkeypatch.setattr(auth_api, "send_verification_email", capture_email)
    with TestClient(_application()) as client:
        headers = _admin_csrf(client)
        client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                email_required=True,
                smtp_password_action="replace",
                smtp_password="smtp-password",
            ),
        )
        for index in range(5):
            address = f"limited-{index}@example.test"
            assert (
                client.post(
                    f"{API_PREFIX}/auth/email-code",
                    json={"email": address},
                ).status_code
                == 202
            )
        blocked = client.post(
            f"{API_PREFIX}/auth/email-code",
            json={"email": "limited-last@example.test"},
        )
        assert blocked.status_code == 429

    with TestClient(_application()) as client:
        address = "attempts@example.test"
        assert client.post(f"{API_PREFIX}/auth/email-code", json={"email": address}).status_code == 202
        for _ in range(5):
            rejected = client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": "attempt_reader",
                    "email": address,
                    "password": USER_PASSWORD,
                    "emailCode": "999999",
                },
            )
            assert rejected.status_code == 400
        correct_after_limit = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "attempt_reader",
                "email": address,
                "password": USER_PASSWORD,
                "emailCode": delivered[address],
            },
        )
        assert correct_after_limit.status_code == 400


def test_registration_failure_limit_blocks_before_expensive_badge_check(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    badge_checks = 0

    def reject_badge(candidate: str, settings) -> bool:
        nonlocal badge_checks
        badge_checks += 1
        return False

    monkeypatch.setattr(auth_api, "verify_identity_badge", reject_badge)
    with TestClient(_application()) as client:
        headers = _admin_csrf(client)
        configured = client.put(
            "/admin/api/registration-settings",
            headers=headers,
            json=_settings_payload(
                badge_required=True,
                badge_action="replace",
                badge="access-badge",
            ),
        )
        assert configured.status_code == 200
        for index in range(10):
            rejected = client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": f"badge_reader_{index}",
                    "email": f"badge-{index}@example.test",
                    "password": USER_PASSWORD,
                    "identityBadge": "wrong-badge",
                },
            )
            assert rejected.status_code == 400
        blocked = client.post(
            f"{API_PREFIX}/auth/register",
            json={
                "username": "badge_reader_last",
                "email": "badge-last@example.test",
                "password": USER_PASSWORD,
                "identityBadge": "wrong-badge",
            },
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
    assert badge_checks == 10


def test_email_code_is_inactive_until_sent_and_expires(
    registration_database: Path,
) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    code_hash = registration_service.reserve_email_code(
        "expiry@example.test",
        "123456",
        now=now,
    )
    assert (
        registration_service.verify_email_code(
            "expiry@example.test",
            "123456",
            now=now,
        )
        is None
    )
    assert registration_service.activate_email_code("expiry@example.test", code_hash)
    assert (
        registration_service.verify_email_code(
            "expiry@example.test",
            "123456",
            now=now + timedelta(seconds=601),
        )
        is None
    )


@pytest.mark.parametrize(
    ("security", "uses_ssl", "uses_starttls"),
    [("none", False, False), ("starttls", False, True), ("ssl", True, False)],
)
def test_smtp_security_modes_and_password_preservation(
    monkeypatch: pytest.MonkeyPatch,
    security: str,
    uses_ssl: bool,
    uses_starttls: bool,
) -> None:
    events: list[tuple[str, object]] = []

    class FakeSmtp:
        def __init__(self, host: str, port: int, **kwargs: object) -> None:
            events.append(("connect", (host, port, "context" in kwargs)))

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def ehlo(self) -> None:
            events.append(("ehlo", True))

        def starttls(self, **kwargs: object) -> None:
            events.append(("starttls", "context" in kwargs))

        def login(self, username: str, password: str) -> None:
            events.append(("login", (username, password)))

        def send_message(self, message) -> None:
            events.append(("message", (message["To"], "123456" in message.get_content())))

    monkeypatch.setattr(registration_service.smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(registration_service.smtplib, "SMTP_SSL", FakeSmtp)
    settings = registration_service.StoredRegistrationSettings(
        email_verification_required=True,
        identity_badge_required=False,
        smtp_host="smtp.example.test",
        smtp_port=465 if uses_ssl else 587,
        smtp_security=security,  # type: ignore[arg-type]
        smtp_username="mailer",
        smtp_password="  preserved password  ",
        smtp_from_address="noreply@example.test",
        smtp_from_name="青卷",
        identity_badge_hash="",
    )
    registration_service.send_verification_email(
        settings,
        recipient="reader@example.test",
        code="123456",
    )

    assert ("login", ("mailer", "  preserved password  ")) in events
    assert ("message", ("reader@example.test", True)) in events
    assert any(event[0] == "starttls" for event in events) is uses_starttls
    assert events[0][1][2] is uses_ssl  # type: ignore[index]


def test_registration_endpoints_are_hidden_when_multi_user_is_disabled(
    registration_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "0")
    with TestClient(_application()) as client:
        assert client.get(f"{API_PREFIX}/auth/registration-policy").status_code == 404
        assert (
            client.post(
                f"{API_PREFIX}/auth/email-code",
                json={"email": "reader@example.test"},
            ).status_code
            == 404
        )
        assert client.get("/admin/api/registration-settings").status_code == 404
        assert client.get("/admin/api/users").status_code == 404
        assert (
            client.post(
                "/admin/api/users",
                json={"username": "hidden_user", "password": USER_PASSWORD},
            ).status_code
            == 404
        )
        assert (
            client.patch(
                "/admin/api/users/user-hidden",
                json={"displayName": "Hidden"},
            ).status_code
            == 404
        )
        assert (
            client.put(
                "/admin/api/users/user-hidden/password",
                json={"password": USER_PASSWORD},
            ).status_code
            == 404
        )
        assert client.post("/admin/api/users/user-hidden/sessions/revoke").status_code == 404


def test_legacy_user_schema_adds_nullable_unique_email_columns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    with sqlite3.connect(db.DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL,
                username_key TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, last_login_at TEXT
            )
            """
        )
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(users)")}
    assert {"email", "email_key"}.issubset(columns)
    assert "idx_users_email_key" in indexes
