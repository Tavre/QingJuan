from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .application import APP_VERSION

UPDATE_REQUEST_FILE_ENV = "QINGJUAN_UPDATE_REQUEST_FILE"
UPDATE_STATUS_FILE_ENV = "QINGJUAN_UPDATE_STATUS_FILE"
UPDATE_REPO_DIR_ENV = "QINGJUAN_UPDATE_REPO_DIR"

BackendUpdateState = Literal[
    "idle",
    "checking",
    "up_to_date",
    "available",
    "queued",
    "updating",
    "restarting",
    "verifying",
    "completed",
    "failed",
    "unsupported",
]

_ACTIVE_STATES = {"checking", "queued", "updating", "restarting", "verifying"}
_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
_UPSTREAM_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$")
_MAX_STATUS_BYTES = 64 * 1024
_QUEUED_TRIGGER_GRACE_SECONDS = 30
_QUEUED_TIMEOUT_SECONDS = 5 * 60
_UPDATE_LOCK = threading.Lock()


class BackendUpdateStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    state: BackendUpdateState = "idle"
    supported: bool = True
    canUpdate: bool = False
    currentVersion: str = APP_VERSION
    targetVersion: str | None = None
    candidateId: str | None = None
    jobId: str | None = None
    checkedAt: str | None = None
    startedAt: str | None = None
    finishedAt: str | None = None
    message: str = "尚未检查后端更新"
    blockedReason: str | None = None
    error: str | None = None


class BackendUpdateStartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidateId: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    requestId: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9-]+$")


class BackendUpdateStartResponse(BaseModel):
    accepted: Literal[True] = True
    jobId: str
    fromVersion: str
    targetVersion: str | None = None
    disconnectExpected: Literal[True] = True


class BackendUpdateError(RuntimeError):
    pass


class BackendUpdateUnsupported(BackendUpdateError):
    pass


class BackendUpdateConflict(BackendUpdateError):
    pass


class BackendUpdateDispatchError(BackendUpdateError):
    pass


def backend_update_supported() -> bool:
    return _support_blocked_reason() is None


def get_backend_update_status() -> BackendUpdateStatus:
    with _UPDATE_LOCK:
        return _get_backend_update_status()


def _get_backend_update_status() -> BackendUpdateStatus:
    blocked_reason = _support_blocked_reason()
    if blocked_reason is not None:
        return BackendUpdateStatus(
            state="unsupported",
            supported=False,
            message="当前部署尚未启用在线升级",
            blockedReason=blocked_reason,
        )

    status_path = _status_path()
    if not status_path.exists():
        return BackendUpdateStatus()
    try:
        payload = _read_json_file(status_path)
        result = BackendUpdateStatus.model_validate(payload)
    except (OSError, ValueError, ValidationError):
        return BackendUpdateStatus(
            state="failed",
            message="升级状态文件无法读取，请在服务器终端检查升级服务",
            error="UPDATE_STATUS_INVALID",
        )
    result.currentVersion = APP_VERSION
    result.supported = True
    result.canUpdate = result.state == "available"
    if result.state == "queued":
        result = _reconcile_queued_status(result)
    return result


def check_for_backend_update() -> BackendUpdateStatus:
    with _UPDATE_LOCK:
        blocked_reason = _support_blocked_reason()
        if blocked_reason is not None:
            raise BackendUpdateUnsupported(blocked_reason)
        current_status = _get_backend_update_status()
        if current_status.state in _ACTIVE_STATES - {"checking"}:
            raise BackendUpdateConflict("已有后端升级任务正在执行")

        checking = BackendUpdateStatus(
            state="checking",
            message="正在检查部署仓库的上游版本",
            checkedAt=_now(),
        )
        _write_status(checking)
        try:
            current_revision = _git("rev-parse", "HEAD")
            upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
            if _UPSTREAM_PATTERN.fullmatch(upstream) is None:
                raise BackendUpdateError("部署仓库没有可用的固定上游分支")
            remote_name, branch_name = upstream.split("/", 1)
            remote_url = _git("config", "--get", f"remote.{remote_name}.url")
            if not remote_url:
                raise BackendUpdateError("部署仓库没有配置上游地址")
            remote_line = _run_git(
                "ls-remote",
                "--exit-code",
                "--heads",
                "--",
                remote_url,
                f"refs/heads/{branch_name}",
                use_repo=False,
            ).splitlines()[0]
            candidate_id = remote_line.split(maxsplit=1)[0].lower()
            if _REVISION_PATTERN.fullmatch(candidate_id) is None:
                raise BackendUpdateError("上游返回了无效的版本标识")

            available = candidate_id != current_revision.lower()
            result = BackendUpdateStatus(
                state="available" if available else "up_to_date",
                canUpdate=available,
                candidateId=candidate_id,
                checkedAt=_now(),
                message="检测到可用的后端更新" if available else "当前后端已是上游最新版本",
            )
        except (BackendUpdateError, OSError, subprocess.SubprocessError, IndexError):
            result = BackendUpdateStatus(
                state="failed",
                checkedAt=_now(),
                message="无法检查上游更新，请确认服务器能够访问部署仓库",
                error="UPDATE_CHECK_FAILED",
            )
        _write_status(result)
        return result


def queue_backend_update(
    payload: BackendUpdateStartPayload,
) -> tuple[BackendUpdateStartResponse, dict[str, str | int]]:
    with _UPDATE_LOCK:
        blocked_reason = _support_blocked_reason()
        if blocked_reason is not None:
            raise BackendUpdateUnsupported(blocked_reason)
        current = _get_backend_update_status()
        if current.state in _ACTIVE_STATES:
            raise BackendUpdateConflict("已有后端升级任务正在执行")
        if (
            current.state != "available"
            or current.candidateId is None
            or payload.candidateId != current.candidateId
        ):
            raise BackendUpdateConflict("可用版本已经变化，请重新检查更新")

        job_id = str(uuid4())
        queued_at = _now()
        queued = current.model_copy(
            update={
                "state": "queued",
                "canUpdate": False,
                "jobId": job_id,
                "startedAt": queued_at,
                "finishedAt": None,
                "message": "升级任务已受理，正在交给系统升级服务",
                "error": None,
            }
        )
        trigger = {
            "schemaVersion": 1,
            "jobId": job_id,
            "requestId": payload.requestId,
            "candidateId": payload.candidateId,
            "fromVersion": APP_VERSION,
            "queuedAt": queued_at,
        }
        response = BackendUpdateStartResponse(
            jobId=job_id,
            fromVersion=APP_VERSION,
            targetVersion=current.targetVersion,
        )
        try:
            _write_status(queued)
            write_backend_update_trigger(trigger)
        except OSError as error:
            failed = queued.model_copy(
                update={
                    "state": "failed",
                    "finishedAt": _now(),
                    "message": "系统升级服务未能接收任务，请在服务器终端检查部署",
                    "error": "UPDATE_TRIGGER_FAILED",
                }
            )
            with suppress(OSError):
                _write_status(failed)
            raise BackendUpdateDispatchError("系统升级服务暂时无法接收任务") from error
        return response, trigger


def write_backend_update_trigger(trigger: dict[str, str | int]) -> None:
    _atomic_write_json(_request_path(), trigger, mode=0o600)


def _reconcile_queued_status(current: BackendUpdateStatus) -> BackendUpdateStatus:
    age_seconds = _queued_age_seconds(current.startedAt)
    trigger_matches = _queued_trigger_matches(current)

    if age_seconds is None:
        return _fail_queued_status(
            current,
            message="升级排队状态无效，请重新检查更新",
            error="UPDATE_QUEUE_STATE_INVALID",
        )
    if not trigger_matches and age_seconds >= _QUEUED_TRIGGER_GRACE_SECONDS:
        return _fail_queued_status(
            current,
            message="系统升级服务未接收到排队任务，请重新检查更新",
            error="UPDATE_TRIGGER_MISSING",
        )
    if age_seconds < _QUEUED_TIMEOUT_SECONDS:
        return current

    if trigger_matches:
        with suppress(OSError, ValueError):
            _remove_matching_queued_trigger(current)
    return _fail_queued_status(
        current,
        message="升级任务排队超时，请检查系统升级服务后重试",
        error="UPDATE_QUEUE_TIMEOUT",
    )


def _queued_trigger_matches(current: BackendUpdateStatus) -> bool:
    try:
        payload = _read_json_file(_request_path())
    except (OSError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("jobId") == current.jobId
        and payload.get("candidateId") == current.candidateId
    )


def _remove_matching_queued_trigger(current: BackendUpdateStatus) -> None:
    request_path = _request_path()
    payload = _read_json_file(request_path)
    if (
        isinstance(payload, dict)
        and payload.get("jobId") == current.jobId
        and payload.get("candidateId") == current.candidateId
    ):
        request_path.unlink()


def _queued_age_seconds(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        normalized = started_at[:-1] + "+00:00" if started_at.endswith("Z") else started_at
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return max(0.0, (_utc_now() - timestamp.astimezone(UTC)).total_seconds())


def _fail_queued_status(
    current: BackendUpdateStatus,
    *,
    message: str,
    error: str,
) -> BackendUpdateStatus:
    failed = current.model_copy(
        update={
            "state": "failed",
            "canUpdate": False,
            "finishedAt": _now(),
            "message": message,
            "error": error,
        }
    )
    with suppress(OSError):
        _write_status(failed)
    return failed


def _support_blocked_reason() -> str | None:
    request_value = os.getenv(UPDATE_REQUEST_FILE_ENV, "").strip()
    status_value = os.getenv(UPDATE_STATUS_FILE_ENV, "").strip()
    if not request_value or not status_value:
        return "请先在服务器终端执行一次新版 update.sh 以安装在线升级服务"
    repo = _repo_dir()
    if not (repo / ".git").is_dir():
        return "当前后端不是受管理的 Git 部署"
    request_path = Path(request_value)
    status_path = Path(status_value)
    if not request_path.is_absolute() or not status_path.is_absolute():
        return "在线升级路径配置无效"
    if not request_path.parent.is_dir() or not os.access(request_path.parent, os.W_OK):
        return "系统升级触发目录不可写"
    if not status_path.parent.is_dir() or not os.access(status_path.parent, os.W_OK | os.R_OK):
        return "系统升级状态目录不可用"
    for path in (request_path, status_path):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return "在线升级状态路径不安全"
    return None


def _git(*arguments: str) -> str:
    return _run_git(*arguments, use_repo=True)


def _run_git(*arguments: str, use_repo: bool) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={_repo_dir()}",
        "-c",
        "protocol.ext.allow=never",
    ]
    if use_repo:
        command.extend(["-C", str(_repo_dir())])
    command.extend(arguments)
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_ALLOW_PROTOCOL"] = "https:http:ssh:git"
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )
    return result.stdout.strip()


def _read_json_file(path: Path) -> object:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("unsafe status file")
    if metadata.st_size > _MAX_STATUS_BYTES:
        raise ValueError("status file is too large")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_status(value: BackendUpdateStatus) -> None:
    _atomic_write_json(_status_path(), value.model_dump(mode="json"), mode=0o640)


def _atomic_write_json(path: Path, value: object, *, mode: int) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_parent_directory(path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _fsync_parent_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _repo_dir() -> Path:
    return Path(os.getenv(UPDATE_REPO_DIR_ENV, "/opt/qingjuan/app")).resolve()


def _request_path() -> Path:
    return Path(os.environ[UPDATE_REQUEST_FILE_ENV])


def _status_path() -> Path:
    return Path(os.environ[UPDATE_STATUS_FILE_ENV])


def _now() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)
