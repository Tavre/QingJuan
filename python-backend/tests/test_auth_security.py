from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.account_security import generate_recovery_code_material
from app.admin_auth import (
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api import auth as auth_api
from app.api import auth_security as security_api
from app.api.auth import router as auth_router
from app.application import create_application
from app.security import API_PREFIX
from app.two_factor import (
    TWO_FACTOR_ENCRYPTION_KEY_ENV,
    encrypt_totp_secret,
    generate_totp_code,
    generate_totp_secret,
)

USER_PASSWORD = "correct-user-password"
ADMIN_PASSWORD = "correct-admin-password"


@pytest.fixture
def security_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
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


def _application():
    return create_application(routers=[auth_router], api_prefix=API_PREFIX)


def _create_user(username: str = "alice") -> None:
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


def _login(client: TestClient, username: str = "alice") -> dict[str, object]:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": username, "password": USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def _headers(token: object) -> dict[str, str]:
    assert isinstance(token, str)
    return {"X-QingJuan-User-Token": token}


def _enable_two_factor(client: TestClient, session_token: object) -> tuple[str, list[str]]:
    setup_response = client.post(
        f"{API_PREFIX}/auth/account/2fa/setup",
        headers=_headers(session_token),
        json={"password": USER_PASSWORD},
    )
    assert setup_response.status_code == 200, setup_response.text
    setup = setup_response.json()
    assert setup["expiresInSeconds"] == 600
    assert setup["secret"] in setup["otpauthUri"]
    assert setup_response.headers["cache-control"] == "no-store"

    enable_response = client.post(
        f"{API_PREFIX}/auth/account/2fa/enable",
        headers=_headers(session_token),
        json={
            "setupId": setup["setupId"],
            "code": generate_totp_code(setup["secret"]),
        },
    )
    assert enable_response.status_code == 200, enable_response.text
    codes = enable_response.json()["recoveryCodes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10
    return setup["secret"], codes


def test_password_login_setup_totp_replay_and_recovery_codes(
    security_database: Path,
) -> None:
    _create_user()
    with TestClient(_application()) as client:
        initial = _login(client)
        assert initial["requiresTwoFactor"] is False
        assert isinstance(initial["token"], str)
        secret, recovery_codes = _enable_two_factor(client, initial["token"])

        state = db.get_user_security_state("user-alice")
        assert state is not None
        assert state.totp_secret_encrypted is not None
        assert secret not in state.totp_secret_encrypted
        assert state.totp_last_counter is not None
        assert db.count_user_recovery_codes("user-alice") == 10

        security = client.get(
            f"{API_PREFIX}/auth/account/security",
            headers=_headers(initial["token"]),
        )
        assert security.status_code == 200
        assert security.json() == {
            "github": {"available": False, "bound": False, "login": None},
            "twoFactor": {"enabled": True, "recoveryCodesRemaining": 10},
        }

        challenged = _login(client)
        assert challenged == {
            "requiresTwoFactor": True,
            "challengeToken": challenged["challengeToken"],
            "expiresInSeconds": 300,
        }
        state = db.get_user_security_state("user-alice")
        assert state is not None and state.totp_last_counter is not None
        next_code = generate_totp_code(secret, counter=state.totp_last_counter + 1)
        completed = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": challenged["challengeToken"], "code": next_code},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["requiresTwoFactor"] is False
        assert completed.json()["user"]["lastLoginAt"] is not None

        replay_challenge = _login(client)
        replay = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": replay_challenge["challengeToken"], "code": next_code},
        )
        assert replay.status_code == 401

        recovery_challenge = _login(client)
        recovered = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": recovery_challenge["challengeToken"],
                "code": recovery_codes[0],
            },
        )
        assert recovered.status_code == 200
        assert db.count_user_recovery_codes("user-alice") == 9

        reused_challenge = _login(client)
        reused = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": reused_challenge["challengeToken"],
                "code": recovery_codes[0],
            },
        )
        assert reused.status_code == 401


def test_recovery_codes_survive_totp_key_rotation_and_can_disable(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    with TestClient(_application()) as client:
        initial = _login(client)
        _, recovery_codes = _enable_two_factor(client, initial["token"])

        with db.get_connection() as conn:
            conn.execute(
                "UPDATE users SET totp_secret_encrypted = ? WHERE id = ?",
                ("qj2fa:v1:invalid:invalid:invalid", "user-alice"),
            )
        monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "88" * 32)

        challenged = _login(client)
        recovered = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": challenged["challengeToken"],
                "code": recovery_codes[0],
            },
        )
        assert recovered.status_code == 200, recovered.text
        token = recovered.json()["token"]

        regenerated = client.post(
            f"{API_PREFIX}/auth/account/2fa/recovery-codes",
            headers=_headers(token),
            json={"password": USER_PASSWORD, "code": recovery_codes[1]},
        )
        assert regenerated.status_code == 200, regenerated.text
        replacement_codes = regenerated.json()["recoveryCodes"]
        assert len(replacement_codes) == 10

        old_code = client.post(
            f"{API_PREFIX}/auth/account/2fa/disable",
            headers=_headers(token),
            json={"password": USER_PASSWORD, "code": recovery_codes[2]},
        )
        assert old_code.status_code == 403

        disabled = client.post(
            f"{API_PREFIX}/auth/account/2fa/disable",
            headers=_headers(token),
            json={"password": USER_PASSWORD, "code": replacement_codes[0]},
        )
        assert disabled.status_code == 204, disabled.text
        assert db.count_user_recovery_codes("user-alice") == 0
        assert db.get_user_security_state("user-alice").totp_secret_encrypted is None  # type: ignore[union-attr]


def test_totp_survives_admin_session_secret_rotation(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    with TestClient(_application()) as client:
        initial = _login(client)
        secret, _ = _enable_two_factor(client, initial["token"])

        monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "88" * 32)
        challenged = _login(client)
        state = db.get_user_security_state("user-alice")
        assert state is not None and state.totp_last_counter is not None
        completed = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": challenged["challengeToken"],
                "code": generate_totp_code(secret, counter=state.totp_last_counter + 1),
            },
        )

    assert completed.status_code == 200, completed.text
    assert completed.json()["requiresTwoFactor"] is False


def test_enabling_and_disabling_two_factor_revoke_other_sessions_only(
    security_database: Path,
) -> None:
    _create_user()
    with TestClient(_application()) as client:
        first = _login(client)
        second = _login(client)
        secret, recovery_codes = _enable_two_factor(client, first["token"])

        kept_after_enable = client.get(
            f"{API_PREFIX}/auth/session",
            headers=_headers(first["token"]),
        )
        revoked_after_enable = client.get(
            f"{API_PREFIX}/auth/session",
            headers=_headers(second["token"]),
        )
        assert kept_after_enable.status_code == 200
        assert revoked_after_enable.status_code == 401

        challenged = _login(client)
        state = db.get_user_security_state("user-alice")
        assert state is not None and state.totp_last_counter is not None
        completed = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": challenged["challengeToken"],
                "code": generate_totp_code(secret, counter=state.totp_last_counter + 1),
            },
        )
        assert completed.status_code == 200
        third_token = completed.json()["token"]

        disabled = client.post(
            f"{API_PREFIX}/auth/account/2fa/disable",
            headers=_headers(first["token"]),
            json={"password": USER_PASSWORD, "code": recovery_codes[0]},
        )
        assert disabled.status_code == 204
        kept_after_disable = client.get(
            f"{API_PREFIX}/auth/session",
            headers=_headers(first["token"]),
        )
        revoked_after_disable = client.get(
            f"{API_PREFIX}/auth/session",
            headers=_headers(third_token),
        )
        assert kept_after_disable.status_code == 200
        assert revoked_after_disable.status_code == 401


def test_account_password_reauthentication_is_shared_rate_limited_and_not_401(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE registration_settings SET github_enabled = 1, github_client_id = ? WHERE id = 1",
            ("Ov23liABCDEFGHIJKLMN",),
        )
    original_verifier = security_api.verify_current_user_password_state
    verifier_calls = 0

    def counting_verifier(user_id: str, password: str):
        nonlocal verifier_calls
        verifier_calls += 1
        return original_verifier(user_id, password)

    monkeypatch.setattr(security_api, "verify_current_user_password_state", counting_verifier)
    with TestClient(_application()) as client:
        session = _login(client)
        headers = _headers(session["token"])
        attempts = (
            ("/auth/account/2fa/setup", {"password": "wrong-password"}),
            ("/auth/account/github/unbind", {"password": "wrong-password"}),
            (
                "/auth/account/2fa/disable",
                {"password": "wrong-password", "code": "000000"},
            ),
            (
                "/auth/account/2fa/recovery-codes",
                {"password": "wrong-password", "code": "000000"},
            ),
            (
                "/auth/github/device/start",
                {"purpose": "bind", "password": "wrong-password"},
            ),
        )
        for path, payload in attempts:
            response = client.post(f"{API_PREFIX}{path}", headers=headers, json=payload)
            assert response.status_code == 403, (path, response.text)
        blocked = client.post(
            f"{API_PREFIX}/auth/account/2fa/setup",
            headers=headers,
            json={"password": "wrong-password"},
        )
        assert blocked.status_code == 429
        assert verifier_calls == 5
        # A reauthentication failure must not be interpreted as an invalid user session.
        assert client.get(f"{API_PREFIX}/auth/session", headers=headers).status_code == 200


def test_login_challenge_serializes_concurrent_recovery_code_attempts(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    entered = Event()
    release = Event()
    with TestClient(_application()) as client:
        initial = _login(client)
        _, recovery_codes = _enable_two_factor(client, initial["token"])
        challenged = _login(client)
        original_verifier = security_api.verify_second_factor_code

        def blocking_verifier(user_id: str, code: str) -> bool:
            if code == recovery_codes[0]:
                entered.set()
                assert release.wait(timeout=5)
            return original_verifier(user_id, code)

        monkeypatch.setattr(security_api, "verify_second_factor_code", blocking_verifier)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(
                client.post,
                f"{API_PREFIX}/auth/login/2fa",
                json={
                    "challengeToken": challenged["challengeToken"],
                    "code": recovery_codes[0],
                },
            )
            assert entered.wait(timeout=5)
            concurrent = client.post(
                f"{API_PREFIX}/auth/login/2fa",
                json={
                    "challengeToken": challenged["challengeToken"],
                    "code": recovery_codes[1],
                },
            )
            assert concurrent.status_code == 409
            release.set()
            first = first_future.result(timeout=5)
        assert first.status_code == 200, first.text
        assert db.count_user_recovery_codes("user-alice") == 9

        next_challenge = _login(client)
        still_available = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": next_challenge["challengeToken"],
                "code": recovery_codes[1],
            },
        )
        assert still_available.status_code == 200
        assert db.count_user_recovery_codes("user-alice") == 8


def test_stale_login_challenge_does_not_consume_recovery_code(
    security_database: Path,
) -> None:
    _create_user()
    replacement_hash = hash_admin_password(
        "replacement-user-password",
        salt=b"fedcba9876543210",
        iterations=100_000,
    )
    with TestClient(_application()) as client:
        initial = _login(client)
        _, recovery_codes = _enable_two_factor(client, initial["token"])
        challenged = _login(client)
        assert db.count_user_recovery_codes("user-alice") == 10

        assert db.update_user_password(
            "user-alice",
            replacement_hash,
            revoke_sessions=True,
        )
        stale = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={
                "challengeToken": challenged["challengeToken"],
                "code": recovery_codes[0],
            },
        )

    assert stale.status_code == 401
    assert db.count_user_recovery_codes("user-alice") == 10


def test_password_change_invalidates_pending_two_factor_setup(
    security_database: Path,
) -> None:
    _create_user()
    replacement_hash = hash_admin_password(
        "replacement-user-password",
        salt=b"fedcba9876543210",
        iterations=100_000,
    )
    with TestClient(_application()) as client:
        initial = _login(client)
        setup = client.post(
            f"{API_PREFIX}/auth/account/2fa/setup",
            headers=_headers(initial["token"]),
            json={"password": USER_PASSWORD},
        )
        assert setup.status_code == 200
        assert db.update_user_password(
            "user-alice",
            replacement_hash,
            revoke_sessions=True,
        )
        replacement_login = client.post(
            f"{API_PREFIX}/auth/login",
            json={"username": "alice", "password": "replacement-user-password"},
        )
        assert replacement_login.status_code == 200
        stale = client.post(
            f"{API_PREFIX}/auth/account/2fa/enable",
            headers=_headers(replacement_login.json()["token"]),
            json={
                "setupId": setup.json()["setupId"],
                "code": generate_totp_code(setup.json()["secret"]),
            },
        )

    assert stale.status_code == 409
    state = db.get_user_security_state("user-alice")
    assert state is not None and state.totp_secret_encrypted is None


def test_password_login_reserves_rate_limit_before_parallel_hashing(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    barrier = Barrier(6)
    verifier_calls = 0

    def blocking_invalid_authentication(_username: str, _password: str):
        nonlocal verifier_calls
        verifier_calls += 1
        barrier.wait(timeout=5)
        return None

    monkeypatch.setattr(auth_api, "authenticate_user_state", blocking_invalid_authentication)
    with TestClient(_application()) as client, ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(
                client.post,
                f"{API_PREFIX}/auth/login",
                json={"username": "alice", "password": "wrong-password"},
            )
            for _ in range(5)
        ]
        barrier.wait(timeout=5)
        blocked = client.post(
            f"{API_PREFIX}/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        responses = [future.result(timeout=5) for future in futures]

    assert blocked.status_code == 429
    assert all(response.status_code == 401 for response in responses)
    assert verifier_calls == 5


def test_password_change_blocks_in_flight_primary_authentication_session(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    entered = Event()
    release = Event()
    original_authenticate = auth_api.authenticate_user_state
    replacement_hash = hash_admin_password(
        "replacement-user-password",
        salt=b"fedcba9876543210",
        iterations=100_000,
    )

    def blocking_authenticate(username: str, password: str):
        authenticated = original_authenticate(username, password)
        entered.set()
        assert release.wait(timeout=5)
        return authenticated

    monkeypatch.setattr(auth_api, "authenticate_user_state", blocking_authenticate)
    with TestClient(_application()) as client, ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            client.post,
            f"{API_PREFIX}/auth/login",
            json={"username": "alice", "password": USER_PASSWORD},
        )
        assert entered.wait(timeout=5)
        assert db.update_user_password(
            "user-alice",
            replacement_hash,
            revoke_sessions=True,
        )
        release.set()
        response = future.result(timeout=5)

    assert response.status_code == 409, response.text
    with db.get_connection() as conn:
        session_count = conn.execute(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id = ?",
            ("user-alice",),
        ).fetchone()[0]
    assert session_count == 0


def test_auth_epoch_changes_only_at_authentication_boundaries(
    security_database: Path,
) -> None:
    _create_user()

    def epoch() -> int:
        state = db.get_user_security_state("user-alice")
        assert state is not None
        return state.auth_epoch

    assert epoch() == 0
    assert db.update_user_profile("user-alice", display_name="Alice Renamed") is not None
    assert db.mark_user_login("user-alice", "2030-01-01T00:00:00Z") is not None
    assert epoch() == 0

    assert db.bind_github_identity("user-alice", "123456789", "octocat") is not None
    assert epoch() == 1
    assert db.refresh_github_login("123456789", "octocat-renamed") is not None
    assert epoch() == 1
    assert db.unbind_github_identity("user-alice")
    assert epoch() == 2

    secret = generate_totp_secret()
    _, recovery_hashes = generate_recovery_code_material()
    assert db.enable_user_two_factor(
        "user-alice",
        encrypted_secret=encrypt_totp_secret(secret),
        accepted_counter=0,
        recovery_code_hashes=recovery_hashes,
        keep_session_hash=None,
    )
    assert epoch() == 3
    assert db.accept_user_totp_counter("user-alice", 1)
    assert db.consume_user_recovery_code("user-alice", recovery_hashes[0])
    assert epoch() == 3

    _, replacement_hashes = generate_recovery_code_material()
    assert db.replace_user_recovery_codes(
        "user-alice",
        replacement_hashes,
        expected_auth_epoch=3,
    )
    assert epoch() == 4
    assert db.disable_user_two_factor(
        "user-alice",
        expected_auth_epoch=4,
        keep_session_hash=None,
    )
    assert epoch() == 5

    assert db.update_user_profile("user-alice", role="admin") is not None
    assert epoch() == 6
    assert db.update_user_profile("user-alice", role="admin") is not None
    assert epoch() == 6
    replacement_password_hash = hash_admin_password(
        "replacement-user-password",
        salt=b"fedcba9876543210",
        iterations=100_000,
    )
    assert db.update_user_password("user-alice", replacement_password_hash)
    assert epoch() == 7
    db.revoke_user_sessions("user-alice")
    assert epoch() == 8


def test_two_factor_challenge_attempt_and_cross_challenge_limits(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_user()
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET totp_secret_encrypted = ? WHERE id = ?",
            ("configured-but-invalid", "user-alice"),
        )
    verifier_calls = 0

    def always_invalid(_user_id: str, _code: str) -> bool:
        nonlocal verifier_calls
        verifier_calls += 1
        return False

    monkeypatch.setattr(security_api, "verify_second_factor_code", always_invalid)
    with TestClient(_application()) as client:
        challenge = _login(client)
        for _ in range(5):
            response = client.post(
                f"{API_PREFIX}/auth/login/2fa",
                json={"challengeToken": challenge["challengeToken"], "code": "000000"},
            )
            assert response.status_code == 401
        exhausted = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": challenge["challengeToken"], "code": "000000"},
        )
        assert exhausted.status_code == 401
        assert verifier_calls == 5

        # Five failures above count toward the same user+IP window. Five new challenges
        # are verified, then the next request is rejected before invoking the verifier.
        for _ in range(5):
            fresh = _login(client)
            response = client.post(
                f"{API_PREFIX}/auth/login/2fa",
                json={"challengeToken": fresh["challengeToken"], "code": "000000"},
            )
            assert response.status_code == 401
        blocked_challenge = _login(client)
        blocked = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": blocked_challenge["challengeToken"], "code": "000000"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        assert verifier_calls == 10


def test_expired_two_factor_challenge_is_one_time(
    security_database: Path,
) -> None:
    _create_user()
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE users SET totp_secret_encrypted = ? WHERE id = ?",
            ("configured-but-invalid", "user-alice"),
        )
    with TestClient(_application()) as client:
        challenge = _login(client)
        store = client.app.state.two_factor_challenge_store
        store._items[challenge["challengeToken"]].expires_at = time.monotonic() - 1
        expired = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": challenge["challengeToken"], "code": "000000"},
        )
        assert expired.status_code == 410
        missing = client.post(
            f"{API_PREFIX}/auth/login/2fa",
            json={"challengeToken": challenge["challengeToken"], "code": "000000"},
        )
        assert missing.status_code == 401


def test_security_endpoints_are_hidden_outside_multi_user_mode(
    security_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "0")
    with TestClient(_application()) as client:
        requests = (
            ("get", "/auth/account/security", None),
            ("post", "/auth/account/2fa/setup", {"password": USER_PASSWORD}),
            (
                "post",
                "/auth/account/2fa/enable",
                {"setupId": "x" * 43, "code": "000000"},
            ),
            (
                "post",
                "/auth/login/2fa",
                {"challengeToken": "x" * 43, "code": "000000"},
            ),
        )
        for method, path, payload in requests:
            if payload is None:
                response = getattr(client, method)(f"{API_PREFIX}{path}")
            else:
                response = getattr(client, method)(f"{API_PREFIX}{path}", json=payload)
            assert response.status_code == 404, (path, response.text)


def test_old_database_migrates_github_and_two_factor_columns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    database_path = data_dir / "qingjuan.db"
    monkeypatch.setenv("QINGJUAN_MULTI_USER", "1")
    monkeypatch.setenv(ADMIN_PASSWORD_HASH_ENV, hash_admin_password(ADMIN_PASSWORD))
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "77" * 32)
    monkeypatch.setenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, "99" * 32)
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    monkeypatch.setattr(db, "_SITE_PLUGIN_STATE_CACHE", None)
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
                email TEXT, email_key TEXT, display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, last_login_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE registration_settings (
                id INTEGER PRIMARY KEY, email_verification_required INTEGER NOT NULL DEFAULT 0,
                identity_badge_required INTEGER NOT NULL DEFAULT 0,
                smtp_host TEXT NOT NULL DEFAULT '', smtp_port INTEGER NOT NULL DEFAULT 587,
                smtp_security TEXT NOT NULL DEFAULT 'starttls', smtp_username TEXT NOT NULL DEFAULT '',
                smtp_password TEXT NOT NULL DEFAULT '', smtp_from_address TEXT NOT NULL DEFAULT '',
                smtp_from_name TEXT NOT NULL DEFAULT '青卷', identity_badge_hash TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE user_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO registration_settings (id, updated_at) VALUES (1, '2025-01-01T00:00:00Z')")

    db.init_db()
    with db.get_connection() as conn:
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(user_sessions)")}
        settings_columns = {row[1] for row in conn.execute("PRAGMA table_info(registration_settings)")}
        recovery_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user_recovery_codes'"
        ).fetchone()
    assert {
        "github_user_id",
        "github_login",
        "totp_secret_encrypted",
        "totp_last_counter",
        "auth_epoch",
    } <= user_columns
    assert "auth_epoch" in session_columns
    assert {"github_enabled", "github_client_id", "github_config_revision"} <= settings_columns
    assert recovery_table is not None
