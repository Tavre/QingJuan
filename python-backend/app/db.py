from __future__ import annotations

import os
import sqlite3
import shutil
import sys
from pathlib import Path

from .models import (
    BookRecord,
    ComicSourceConfig,
    ProviderConfig,
    ReadingProgressRecord,
    TaskLogRecord,
    TaskRecord,
    TranslationSettings,
)

BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = BASE_DIR / "data"
APP_DIR_NAME = "QingJuan"


def _resolve_platform_data_dirs() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.getenv(env_name, "").strip()
            if base:
                candidates.append((Path(base) / APP_DIR_NAME / "data").resolve())
    else:
        xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
        if xdg_data_home:
            candidates.append((Path(xdg_data_home) / "qingjuan").resolve())
        candidates.append((Path.home() / ".local" / "share" / "qingjuan").resolve())
    return candidates


def _resolve_default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / "data").resolve()
    return LEGACY_DATA_DIR.resolve()


def _resolve_data_dir() -> Path:
    override = os.getenv("QINGJUAN_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _resolve_default_data_dir()


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "qingjuan.db"
_DATA_DIR_READY = False

DEFAULT_SETTINGS = TranslationSettings(
    defaultProvider="openai",
    autoTranslateNextChapters=0,
    providers={
        "openai": ProviderConfig(enabled=True, baseUrl="https://api.openai.com/v1", model="gpt-5.4"),
        "newapi": ProviderConfig(enabled=False, baseUrl="https://your-newapi-endpoint/v1", model="gpt-5.4"),
        "anthropic": ProviderConfig(enabled=False, baseUrl="https://api.anthropic.com/v1", model="claude-3-7-sonnet-latest"),
        "grok2api": ProviderConfig(enabled=False, baseUrl="http://127.0.0.1:8000/v1", model="grok-4"),
        "custom": ProviderConfig(enabled=False, baseUrl="https://localhost:8001/v1", model="custom-model"),
    },
    bika=ComicSourceConfig(),
)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    return sqlite3.connect(DB_PATH)


def ensure_data_dir() -> None:
    global _DATA_DIR_READY
    if _DATA_DIR_READY:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_data()
    _DATA_DIR_READY = True


def _migrate_legacy_data() -> None:
    if any(DATA_DIR.iterdir()):
        return
    migration_sources: list[Path] = []
    migration_sources.extend(_resolve_platform_data_dirs())
    migration_sources.append(LEGACY_DATA_DIR.resolve())

    seen_sources: set[Path] = set()
    for source_dir in migration_sources:
        if source_dir in seen_sources or source_dir == DATA_DIR:
            continue
        seen_sources.add(source_dir)
        if not source_dir.exists():
            continue
        if not any(source_dir.iterdir()):
            continue
        shutil.copytree(source_dir, DATA_DIR, dirs_exist_ok=True)
        break


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                book_kind TEXT NOT NULL,
                language TEXT NOT NULL,
                status TEXT NOT NULL,
                chapter_count INTEGER NOT NULL,
                translated INTEGER NOT NULL,
                local_path TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                synopsis TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reading_progress (
                book_id TEXT PRIMARY KEY,
                last_chapter_index INTEGER NOT NULL,
                last_scroll_ratio REAL NOT NULL DEFAULT 0,
                last_anchor_type TEXT NOT NULL DEFAULT 'top',
                last_anchor_index INTEGER NOT NULL DEFAULT 0,
                last_anchor_offset_ratio REAL NOT NULL DEFAULT 0,
                last_read_at TEXT
            )
            """
        )
        _ensure_reading_progress_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                chapter_indexes TEXT NOT NULL,
                status TEXT NOT NULL,
                total_count INTEGER NOT NULL,
                completed_count INTEGER NOT NULL,
                progress REAL NOT NULL,
                message TEXT NOT NULL,
                error TEXT,
                attempts INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_logs (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_logs_task_sequence
            ON task_logs (task_id, sequence)
            """
        )


def _ensure_reading_progress_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(reading_progress)").fetchall()
    }
    required_columns = {
        "last_scroll_ratio": "ALTER TABLE reading_progress ADD COLUMN last_scroll_ratio REAL NOT NULL DEFAULT 0",
        "last_anchor_type": "ALTER TABLE reading_progress ADD COLUMN last_anchor_type TEXT NOT NULL DEFAULT 'top'",
        "last_anchor_index": "ALTER TABLE reading_progress ADD COLUMN last_anchor_index INTEGER NOT NULL DEFAULT 0",
        "last_anchor_offset_ratio": "ALTER TABLE reading_progress ADD COLUMN last_anchor_offset_ratio REAL NOT NULL DEFAULT 0",
    }
    for column_name, statement in required_columns.items():
        if column_name not in existing_columns:
            conn.execute(statement)


def list_books() -> list[BookRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT b.id, b.title, b.source_url, b.book_kind, b.language, b.status,
                   b.chapter_count, b.translated, b.local_path, b.updated_at, b.synopsis,
                   COALESCE(rp.last_chapter_index, 0), rp.last_read_at
            FROM books b
            LEFT JOIN reading_progress rp ON rp.book_id = b.id
            ORDER BY b.updated_at DESC
            """
        ).fetchall()

    return [_row_to_book(row) for row in rows]


def get_book(book_id: str) -> BookRecord | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT b.id, b.title, b.source_url, b.book_kind, b.language, b.status,
                   b.chapter_count, b.translated, b.local_path, b.updated_at, b.synopsis,
                   COALESCE(rp.last_chapter_index, 0), rp.last_read_at
            FROM books b
            LEFT JOIN reading_progress rp ON rp.book_id = b.id
            WHERE b.id = ?
            """,
            (book_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_book(row)


def save_book(book: BookRecord) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO books (
                id, title, source_url, book_kind, language, status,
                chapter_count, translated, local_path, updated_at, synopsis
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book.id,
                book.title,
                book.sourceUrl,
                book.bookKind,
                book.language,
                book.status,
                book.chapterCount,
                int(book.translated),
                book.localPath,
                book.updatedAt,
                book.synopsis,
            ),
        )


def delete_book(book_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM task_logs
            WHERE task_id IN (SELECT id FROM tasks WHERE book_id = ?)
            """,
            (book_id,),
        )
        conn.execute("DELETE FROM tasks WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM reading_progress WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))


def load_reading_progress(book_id: str) -> ReadingProgressRecord:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                book_id,
                last_chapter_index,
                last_scroll_ratio,
                last_anchor_type,
                last_anchor_index,
                last_anchor_offset_ratio,
                last_read_at
            FROM reading_progress
            WHERE book_id = ?
            """,
            (book_id,),
        ).fetchone()

    if row is None:
        return ReadingProgressRecord(bookId=book_id, lastChapterIndex=0, lastReadAt=None)

    return ReadingProgressRecord(
        bookId=row[0],
        lastChapterIndex=row[1],
        lastScrollRatio=row[2],
        lastAnchorType=row[3],
        lastAnchorIndex=row[4],
        lastAnchorOffsetRatio=row[5],
        lastReadAt=row[6],
    )


def save_reading_progress(progress: ReadingProgressRecord) -> ReadingProgressRecord:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reading_progress (
                book_id,
                last_chapter_index,
                last_scroll_ratio,
                last_anchor_type,
                last_anchor_index,
                last_anchor_offset_ratio,
                last_read_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                last_chapter_index = excluded.last_chapter_index,
                last_scroll_ratio = excluded.last_scroll_ratio,
                last_anchor_type = excluded.last_anchor_type,
                last_anchor_index = excluded.last_anchor_index,
                last_anchor_offset_ratio = excluded.last_anchor_offset_ratio,
                last_read_at = excluded.last_read_at
            """,
            (
                progress.bookId,
                progress.lastChapterIndex,
                progress.lastScrollRatio,
                progress.lastAnchorType,
                progress.lastAnchorIndex,
                progress.lastAnchorOffsetRatio,
                progress.lastReadAt,
            ),
        )
    return progress


def create_task(task: TaskRecord) -> TaskRecord:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, book_id, task_type, chapter_indexes, status, total_count,
                completed_count, progress, message, error, attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.bookId,
                task.taskType,
                json_dumps(task.chapterIndexes),
                task.status,
                task.totalCount,
                task.completedCount,
                task.progress,
                task.message,
                task.error,
                task.attempts,
                task.createdAt,
                task.updatedAt,
            ),
        )
    return task


def get_task(task_id: str) -> TaskRecord | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, book_id, task_type, chapter_indexes, status, total_count,
                   completed_count, progress, message, error, attempts, created_at, updated_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_task(row)


def list_tasks(book_id: str | None = None) -> list[TaskRecord]:
    query = """
        SELECT id, book_id, task_type, chapter_indexes, status, total_count,
               completed_count, progress, message, error, attempts, created_at, updated_at
        FROM tasks
    """
    params: tuple[str, ...] = ()
    if book_id:
        query += " WHERE book_id = ?"
        params = (book_id,)
    query += " ORDER BY updated_at DESC, created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_row_to_task(row) for row in rows]


def list_pending_tasks() -> list[TaskRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, book_id, task_type, chapter_indexes, status, total_count,
                   completed_count, progress, message, error, attempts, created_at, updated_at
            FROM tasks
            WHERE status IN ('queued', 'running')
            ORDER BY created_at ASC
            """
        ).fetchall()

    return [_row_to_task(row) for row in rows]


def save_task(task: TaskRecord) -> TaskRecord:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, book_id, task_type, chapter_indexes, status, total_count,
                completed_count, progress, message, error, attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                book_id = excluded.book_id,
                task_type = excluded.task_type,
                chapter_indexes = excluded.chapter_indexes,
                status = excluded.status,
                total_count = excluded.total_count,
                completed_count = excluded.completed_count,
                progress = excluded.progress,
                message = excluded.message,
                error = excluded.error,
                attempts = excluded.attempts,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                task.id,
                task.bookId,
                task.taskType,
                json_dumps(task.chapterIndexes),
                task.status,
                task.totalCount,
                task.completedCount,
                task.progress,
                task.message,
                task.error,
                task.attempts,
                task.createdAt,
                task.updatedAt,
            ),
        )
    return task


def append_task_log(task_id: str, level: str, message: str, created_at: str) -> TaskLogRecord:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO task_logs (task_id, level, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, level, message, created_at),
        )
        sequence = int(cursor.lastrowid)
    return TaskLogRecord(
        sequence=sequence,
        taskId=task_id,
        level=level,  # type: ignore[arg-type]
        message=message,
        createdAt=created_at,
    )


def list_task_logs(task_id: str, after_sequence: int = 0) -> list[TaskLogRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT sequence, task_id, level, message, created_at
            FROM task_logs
            WHERE task_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (task_id, max(0, int(after_sequence))),
        ).fetchall()
    return [_row_to_task_log(row) for row in rows]


def load_settings() -> TranslationSettings:
    with get_connection() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()

    if not row:
        return DEFAULT_SETTINGS.model_copy(deep=True)

    loaded = TranslationSettings.model_validate_json(row[0])
    return _normalize_settings(loaded)


def save_settings(settings: TranslationSettings) -> TranslationSettings:
    normalized = _normalize_settings(settings)
    payload = normalized.model_dump_json()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (id, payload)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
            """,
            (payload,),
        )
    return normalized


def _normalize_settings(settings: TranslationSettings) -> TranslationSettings:
    normalized = DEFAULT_SETTINGS.model_copy(deep=True)
    normalized.defaultProvider = settings.defaultProvider
    normalized.systemPrompt = settings.systemPrompt
    normalized.autoTranslateNextChapters = settings.autoTranslateNextChapters
    normalized.downloadConcurrency = settings.downloadConcurrency
    normalized.providers.update(settings.providers)
    normalized.providers[normalized.defaultProvider].enabled = True
    normalized.bika = settings.bika.model_copy(deep=True)
    return normalized


def _row_to_book(row: sqlite3.Row | tuple) -> BookRecord:
    return BookRecord(
        id=row[0],
        title=row[1],
        sourceUrl=row[2],
        bookKind=_normalize_book_kind(row[3]),
        language=_normalize_language(row[4]),
        status=_normalize_book_status(row[5]),
        chapterCount=row[6],
        translated=bool(row[7]),
        localPath=row[8],
        updatedAt=row[9],
        synopsis=row[10],
        lastReadChapterIndex=row[11] if len(row) > 11 else 0,
        lastReadAt=row[12] if len(row) > 12 else None,
    )


def _normalize_book_kind(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized in {"长小说", "轻小说", "漫画"}:
        return normalized
    return "轻小说"


def _normalize_language(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized in {"中文", "英文", "日文"}:
        return normalized
    return "中文"


def _normalize_book_status(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized in {"待处理", "解析中", "已下载", "已完成"}:
        return normalized
    return "已下载"


def _row_to_task(row: sqlite3.Row | tuple) -> TaskRecord:
    return TaskRecord(
        id=row[0],
        bookId=row[1],
        taskType=row[2],
        chapterIndexes=json_loads(row[3]),
        status=row[4],
        totalCount=row[5],
        completedCount=row[6],
        progress=row[7],
        message=row[8],
        error=row[9],
        attempts=row[10],
        createdAt=row[11],
        updatedAt=row[12],
    )


def _row_to_task_log(row: sqlite3.Row | tuple) -> TaskLogRecord:
    return TaskLogRecord(
        sequence=row[0],
        taskId=row[1],
        level=row[2],
        message=row[3],
        createdAt=row[4],
    )


def json_dumps(value: list[int]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str) -> list[int]:
    import json

    payload = json.loads(value)
    if isinstance(payload, list):
        return [int(item) for item in payload]
    return []
