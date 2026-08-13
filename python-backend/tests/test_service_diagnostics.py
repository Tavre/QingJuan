import hashlib
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import db
from app.admin_auth import (
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api.admin import router as admin_router
from app.application import create_application
from app.runtime_logs import RUNTIME_LOG_FILE_ENV
from app.service_diagnostics import RequestMetrics


def _configure_admin(monkeypatch, password: str = "diagnostic-admin-password") -> None:
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(password, salt=b"0123456789abcdef", iterations=100_000),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "44" * 32)


def _configure_database(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    db.init_db()


def test_request_metrics_use_bounded_p95_sample() -> None:
    metrics = RequestMetrics(sample_limit=3)
    metrics.record(200, 10)
    metrics.record(201, 20)
    metrics.record(404, 30)
    metrics.record(500, 40)

    snapshot = metrics.snapshot()

    assert snapshot.total == 4
    assert snapshot.successful == 2
    assert snapshot.clientErrors == 1
    assert snapshot.serverErrors == 1
    assert snapshot.sampleSize == 3
    assert snapshot.averageDurationMs == 30
    assert snapshot.p95DurationMs == 40


def test_request_metrics_are_isolated_and_skip_health_or_static_routes() -> None:
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    first = create_application(routers=[router])
    second = create_application(routers=[router])

    with TestClient(first) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/ping").status_code == 200

    assert first.state.request_metrics.snapshot().total == 1
    assert second.state.request_metrics.snapshot().total == 0


def test_diagnostics_require_admin_and_return_redacted_read_only_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    _configure_database(monkeypatch, tmp_path)
    connection_token = "client-bearer-token-for-diagnostics"
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(connection_token.encode()).hexdigest(),
    )

    log_path = tmp_path / "logs" / "server.jsonl"
    log_path.parent.mkdir()
    private_path = tmp_path / "private" / "payload.txt"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": "2030-01-01T00:00:00Z",
                "level": "warning",
                "source": "qingjuan.runtime",
                "message": (
                    f"Authorization: Bearer hidden-diagnostic-token at {private_path}"
                ),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(RUNTIME_LOG_FILE_ENV, str(log_path))
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        rejected = client.get(
            "/admin/api/diagnostics",
            headers={"Authorization": f"Bearer {connection_token}"},
        )
        login = client.post(
            "/admin/api/login",
            json={"password": "diagnostic-admin-password"},
        )
        accepted = client.get("/admin/api/diagnostics")

    assert rejected.status_code == 401
    assert login.status_code == 200
    assert accepted.status_code == 200
    assert accepted.headers["cache-control"] == "no-store"
    payload = accepted.json()
    assert payload["schemaVersion"] == 1
    assert payload["requests"]["total"] >= 2
    assert payload["storage"]["databaseBytes"] > 0
    assert payload["workload"]["tasks"] == 0
    assert {check["key"] for check in payload["checks"]} == {
        "database",
        "data-directory",
        "disk-space",
        "task-worker",
        "runtime-logs",
    }
    assert payload["recentIssues"][0]["message"].count("[REDACTED]") == 1
    assert "hidden-diagnostic-token" not in accepted.text
    assert str(private_path) not in accepted.text
    assert "[PATH]" in accepted.text
    assert connection_token not in accepted.text
