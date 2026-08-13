from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path

from .admin_auth import (
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)


def update_backend_environment(path: Path, password: str) -> None:
    password_hash = hash_admin_password(password)
    session_secret = secrets.token_hex(32)
    _replace_environment_values(
        path,
        {
            ADMIN_PASSWORD_HASH_ENV: password_hash,
            ADMIN_SESSION_SECRET_ENV: session_secret,
        },
    )


def ensure_admin_session_secret(path: Path) -> None:
    values = _read_environment_values(path)
    if not values.get(ADMIN_PASSWORD_HASH_ENV):
        raise ValueError("管理密码尚未配置")
    if values.get(ADMIN_SESSION_SECRET_ENV):
        return
    _replace_environment_values(
        path,
        {ADMIN_SESSION_SECRET_ENV: secrets.token_hex(32)},
    )


def _read_environment_values(path: Path) -> dict[str, str]:
    return {
        key: value
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
        for key, value in (line.split("=", 1),)
    }


def _replace_environment_values(path: Path, replacements: dict[str, str]) -> None:
    original = path.stat()
    if not stat.S_ISREG(original.st_mode):
        raise ValueError(f"配置不是普通文件：{path}")

    retained_lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(f"{key}=") for key in replacements)
    ]
    retained_lines.extend(f"{key}={value}" for key, value in replacements.items())
    payload = "\n".join(retained_lines) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(prefix=".backend.env.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, stat.S_IMODE(original.st_mode))
        if hasattr(os, "fchown"):
            os.fchown(descriptor, original.st_uid, original.st_gid)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="更新青卷管理密码摘要并轮换会话密钥")
    parser.add_argument("--ensure-session-secret", action="store_true")
    parser.add_argument("backend_env", type=Path)
    arguments = parser.parse_args()
    if arguments.ensure_session_secret:
        try:
            ensure_admin_session_secret(arguments.backend_env)
        except (OSError, ValueError, RuntimeError) as error:
            raise SystemExit(str(error)) from error
        return

    password = sys.stdin.read(257)
    if len(password) > 256:
        raise SystemExit("管理密码不能超过 256 个字符")
    try:
        update_backend_environment(arguments.backend_env, password)
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
