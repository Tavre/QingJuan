from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress

CacheChapter = Callable[[str, int], Awaitable[None]]
CacheErrorHandler = Callable[[str, int, Exception], None]
CacheKey = tuple[str, int]


class ChapterCacheCoordinator:
    """Keeps sequential server caching out of the reader's critical path."""

    def __init__(
        self,
        cache_chapter: CacheChapter,
        *,
        on_error: CacheErrorHandler | None = None,
    ) -> None:
        self._cache_chapter = cache_chapter
        self._on_error = on_error
        self._queues: dict[str, deque[int]] = {}
        self._queued: set[CacheKey] = set()
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._inflight: dict[CacheKey, asyncio.Task[None]] = {}
        self._prefetch_tasks: dict[CacheKey, asyncio.Task[None]] = {}
        self._background_current: tuple[CacheKey, asyncio.Task[None]] | None = None
        self._foreground_idle = asyncio.Event()
        self._foreground_idle.set()
        self._foreground_count = 0
        self._foreground_keys: dict[CacheKey, int] = {}
        self._background_slot = asyncio.Semaphore(1)
        self._closed = False

    @property
    def active_book_ids(self) -> set[str]:
        return set(self._workers)

    def schedule(
        self,
        book_id: str,
        chapter_indexes: Iterable[int],
    ) -> asyncio.Task[None] | None:
        if self._closed:
            return None

        queue = self._queues.setdefault(book_id, deque())
        for chapter_index in sorted({index for index in chapter_indexes if index > 0}):
            key = (book_id, chapter_index)
            if key in self._queued:
                continue
            self._queued.add(key)
            queue.append(chapter_index)

        worker = self._workers.get(book_id)
        if worker is not None and not worker.done():
            return worker
        if not queue:
            self._queues.pop(book_id, None)
            return None

        worker = asyncio.create_task(self._run_book(book_id))
        self._workers[book_id] = worker
        return worker

    async def ensure(
        self,
        book_id: str,
        chapter_index: int,
        *,
        read_ahead_indexes: Iterable[int] = (),
    ) -> None:
        if self._closed:
            raise RuntimeError("章节缓存协调器已关闭")

        read_ahead = sorted({index for index in read_ahead_indexes if index > 0 and index != chapter_index})
        protected_keys = {(book_id, index) for index in [chapter_index, *read_ahead]}
        self._enter_foreground(protected_keys, preempt_background=True)
        cache_task = self._cache_task_for(book_id, chapter_index)
        self.prefetch(
            book_id,
            read_ahead,
            preempt_background=False,
        )
        try:
            await asyncio.shield(cache_task)
        finally:
            self._leave_foreground(protected_keys)

    def prefetch(
        self,
        book_id: str,
        chapter_indexes: Iterable[int],
        *,
        preempt_background: bool = True,
    ) -> list[asyncio.Task[None]]:
        if self._closed:
            return []

        indexes = sorted({index for index in chapter_indexes if index > 0})
        protected_keys = {(book_id, index) for index in indexes}
        tasks: list[asyncio.Task[None]] = []
        for chapter_index in indexes:
            key = (book_id, chapter_index)
            existing = self._prefetch_tasks.get(key)
            if existing is not None and not existing.done():
                tasks.append(existing)
                continue
            task = asyncio.create_task(
                self._run_prefetch(
                    book_id,
                    chapter_index,
                    protected_keys=protected_keys,
                    preempt_background=preempt_background,
                )
            )
            self._prefetch_tasks[key] = task
            task.add_done_callback(
                lambda completed, cache_key=key: self._forget_prefetch_task(
                    cache_key,
                    completed,
                )
            )
            tasks.append(task)
        return tasks

    async def cancel_book(self, book_id: str) -> None:
        queued = self._queues.pop(book_id, deque())
        for chapter_index in queued:
            self._queued.discard((book_id, chapter_index))

        tasks: set[asyncio.Task[None]] = set()
        worker = self._workers.pop(book_id, None)
        if worker is not None:
            tasks.add(worker)
        tasks.update(
            task for (current_book_id, _), task in self._prefetch_tasks.items() if current_book_id == book_id
        )
        tasks.update(
            task for (current_book_id, _), task in self._inflight.items() if current_book_id == book_id
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for key in [key for key in self._prefetch_tasks if key[0] == book_id]:
            self._prefetch_tasks.pop(key, None)
        for key in [key for key in self._inflight if key[0] == book_id]:
            self._inflight.pop(key, None)
        if self._background_current is not None and self._background_current[0][0] == book_id:
            self._background_current = None

    async def shutdown(self) -> None:
        self._closed = True
        tasks = {
            *self._workers.values(),
            *self._prefetch_tasks.values(),
            *self._inflight.values(),
        }
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._workers.clear()
        self._queues.clear()
        self._queued.clear()
        self._inflight.clear()
        self._prefetch_tasks.clear()
        self._background_current = None
        self._foreground_count = 0
        self._foreground_keys.clear()
        self._foreground_idle.set()

    async def _run_prefetch(
        self,
        book_id: str,
        chapter_index: int,
        *,
        protected_keys: set[CacheKey],
        preempt_background: bool,
    ) -> None:
        self._enter_foreground(
            protected_keys,
            preempt_background=preempt_background,
        )
        try:
            await asyncio.shield(self._cache_task_for(book_id, chapter_index))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._report_error(book_id, chapter_index, error)
        finally:
            self._leave_foreground(protected_keys)

    async def _run_book(self, book_id: str) -> None:
        queue = self._queues[book_id]
        current_worker = asyncio.current_task()
        try:
            while queue:
                chapter_index = queue.popleft()
                key = (book_id, chapter_index)
                if key not in self._queued:
                    continue

                await self._foreground_idle.wait()
                await asyncio.sleep(0)
                async with self._background_slot:
                    await self._foreground_idle.wait()
                    if key not in self._queued:
                        continue

                    cache_task = self._cache_task_for(book_id, chapter_index)
                    self._background_current = (key, cache_task)
                    preempted = False
                    try:
                        await asyncio.shield(cache_task)
                    except asyncio.CancelledError:
                        if current_worker is not None and current_worker.cancelling():
                            raise
                        preempted = True
                    except Exception as error:
                        self._report_error(book_id, chapter_index, error)
                    finally:
                        if self._background_current == (key, cache_task):
                            self._background_current = None

                    if preempted:
                        if not self._closed and key in self._queued:
                            queue.appendleft(chapter_index)
                        continue
                    self._queued.discard(key)
        finally:
            if self._workers.get(book_id) is current_worker:
                self._workers.pop(book_id, None)
            if not queue:
                self._queues.pop(book_id, None)

    def _cache_task_for(self, book_id: str, chapter_index: int) -> asyncio.Task[None]:
        key = (book_id, chapter_index)
        existing = self._inflight.get(key)
        if existing is not None and not existing.done():
            return existing

        task = asyncio.create_task(self._cache_chapter(book_id, chapter_index))
        self._inflight[key] = task
        task.add_done_callback(
            lambda completed, cache_key=key: self._forget_cache_task(
                cache_key,
                completed,
            )
        )
        return task

    def _enter_foreground(
        self,
        protected_keys: set[CacheKey],
        *,
        preempt_background: bool,
    ) -> None:
        self._foreground_count += 1
        self._foreground_idle.clear()
        for key in protected_keys:
            self._foreground_keys[key] = self._foreground_keys.get(key, 0) + 1
        if not preempt_background or self._background_current is None:
            return
        background_key, background_task = self._background_current
        if background_key not in self._foreground_keys and not background_task.done():
            background_task.cancel()

    def _leave_foreground(self, protected_keys: set[CacheKey]) -> None:
        for key in protected_keys:
            remaining = self._foreground_keys.get(key, 1) - 1
            if remaining <= 0:
                self._foreground_keys.pop(key, None)
            else:
                self._foreground_keys[key] = remaining
        self._foreground_count = max(0, self._foreground_count - 1)
        if self._foreground_count == 0:
            self._foreground_idle.set()

    def _forget_cache_task(
        self,
        key: CacheKey,
        task: asyncio.Task[None],
    ) -> None:
        if self._inflight.get(key) is task:
            self._inflight.pop(key, None)
        with suppress(asyncio.CancelledError, Exception):
            task.exception()

    def _forget_prefetch_task(
        self,
        key: CacheKey,
        task: asyncio.Task[None],
    ) -> None:
        if self._prefetch_tasks.get(key) is task:
            self._prefetch_tasks.pop(key, None)
        with suppress(asyncio.CancelledError, Exception):
            task.exception()

    def _report_error(self, book_id: str, chapter_index: int, error: Exception) -> None:
        if self._on_error is None:
            return
        try:
            self._on_error(book_id, chapter_index, error)
        except Exception:
            return
