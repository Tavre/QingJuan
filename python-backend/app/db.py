from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import (
    BookRecord,
    BookSourceRecord,
    ComicSourceConfig,
    DeviceRecord,
    DeviceView,
    MangaOcrConfig,
    OpenAICompatibleConfig,
    ReadingProgressRecord,
    TaskLogRecord,
    TaskRecord,
    TranslationSettings,
)
from .site_plugins import get_site_plugin, list_site_plugins

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
_SITE_PLUGIN_STATE_LOCK = threading.RLock()
_SITE_PLUGIN_STATE_CACHE: tuple[Path, dict[str, bool]] | None = None

DEFAULT_SETTINGS = TranslationSettings(
    autoTranslateNextChapters=0,
    translationModel=OpenAICompatibleConfig(
        enabled=False,
        baseUrl="https://api.openai.com/v1",
        model="gpt-5.4",
        supportsVision=False,
    ),
    # 默认使用本机 Windows 系统 OCR（离线、免外部服务）；密钥留空即用默认语言优先级。
    mangaOcr=MangaOcrConfig(enabled=True, baseUrl="windows"),
    bika=ComicSourceConfig(),
)

DEFAULT_BOOK_SOURCES = [
    BookSourceRecord(
        id="source-builtin-fanqie",
        name="番茄小说",
        baseUrl="https://fanqienovel.com",
        description="番茄中文网络小说，可搜索、按作品链接导入或同步当前登录账号书架。",
        bookKind="长小说",
        language="中文",
        sampleUrl="https://fanqienovel.com",
        tags=["中文", "连载", "账号书架"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-qidian",
        name="起点中文网",
        baseUrl="https://www.qidian.com",
        description="可匿名搜索并导入起点作品、完整目录和可取得的章节正文，也可同步当前登录账号书架。",
        bookKind="长小说",
        language="中文",
        sampleUrl="https://www.qidian.com/book/1209977/",
        tags=["中文", "匿名搜索", "账号书架"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-ciweimao",
        name="刺猬猫阅读",
        baseUrl="https://www.ciweimao.com",
        description="可搜索并导入刺猬猫作品、完整分卷目录和可取得的章节正文。",
        bookKind="轻小说",
        language="中文",
        sampleUrl="https://www.ciweimao.com/book/100495948",
        tags=["中文", "轻小说", "章节解析"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-sfacg",
        name="SF 轻小说",
        baseUrl="https://book.sfacg.com",
        description="可搜索并导入菠萝包/SF 轻小说作品、完整目录和可取得的章节正文。",
        bookKind="轻小说",
        language="中文",
        sampleUrl="https://book.sfacg.com/Novel/465469/",
        tags=["中文", "轻小说", "菠萝包"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-shaoniandream",
        name="少年梦阅读",
        baseUrl="https://www.shaoniandream.com",
        description="可搜索并导入少年梦作品、完整分卷目录和可取得的章节正文。",
        bookKind="长小说",
        language="中文",
        sampleUrl="https://www.shaoniandream.com/book_detail/3490",
        tags=["中文", "原创小说", "章节解析"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-linovelib",
        name="Linovelib",
        baseUrl="https://www.linovelib.com",
        description="轻小说文库站点，适合轻小说与插图内容导入。",
        bookKind="轻小说",
        language="日文",
        sampleUrl="https://www.linovelib.com",
        tags=["轻小说", "插图"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-kakuyomu",
        name="Kakuyomu",
        baseUrl="https://kakuyomu.jp",
        description="角川旗下小说平台，适合在线轻小说与原创长篇导入。",
        bookKind="轻小说",
        language="日文",
        sampleUrl="https://kakuyomu.jp",
        tags=["轻小说", "连载"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-syosetu",
        name="Syosetu",
        baseUrl="https://syosetu.com",
        description="小説家になろう系列站点，适合日文网络小说导入。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://syosetu.com",
        tags=["网络小说", "日文"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-novel18",
        name="Novel18",
        baseUrl="https://novel18.syosetu.com",
        description="成人向小说站点，适合已成年用户按作品链接导入。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://novel18.syosetu.com",
        tags=["R18", "小说"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-pixiv",
        name="Pixiv Novels",
        baseUrl="https://www.pixiv.net",
        description="Pixiv 小说与系列作品入口，适合按 series / novel 链接导入。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://www.pixiv.net/novel",
        tags=["Pixiv", "系列"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-hameln",
        name="Hameln",
        baseUrl="https://syosetu.org",
        description="同人小说站点，部分环境可能触发挑战页，导入前建议先做检测。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://syosetu.org",
        tags=["同人", "小说"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-alphapolis",
        name="Alphapolis",
        baseUrl="https://www.alphapolis.co.jp",
        description="综合小说平台，当前部分环境会触发 WAF，建议先检测再导入。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://www.alphapolis.co.jp",
        tags=["网站", "小说"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-novelup",
        name="Novelup",
        baseUrl="https://novelup.plus",
        description="小说投稿平台，当前环境下可能受 CloudFront 限制。",
        bookKind="长小说",
        language="日文",
        sampleUrl="https://novelup.plus",
        tags=["投稿", "小说"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-18comic",
        name="18Comic",
        baseUrl="https://18comic.vip",
        description="内置漫画站点适配，适合按专辑详情页导入到本地书架。",
        bookKind="漫画",
        language="中文",
        sampleUrl="https://18comic.vip",
        tags=["漫画", "站点"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-ehentai",
        name="E-Hentai",
        baseUrl="https://e-hentai.org",
        description="可搜索并导入 E-Hentai 公开画廊；一本画廊作为一个漫画章节保存。",
        bookKind="漫画",
        language="日文",
        sampleUrl="https://e-hentai.org",
        tags=["漫画", "画廊", "R18"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-bikawebapp",
        name="Bika Web App",
        baseUrl="https://bikawebapp.com",
        description="哔咔漫画 Web App，导入前请先在设置中确认账号凭证。",
        bookKind="漫画",
        language="中文",
        sampleUrl="https://bikawebapp.com",
        tags=["漫画", "Bika"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-quark",
        name="夸克小说",
        baseUrl="https://www.shuqi.com",
        description="通过书旗网页内核搜索并导入夸克小说作品、完整目录和可取得的章节正文。",
        bookKind="长小说",
        language="中文",
        sampleUrl="https://www.shuqi.com/book/46543.html",
        tags=["中文", "夸克", "章节解析"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-copymanga",
        name="拷贝漫画 (CopyManga)",
        baseUrl="https://www.mangacopy.com",
        description="可搜索并导入作品、完整分组目录和可取得的漫画页面。",
        bookKind="漫画",
        language="中文",
        sampleUrl="https://www.mangacopy.com/comic/grandblue",
        tags=["漫画", "公开接口"],
        origin="builtin",
    ),
    BookSourceRecord(
        id="source-builtin-comicores",
        name="COMICORES 漫核",
        baseUrl="https://www.comicores.cc",
        description="搜索和预览作品元数据；当前解析器尚未实现章节资源解析。",
        bookKind="漫画",
        language="中文",
        sampleUrl="https://www.comicores.cc",
        tags=["漫画", "公开元数据"],
        origin="builtin",
    ),
]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_data_dir()
    connection = sqlite3.connect(DB_PATH, timeout=5)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        with connection:
            yield connection
    finally:
        connection.close()


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
    global _SITE_PLUGIN_STATE_CACHE
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS book_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                book_kind TEXT,
                language TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                supported INTEGER NOT NULL DEFAULT 1,
                sample_url TEXT,
                tags TEXT NOT NULL,
                origin TEXT NOT NULL,
                import_url TEXT,
                status TEXT NOT NULL DEFAULT 'unknown',
                status_message TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT,
                rule_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _ensure_book_source_columns(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_book_sources_origin_name
            ON book_sources (origin, name)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_plugin_settings (
                plugin_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                banned INTEGER NOT NULL DEFAULT 0,
                banned_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_devices_last_seen
            ON devices (last_seen_at DESC)
            """
        )
        _seed_builtin_book_sources(conn)
        _seed_site_plugin_settings(conn)
    with _SITE_PLUGIN_STATE_LOCK:
        _SITE_PLUGIN_STATE_CACHE = None


def _ensure_reading_progress_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(reading_progress)").fetchall()}
    required_columns = {
        "last_scroll_ratio": "ALTER TABLE reading_progress ADD COLUMN last_scroll_ratio REAL NOT NULL DEFAULT 0",
        "last_anchor_type": "ALTER TABLE reading_progress ADD COLUMN last_anchor_type TEXT NOT NULL DEFAULT 'top'",
        "last_anchor_index": "ALTER TABLE reading_progress ADD COLUMN last_anchor_index INTEGER NOT NULL DEFAULT 0",
        "last_anchor_offset_ratio": "ALTER TABLE reading_progress ADD COLUMN last_anchor_offset_ratio REAL NOT NULL DEFAULT 0",
    }
    for column_name, statement in required_columns.items():
        if column_name not in existing_columns:
            conn.execute(statement)


def _ensure_book_source_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(book_sources)").fetchall()}
    if "rule_payload" not in existing_columns:
        conn.execute("ALTER TABLE book_sources ADD COLUMN rule_payload TEXT")


DEVICE_ONLINE_WINDOW_SECONDS = 120
DEVICE_TOUCH_INTERVAL_SECONDS = 30


def touch_device(
    *,
    device_id: str,
    name: str,
    platform: str,
    ip_address: str,
    seen_at: datetime | None = None,
) -> DeviceRecord:
    timestamp = seen_at or datetime.now(UTC)
    timestamp_text = _datetime_text(timestamp)
    update_before = _datetime_text(timestamp - timedelta(seconds=DEVICE_TOUCH_INTERVAL_SECONDS))
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, platform, ip_address, first_seen_at, last_seen_at,
                   banned, banned_at
            FROM devices
            WHERE id = ?
            """,
            (device_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO devices (
                    id, name, platform, ip_address, first_seen_at, last_seen_at,
                    banned, banned_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
                """,
                (device_id, name, platform, ip_address, timestamp_text, timestamp_text),
            )
        elif not bool(row[6]) and (
            row[1] != name or row[2] != platform or row[3] != ip_address or row[5] <= update_before
        ):
            conn.execute(
                """
                UPDATE devices
                SET name = ?, platform = ?, ip_address = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (name, platform, ip_address, timestamp_text, device_id),
            )
        refreshed = conn.execute(
            """
            SELECT id, name, platform, ip_address, first_seen_at, last_seen_at,
                   banned, banned_at
            FROM devices
            WHERE id = ?
            """,
            (device_id,),
        ).fetchone()
    if refreshed is None:
        raise RuntimeError("设备登记失败")
    return _row_to_device(refreshed)


def list_devices(*, now: datetime | None = None) -> list[DeviceView]:
    current_time = now or datetime.now(UTC)
    online_after = current_time - timedelta(seconds=DEVICE_ONLINE_WINDOW_SECONDS)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, platform, ip_address, first_seen_at, last_seen_at,
                   banned, banned_at
            FROM devices
            ORDER BY banned ASC, last_seen_at DESC, first_seen_at DESC
            """
        ).fetchall()
    devices: list[DeviceView] = []
    for row in rows:
        record = _row_to_device(row)
        devices.append(
            DeviceView(
                **record.model_dump(),
                online=not record.banned and _parse_datetime(record.lastSeenAt) >= online_after,
            )
        )
    return devices


def set_device_banned(
    device_id: str,
    *,
    banned: bool,
    changed_at: datetime | None = None,
) -> DeviceView | None:
    timestamp_text = _datetime_text(changed_at or datetime.now(UTC))
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE devices
            SET banned = ?, banned_at = ?
            WHERE id = ?
            """,
            (int(banned), timestamp_text if banned else None, device_id),
        )
        if cursor.rowcount == 0:
            return None
    return next((device for device in list_devices() if device.id == device_id), None)


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


def list_book_sources() -> list[BookSourceRecord]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id, name, base_url, description, book_kind, language,
                enabled, supported, sample_url, tags, origin, import_url,
                status, status_message, last_checked_at, rule_payload, created_at, updated_at
            FROM book_sources
            WHERE origin != 'builtin'
            ORDER BY lower(name) ASC, created_at DESC
            """
        ).fetchall()
    return [_row_to_book_source(row) for row in rows]


def list_builtin_book_source_base_urls() -> list[str]:
    """返回内置书源的 base_url 列表。

    导入 Legado 书源时，book_sources 表的 base_url 唯一约束会同时覆盖内置书源，
    但 list_book_sources 只返回非内置书源，导致去重逻辑看不到内置站点。
    此处单独提供内置 base_url，供导入流程跳过与内置站点 URL 冲突的条目。
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT base_url FROM book_sources WHERE origin = 'builtin'").fetchall()
    return [row[0] for row in rows]


def get_book_source(source_id: str) -> BookSourceRecord | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                id, name, base_url, description, book_kind, language,
                enabled, supported, sample_url, tags, origin, import_url,
                status, status_message, last_checked_at, rule_payload, created_at, updated_at
            FROM book_sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_book_source(row)


def save_book_source(source: BookSourceRecord) -> BookSourceRecord:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO book_sources (
                id, name, base_url, description, book_kind, language,
                enabled, supported, sample_url, tags, origin, import_url,
                status, status_message, last_checked_at, rule_payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                base_url = excluded.base_url,
                description = excluded.description,
                book_kind = excluded.book_kind,
                language = excluded.language,
                enabled = excluded.enabled,
                supported = excluded.supported,
                sample_url = excluded.sample_url,
                tags = excluded.tags,
                origin = excluded.origin,
                import_url = excluded.import_url,
                status = excluded.status,
                status_message = excluded.status_message,
                last_checked_at = excluded.last_checked_at,
                rule_payload = excluded.rule_payload,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                source.id,
                source.name,
                source.baseUrl,
                source.description,
                source.bookKind,
                source.language,
                int(source.enabled),
                int(source.supported),
                source.sampleUrl,
                json_dumps(source.tags),
                source.origin,
                source.importUrl,
                source.status,
                source.statusMessage,
                source.lastCheckedAt,
                json_dumps(source.rulePayload) if source.rulePayload else None,
                source.createdAt,
                source.updatedAt,
            ),
        )
    return source


def delete_book_source(source_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM book_sources WHERE id = ?", (source_id,))


def list_site_plugin_enabled_states() -> dict[str, bool]:
    global _SITE_PLUGIN_STATE_CACHE
    with _SITE_PLUGIN_STATE_LOCK:
        if _SITE_PLUGIN_STATE_CACHE is not None and _SITE_PLUGIN_STATE_CACHE[0] == DB_PATH:
            return dict(_SITE_PLUGIN_STATE_CACHE[1])

    states = {plugin.id: plugin.default_enabled for plugin in list_site_plugins()}
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT plugin_id, enabled FROM site_plugin_settings").fetchall()
    except sqlite3.OperationalError as exc:
        error_text = str(exc).lower()
        if "no such table" not in error_text or "site_plugin_settings" not in error_text:
            raise
        # 启动迁移前可以暂用代码默认值，但不能缓存；否则后续建表或一次临时锁库
        # 都可能让停用状态在当前进程中永久回退为默认启用。
        return dict(states)
    for plugin_id, enabled in rows:
        if plugin_id in states:
            states[str(plugin_id)] = bool(enabled)
    with _SITE_PLUGIN_STATE_LOCK:
        _SITE_PLUGIN_STATE_CACHE = (DB_PATH, dict(states))
    return dict(states)


def is_site_plugin_enabled(plugin_id: str) -> bool:
    plugin = get_site_plugin(plugin_id)
    if plugin is None:
        return False
    return list_site_plugin_enabled_states().get(plugin_id, plugin.default_enabled)


def save_site_plugin_enabled(plugin_id: str, enabled: bool) -> None:
    global _SITE_PLUGIN_STATE_CACHE
    if get_site_plugin(plugin_id) is None:
        raise ValueError(f"未知站点插件：{plugin_id}")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO site_plugin_settings (plugin_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                plugin_id,
                int(enabled),
                datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            ),
        )
    with _SITE_PLUGIN_STATE_LOCK:
        if _SITE_PLUGIN_STATE_CACHE is not None and _SITE_PLUGIN_STATE_CACHE[0] == DB_PATH:
            states = dict(_SITE_PLUGIN_STATE_CACHE[1])
            states[plugin_id] = enabled
            _SITE_PLUGIN_STATE_CACHE = (DB_PATH, states)


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


def _migrate_settings_payload(payload: dict[str, object]) -> dict[str, object]:
    migrated = dict(payload)
    if not isinstance(migrated.get("translationModel"), dict):
        providers = migrated.get("providers")
        provider_map = providers if isinstance(providers, dict) else {}
        selected = str(migrated.get("defaultProvider") or "openai").strip().lower()
        selected_config = provider_map.get(selected)
        openai_config = provider_map.get("openai")
        if selected != "anthropic" and isinstance(selected_config, dict):
            translation_model = dict(selected_config)
        elif isinstance(openai_config, dict):
            translation_model = dict(openai_config)
        else:
            translation_model = DEFAULT_SETTINGS.translationModel.model_dump()
        migrated["translationModel"] = translation_model
    migrated.pop("defaultProvider", None)
    migrated.pop("providers", None)
    return migrated


def load_settings() -> TranslationSettings:
    with get_connection() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id = 1").fetchone()

    if not row:
        return DEFAULT_SETTINGS.model_copy(deep=True)

    raw_payload = json.loads(row[0])
    if not isinstance(raw_payload, dict):
        return DEFAULT_SETTINGS.model_copy(deep=True)
    loaded = TranslationSettings.model_validate(_migrate_settings_payload(raw_payload))
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
    normalized.systemPrompt = settings.systemPrompt
    normalized.autoTranslateNextChapters = settings.autoTranslateNextChapters
    normalized.downloadConcurrency = settings.downloadConcurrency
    normalized.translationModel = settings.translationModel.model_copy(deep=True)
    normalized.mangaOcr = settings.mangaOcr.model_copy(deep=True)
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


def _row_to_device(row: sqlite3.Row | tuple) -> DeviceRecord:
    platform = str(row[2] or "other").lower()
    if platform not in {"android", "windows", "linux", "macos", "ios", "other"}:
        platform = "other"
    return DeviceRecord(
        id=row[0],
        name=row[1],
        platform=platform,
        ipAddress=row[3],
        firstSeenAt=row[4],
        lastSeenAt=row[5],
        banned=bool(row[6]),
        bannedAt=row[7],
    )


def _datetime_text(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
        chapterIndexes=json_load_int_list(row[3]),
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


def _row_to_book_source(row: sqlite3.Row | tuple) -> BookSourceRecord:
    payload = json_loads(row[9])
    tags = [str(item).strip() for item in payload] if isinstance(payload, list) else []
    return BookSourceRecord(
        id=row[0],
        name=row[1],
        baseUrl=row[2],
        description=row[3],
        bookKind=_normalize_optional_book_kind(row[4]),
        language=_normalize_optional_language(row[5]),
        enabled=bool(row[6]),
        supported=bool(row[7]),
        sampleUrl=row[8],
        tags=[tag for tag in tags if tag],
        origin=row[10],
        importUrl=row[11],
        status=_normalize_source_status(row[12]),
        statusMessage=row[13] or "",
        lastCheckedAt=row[14],
        rulePayload=_normalize_rule_payload(row[15]),
        createdAt=row[16],
        updatedAt=row[17],
    )


def _normalize_optional_book_kind(value: object) -> str | None:
    normalized = str(value or "").strip()
    if normalized in {"长小说", "轻小说", "漫画"}:
        return normalized
    return None


def _normalize_optional_language(value: object) -> str | None:
    normalized = str(value or "").strip()
    if normalized in {"中文", "英文", "日文"}:
        return normalized
    return None


def _normalize_rule_payload(value: object) -> dict | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        payload = json_loads(value)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_source_status(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized in {"unknown", "online", "slow", "offline", "unsupported"}:
        return normalized
    return "unknown"


def _seed_builtin_book_sources(conn: sqlite3.Connection) -> None:
    for source in DEFAULT_BOOK_SOURCES:
        conn.execute(
            """
            INSERT INTO book_sources (
                id, name, base_url, description, book_kind, language,
                enabled, supported, sample_url, tags, origin, import_url,
                status, status_message, last_checked_at, rule_payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                base_url = excluded.base_url,
                description = excluded.description,
                book_kind = excluded.book_kind,
                language = excluded.language,
                enabled = excluded.enabled,
                supported = excluded.supported,
                sample_url = excluded.sample_url,
                tags = excluded.tags,
                origin = excluded.origin,
                updated_at = excluded.updated_at
            """,
            (
                source.id,
                source.name,
                source.baseUrl,
                source.description,
                source.bookKind,
                source.language,
                int(source.enabled),
                int(source.supported),
                source.sampleUrl,
                json_dumps(source.tags),
                source.origin,
                source.importUrl,
                source.status,
                source.statusMessage,
                source.lastCheckedAt,
                json_dumps(source.rulePayload) if source.rulePayload else None,
                source.createdAt,
                datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            ),
        )


def _seed_site_plugin_settings(conn: sqlite3.Connection) -> None:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for plugin in list_site_plugins():
        conn.execute(
            """
            INSERT INTO site_plugin_settings (plugin_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO NOTHING
            """,
            (plugin.id, int(plugin.default_enabled), now),
        )


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def json_loads(value: str) -> object:
    import json

    return json.loads(value)


def json_load_int_list(value: str) -> list[int]:
    payload = json_loads(value)
    if isinstance(payload, list):
        return [int(item) for item in payload]
    return []
