#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly REQUEST_FILE="/run/qingjuan/update-request.json"
readonly STATUS_FILE="/var/lib/qingjuan/backend-update.json"
readonly UPDATER_STATE_DIR="/var/lib/qingjuan-updater"
readonly REPO_DIR="/opt/qingjuan/app"
readonly UPDATE_SCRIPT="$REPO_DIR/deploy/linux/update.sh"
readonly SERVICE_USER="qingjuan"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf '受控升级器必须由 root 运行。\n' >&2
  exit 1
fi

cleanup_runner_copy() {
  local target="${QINGJUAN_UPDATE_RUNNER_TEMP:-}"
  case "$target" in
    "$UPDATER_STATE_DIR"/runner.*) rm -f -- "$target" ;;
  esac
}

if [[ -L "$UPDATER_STATE_DIR" ]] || { [[ -e "$UPDATER_STATE_DIR" ]] && [[ ! -d "$UPDATER_STATE_DIR" ]]; }; then
  printf '升级器状态目录类型不安全。\n' >&2
  exit 1
fi
install -d -o root -g root -m 0700 "$UPDATER_STATE_DIR"

JOB_ID=""
CANDIDATE_ID=""
FROM_VERSION=""
QUEUED_AT=""
finished="false"

mark_current_status_failed() {
  local message="$1"
  local error_code="$2"
  python3 - "$STATUS_FILE" "$SERVICE_USER" "$message" "$error_code" <<'PY'
import datetime
import json
import os
import pwd
import stat
import sys
import tempfile

path, group_name, message, error_code = sys.argv[1:]
try:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
except OSError:
    raise SystemExit(0)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
        raise SystemExit(0)
    with os.fdopen(descriptor, encoding="utf-8") as stream:
        descriptor = -1
        payload = json.load(stream)
finally:
    if descriptor >= 0:
        os.close(descriptor)
if payload.get("state") != "queued":
    raise SystemExit(0)
now = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
payload["state"] = "failed"
payload["canUpdate"] = False
payload["finishedAt"] = now
payload["message"] = message
payload["error"] = error_code
directory = os.path.dirname(path)
temporary_descriptor, temporary = tempfile.mkstemp(prefix=".backend-update.", suffix=".tmp", dir=directory)
try:
    group_id = pwd.getpwnam(group_name).pw_gid
    os.fchown(temporary_descriptor, 0, group_id)
    os.fchmod(temporary_descriptor, 0o640)
    with os.fdopen(temporary_descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
}

write_status() {
  local state="$1"
  local message="$2"
  local error_code="${3:-}"
  local version="${4:-$FROM_VERSION}"
  python3 - "$STATUS_FILE" "$SERVICE_USER" "$state" "$message" "$error_code" "$version" "$JOB_ID" "$CANDIDATE_ID" "$QUEUED_AT" <<'PY'
import datetime
import json
import os
import pwd
import stat
import sys
import tempfile

path, group_name, state, message, error_code, version, job_id, candidate_id, queued_at = sys.argv[1:]
allowed_states = {"updating", "restarting", "verifying", "completed", "failed"}
if state not in allowed_states:
    raise SystemExit("invalid updater state")
payload = {
    "schemaVersion": 1,
    "state": state,
    "supported": True,
    "canUpdate": False,
    "currentVersion": version,
    "targetVersion": version if state == "completed" else None,
    "candidateId": candidate_id,
    "jobId": job_id,
    "checkedAt": None,
    "startedAt": queued_at,
    "finishedAt": None,
    "message": message,
    "blockedReason": None,
    "error": error_code or None,
}
try:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
except FileNotFoundError:
    descriptor = -1
if descriptor >= 0:
    try:
        metadata = os.fstat(descriptor)
        if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= 65536:
            with os.fdopen(descriptor, encoding="utf-8") as stream:
                descriptor = -1
                previous = json.load(stream)
            if previous.get("jobId") == job_id:
                payload["checkedAt"] = previous.get("checkedAt")
                if (
                    state == "failed"
                    and previous.get("state") == "failed"
                    and previous.get("error") in {"UPDATE_ROLLED_BACK", "ROLLBACK_FAILED"}
                ):
                    payload["message"] = previous.get("message")
                    payload["error"] = previous.get("error")
                    payload["finishedAt"] = previous.get("finishedAt")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
now = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
if state in {"completed", "failed"} and payload["finishedAt"] is None:
    payload["finishedAt"] = now
directory = os.path.dirname(path)
temporary_descriptor, temporary = tempfile.mkstemp(prefix=".backend-update.", suffix=".tmp", dir=directory)
try:
    group_id = pwd.getpwnam(group_name).pw_gid
    os.fchown(temporary_descriptor, 0, group_id)
    os.fchmod(temporary_descriptor, 0o640)
    with os.fdopen(temporary_descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY
}

on_exit() {
  local exit_code="${1:-$?}"
  if [[ "$finished" != "true" && "$exit_code" -ne 0 ]]; then
    if [[ -n "$JOB_ID" ]]; then
      write_status "failed" "后端升级失败；请查看升级服务日志" "UPDATE_EXECUTION_FAILED" || true
    else
      rm -rf -- "$REQUEST_FILE"
      mark_current_status_failed "系统升级服务拒绝了无效请求，请重新检查更新" "UPDATE_REQUEST_INVALID" || true
    fi
  fi
  cleanup_runner_copy
}
trap on_exit EXIT

if [[ "${QINGJUAN_UPDATE_RUNNER_COPY:-}" != "1" ]]; then
  runner_copy="$(mktemp "$UPDATER_STATE_DIR/runner.XXXXXX")"
  install -o root -g root -m 0700 "$0" "$runner_copy"
  QINGJUAN_UPDATE_RUNNER_COPY=1 QINGJUAN_UPDATE_RUNNER_TEMP="$runner_copy" exec "$runner_copy" "$@"
fi

if [[ ! -e "$REQUEST_FILE" && ! -L "$REQUEST_FILE" ]]; then
  finished="true"
  exit 0
fi
if [[ ! -x /usr/bin/python3 && ! -x /bin/python3 ]]; then
  printf '受控升级器找不到 Python 3。\n' >&2
  rm -rf -- "$REQUEST_FILE"
  exit 1
fi

parsed_request="$(mktemp "$UPDATER_STATE_DIR/request.XXXXXX")"
cleanup_parsed_request() {
  rm -f -- "$parsed_request"
}
finalize_exit() {
  local exit_code=$?
  cleanup_parsed_request
  on_exit "$exit_code"
}
trap finalize_exit EXIT
rejected_request="$UPDATER_STATE_DIR/rejected-request.$(date -u +%Y%m%dT%H%M%SZ).$$.json"
if ! python3 - "$REQUEST_FILE" "$rejected_request" "$SERVICE_USER" >"$parsed_request" <<'PY'
import datetime
import json
import os
import pwd
import re
import stat
import sys
import uuid

path, rejected_path, service_user = sys.argv[1:]
raw = b""
directory, name = os.path.split(path)
directory_descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_descriptor,
    )
    try:
        metadata = os.fstat(descriptor)
        expected_uid = pwd.getpwnam(service_user).pw_uid
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_nlink != 1
            or metadata.st_size > 65536
        ):
            raise ValueError("升级请求文件权限或类型无效")
        raw = os.read(descriptor, 65537)
        if len(raw) > 65536:
            raise ValueError("升级请求文件过大")
    finally:
        os.close(descriptor)
    payload = json.loads(raw.decode("utf-8"))
    expected_keys = {"schemaVersion", "jobId", "requestId", "candidateId", "fromVersion", "queuedAt"}
    if not isinstance(payload, dict) or set(payload) != expected_keys or payload.get("schemaVersion") != 1:
        raise ValueError("升级请求格式无效")
    candidate = str(payload["candidateId"])
    if re.fullmatch(r"[0-9a-f]{40,64}", candidate) is None:
        raise ValueError("候选版本标识无效")
    job_id = str(payload["jobId"])
    request_id = str(payload["requestId"])
    try:
        parsed_job_id = uuid.UUID(job_id)
    except ValueError as error:
        raise ValueError("升级任务标识无效") from error
    if str(parsed_job_id) != job_id or parsed_job_id.version != 4:
        raise ValueError("升级任务标识无效")
    if re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id) is None:
        raise ValueError("升级请求标识无效")
    from_version = str(payload["fromVersion"])
    queued_at = str(payload["queuedAt"])
    if len(from_version) > 64 or any(not char.isprintable() for char in from_version):
        raise ValueError("来源版本无效")
    if len(queued_at) > 64 or any(not char.isprintable() for char in queued_at):
        raise ValueError("排队时间无效")
    datetime.datetime.fromisoformat(queued_at.replace("Z", "+00:00"))
    for value in (job_id, request_id, candidate, from_version, queued_at):
        print(value)
except Exception:
    if raw:
        rejected_descriptor = os.open(
            rejected_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(rejected_descriptor, "wb") as rejected:
            rejected.write(raw[:65536])
    raise
finally:
    try:
        os.unlink(name, dir_fd=directory_descriptor)
    except (FileNotFoundError, IsADirectoryError):
        pass
    os.close(directory_descriptor)
PY
then
  rm -rf -- "$REQUEST_FILE"
  printf '升级请求无效，已拒绝并隔离。\n' >&2
  exit 1
fi

mapfile -t request_values < "$parsed_request"
if [[ "${#request_values[@]}" -ne 5 ]]; then
  printf '升级请求缺少必要字段。\n' >&2
  exit 1
fi

readonly JOB_ID="${request_values[0]}"
readonly REQUEST_ID="${request_values[1]}"
readonly CANDIDATE_ID="${request_values[2]}"
readonly FROM_VERSION="${request_values[3]}"
readonly QUEUED_AT="${request_values[4]}"

write_status "updating" "正在准备独立 release，当前服务仍可使用"
export QINGJUAN_ONLINE_UPDATE_JOB_ID="$JOB_ID"
export QINGJUAN_UPDATE_STATUS_FILE="$STATUS_FILE"
bash "$UPDATE_SCRIPT" --online --expected-revision "$CANDIDATE_ID"

target_version="$(sed -nE 's/^version:[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' "$REPO_DIR/pubspec.yaml" | head -n 1)"
if [[ -z "$target_version" ]]; then
  target_version="$FROM_VERSION"
fi
write_status "completed" "后端升级完成，服务已从新 release 恢复" "" "$target_version"
finished="true"
printf '青卷后端升级任务 %s 已完成。\n' "$JOB_ID"
