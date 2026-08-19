from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app import main
from app.link_jobs import LinkJobStore
from app.models import AddBookPayload, BookRecord, PreviewResponse


def _payload() -> AddBookPayload:
    return AddBookPayload(
        sourceUrl="https://example.com/comic/1",
        bookKind="漫画",
        language="中文",
    )


def test_link_job_store_tracks_progress_and_incremental_logs() -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())

    store.start(job.id, "开始识别作品链接")
    first_log = store.append_log(job.id, "info", "正在连接目标站点", progress=20)
    second_log = store.append_log(job.id, "info", "正在解析章节目录", progress=55)

    snapshot = store.get(job.id)
    assert snapshot.status == "running"
    assert snapshot.progress == 55
    assert [item.sequence for item in snapshot.logs] == [first_log.sequence, second_log.sequence]
    assert [item.message for item in store.logs_after(job.id, first_log.sequence)] == ["正在解析章节目录"]


def test_link_job_store_keeps_preview_after_completion() -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())
    preview = PreviewResponse(
        title="测试漫画",
        chapterCount=2,
        chapters=[
            {"title": "第一话", "url": "https://example.com/comic/1/1"},
            {"title": "第二话", "url": "https://example.com/comic/1/2"},
        ],
        bookKind="漫画",
    )

    store.complete(job.id, "解析完成", preview=preview)

    snapshot = store.get(job.id)
    assert snapshot.status == "completed"
    assert snapshot.progress == 100
    assert snapshot.preview == preview
    assert store.payload_for(job.id) == _payload()


@pytest.mark.asyncio
async def test_preview_link_job_runs_in_background_and_keeps_logs(monkeypatch) -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())

    async def fake_preview(_: AddBookPayload) -> PreviewResponse:
        return PreviewResponse(
            title="后台解析作品",
            chapterCount=1,
            chapters=[{"title": "第一章", "url": "https://example.com/chapter/1"}],
            bookKind="漫画",
        )

    monkeypatch.setattr(main, "LINK_JOB_STORE", store)
    monkeypatch.setattr(main, "preview_from_url", fake_preview)

    await main._run_link_job(job.id)

    completed = store.get(job.id)
    assert completed.status == "completed"
    assert completed.preview is not None
    assert completed.preview.title == "后台解析作品"
    assert completed.logs[0].message.startswith("已提交链接")
    assert completed.logs[-1].message == "链接解析完成"


@pytest.mark.asyncio
async def test_fanqie_on_demand_import_creates_manifest_without_full_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    preview = PreviewResponse(
        title="长篇测试小说",
        chapterCount=2,
        chapters=[
            {"title": "第一章", "url": "https://fanqienovel.com/reader/10001"},
            {"title": "第二章", "url": "https://fanqienovel.com/reader/10002"},
        ],
        bookKind="长小说",
    )
    payload = AddBookPayload(
        sourceUrl="https://fanqienovel.com/page/20001",
        bookKind="长小说",
        language="中文",
        downloadMode="on_demand",
    )
    calls: list[str] = []

    async def fake_manifest_only(*_: object) -> SimpleNamespace:
        calls.append("manifest")
        return SimpleNamespace(
            title=preview.title,
            synopsis="",
            cover=None,
            chapters=preview.chapters,
            local_path=tmp_path / "book",
        )

    async def reject_full_download(*_: object) -> None:
        pytest.fail("边看边下不应在导入阶段下载全部正文")

    saved = []
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "LIBRARY_ROOT", tmp_path)
    monkeypatch.setattr(main, "create_book_manifest_only", fake_manifest_only)
    monkeypatch.setattr(main, "download_book", reject_full_download)
    monkeypatch.setattr(main, "save_book", lambda book: saved.append(book))
    monkeypatch.setattr(main, "_hydrate_book_record", lambda book: book)
    scheduled: list[BookRecord] = []
    monkeypatch.setattr(
        main,
        "_schedule_server_managed_source_cache",
        lambda book: scheduled.append(book),
    )

    book = await main._create_imported_book(payload, preview)

    assert calls == ["manifest"]
    assert book.status == "待处理"
    assert saved[-1].id == book.id
    assert scheduled == [book]


@pytest.mark.asyncio
async def test_fanqie_full_import_keeps_existing_download_behavior(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    preview = PreviewResponse(
        title="短篇测试小说",
        chapterCount=1,
        chapters=[{"title": "第一章", "url": "https://fanqienovel.com/reader/10001"}],
        bookKind="长小说",
    )
    payload = AddBookPayload(
        sourceUrl="https://fanqienovel.com/page/20001",
        bookKind="长小说",
        language="中文",
        downloadMode="all",
    )
    calls: list[str] = []

    async def fake_download(*_: object) -> SimpleNamespace:
        calls.append("download")
        return SimpleNamespace(
            title=preview.title,
            synopsis="",
            cover=None,
            chapters=preview.chapters,
            local_path=tmp_path / "book",
        )

    async def reject_manifest_only(*_: object) -> None:
        pytest.fail("全量下载不应只创建目录清单")

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "LIBRARY_ROOT", tmp_path)
    monkeypatch.setattr(main, "create_book_manifest_only", reject_manifest_only)
    monkeypatch.setattr(main, "download_book", fake_download)
    monkeypatch.setattr(main, "save_book", lambda _: None)
    monkeypatch.setattr(main, "_hydrate_book_record", lambda book: book)
    monkeypatch.setattr(
        main,
        "_schedule_server_managed_source_cache",
        lambda _: pytest.fail("完整下载不应启动服务器托管缓存"),
    )

    book = await main._create_imported_book(payload, preview)

    assert calls == ["download"]
    assert book.status == "已下载"


def test_on_demand_reader_prefetches_twenty_chapters_after_current(tmp_path) -> None:
    chapters = [
        {
            "index": index,
            "title": f"第{index}章",
            "url": f"https://fanqienovel.com/reader/{10000 + index}",
            "file_name": f"{index:04d}-chapter.txt",
        }
        for index in range(1, 31)
    ]
    (tmp_path / "0005-chapter.txt").write_text("当前章已缓存", encoding="utf-8")

    indexes = main._source_chapter_cache_indexes(
        tmp_path,
        {"chapters": chapters},
        chapter_index=5,
    )

    assert indexes == list(range(6, 26))


@pytest.mark.asyncio
async def test_reader_starts_selected_chapter_with_next_chapter_priority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    manifest = {
        "download_mode": "on_demand",
        "chapters": [
            {
                "index": index,
                "title": f"第{index}章",
                "url": f"https://example.com/chapter/{index}",
                "file_name": f"{index:04d}-chapter.txt",
            }
            for index in range(1, 8)
        ],
    }
    book = BookRecord(
        id="book-read-priority",
        title="阅读优先",
        sourceUrl="https://example.com/book/1",
        bookKind="长小说",
        language="中文",
        status="待处理",
        chapterCount=7,
        translated=False,
        localPath=str(tmp_path),
    )
    ensured: list[tuple[str, int, list[int]]] = []

    class FakeCoordinator:
        async def ensure(
            self,
            book_id: str,
            chapter_index: int,
            *,
            read_ahead_indexes: list[int],
        ) -> None:
            ensured.append((book_id, chapter_index, list(read_ahead_indexes)))

    monkeypatch.setattr(main, "_get_chapter_cache_coordinator", FakeCoordinator)
    monkeypatch.setattr(main, "_load_or_initialize_manifest", lambda *_: manifest)

    await main._ensure_source_chapter_cached(book, tmp_path, manifest, 5)
    await main._ensure_source_chapter_cached(
        book,
        tmp_path,
        manifest,
        5,
        prepare_next=False,
    )

    assert ensured == [
        ("book-read-priority", 5, [6]),
        ("book-read-priority", 5, []),
    ]


@pytest.mark.asyncio
async def test_cached_current_chapter_still_prefetches_next_immediately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    manifest = {
        "download_mode": "on_demand",
        "chapters": [
            {
                "index": index,
                "title": f"第{index}章",
                "url": f"https://example.com/chapter/{index}",
                "file_name": f"{index:04d}-chapter.txt",
            }
            for index in range(1, 4)
        ],
    }
    (tmp_path / "0002-chapter.txt").write_text("当前章", encoding="utf-8")
    book = BookRecord(
        id="book-prefetch-next",
        title="下一章预取",
        sourceUrl="https://example.com/book/2",
        bookKind="长小说",
        language="中文",
        status="待处理",
        chapterCount=3,
        translated=False,
        localPath=str(tmp_path),
    )
    prefetched: list[tuple[str, list[int]]] = []

    class FakeCoordinator:
        async def ensure(self, *_: object, **__: object) -> None:
            pytest.fail("已缓存当前章不应再次下载")

        def prefetch(self, book_id: str, chapter_indexes: list[int]) -> None:
            prefetched.append((book_id, list(chapter_indexes)))

    monkeypatch.setattr(main, "_get_chapter_cache_coordinator", FakeCoordinator)

    await main._ensure_source_chapter_cached(book, tmp_path, manifest, 2)

    assert prefetched == [("book-prefetch-next", [3])]


@pytest.mark.asyncio
async def test_concurrent_chapter_downloads_merge_manifest_updates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    manifest = {
        "download_mode": "on_demand",
        "chapters": [
            {
                "index": index,
                "title": f"第{index}章",
                "url": f"https://example.com/chapter/{index}",
                "file_name": f"{index:04d}-chapter.txt",
                "downloaded": False,
            }
            for index in range(1, 3)
        ],
    }
    main.save_manifest(tmp_path, manifest)
    book = BookRecord(
        id="book-manifest-merge",
        title="并发写回",
        sourceUrl="https://example.com/book/3",
        bookKind="长小说",
        language="中文",
        status="待处理",
        chapterCount=2,
        translated=False,
        localPath=str(tmp_path),
    )
    both_started = asyncio.Event()
    started: set[int] = set()

    async def fake_download(_: object, __: dict, chapter_index: int) -> dict:
        started.add(chapter_index)
        if len(started) == 2:
            both_started.set()
        await both_started.wait()
        (tmp_path / f"{chapter_index:04d}-chapter.txt").write_text(
            f"第{chapter_index}章",
            encoding="utf-8",
        )
        return {
            "index": chapter_index,
            "file_name": f"{chapter_index:04d}-chapter.txt",
            "downloaded": True,
            "illustration": False,
            "image_urls": [],
            "image_files": [],
            "translated_image_files": [],
            "page_count": 0,
            "images_repaired": False,
            "content_source": "test",
            "authorization_method": "public",
            "access_restricted": False,
        }

    monkeypatch.setattr(main, "_is_book_deleted", lambda _: False)
    monkeypatch.setattr(main, "_get_book_or_404", lambda _: book)
    monkeypatch.setattr(main, "_resolve_book_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "download_chapter_payload", fake_download)
    monkeypatch.setattr(main, "_refresh_book_state", lambda _: None)
    main.app.state.chapter_manifest_locks = {}

    await asyncio.gather(
        main._cache_source_chapter_by_id(book.id, 1),
        main._cache_source_chapter_by_id(book.id, 2),
    )

    updated = main.load_manifest(tmp_path)
    assert [chapter["downloaded"] for chapter in updated["chapters"]] == [True, True]
    assert [chapter["content_source"] for chapter in updated["chapters"]] == ["test", "test"]


def test_server_managed_cache_queues_every_missing_chapter_in_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    chapters = [
        {
            "index": index,
            "title": f"第{index}章",
            "url": f"https://fanqienovel.com/reader/{10000 + index}",
            "file_name": f"{index:04d}-chapter.txt",
        }
        for index in range(1, 6)
    ]
    (tmp_path / "0002-chapter.txt").write_text("已缓存", encoding="utf-8")
    queued: list[tuple[str, list[int]]] = []
    coordinator = SimpleNamespace(
        schedule=lambda book_id, indexes: queued.append((book_id, list(indexes)))
    )
    book = BookRecord(
        id="book-linux",
        title="Linux 顺序缓存",
        sourceUrl="https://fanqienovel.com/page/20001",
        bookKind="长小说",
        language="中文",
        status="待处理",
        chapterCount=5,
        translated=False,
        localPath=str(tmp_path),
    )

    monkeypatch.setattr(main, "_server_managed_chapter_cache_enabled", lambda: True)
    monkeypatch.setattr(main, "_get_chapter_cache_coordinator", lambda: coordinator)

    main._schedule_server_managed_source_cache(
        book,
        tmp_path,
        {"download_mode": "on_demand", "chapters": chapters},
    )

    assert queued == [("book-linux", [1, 3, 4, 5])]


def test_server_startup_resumes_incomplete_manifest_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = BookRecord(
        id="book-existing",
        title="已有作品",
        sourceUrl="https://example.com/book/1",
        bookKind="长小说",
        language="中文",
        status="解析中",
        chapterCount=3,
        translated=False,
        localPath="library/existing",
    )
    scheduled: list[str] = []

    monkeypatch.setattr(main, "_server_managed_chapter_cache_enabled", lambda: True)
    monkeypatch.setattr(main, "list_books", lambda: [book])
    monkeypatch.setattr(
        main,
        "_schedule_server_managed_source_cache",
        lambda current: scheduled.append(current.id),
    )

    main._resume_server_managed_source_caches()

    assert scheduled == ["book-existing"]
