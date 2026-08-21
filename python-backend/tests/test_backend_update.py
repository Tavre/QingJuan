from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import app.backend_update as backend_update
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api.admin import router as admin_router
from app.application import APP_VERSION, create_application


def _configure_admin(monkeypatch) -> None:
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(
            "correct-admin-password",
            salt=b"0123456789abcdef",
            iterations=100_000,
        ),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "11" * 32)


def _configure_update_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    runtime = tmp_path / "run"
    runtime.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    request_file = runtime / "update-request.json"
    status_file = data / "backend-update.json"
    monkeypatch.setenv(backend_update.UPDATE_REPO_DIR_ENV, str(repo))
    monkeypatch.setenv(backend_update.UPDATE_REQUEST_FILE_ENV, str(request_file))
    monkeypatch.setenv(backend_update.UPDATE_STATUS_FILE_ENV, str(status_file))
    return request_file, status_file


def test_update_status_is_unsupported_until_system_service_is_installed(monkeypatch) -> None:
    monkeypatch.delenv(backend_update.UPDATE_REQUEST_FILE_ENV, raising=False)
    monkeypatch.delenv(backend_update.UPDATE_STATUS_FILE_ENV, raising=False)

    result = backend_update.get_backend_update_status()

    assert result.state == "unsupported"
    assert result.supported is False
    assert "update.sh" in (result.blockedReason or "")


def test_check_uses_fixed_upstream_and_persists_available_revision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _, status_file = _configure_update_paths(monkeypatch, tmp_path)
    current_revision = "1" * 40
    candidate_revision = "2" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return current_revision
        if arguments[-1] == "@{upstream}":
            return "origin/main"
        if arguments == ("config", "--get", "remote.origin.url"):
            return "https://example.invalid/qingjuan.git"
        raise AssertionError(arguments)

    monkeypatch.setattr(backend_update, "_git", fake_git)
    monkeypatch.setattr(
        backend_update,
        "_run_git",
        lambda *arguments, use_repo: f"{candidate_revision}\trefs/heads/main\n",
    )

    result = backend_update.check_for_backend_update()

    assert result.state == "available"
    assert result.canUpdate is True
    assert result.candidateId == candidate_revision
    persisted = json.loads(status_file.read_text(encoding="utf-8"))
    assert persisted["candidateId"] == candidate_revision
    assert "example.invalid" not in status_file.read_text(encoding="utf-8")


def test_admin_update_api_requires_session_and_csrf_then_creates_fixed_trigger(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    request_file, status_file = _configure_update_paths(monkeypatch, tmp_path)
    candidate_revision = "a" * 40
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="available",
            canUpdate=True,
            candidateId=candidate_revision,
            checkedAt="2030-01-01T00:00:00Z",
            message="检测到可用的后端更新",
        ).model_dump_json(),
        encoding="utf-8",
    )
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        unauthorized = client.get("/admin/api/backend-update")
        session = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        ).json()
        status_response = client.get("/admin/api/backend-update")
        missing_csrf = client.post(
            "/admin/api/backend-update",
            json={"candidateId": candidate_revision, "requestId": "request-1234"},
        )
        accepted = client.post(
            "/admin/api/backend-update",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
            json={"candidateId": candidate_revision, "requestId": "request-1234"},
        )

    assert unauthorized.status_code == 401
    assert status_response.status_code == 200
    assert status_response.headers["cache-control"] == "no-store"
    assert status_response.json()["currentVersion"] == APP_VERSION
    assert missing_csrf.status_code == 403
    assert accepted.status_code == 202
    assert accepted.headers["cache-control"] == "no-store"
    assert accepted.headers["location"] == "/admin/api/backend-update"
    assert accepted.json()["disconnectExpected"] is True
    trigger = json.loads(request_file.read_text(encoding="utf-8"))
    assert trigger["candidateId"] == candidate_revision
    assert trigger["requestId"] == "request-1234"
    assert set(trigger) == {
        "schemaVersion",
        "jobId",
        "requestId",
        "candidateId",
        "fromVersion",
        "queuedAt",
    }


def test_queue_persists_trigger_before_return(monkeypatch, tmp_path: Path) -> None:
    request_file, status_file = _configure_update_paths(monkeypatch, tmp_path)
    candidate_revision = "d" * 40
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="available",
            canUpdate=True,
            candidateId=candidate_revision,
        ).model_dump_json(),
        encoding="utf-8",
    )

    response, returned_trigger = backend_update.queue_backend_update(
        backend_update.BackendUpdateStartPayload(
            candidateId=candidate_revision,
            requestId="request-sync",
        )
    )

    assert response.accepted is True
    assert request_file.exists()
    trigger = json.loads(request_file.read_text(encoding="utf-8"))
    assert returned_trigger == trigger
    assert trigger["jobId"] == response.jobId
    assert json.loads(status_file.read_text(encoding="utf-8"))["state"] == "queued"


def test_admin_update_returns_service_unavailable_when_trigger_cannot_be_written(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    request_file, status_file = _configure_update_paths(monkeypatch, tmp_path)
    candidate_revision = "d" * 40
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="available",
            canUpdate=True,
            candidateId=candidate_revision,
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        backend_update,
        "write_backend_update_trigger",
        lambda trigger: (_ for _ in ()).throw(OSError("read-only runtime")),
    )
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        session = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        ).json()
        response = client.post(
            "/admin/api/backend-update",
            headers={ADMIN_CSRF_HEADER: session["csrfToken"]},
            json={"candidateId": candidate_revision, "requestId": "request-failed"},
        )

    assert response.status_code == 503
    assert not request_file.exists()
    persisted = json.loads(status_file.read_text(encoding="utf-8"))
    assert persisted["state"] == "failed"
    assert persisted["error"] == "UPDATE_TRIGGER_FAILED"


def test_missing_queued_trigger_is_reconciled_after_grace(monkeypatch, tmp_path: Path) -> None:
    _, status_file = _configure_update_paths(monkeypatch, tmp_path)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(backend_update, "_utc_now", lambda: now)
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="queued",
            candidateId="e" * 40,
            jobId="queued-job",
            startedAt=(now - timedelta(seconds=31)).isoformat().replace("+00:00", "Z"),
        ).model_dump_json(),
        encoding="utf-8",
    )

    result = backend_update.get_backend_update_status()

    assert result.state == "failed"
    assert result.error == "UPDATE_TRIGGER_MISSING"
    assert json.loads(status_file.read_text(encoding="utf-8"))["state"] == "failed"


def test_queued_timeout_cancels_matching_trigger(monkeypatch, tmp_path: Path) -> None:
    request_file, status_file = _configure_update_paths(monkeypatch, tmp_path)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(backend_update, "_utc_now", lambda: now)
    candidate_id = "f" * 40
    job_id = "queued-job"
    queued_at = (now - timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="queued",
            candidateId=candidate_id,
            jobId=job_id,
            startedAt=queued_at,
        ).model_dump_json(),
        encoding="utf-8",
    )
    request_file.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "requestId": "request-timeout",
                "candidateId": candidate_id,
                "fromVersion": APP_VERSION,
                "queuedAt": queued_at,
            }
        ),
        encoding="utf-8",
    )

    result = backend_update.get_backend_update_status()

    assert result.state == "failed"
    assert result.error == "UPDATE_QUEUE_TIMEOUT"
    assert not request_file.exists()


def test_admin_update_rejects_stale_candidate_and_extra_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_admin(monkeypatch)
    _, status_file = _configure_update_paths(monkeypatch, tmp_path)
    status_file.write_text(
        backend_update.BackendUpdateStatus(
            state="available",
            canUpdate=True,
            candidateId="b" * 40,
        ).model_dump_json(),
        encoding="utf-8",
    )
    application = create_application(routers=[], public_routers=[admin_router])

    with TestClient(application) as client:
        session = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        ).json()
        headers = {ADMIN_CSRF_HEADER: session["csrfToken"]}
        stale = client.post(
            "/admin/api/backend-update",
            headers=headers,
            json={"candidateId": "c" * 40, "requestId": "request-1234"},
        )
        invalid = client.post(
            "/admin/api/backend-update",
            headers=headers,
            json={
                "candidateId": "b" * 40,
                "requestId": "request-5678",
                "command": "touch /tmp/not-allowed",
            },
        )

    assert stale.status_code == 409
    assert invalid.status_code == 422
    assert not (tmp_path / "run" / "update-request.json").exists()
