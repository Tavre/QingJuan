from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, main
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    TRUST_LOCAL_ADMIN_ENV,
    hash_admin_password,
)
from app.api.admin import router as admin_router
from app.api.routers import settings_router
from app.application import create_application
from app.models import TranslationSettings
from app.security import API_PREFIX


def _configure_remote_app(monkeypatch, tmp_path: Path) -> tuple[TestClient, str]:
    bearer_token = "client-connection-token"
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(bearer_token.encode()).hexdigest(),
    )
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(
            "settings-admin-password",
            salt=b"0123456789abcdef",
            iterations=100_000,
        ),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "66" * 32)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    db.init_db()
    application = create_application(
        routers=[settings_router],
        public_routers=[admin_router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )
    return TestClient(application), bearer_token


def _settings_payload(*, base_url: str, api_key_action: str = "keep") -> dict:
    payload = TranslationSettings().model_dump()
    payload["translationModel"].update(
        {
            "enabled": True,
            "baseUrl": base_url,
            "apiKey": "",
            "apiKeyAction": api_key_action,
            "model": "translation-model",
        }
    )
    return payload


def test_client_bearer_can_read_but_cannot_modify_model_settings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client, bearer_token = _configure_remote_app(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        read_response = client.get(f"{API_PREFIX}/settings", headers=headers)
        write_response = client.put(
            f"{API_PREFIX}/settings",
            headers=headers,
            json=_settings_payload(base_url="https://models.example.test/v1"),
        )
    finally:
        client.close()

    assert read_response.status_code == 200
    assert write_response.status_code == 401


def test_admin_settings_reject_loopback_model_endpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client, _ = _configure_remote_app(monkeypatch, tmp_path)
    try:
        session = client.post(
            "/admin/api/login",
            json={"password": "settings-admin-password"},
        ).json()
        response = client.put(
            f"{API_PREFIX}/settings",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
            json=_settings_payload(base_url="http://127.0.0.1:80"),
        )
    finally:
        client.close()

    assert response.status_code == 400
    assert "127.0.0.1" not in response.text


def test_changing_model_origin_with_keep_clears_stored_key(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client, _ = _configure_remote_app(monkeypatch, tmp_path)
    current = db.load_settings()
    current.translationModel.enabled = True
    current.translationModel.baseUrl = "https://first-provider.example/v1"
    current.translationModel.apiKey = "stored-provider-key"
    current.translationModel.model = "translation-model"
    db.save_settings(current)
    try:
        session = client.post(
            "/admin/api/login",
            json={"password": "settings-admin-password"},
        ).json()
        response = client.put(
            f"{API_PREFIX}/settings",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
            json=_settings_payload(base_url="https://second-provider.example/v1"),
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["translationModel"]["apiKeyConfigured"] is False
    assert db.load_settings().translationModel.apiKey == ""
    assert "stored-provider-key" not in response.text


def test_endpoint_secret_is_kept_only_for_the_same_origin() -> None:
    assert (
        main._merge_endpoint_secret(
            "https://models.example.test/v1",
            "stored-provider-key",
            "https://models.example.test/compatible/v1",
            "",
            "keep",
        )
        == "stored-provider-key"
    )
    assert (
        main._merge_endpoint_secret(
            "https://models.example.test/v1",
            "stored-provider-key",
            "https://models.example.test:8443/v1",
            "",
            "keep",
        )
        == ""
    )


def test_trusted_windows_loopback_updates_settings_without_admin_routes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(TRUST_LOCAL_ADMIN_ENV, "1")
    monkeypatch.delenv("QINGJUAN_AUTH_TOKEN_SHA256", raising=False)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    db.init_db()
    application = create_application(
        routers=[settings_router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )
    payload = _settings_payload(base_url="https://models.example.test/v1")
    payload["translationModel"]["apiKey"] = "local-provider-key"
    payload["translationModel"]["apiKeyAction"] = "replace"

    with TestClient(
        application,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.put(f"{API_PREFIX}/settings", json=payload)
        admin_response = client.get("/admin/")

    assert response.status_code == 200
    assert response.json()["translationModel"]["apiKeyConfigured"] is True
    assert admin_response.status_code == 404
    assert db.load_settings().translationModel.apiKey == "local-provider-key"
