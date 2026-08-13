from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import db
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api.admin import router as admin_router
from app.api.devices import router as devices_router
from app.application import create_application
from app.security import API_PREFIX


def _prepare_database(monkeypatch, tmp_path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    db.init_db()


def _configure_auth(monkeypatch) -> str:
    bearer_token = "client-bearer-token"
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(bearer_token.encode()).hexdigest(),
    )
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(
            "correct-admin-password",
            salt=b"0123456789abcdef",
            iterations=100_000,
        ),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "11" * 32)
    return bearer_token


def _application() -> object:
    private_router = APIRouter()

    @private_router.get("/private")
    async def private_route() -> dict[str, str]:
        return {"status": "ok"}

    return create_application(
        routers=[devices_router, private_router],
        public_routers=[admin_router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )


def _device_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-QingJuan-Device-ID": "0123456789abcdef0123456789abcdef",
        "X-QingJuan-Device-Name": quote("客厅 Windows", safe=""),
        "X-QingJuan-Device-Platform": "windows",
    }


def test_device_registration_admin_listing_ban_and_unban(monkeypatch, tmp_path) -> None:
    _prepare_database(monkeypatch, tmp_path)
    bearer_token = _configure_auth(monkeypatch)
    application = _application()

    with TestClient(application) as client:
        registered = client.get(f"{API_PREFIX}/private", headers=_device_headers(bearer_token))
        heartbeat = client.post(
            f"{API_PREFIX}/devices/heartbeat",
            headers=_device_headers(bearer_token),
        )
        login = client.post("/admin/api/login", json={"password": "correct-admin-password"})
        session = login.json()
        listed = client.get(f"{API_PREFIX}/devices")

        banned = client.put(
            f"{API_PREFIX}/devices/0123456789abcdef0123456789abcdef/ban",
            json={"banned": True},
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )
        rejected = client.get(f"{API_PREFIX}/private", headers=_device_headers(bearer_token))
        unbanned = client.put(
            f"{API_PREFIX}/devices/0123456789abcdef0123456789abcdef/ban",
            json={"banned": False},
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
        )
        restored = client.get(f"{API_PREFIX}/private", headers=_device_headers(bearer_token))

    assert registered.status_code == 200
    assert heartbeat.status_code == 204
    assert login.status_code == 200
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": "0123456789abcdef0123456789abcdef",
            "name": "客厅 Windows",
            "platform": "windows",
            "ipAddress": "testclient",
            "firstSeenAt": listed.json()[0]["firstSeenAt"],
            "lastSeenAt": listed.json()[0]["lastSeenAt"],
            "banned": False,
            "bannedAt": None,
            "online": True,
        }
    ]
    assert banned.status_code == 200
    assert banned.json()["banned"] is True
    assert banned.json()["online"] is False
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "此设备已被管理员封禁"
    assert unbanned.status_code == 200
    assert unbanned.json()["banned"] is False
    assert restored.status_code == 200


def test_device_management_requires_admin_session_and_csrf(monkeypatch, tmp_path) -> None:
    _prepare_database(monkeypatch, tmp_path)
    bearer_token = _configure_auth(monkeypatch)
    application = _application()

    with TestClient(application) as client:
        client.get(f"{API_PREFIX}/private", headers=_device_headers(bearer_token))
        bearer_list = client.get(f"{API_PREFIX}/devices", headers=_device_headers(bearer_token))
        login = client.post("/admin/api/login", json={"password": "correct-admin-password"})
        missing_csrf = client.put(
            f"{API_PREFIX}/devices/0123456789abcdef0123456789abcdef/ban",
            json={"banned": True},
        )

    assert bearer_list.status_code == 401
    assert login.status_code == 200
    assert missing_csrf.status_code == 403


def test_legacy_client_is_accepted_but_invalid_device_header_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    _prepare_database(monkeypatch, tmp_path)
    bearer_token = _configure_auth(monkeypatch)
    application = _application()

    with TestClient(application) as client:
        legacy = client.get(
            f"{API_PREFIX}/private",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        invalid = client.get(
            f"{API_PREFIX}/private",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "X-QingJuan-Device-ID": "not-a-valid-device-id",
            },
        )

    assert legacy.status_code == 200
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "设备标识格式无效"
    assert db.list_devices() == []


def test_online_window_and_touch_throttling(monkeypatch, tmp_path) -> None:
    _prepare_database(monkeypatch, tmp_path)
    first_seen = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    original = db.touch_device(
        device_id="fedcba9876543210fedcba9876543210",
        name="Android 设备",
        platform="android",
        ip_address="10.0.0.3",
        seen_at=first_seen,
    )
    throttled = db.touch_device(
        device_id=original.id,
        name=original.name,
        platform=original.platform,
        ip_address=original.ipAddress,
        seen_at=first_seen + timedelta(seconds=10),
    )

    assert throttled.lastSeenAt == original.lastSeenAt
    assert db.list_devices(now=first_seen + timedelta(seconds=119))[0].online is True
    assert db.list_devices(now=first_seen + timedelta(seconds=121))[0].online is False
