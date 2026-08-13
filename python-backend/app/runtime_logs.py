from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import deque
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import db

RUNTIME_LOG_FILE_ENV = "QINGJUAN_RUNTIME_LOG_FILE"
RUNTIME_LOG_MAX_BYTES = 2 * 1024 * 1024
RUNTIME_LOG_BACKUP_COUNT = 2
_MAX_LOG_MESSAGE_LENGTH = 20_000
_MAX_LOG_LINE_LENGTH = 64 * 1024
_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}
_LOGGER_NAMES = ("qingjuan", "uvicorn.error", "uvicorn.access")
_RUNTIME_HANDLER: RotatingFileHandler | None = None
_HANDLER_LOCK = threading.RLock()

_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/-]{8,}=*)"
    ),
    re.compile(
        r"(?i)((?:api[_ -]?key|token|password|secret|csrf(?:token)?|cookie|"
        r"管理密码|连接\s*token|api\s*密钥)\s*[:=：]\s*[\"']?)([^\s,;，；\"'}]{4,})"
    ),
)
_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\r\n]+\\)*[^\\\r\n\s,;:)}\]]+"),
    re.compile(r"(?<![\w/:])/(?:home|var|etc|opt|tmp|srv|root|Users)(?:/[^\s,;:)}\]]+)+"),
)


class RuntimeLogRecord(BaseModel):
    timestamp: str
    level: Literal["debug", "info", "warning", "error", "critical"]
    source: str
    message: str


class RuntimeLogBatch(BaseModel):
    items: list[RuntimeLogRecord] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    total: int = 0


class RuntimeLogReadError(RuntimeError):
    pass


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            if exception_text:
                message = f"{message}\n{exception_text}"
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "source": record.name,
            "message": redact_runtime_log_message(message),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def runtime_log_file_path() -> Path:
    override = os.getenv(RUNTIME_LOG_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (db.DATA_DIR / "logs" / "server.jsonl").resolve()


def configure_runtime_logging() -> Path:
    global _RUNTIME_HANDLER
    path = runtime_log_file_path()
    with _HANDLER_LOCK:
        if _RUNTIME_HANDLER is not None:
            if Path(_RUNTIME_HANDLER.baseFilename) == path:
                return path
            shutdown_runtime_logging()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = RotatingFileHandler(
            path,
            maxBytes=RUNTIME_LOG_MAX_BYTES,
            backupCount=RUNTIME_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(_JsonLogFormatter())
        for logger_name in _LOGGER_NAMES:
            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
            if logger_name == "qingjuan":
                logger.setLevel(logging.INFO)
                logger.propagate = False
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        _RUNTIME_HANDLER = handler
    return path


def shutdown_runtime_logging() -> None:
    global _RUNTIME_HANDLER
    with _HANDLER_LOCK:
        handler = _RUNTIME_HANDLER
        if handler is None:
            return
        for logger_name in _LOGGER_NAMES:
            logging.getLogger(logger_name).removeHandler(handler)
        logging.getLogger().removeHandler(handler)
        handler.close()
        _RUNTIME_HANDLER = None


def read_runtime_logs(*, limit: int = 500) -> RuntimeLogBatch:
    safe_limit = max(1, min(limit, 1000))
    records: deque[RuntimeLogRecord] = deque(maxlen=safe_limit)
    sources: set[str] = set()
    total = 0
    try:
        for path in _runtime_log_files():
            if not path.is_file():
                continue
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    record = _parse_runtime_log_line(raw_line)
                    if record is None:
                        continue
                    sources.add(record.source)
                    total += 1
                    records.append(record)
    except OSError as error:
        raise RuntimeLogReadError("运行日志暂时不可读取") from error
    return RuntimeLogBatch(items=list(records), sources=sorted(sources), total=total)


def redact_runtime_log_message(message: object) -> str:
    redacted = str(message).replace("\x00", "").strip()
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    for pattern in _ABSOLUTE_PATH_PATTERNS:
        redacted = pattern.sub("[PATH]", redacted)
    if len(redacted) > _MAX_LOG_MESSAGE_LENGTH:
        redacted = f"{redacted[:_MAX_LOG_MESSAGE_LENGTH]}…[truncated]"
    return redacted


def runtime_log_storage_bytes() -> int:
    try:
        return sum(path.stat().st_size for path in _runtime_log_files() if path.is_file())
    except OSError as error:
        raise RuntimeLogReadError("运行日志暂时不可读取") from error


def _runtime_log_files() -> list[Path]:
    current = runtime_log_file_path()
    backups = [Path(f"{current}.{index}") for index in range(RUNTIME_LOG_BACKUP_COUNT, 0, -1)]
    return [*backups, current]


def _parse_runtime_log_line(raw_line: str) -> RuntimeLogRecord | None:
    if not raw_line.strip() or len(raw_line) > _MAX_LOG_LINE_LENGTH:
        return None
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    timestamp = str(payload.get("timestamp") or "").strip()
    source = str(payload.get("source") or "qingjuan").strip()[:120] or "qingjuan"
    level = str(payload.get("level") or "info").strip().lower()
    if not timestamp or level not in _LOG_LEVELS:
        return None
    return RuntimeLogRecord(
        timestamp=timestamp,
        level=level,
        source=source,
        message=redact_runtime_log_message(payload.get("message") or ""),
    )
