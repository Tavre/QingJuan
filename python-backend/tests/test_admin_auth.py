import hashlib
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    TRUST_LOCAL_ADMIN_ENV,
    create_admin_session,
    hash_admin_password,
    parse_admin_session,
    verify_admin_password,
)
from app.admin_password import ensure_admin_session_secret, update_backend_environment
from app.api.admin import LoginAttemptLimiter
from app.api.admin import router as admin_router
from app.application import create_application
from app.connection_token import CONNECTION_TOKEN_FILE_ENV
from app.runtime_logs import RUNTIME_LOG_FILE_ENV
from app.security import API_PREFIX


def _configure_admin(monkeypatch, password: str = "correct-admin-password") -> None:
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(password, salt=b"0123456789abcdef", iterations=100_000),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "11" * 32)


def test_password_hash_uses_salt_and_does_not_store_plaintext(monkeypatch) -> None:
    password = "correct-admin-password"
    password_hash = hash_admin_password(password, salt=b"0123456789abcdef", iterations=100_000)
    monkeypatch.setenv(ADMIN_PASSWORD_HASH_ENV, password_hash)

    assert password not in password_hash
    assert verify_admin_password(password) is True
    assert verify_admin_password("incorrect-admin-password") is False


def test_admin_login_session_csrf_and_logout(monkeypatch) -> None:
    _configure_admin(monkeypatch)
    bearer_token = "client-bearer-token"
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(bearer_token.encode()).hexdigest(),
    )
    private_router = APIRouter()

    @private_router.get("/private")
    async def get_private() -> dict[str, str]:
        return {"status": "ok"}

    @private_router.post("/private")
    async def post_private() -> dict[str, str]:
        return {"status": "updated"}

    application = create_application(
        routers=[private_router],
        public_routers=[admin_router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )
    with TestClient(application) as client:
        login = client.post("/admin/api/login", json={"password": "correct-admin-password"})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]
        session = login.json()

        assert client.get(f"{API_PREFIX}/private").status_code == 200
        missing_csrf = client.post(f"{API_PREFIX}/private")
        accepted = client.post(
            f"{API_PREFIX}/private",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )
        bearer_accepted = client.post(
            f"{API_PREFIX}/private",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        logout = client.post(
            "/admin/api/logout",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )

        assert missing_csrf.status_code == 403
        assert accepted.status_code == 200
        assert bearer_accepted.status_code == 200
        assert logout.status_code == 204
        assert client.get(f"{API_PREFIX}/private").status_code == 401


def test_tampered_admin_session_is_rejected(monkeypatch) -> None:
    _configure_admin(monkeypatch)
    application = create_application(routers=[], public_routers=[admin_router])
    with TestClient(application) as client:
        response = client.post("/admin/api/login", json={"password": "correct-admin-password"})
        token = client.cookies.get("qingjuan_admin_session")

    assert response.status_code == 200
    assert token is not None
    assert parse_admin_session(token) is not None
    assert parse_admin_session(f"{token}x") is None
    assert parse_admin_session("v1.1.2.非ASCII.signature") is None


def test_explicit_desktop_mode_trusts_only_loopback_admin_requests(monkeypatch) -> None:
    monkeypatch.setenv(TRUST_LOCAL_ADMIN_ENV, "1")
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(
        application,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ) as local_client:
        session_response = local_client.get("/admin/api/session")
        session = session_response.json()
        missing_csrf = local_client.post("/admin/api/logout")
        accepted = local_client.post(
            "/admin/api/logout",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )

    with TestClient(application, client=("192.0.2.10", 50000)) as remote_client:
        rejected = remote_client.get("/admin/api/session")
    with TestClient(application, client=("127.0.0.1", 50000)) as rebound_client:
        rebound_rejected = rebound_client.get(
            "/admin/api/session",
            headers={"Host": "attacker.example"},
        )

    assert session_response.status_code == 200
    assert session["authenticated"] is True
    assert session["csrfToken"]
    assert missing_csrf.status_code == 403
    assert accepted.status_code == 204
    assert rejected.status_code == 401
    assert rebound_rejected.status_code == 401


def test_session_secret_rotation_invalidates_existing_session(monkeypatch) -> None:
    _configure_admin(monkeypatch)
    session = create_admin_session(now=1_800_000_000)

    assert parse_admin_session(session.token, now=1_800_000_001) is not None
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "33" * 32)
    assert parse_admin_session(session.token, now=1_800_000_001) is None


def test_login_attempt_limiter_recovers_after_window() -> None:
    limiter = LoginAttemptLimiter()
    for offset in range(5):
        limiter.record_failure("client", now=100 + offset)

    assert limiter.is_blocked("client", now=105) is True
    assert limiter.is_blocked("client", now=401) is False


def test_password_update_preserves_environment_and_rotates_sessions(tmp_path: Path) -> None:
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        "QINGJUAN_PORT=19453\n"
        f"{ADMIN_PASSWORD_HASH_ENV}=old-hash\n"
        f"{ADMIN_SESSION_SECRET_ENV}={'22' * 32}\n",
        encoding="utf-8",
    )

    update_backend_environment(backend_env, "new-admin-password")
    first = backend_env.read_text(encoding="utf-8")
    update_backend_environment(backend_env, "another-admin-password")
    second = backend_env.read_text(encoding="utf-8")

    assert "QINGJUAN_PORT=19453" in second
    assert "new-admin-password" not in first
    assert "another-admin-password" not in second
    assert first != second
    assert first.count(f"{ADMIN_PASSWORD_HASH_ENV}=") == 1
    assert second.count(f"{ADMIN_SESSION_SECRET_ENV}=") == 1


def test_missing_session_secret_can_be_repaired_without_changing_password(tmp_path: Path) -> None:
    password_hash = hash_admin_password(
        "existing-admin-password",
        salt=b"0123456789abcdef",
        iterations=100_000,
    )
    backend_env = tmp_path / "backend.env"
    backend_env.write_text(
        f"{ADMIN_PASSWORD_HASH_ENV}={password_hash}\nQINGJUAN_PORT=19453\n",
        encoding="utf-8",
    )

    ensure_admin_session_secret(backend_env)
    updated = backend_env.read_text(encoding="utf-8")

    assert f"{ADMIN_PASSWORD_HASH_ENV}={password_hash}" in updated
    assert f"{ADMIN_SESSION_SECRET_ENV}=" in updated


def test_connection_token_reveal_requires_admin_csrf_and_never_returns_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    connection_token = "0123456789abcdef" * 4
    token_file = tmp_path / "client.env"
    token_file.write_text(
        f"QINGJUAN_BACKEND_URL=https://qingjuan.example\n"
        f"QINGJUAN_CONNECTION_TOKEN={connection_token}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(connection_token.encode()).hexdigest(),
    )
    monkeypatch.setenv(CONNECTION_TOKEN_FILE_ENV, str(token_file))
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        assert client.get("/admin/api/connection-token").status_code == 401
        login = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        )
        session = login.json()
        status_response = client.get("/admin/api/connection-token")
        missing_csrf = client.post("/admin/api/connection-token/reveal")
        reveal = client.post(
            "/admin/api/connection-token/reveal",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )

    assert status_response.status_code == 200
    assert status_response.headers["cache-control"] == "no-store"
    status_payload = status_response.json()
    assert status_payload["configured"] is True
    assert status_payload["revealAvailable"] is True
    assert status_payload["maskedToken"].startswith(connection_token[:6])
    assert connection_token not in status_response.text
    assert missing_csrf.status_code == 403
    assert reveal.status_code == 200
    assert reveal.headers["cache-control"] == "no-store"
    assert reveal.json() == {"token": connection_token}


def test_connection_token_reveal_rejects_stale_file_without_leaking_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    stale_token = "a" * 64
    token_file = tmp_path / "client.env"
    token_file.write_text(
        f"QINGJUAN_CONNECTION_TOKEN={stale_token}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(("b" * 64).encode()).hexdigest(),
    )
    monkeypatch.setenv(CONNECTION_TOKEN_FILE_ENV, str(token_file))
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        login = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        ).json()
        status_response = client.get("/admin/api/connection-token")
        reveal = client.post(
            "/admin/api/connection-token/reveal",
            headers={ADMIN_CSRF_HEADER: login["csrfToken"]},
        )

    assert status_response.json()["revealAvailable"] is False
    assert reveal.status_code == 409
    assert stale_token not in reveal.text


def test_runtime_log_endpoint_requires_admin_session(monkeypatch, tmp_path: Path) -> None:
    _configure_admin(monkeypatch)
    log_file = tmp_path / "server.jsonl"
    log_file.write_text(
        '{"timestamp":"2030-01-01T00:00:00Z","level":"info",'
        '"source":"qingjuan.runtime","message":"服务启动完成"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(RUNTIME_LOG_FILE_ENV, str(log_file))
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        rejected = client.get("/admin/api/runtime-logs")
        client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        )
        accepted = client.get("/admin/api/runtime-logs?limit=50")

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.headers["cache-control"] == "no-store"
    assert accepted.json()["items"][0]["message"] == "服务启动完成"


def test_application_serves_built_admin_files(tmp_path: Path) -> None:
    admin_static = tmp_path / "admin"
    admin_static.mkdir()
    assets = admin_static / "assets"
    assets.mkdir()
    (admin_static / "index.html").write_text("<h1>青卷管理界面</h1>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('admin')", encoding="utf-8")
    application = create_application(routers=[], admin_static_path=admin_static)

    with TestClient(application) as client:
        response = client.get("/admin/")
        asset_response = client.get("/admin/assets/app.js")

    assert response.status_code == 200
    assert "青卷管理界面" in response.text
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert asset_response.status_code == 200
    assert asset_response.headers["cache-control"] == "public, max-age=31536000, immutable"
