from __future__ import annotations

import os
import sqlite3
import shutil
from pathlib import Path

from .models import BookRecord, ProviderConfig, ReadingProgressRecord, TaskRecord, TranslationSettings

BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = BASE_DIR / "data"
APP_DIR_NAME = "QingJuan"


def _resolve_platform_data_dir() -> Path:
    override = os.getenv("QINGJUAN_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return (Path(base) / APP_DIR_NAME / "data").resolve()
        return (Path.home() / "AppData" / "Local" / APP_DIR_NAME / "data").resolve()

    xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return (Path(xdg_data_home) / "qingjuan").resolve()
    return (Path.home() / ".local" / "share" / "qingjuan").resolve()


DATA_DIR = _resolve_platform_data_dir()
DB_PATH = DATA_DIR / "qingjuan.db"
_DATA_DIR_READY = False

DEFAULT_SETTINGS = TranslationSettings(
    defaultProvider="openai",
    autoTranslateNextChapters=0,
    providers={
        "openai": ProviderConfig(enabled=True, baseUrl="https://api.openai.com/v1", model="gpt-4.1-mini"),
        "newapi": ProviderConfig(enabled=False, baseUrl="https://your-newapi-endpoint/v1", model="gpt-4.1-mini"),
        "anthropic": ProviderConfig(enabled=False, baseUrl="https://api.anthropic.com/v1", model="claude-3-7-sonnet-latest"),
        "custom": ProviderConfig(enabled=False, baseUrl="https://localhost:8001/v1", model="custom-model"),
    },
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
    if DATA_DIR == LEGACY_DATA_DIR.resolve():
        return
    if not LEGACY_DATA_DIR.exists():
        return
    if any(DATA_DIR.iterdir()):
        return

    shutil.copytree(LEGACY_DATA_DIR, DATA_DIR, dirs_exist_ok=True)


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
                last_read_at TEXT
            )
            """
        )
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
        conn.execute("DELETE FROM tasks WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM reading_progress WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))


def load_reading_progress(book_id: str) -> ReadingProgressRecord:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT book_id, last_chapter_index, last_read_at
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
        lastReadAt=row[2],
    )


def save_reading_progress(progress: ReadingProgressRecord) -> ReadingProgressRecord:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reading_progress (book_id, last_chapter_index, last_read_at)
            VALUES (?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                last_chapter_index = excluded.last_chapter_index,
                last_read_at = excluded.last_read_at
            """,
            (progress.bookId, progress.lastChapterIndex, progress.lastReadAt),
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


def load_settings() -> TranslationSettings:
    with get_connection() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()

    if not row:
        return DEFAULT_SETTINGS

    return TranslationSettings.model_validate_json(row[0])


def save_settings(settings: TranslationSettings) -> TranslationSettings:
    payload = settings.model_dump_json()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (id, payload)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
            """,
            (payload,),
        )
    return settings


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
    if normalized in {"长小说", "轻小说"}:
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


def json_dumps(value: list[int]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str) -> list[int]:
    import json

    payload = json.loads(value)
    if isinstance(payload, list):
        return [int(item) for item in payload]
    return []
