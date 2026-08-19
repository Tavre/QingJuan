from __future__ import annotations

import asyncio

import pytest

from app.chapter_cache import ChapterCacheCoordinator


@pytest.mark.asyncio
async def test_background_cache_is_detached_and_runs_in_chapter_order() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls: list[tuple[str, int]] = []

    async def cache_chapter(book_id: str, chapter_index: int) -> None:
        calls.append((book_id, chapter_index))
        if chapter_index == 1:
            first_started.set()
            await release_first.wait()

    coordinator = ChapterCacheCoordinator(cache_chapter)

    worker = coordinator.schedule("book-1", [3, 1, 2, 2])

    assert worker is not None
    await first_started.wait()
    assert not worker.done()
    assert coordinator.active_book_ids == {"book-1"}

    release_first.set()
    await worker

    assert calls == [("book-1", 1), ("book-1", 2), ("book-1", 3)]
    assert coordinator.active_book_ids == set()


@pytest.mark.asyncio
async def test_reader_request_preempts_unrelated_background_chapter() -> None:
    first_started = asyncio.Event()
    first_cancelled = asyncio.Event()
    calls: list[int] = []
    first_attempts = 0

    async def cache_chapter(_: str, chapter_index: int) -> None:
        nonlocal first_attempts
        calls.append(chapter_index)
        if chapter_index == 1 and first_attempts == 0:
            first_attempts += 1
            first_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                first_cancelled.set()
                raise

    coordinator = ChapterCacheCoordinator(cache_chapter)
    worker = coordinator.schedule("book-1", [1, 2])
    assert worker is not None
    await first_started.wait()

    await coordinator.ensure("book-1", 9, read_ahead_indexes=[10])

    await first_cancelled.wait()
    await worker

    assert calls == [1, 9, 10, 1, 2]


@pytest.mark.asyncio
async def test_reader_shares_same_chapter_already_running_in_background() -> None:
    chapter_started = asyncio.Event()
    release_chapter = asyncio.Event()
    calls: list[int] = []

    async def cache_chapter(_: str, chapter_index: int) -> None:
        calls.append(chapter_index)
        chapter_started.set()
        await release_chapter.wait()

    coordinator = ChapterCacheCoordinator(cache_chapter)
    worker = coordinator.schedule("book-1", [1])
    assert worker is not None
    await chapter_started.wait()

    reader = asyncio.create_task(coordinator.ensure("book-1", 1))
    await asyncio.sleep(0)

    assert calls == [1]

    release_chapter.set()
    await asyncio.gather(reader, worker)

    assert calls == [1]


@pytest.mark.asyncio
async def test_next_chapter_request_keeps_shared_current_background_download() -> None:
    current_started = asyncio.Event()
    next_started = asyncio.Event()
    release_current = asyncio.Event()
    release_next = asyncio.Event()
    current_cancelled = asyncio.Event()
    calls: list[int] = []

    async def cache_chapter(_: str, chapter_index: int) -> None:
        calls.append(chapter_index)
        if chapter_index == 1:
            current_started.set()
            try:
                await release_current.wait()
            except asyncio.CancelledError:
                current_cancelled.set()
                raise
        if chapter_index == 2:
            next_started.set()
            await release_next.wait()

    coordinator = ChapterCacheCoordinator(cache_chapter)
    worker = coordinator.schedule("book-1", [1])
    assert worker is not None
    await current_started.wait()

    current_reader = asyncio.create_task(
        coordinator.ensure("book-1", 1, read_ahead_indexes=[2])
    )
    await next_started.wait()
    next_reader = asyncio.create_task(coordinator.ensure("book-1", 2))
    await asyncio.sleep(0)

    assert not current_cancelled.is_set()
    assert calls == [1, 2]

    release_current.set()
    release_next.set()
    await asyncio.gather(current_reader, next_reader, worker)

    assert not current_cancelled.is_set()
    assert calls == [1, 2]


@pytest.mark.asyncio
async def test_reader_starts_current_and_next_chapter_together() -> None:
    current_started = asyncio.Event()
    next_started = asyncio.Event()
    release_current = asyncio.Event()
    calls: list[int] = []

    async def cache_chapter(_: str, chapter_index: int) -> None:
        calls.append(chapter_index)
        if chapter_index == 9:
            current_started.set()
            await release_current.wait()
        if chapter_index == 10:
            next_started.set()

    coordinator = ChapterCacheCoordinator(cache_chapter)
    reader = asyncio.create_task(
        coordinator.ensure("book-1", 9, read_ahead_indexes=[10])
    )

    await current_started.wait()
    await next_started.wait()
    assert not reader.done()

    release_current.set()
    await reader
    await coordinator.shutdown()

    assert calls == [9, 10]


@pytest.mark.asyncio
async def test_reader_disconnect_does_not_cancel_started_chapter_cache() -> None:
    chapter_started = asyncio.Event()
    release_chapter = asyncio.Event()
    chapter_completed = asyncio.Event()
    chapter_cancelled = asyncio.Event()

    async def cache_chapter(_: str, __: int) -> None:
        chapter_started.set()
        try:
            await release_chapter.wait()
            chapter_completed.set()
        except asyncio.CancelledError:
            chapter_cancelled.set()
            raise

    coordinator = ChapterCacheCoordinator(cache_chapter)
    reader = asyncio.create_task(coordinator.ensure("book-1", 5))
    await chapter_started.wait()

    reader.cancel()
    await asyncio.gather(reader, return_exceptions=True)
    assert not chapter_cancelled.is_set()

    release_chapter.set()
    await chapter_completed.wait()
    await coordinator.shutdown()

    assert not chapter_cancelled.is_set()


@pytest.mark.asyncio
async def test_background_cache_limits_global_downloads_to_one() -> None:
    active = 0
    maximum_active = 0

    async def cache_chapter(_: str, __: int) -> None:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1

    coordinator = ChapterCacheCoordinator(cache_chapter)
    first = coordinator.schedule("book-1", [1, 2])
    second = coordinator.schedule("book-2", [1, 2])

    assert first is not None
    assert second is not None
    await asyncio.gather(first, second)

    assert maximum_active == 1


@pytest.mark.asyncio
async def test_background_cache_continues_after_one_chapter_fails() -> None:
    calls: list[int] = []
    failures: list[tuple[str, int, str]] = []

    async def cache_chapter(_: str, chapter_index: int) -> None:
        calls.append(chapter_index)
        if chapter_index == 2:
            raise RuntimeError("chapter unavailable")

    def record_failure(book_id: str, chapter_index: int, error: Exception) -> None:
        failures.append((book_id, chapter_index, str(error)))

    coordinator = ChapterCacheCoordinator(cache_chapter, on_error=record_failure)
    worker = coordinator.schedule("book-1", [1, 2, 3])

    assert worker is not None
    await worker

    assert calls == [1, 2, 3]
    assert failures == [("book-1", 2, "chapter unavailable")]
