from __future__ import annotations

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.account_security import generate_recovery_code_material
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api import auth_security as security_api
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.application import create_application
from app.github_auth import (
    GITHUB_ACCESS_TOKEN_URL,
    GITHUB_DEVICE_CODE_URL,
    GITHUB_USER_URL,
    GITHUB_VERIFICATION_URI,
    GitHubDeviceAuthorization,
    GitHubDeviceFlowStore,
    GitHubDeviceTokenResult,
    GitHubIdentity,
    fetch_github_identity,
    poll_github_device_token,
    start_github_device_authorization,
)
from app.security import API_PREFIX
from app.two_factor import (
    TWO_FACTOR_ENCRYPTION_KEY_ENV,
    encrypt_totp_secret,
    generate_totp_code,
    generate_totp_secret,
)

ADMIN_PASSWORD = "correct-admin-password"
USER_PASSWORD = "correct-user-password"
GITHUB_CLIENT_ID = "Ov23liABCDEFGHIJKLMN"
ACCESS_TOKEN = "github-access-token-must-not-leak"


@pytest.fixture
def github_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "1")
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(ADMIN_PASSWORD, salt=b"0123456789abcdef", iterations=100_000),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "77" * 32)
    monkeypatch.setenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, "99" * 32)
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    monkeypatch.setattr(db, "_SITE_PLUGIN_STATE_CACHE", None)
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    data_dir.mkdir(parents=True)
    db.init_db()
    return data_dir


def _application(*, include_admin: bool = False):
    return create_application(
        routers=[auth_router],
        public_routers=[admin_router] if include_admin else [],
        api_prefix=API_PREFIX,
    )


def _create_user(username: str) -> None:
    db.create_user(
        user_id=f"user-{username}",
        username=username,
        username_key=username,
        email=f"{username}@example.test",
        email_key=f"{username}@example.test",
        display_name=username.title(),
        password_hash=hash_admin_password(
            USER_PASSWORD,
            salt=(username.encode("ascii") + b"0" * 16)[:16],
            iterations=100_000,
        ),
    )


def _set_github(*, enabled: bool, client_id: str = GITHUB_CLIENT_ID) -> None:
    with db.get_connection() as conn:
        current = conn.execute(
            "SELECT github_enabled, github_client_id, github_config_revision "
            "FROM registration_settings WHERE id = 1"
        ).fetchone()
        assert current is not None
        changed = bool(current[0]) != enabled or str(current[1]) != client_id
        conn.execute(
            "UPDATE registration_settings SET github_enabled = ?, github_client_id = ?, "
            "github_config_revision = ? WHERE id = 1",
            (int(enabled), client_id, int(current[2]) + int(changed)),
        )


def _login(client: TestClient, username: str) -> dict[str, object]:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": username, "password": USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token: object) -> dict[str, str]:
    assert isinstance(token, str)
    return {"X-QingJuan-User-Token": token}


def _session_hash(token: object) -> str:
    assert isinstance(token, str)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _allow_poll(client: TestClient, flow_id: str) -> None:
    client.app.state.github_device_flow_store._flows[flow_id].next_poll_at = 0


@pytest.mark.asyncio
async def test_github_http_client_uses_only_official_hosts_and_no_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == GITHUB_DEVICE_CODE_URL:
            assert parse_qs(request.content.decode("ascii")) == {"client_id": [GITHUB_CLIENT_ID]}
            return httpx.Response(
                200,
                request=request,
                json={
                    "device_code": "device-secret",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                    "interval": 5,
                },
            )
        if str(request.url) == GITHUB_ACCESS_TOKEN_URL:
            body = parse_qs(request.content.decode("ascii"))
            assert body == {
                "client_id": [GITHUB_CLIENT_ID],
                "device_code": ["device-secret"],
                "grant_type": ["urn:ietf:params:oauth:grant-type:device_code"],
            }
            assert "scope" not in body
            return httpx.Response(
                200,
                request=request,
                json={"access_token": ACCESS_TOKEN, "token_type": "bearer", "scope": ""},
            )
        assert str(request.url) == GITHUB_USER_URL
        assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        return httpx.Response(200, request=request, json={"id": 123456789, "login": "octocat"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        authorization = await start_github_device_authorization(GITHUB_CLIENT_ID, client=client)
        assert authorization.verification_uri == GITHUB_VERIFICATION_URI
        token_result = await poll_github_device_token(
            GITHUB_CLIENT_ID,
            authorization.device_code,
            client=client,
        )
        identity = await fetch_github_identity(token_result.access_token or "", client=client)
    assert identity == GitHubIdentity(user_id="123456789", login="octocat")
    assert [request.url.host for request in requests] == ["github.com", "github.com", "api.github.com"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("github_error", "expected_status"),
    [
        ("authorization_pending", "pending"),
        ("slow_down", "slow_down"),
        ("expired_token", "expired"),
        ("access_denied", "denied"),
        ("device_flow_disabled", "disabled"),
    ],
)
async def test_github_device_errors_are_mapped(
    github_error: str,
    expected_status: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"error": github_error})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await poll_github_device_token(
            GITHUB_CLIENT_ID,
            "device-secret",
            client=client,
        )
    assert result.status == expected_status
    assert result.access_token is None


def test_device_flow_store_enforces_interval_slow_down_expiry_and_one_time() -> None:
    store = GitHubDeviceFlowStore()
    flow = store.create(
        purpose="login",
        user_id=None,
        device_code="device-secret",
        client_id=GITHUB_CLIENT_ID,
        config_revision=1,
        auth_epoch=None,
        expires_in=600,
        interval=5,
        now=100,
    )
    _, retry_after = store.reserve_poll(flow.flow_id, now=101)
    assert retry_after == 4
    _, retry_after = store.reserve_poll(flow.flow_id, now=105)
    assert retry_after is None
    assert store.slow_down(flow.flow_id, now=105) == 10
    _, retry_after = store.reserve_poll(flow.flow_id, now=106)
    assert retry_after == 9
    assert store.consume(flow.flow_id) == flow
    with pytest.raises(KeyError):
        store.consume(flow.flow_id)

    expired = store.create(
        purpose="login",
        user_id=None,
        device_code="expired-secret",
        client_id=GITHUB_CLIENT_ID,
        config_revision=1,
        auth_epoch=None,
        expires_in=60,
        interval=5,
        now=200,
    )
    with pytest.raises(TimeoutError):
        store.reserve_poll(expired.flow_id, now=260)


def test_github_bind_login_unique_binding_and_two_factor(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice")
    _create_user("bob")
    _set_github(enabled=True)
    start_calls = 0
    poll_calls = 0
    identity_login = "octocat"

    async def fake_start(client_id: str) -> GitHubDeviceAuthorization:
        nonlocal start_calls
        start_calls += 1
        assert client_id == GITHUB_CLIENT_ID
        return GitHubDeviceAuthorization(
            device_code=f"device-secret-{start_calls}",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    async def fake_poll(client_id: str, device_code: str) -> GitHubDeviceTokenResult:
        nonlocal poll_calls
        poll_calls += 1
        assert client_id == GITHUB_CLIENT_ID
        assert device_code.startswith("device-secret-")
        return GitHubDeviceTokenResult(status="authorized", access_token=ACCESS_TOKEN)

    async def fake_identity(access_token: str) -> GitHubIdentity:
        assert access_token == ACCESS_TOKEN
        return GitHubIdentity(user_id="123456789", login=identity_login)

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    monkeypatch.setattr(security_api, "poll_github_device_token", fake_poll)
    monkeypatch.setattr(security_api, "fetch_github_identity", fake_identity)

    with TestClient(_application()) as client:
        alice = _login(client, "alice")
        bind_start = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            headers=_headers(alice["token"]),
            json={"purpose": "bind", "password": USER_PASSWORD},
        )
        assert bind_start.status_code == 200, bind_start.text
        bind_flow = bind_start.json()
        assert bind_flow["verificationUri"] == GITHUB_VERIFICATION_URI
        assert ACCESS_TOKEN not in bind_start.text

        too_early = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            headers=_headers(alice["token"]),
            json={"flowId": bind_flow["flowId"]},
        )
        assert too_early.status_code == 200
        assert too_early.json() == {"status": "pending", "retryAfterSeconds": 5}
        assert poll_calls == 0
        _allow_poll(client, bind_flow["flowId"])
        bound = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            headers=_headers(alice["token"]),
            json={"flowId": bind_flow["flowId"]},
        )
        assert bound.status_code == 200, bound.text
        assert bound.json() == {"status": "bound", "githubLogin": "octocat"}
        assert ACCESS_TOKEN not in bound.text

        identity_login = "octocat-renamed"
        login_start = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert login_start.status_code == 200
        _allow_poll(client, login_start.json()["flowId"])
        authenticated = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": login_start.json()["flowId"]},
        )
        assert authenticated.status_code == 200, authenticated.text
        assert authenticated.json()["status"] == "authenticated"
        assert authenticated.json()["user"]["username"] == "alice"
        assert ACCESS_TOKEN not in authenticated.text
        assert db.get_user_security_state("user-alice").github_login == "octocat-renamed"  # type: ignore[union-attr]

        secret = generate_totp_secret()
        recovery_codes, recovery_hashes = generate_recovery_code_material()
        current_counter = int(time.time()) // 30
        assert db.enable_user_two_factor(
            "user-alice",
            encrypted_secret=encrypt_totp_secret(secret),
            accepted_counter=current_counter - 1,
            recovery_code_hashes=recovery_hashes,
            keep_session_hash=None,
        )
        two_factor_start = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert two_factor_start.status_code == 200
        _allow_poll(client, two_factor_start.json()["flowId"])
        two_factor = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": two_factor_start.json()["flowId"]},
        )
        assert two_factor.status_code == 200
        assert two_factor.json()["status"] == "twoFactorRequired"
        assert "token" not in two_factor.json()
        completed = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": two_factor.json()["challengeToken"],
                "code": generate_totp_code(secret, counter=current_counter),
            },
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["requiresTwoFactor"] is False
        assert len(recovery_codes) == 10

        bob = _login(client, "bob")
        bob_start = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            headers=_headers(bob["token"]),
            json={"purpose": "bind", "password": USER_PASSWORD},
        )
        assert bob_start.status_code == 200
        _allow_poll(client, bob_start.json()["flowId"])
        duplicate = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            headers=_headers(bob["token"]),
            json={"flowId": bob_start.json()["flowId"]},
        )
        assert duplicate.status_code == 409
        assert db.get_user_security_state("user-bob").github_user_id is None  # type: ignore[union-attr]


def test_overlapping_bind_flows_cannot_silently_replace_identity(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice")
    _set_github(enabled=True)
    device_number = 0

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        nonlocal device_number
        device_number += 1
        return GitHubDeviceAuthorization(
            device_code=f"device-{device_number}",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    async def fake_poll(_client_id: str, device_code: str) -> GitHubDeviceTokenResult:
        return GitHubDeviceTokenResult(status="authorized", access_token=device_code)

    async def fake_identity(access_token: str) -> GitHubIdentity:
        suffix = access_token.rsplit("-", 1)[-1]
        return GitHubIdentity(user_id=f"900{suffix}", login=f"octocat-{suffix}")

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    monkeypatch.setattr(security_api, "poll_github_device_token", fake_poll)
    monkeypatch.setattr(security_api, "fetch_github_identity", fake_identity)
    with TestClient(_application()) as client:
        session = _login(client, "alice")
        starts = [
            client.post(
                f"{API_PREFIX}/auth/github/device/start",
                headers=_headers(session["token"]),
                json={"purpose": "bind", "password": USER_PASSWORD},
            )
            for _ in range(2)
        ]
        assert all(response.status_code == 200 for response in starts)
        for response in starts:
            _allow_poll(client, response.json()["flowId"])
        first = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            headers=_headers(session["token"]),
            json={"flowId": starts[0].json()["flowId"]},
        )
        second = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            headers=_headers(session["token"]),
            json={"flowId": starts[1].json()["flowId"]},
        )
        assert first.status_code == 200
        assert second.status_code == 409
        state = db.get_user_security_state("user-alice")
        assert state is not None
        assert (state.github_user_id, state.github_login) == ("9001", "octocat-1")


def test_binding_requires_second_factor_when_enabled(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice")
    _set_github(enabled=True)
    upstream_calls = 0

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        nonlocal upstream_calls
        upstream_calls += 1
        return GitHubDeviceAuthorization(
            device_code="device-secret",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    with TestClient(_application()) as client:
        session = _login(client, "alice")
        secret = generate_totp_secret()
        recovery_codes, recovery_hashes = generate_recovery_code_material()
        assert db.enable_user_two_factor(
            "user-alice",
            encrypted_secret=encrypt_totp_secret(secret),
            accepted_counter=int(time.time()) // 30,
            recovery_code_hashes=recovery_hashes,
            keep_session_hash=_session_hash(session["token"]),
        )
        missing = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            headers=_headers(session["token"]),
            json={"purpose": "bind", "password": USER_PASSWORD},
        )
        assert missing.status_code == 403
        invalid = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            headers=_headers(session["token"]),
            json={"purpose": "bind", "password": USER_PASSWORD, "code": "000000"},
        )
        assert invalid.status_code == 403
        started = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            headers=_headers(session["token"]),
            json={
                "purpose": "bind",
                "password": USER_PASSWORD,
                "code": recovery_codes[0],
            },
        )
        assert started.status_code == 200, started.text
        assert upstream_calls == 1
        assert db.count_user_recovery_codes("user-alice") == 9


def test_github_flow_invalidates_when_admin_configuration_changes(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_github(enabled=True)
    poll_calls = 0

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        return GitHubDeviceAuthorization(
            device_code="device-secret",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    async def fake_poll(_client_id: str, _device_code: str) -> GitHubDeviceTokenResult:
        nonlocal poll_calls
        poll_calls += 1
        return GitHubDeviceTokenResult(status="pending")

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    monkeypatch.setattr(security_api, "poll_github_device_token", fake_poll)
    with TestClient(_application()) as client:
        started = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert started.status_code == 200
        with db.get_connection() as conn:
            revision_before = int(
                conn.execute(
                    "SELECT github_config_revision FROM registration_settings WHERE id = 1"
                ).fetchone()[0]
            )
        _set_github(enabled=False)
        _set_github(enabled=True)
        with db.get_connection() as conn:
            revision_after = int(
                conn.execute(
                    "SELECT github_config_revision FROM registration_settings WHERE id = 1"
                ).fetchone()[0]
            )
        assert revision_after == revision_before + 2
        invalidated = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": started.json()["flowId"]},
        )
        assert invalidated.status_code == 409
        assert poll_calls == 0
        gone = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": started.json()["flowId"]},
        )
        assert gone.status_code == 404


def test_github_two_factor_challenge_rechecks_revision_before_recovery_consumption(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice")
    assert db.bind_github_identity("user-alice", "123456789", "octocat") is not None
    secret = generate_totp_secret()
    recovery_codes, recovery_hashes = generate_recovery_code_material()
    assert db.enable_user_two_factor(
        "user-alice",
        encrypted_secret=encrypt_totp_secret(secret),
        accepted_counter=int(time.time()) // 30,
        recovery_code_hashes=recovery_hashes,
        keep_session_hash=None,
    )
    _set_github(enabled=True)

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        return GitHubDeviceAuthorization(
            device_code="device-secret",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    async def fake_poll(_client_id: str, _device_code: str) -> GitHubDeviceTokenResult:
        return GitHubDeviceTokenResult(status="authorized", access_token=ACCESS_TOKEN)

    async def fake_identity(_access_token: str) -> GitHubIdentity:
        return GitHubIdentity(user_id="123456789", login="octocat")

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    monkeypatch.setattr(security_api, "poll_github_device_token", fake_poll)
    monkeypatch.setattr(security_api, "fetch_github_identity", fake_identity)
    with TestClient(_application()) as client:
        started = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert started.status_code == 200
        _allow_poll(client, started.json()["flowId"])
        challenged = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": started.json()["flowId"]},
        )
        assert challenged.status_code == 200, challenged.text
        assert challenged.json()["status"] == "twoFactorRequired"

        _set_github(enabled=False)
        _set_github(enabled=True)
        stale = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": challenged.json()["challengeToken"],
                "code": recovery_codes[0],
            },
        )

    assert stale.status_code == 409
    assert db.count_user_recovery_codes("user-alice") == 10


def test_concurrent_github_polls_share_one_upstream_request(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user("alice")
    assert db.bind_github_identity("user-alice", "123456789", "octocat") is not None
    _set_github(enabled=True)
    entered = Event()
    release = Event()
    poll_calls = 0

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        return GitHubDeviceAuthorization(
            device_code="device-secret",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=1,
        )

    async def blocking_poll(_client_id: str, _device_code: str) -> GitHubDeviceTokenResult:
        nonlocal poll_calls
        poll_calls += 1
        entered.set()
        assert await asyncio.to_thread(release.wait, 5)
        return GitHubDeviceTokenResult(status="authorized", access_token=ACCESS_TOKEN)

    async def fake_identity(_access_token: str) -> GitHubIdentity:
        return GitHubIdentity(user_id="123456789", login="octocat")

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    monkeypatch.setattr(security_api, "poll_github_device_token", blocking_poll)
    monkeypatch.setattr(security_api, "fetch_github_identity", fake_identity)
    with TestClient(_application()) as client:
        started = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert started.status_code == 200
        flow_id = started.json()["flowId"]
        _allow_poll(client, flow_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(
                client.post,
                f"{API_PREFIX}/auth/github/device/poll",
                json={"flowId": flow_id},
            )
            assert entered.wait(timeout=5)
            concurrent = client.post(
                f"{API_PREFIX}/auth/github/device/poll",
                json={"flowId": flow_id},
            )
            assert concurrent.status_code == 200
            assert concurrent.json() == {"status": "pending", "retryAfterSeconds": 1}
            _set_github(enabled=False)
            _set_github(enabled=True)
            release.set()
            first = first_future.result(timeout=5)
        assert first.status_code == 409, first.text
        assert poll_calls == 1
        with db.get_connection() as conn:
            session_count = conn.execute(
                "SELECT COUNT(*) FROM user_sessions WHERE user_id = ?",
                ("user-alice",),
            ).fetchone()[0]
        assert session_count == 0


def test_github_start_is_ip_rate_limited_before_upstream(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_github(enabled=True)
    start_calls = 0

    async def fake_start(_client_id: str) -> GitHubDeviceAuthorization:
        nonlocal start_calls
        start_calls += 1
        return GitHubDeviceAuthorization(
            device_code=f"device-{start_calls}",
            user_code="ABCD-EFGH",
            verification_uri=GITHUB_VERIFICATION_URI,
            expires_in=900,
            interval=5,
        )

    monkeypatch.setattr(security_api, "start_github_device_authorization", fake_start)
    with TestClient(_application()) as client:
        for _ in range(10):
            response = client.post(
                f"{API_PREFIX}/auth/github/device/start",
                json={"purpose": "login"},
            )
            assert response.status_code == 200
        blocked = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
    assert start_calls == 10


def test_github_can_be_unbound_while_disabled_with_recovery_code(
    github_database: Path,
) -> None:
    _create_user("alice")
    assert db.bind_github_identity("user-alice", "123456789", "octocat") is not None
    with TestClient(_application()) as client:
        session = _login(client, "alice")
        secret = generate_totp_secret()
        recovery_codes, recovery_hashes = generate_recovery_code_material()
        assert db.enable_user_two_factor(
            "user-alice",
            encrypted_secret=encrypt_totp_secret(secret),
            accepted_counter=int(time.time()) // 30,
            recovery_code_hashes=recovery_hashes,
            keep_session_hash=_session_hash(session["token"]),
        )
        _set_github(enabled=False)
        missing_code = client.post(
            f"{API_PREFIX}/auth/account/github/unbind",
            headers=_headers(session["token"]),
            json={"password": USER_PASSWORD},
        )
        assert missing_code.status_code == 400
        unbound = client.post(
            f"{API_PREFIX}/auth/account/github/unbind",
            headers=_headers(session["token"]),
            json={"password": USER_PASSWORD, "code": recovery_codes[0]},
        )
        assert unbound.status_code == 204, unbound.text
        assert db.get_user_security_state("user-alice").github_user_id is None  # type: ignore[union-attr]


def test_admin_github_settings_and_user_security_summary(
    github_database: Path,
) -> None:
    _create_user("alice")
    assert db.bind_github_identity("user-alice", "123456789", "octocat") is not None
    secret = generate_totp_secret()
    _, recovery_hashes = generate_recovery_code_material()
    assert db.enable_user_two_factor(
        "user-alice",
        encrypted_secret=encrypt_totp_secret(secret),
        accepted_counter=int(time.time()) // 30,
        recovery_code_hashes=recovery_hashes,
        keep_session_hash=None,
    )
    payload: dict[str, object] = {
        "emailVerificationRequired": False,
        "identityBadgeRequired": False,
        "smtp": {
            "host": "",
            "port": 587,
            "security": "starttls",
            "username": "",
            "fromAddress": "",
            "fromName": "青卷",
        },
        "smtpPasswordAction": "keep",
        "identityBadgeAction": "keep",
        "github": {"enabled": True, "clientId": GITHUB_CLIENT_ID},
    }
    with TestClient(_application(include_admin=True)) as client:
        logged_in = client.post("/admin/api/login", json={"password": ADMIN_PASSWORD})
        assert logged_in.status_code == 200
        csrf_headers = {ADMIN_CSRF_HEADER: logged_in.json()["csrfToken"]}
        initial = client.get("/admin/api/registration-settings")
        assert initial.status_code == 200
        assert initial.json()["github"] == {"enabled": False, "clientId": "", "configured": False}

        updated = client.put(
            "/admin/api/registration-settings",
            headers=csrf_headers,
            json=payload,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["github"] == {
            "enabled": True,
            "clientId": GITHUB_CLIENT_ID,
            "configured": True,
        }
        with db.get_connection() as conn:
            updated_revision = int(
                conn.execute(
                    "SELECT github_config_revision FROM registration_settings WHERE id = 1"
                ).fetchone()[0]
            )

        payload.pop("github")
        preserved = client.put(
            "/admin/api/registration-settings",
            headers=csrf_headers,
            json=payload,
        )
        assert preserved.status_code == 200
        assert preserved.json()["github"]["clientId"] == GITHUB_CLIENT_ID
        with db.get_connection() as conn:
            preserved_revision = int(
                conn.execute(
                    "SELECT github_config_revision FROM registration_settings WHERE id = 1"
                ).fetchone()[0]
            )
        assert preserved_revision == updated_revision

        users = client.get("/admin/api/users")
        assert users.status_code == 200
        alice = next(user for user in users.json() if user["username"] == "alice")
        assert alice["githubLogin"] == "octocat"
        assert alice["twoFactorEnabled"] is True

        payload["github"] = {"enabled": True, "clientId": "invalid"}
        invalid = client.put(
            "/admin/api/registration-settings",
            headers=csrf_headers,
            json=payload,
        )
        assert invalid.status_code == 400


def test_github_endpoints_are_hidden_outside_multi_user_mode(
    github_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "0")
    with TestClient(_application(include_admin=True)) as client:
        start = client.post(
            f"{API_PREFIX}/auth/github/device/start",
            json={"purpose": "login"},
        )
        poll = client.post(
            f"{API_PREFIX}/auth/github/device/poll",
            json={"flowId": "x" * 43},
        )
        unbind = client.post(
            f"{API_PREFIX}/auth/account/github/unbind",
            json={"password": USER_PASSWORD},
        )
        settings = client.get("/admin/api/registration-settings")
    assert [start.status_code, poll.status_code, unbind.status_code, settings.status_code] == [
        404,
        404,
        404,
        404,
    ]
