import json
import logging
from pathlib import Path

from app.runtime_logs import (
    RUNTIME_LOG_FILE_ENV,
    configure_runtime_logging,
    read_runtime_logs,
    shutdown_runtime_logging,
)


def test_runtime_logs_capture_details_and_redact_secrets(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "server.jsonl"
    monkeypatch.setenv(RUNTIME_LOG_FILE_ENV, str(log_path))
    shutdown_runtime_logging()
    try:
        configure_runtime_logging()
        logger = logging.getLogger("qingjuan.task")
        logger.info("任务已启动")
        logger.warning("Authorization: Bearer super-secret-token")
        logger.error("API key: provider-secret-value")
        logger.warning("本机文件 C:\\Users\\operator\\private\\payload.txt 无法读取")
        try:
            _ = 1 / 0
        except ZeroDivisionError:
            logger.exception("任务程序异常")

        batch = read_runtime_logs(limit=50)
    finally:
        shutdown_runtime_logging()

    messages = "\n".join(record.message for record in batch.items)
    assert batch.total == 5
    assert batch.sources == ["qingjuan.task"]
    assert "任务已启动" in messages
    assert "Traceback" in messages
    assert "ZeroDivisionError" in messages
    assert "super-secret-token" not in messages
    assert "provider-secret-value" not in messages
    assert "C:\\Users\\operator\\private" not in messages
    assert "[PATH]" in messages
    assert messages.count("[REDACTED]") >= 2


def test_runtime_logs_read_rotated_files_and_skip_invalid_lines(
    monkeypatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "server.jsonl"
    monkeypatch.setenv(RUNTIME_LOG_FILE_ENV, str(log_path))
    rotated = Path(f"{log_path}.1")
    rotated.write_text(
        json.dumps(
            {
                "timestamp": "2030-01-01T00:00:00Z",
                "level": "info",
                "source": "qingjuan.runtime",
                "message": "上一轮服务日志",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    log_path.write_text(
        "not-json\n"
        + json.dumps(
            {
                "timestamp": "2030-01-01T00:01:00Z",
                "level": "error",
                "source": "uvicorn.error",
                "message": "当前服务日志",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    batch = read_runtime_logs(limit=10)

    assert batch.total == 2
    assert [record.message for record in batch.items] == ["上一轮服务日志", "当前服务日志"]
    assert batch.sources == ["qingjuan.runtime", "uvicorn.error"]
