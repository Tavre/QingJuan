from __future__ import annotations

import asyncio
import base64
import importlib
import sys

import httpx
import pytest

from app import scraper
from app.manga_download import fetch_image_with_retry, is_valid_image_file, write_image_atomic
from app.models import TaskRecord

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_image_download_retries_status_and_invalid_payload() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        if attempts == 2:
            return httpx.Response(200, content=b"<html>blocked</html>", request=request)
        return httpx.Response(200, content=PNG_1X1, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        content = await fetch_image_with_retry(
            client,
            "https://img.example.test/page.png",
            headers={"Referer": "https://reader.example.test/chapter/1"},
            max_attempts=3,
            base_delay=0,
            sleep=_no_sleep,
        )

    assert content == PNG_1X1
    assert attempts == 3


@pytest.mark.asyncio
async def test_image_download_does_not_retry_permanent_404() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_image_with_retry(
                client,
                "https://img.example.test/missing.png",
                headers={},
                max_attempts=4,
                base_delay=0,
                sleep=_no_sleep,
            )

    assert attempts == 1


def test_atomic_image_write_replaces_corrupt_cache(tmp_path) -> None:
    target = tmp_path / "page.png"
    target.write_bytes(b"partial-response")

    write_image_atomic(target, PNG_1X1)

    assert is_valid_image_file(target)
    assert target.read_bytes() == PNG_1X1
    assert not target.with_suffix(".png.part").exists()


@pytest.mark.asyncio
async def test_bika_api_retries_retryable_http_status(monkeypatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"code": 200, "data": {}}, request=request)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(scraper.asyncio, "sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await scraper._bika_request_with_retry(client, "comics/example", max_retries=3)

    assert payload["code"] == 200
    assert attempts == 2


@pytest.mark.asyncio
async def test_supported_manga_failure_is_propagated(monkeypatch) -> None:
    async def fail(*_: object) -> scraper.ChapterFetchResult:
        raise ValueError("JM 图片接口暂时不可用")

    monkeypatch.setattr(scraper, "_fetch_18comic_chapter_data", fail)
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="JM 图片接口暂时不可用"):
            await scraper._fetch_chapter_data(
                client,
                "https://18comic.vip/photo/123456/",
                "测试章节",
            )


def test_mainstream_manga_sources_are_detected() -> None:
    supported_urls = (
        "https://18comic.vip/album/123456/",
        "https://bikawebapp.com/comic/abcdef123456",
        "https://www.pixiv.net/artworks/12345678",
        "https://www.webtoons.com/zh-hant/fantasy/example/viewer?title_no=1&episode_no=2",
        "https://www.mangabz.com/m12345/",
        "https://www.manhuagui.com/comic/12345/67890.html",
        "https://www.copymanga.site/comic/example/chapter/1",
        "https://manhua.dmzj.com/example/123.shtml",
    )

    assert all(scraper._is_manga_source_url(url) for url in supported_urls)


def test_jm_chapter_uses_current_api_image_urls(monkeypatch) -> None:
    class FakePhoto(list[object]):
        title = "JM 测试章节"

    class FakeImage:
        download_url = "https://cdn.example.test/media/photos/123456/001.jpg"

    class FakeClient:
        def get_photo_detail(self, photo_id: str) -> FakePhoto:
            assert photo_id == "123456"
            return FakePhoto([FakeImage()])

    monkeypatch.setattr(scraper, "_jm_client", lambda: FakeClient())

    result = scraper._sync_fetch_18comic_chapter_data("https://18comic.vip/photo/123456/")

    assert result.image_urls == ["https://cdn.example.test/media/photos/123456/001.jpg"]
    assert "共 1 页" in result.text


@pytest.mark.asyncio
async def test_pixiv_manga_fetches_original_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ajax/illust/12345678/pages"
        return httpx.Response(
            200,
            json={
                "error": False,
                "body": [
                    {
                        "urls": {
                            "regular": "https://i.pximg.net/regular-1.jpg",
                            "original": "https://i.pximg.net/1.jpg",
                        }
                    },
                    {"urls": {"regular": "https://i.pximg.net/2.jpg"}},
                ],
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await scraper._fetch_pixiv_manga_data(
            client,
            "https://www.pixiv.net/artworks/12345678",
            "Pixiv 测试漫画",
        )

    assert result.image_urls == ["https://i.pximg.net/1.jpg", "https://i.pximg.net/2.jpg"]
    assert "共 2 页" in result.text


def test_generic_manga_html_extracts_lazy_and_script_images() -> None:
    html = """
    <div id="_imageList">
      <img data-url="//cdn.example.test/pages/001.webp">
      <img data-src="/pages/002.jpg">
    </div>
    <script>
      const chapterPath = "/pages/";
      const chapterImages = ["003.png", "004.png"];
    </script>
    """

    assert scraper._extract_generic_manga_image_urls(
        html,
        "https://www.webtoons.com/reader/chapter-1",
    ) == [
        "https://cdn.example.test/pages/001.webp",
        "https://www.webtoons.com/pages/002.jpg",
        "https://www.webtoons.com/pages/003.png",
        "https://www.webtoons.com/pages/004.png",
    ]


@pytest.mark.asyncio
async def test_generic_manga_chapter_returns_image_pages_without_browser() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<div class="reader-main"><img data-original="/chapter/001.jpg"></div>',
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await scraper._fetch_generic_manga_chapter_data(
            client,
            "https://www.mangabz.com/m12345/",
            "第一话",
        )

    assert result.image_urls == ["https://www.mangabz.com/chapter/001.jpg"]
    assert "共 1 页" in result.text


@pytest.mark.asyncio
async def test_retry_requeues_the_same_task(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QINGJUAN_DATA_DIR", str(tmp_path))
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    task = TaskRecord(
        id="task-original",
        bookId="book-1",
        taskType="download",
        chapterIndexes=[1, 2],
        status="failed",
        totalCount=2,
        completedCount=1,
        progress=50,
        message="任务执行失败",
        error="图片下载失败",
        attempts=1,
        createdAt="2026-08-03 10:00:00",
        updatedAt="2026-08-03 10:01:00",
    )
    saved: list[TaskRecord] = []
    queue: asyncio.Queue[str] = asyncio.Queue()

    monkeypatch.setattr(main, "get_task", lambda _: task)
    monkeypatch.setattr(main, "_get_book_or_404", lambda _: object())
    monkeypatch.setattr(main, "save_task", lambda value: saved.append(value.model_copy(deep=True)))
    monkeypatch.setattr(main, "TASK_QUEUE", queue)
    monkeypatch.setattr(
        main,
        "_enqueue_task",
        lambda *_: pytest.fail("重试不应创建新的任务记录"),
    )

    retried = await main.post_retry_task(task.id)

    assert retried.id == "task-original"
    assert retried.status == "queued"
    assert retried.completedCount == 0
    assert retried.progress == 0
    assert retried.error is None
    assert saved[-1].id == "task-original"
    assert queue.get_nowait() == "task-original"
