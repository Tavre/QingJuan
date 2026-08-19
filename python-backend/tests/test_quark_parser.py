from __future__ import annotations

import base64
import html
import json
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

import httpx
import pytest

from app import scraper
from app.models import AddBookPayload, BookSourceRecord
from app.site_plugins import quark_client


def _reader_html(chapters_info: dict[str, object]) -> str:
    payload = html.escape(json.dumps(chapters_info, ensure_ascii=False))
    return f'<i class="page-data js-dataChapters">{payload}</i>'


def _encoded_content(text: str) -> str:
    encoded = base64.b64encode(text.encode()).decode()
    translated: list[str] = []
    for character in encoded:
        if "a" <= character <= "z":
            translated.append(chr((ord(character) - ord("a") + 13) % 26 + ord("a")))
        elif "A" <= character <= "Z":
            translated.append(chr((ord(character) - ord("A") + 13) % 26 + ord("A")))
        else:
            translated.append(character)
    return "".join(translated)


def _chapters_info(*, public: bool = True, prefix: str | None = None) -> dict[str, object]:
    return {
        "bookId": "46543",
        "bookName": "斗罗大陆",
        "authorName": "唐家三少",
        "freeContUrlPrefix": prefix or "https://c13.shuqireader.com/pcapi/chapter/contentfree/",
        "chapterList": [
            {
                "volumeName": "正文",
                "volumeList": [
                    {
                        "chapterId": "2206013",
                        "chapterName": "第一章",
                        "wordCount": 120,
                        "isFreeRead": public,
                        "isBuy": False,
                        "contUrlSuffix": ("?bookId=46543&chapterId=2206013&sign=public-sign"),
                        "shortContUrlSuffix": "?bookId=46543&chapterId=2206013",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_quark_search_maps_public_results_without_forwarding_internal_fields() -> None:
    captured_form: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_form
        assert request.url == httpx.URL(quark_client.QUARK_RENDER_SEARCH_URL)
        captured_form = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "modulesInfos": [
                        {
                            "data": {
                                "bookId": "46543",
                                "displayBookName": "<em>斗罗大陆</em>",
                                "authorName": "唐家三少",
                                "desc": "公开简介",
                                "imgUrl": "http://img-tailor.11222.cn/cover.jpg",
                                "sid": "internal-request-state",
                            }
                        }
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await quark_client.search_quark_books(client, "斗罗大陆", 8)

    assert captured_form["userId"] == [quark_client.QUARK_ANONYMOUS_USER_ID]
    assert captured_form["sign"] == [
        quark_client._make_sign_only_value(
            {
                "timeStamp": captured_form["timeStamp"][0],
                "userId": quark_client.QUARK_ANONYMOUS_USER_ID,
                "params": captured_form["params"][0],
            },
            quark_client.QUARK_RENDER_SKEY,
        )
    ]
    assert results == [
        {
            "bookId": "46543",
            "title": "斗罗大陆",
            "author": "唐家三少",
            "synopsis": "公开简介",
            "cover": "https://img-tailor.11222.cn/cover.jpg",
            "sourceUrl": "https://www.shuqi.com/book/46543.html",
        }
    ]
    assert "sid" not in results[0]


@pytest.mark.asyncio
async def test_quark_builtin_search_uses_registered_source(monkeypatch) -> None:
    @asynccontextmanager
    async def fake_client():
        yield object()

    async def fake_search(client, keyword, limit):
        assert keyword == "斗罗大陆"
        assert limit == 8
        return [
            {
                "title": "斗罗大陆",
                "author": "唐家三少",
                "synopsis": "公开简介",
                "cover": "https://img.example.test/cover.jpg",
                "sourceUrl": "https://www.shuqi.com/book/46543.html",
            }
        ]

    source = BookSourceRecord(
        id="source-builtin-quark",
        name="夸克小说",
        baseUrl="https://www.shuqi.com",
        bookKind="长小说",
        language="中文",
        origin="builtin",
    )
    monkeypatch.setattr(scraper, "_build_http_client", fake_client)
    monkeypatch.setattr(scraper, "search_quark_books", fake_search)
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: True)

    results = await scraper.search_builtin_site_books(source, "斗罗大陆")

    assert results[0].title == "斗罗大陆"
    assert results[0].bookKind == "长小说"
    assert str(results[0].sourceUrl) == "https://www.shuqi.com/book/46543.html"


@pytest.mark.asyncio
async def test_quark_preview_maps_catalog_and_marks_nonfree_chapters(monkeypatch) -> None:
    @asynccontextmanager
    async def fake_client():
        yield object()

    async def fake_book_info(client, book_id):
        assert book_id == "46543"
        return {
            "bookName": "斗罗大陆",
            "authorName": "唐家三少",
            "desc": "作品简介",
            "imgUrl": "http://img-tailor.11222.cn/cover.jpg",
            "readIsOpen": True,
        }

    async def fake_catalog(client, book_id):
        return (
            {"bookId": book_id, "bookName": "斗罗大陆"},
            [
                {
                    "chapterId": "1",
                    "chapterName": "公开章",
                    "isFreeRead": True,
                },
                {
                    "chapterId": "2",
                    "chapterName": "付费章",
                    "isFreeRead": False,
                },
            ],
        )

    monkeypatch.setattr(scraper, "_build_http_client", fake_client)
    monkeypatch.setattr(scraper, "get_quark_book_info", fake_book_info)
    monkeypatch.setattr(scraper, "get_quark_catalog", fake_catalog)
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: True)

    preview = await scraper.preview_from_url(
        AddBookPayload(
            sourceUrl="https://www.shuqi.com/book/46543.html",
            bookKind="长小说",
            language="中文",
        )
    )

    assert preview.title == "斗罗大陆"
    assert preview.cover == "https://img-tailor.11222.cn/cover.jpg"
    assert [chapter.accessRestricted for chapter in preview.chapters] == [False, True]
    assert preview.chapters[0].url == "https://www.shuqi.com/reader?bid=46543&cid=1"


@pytest.mark.asyncio
async def test_quark_free_chapter_is_decoded_and_normalized(monkeypatch) -> None:
    monkeypatch.setattr(quark_client, "QUARK_PAGE_MIN_INTERVAL_SECONDS", 0)
    expected = "第一段公开正文。" * 12 + "<br/>" + "第二段公开正文。" * 12

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.shuqi.com":
            return httpx.Response(200, text=_reader_html(_chapters_info()))
        assert request.url.host == "c13.shuqireader.com"
        return httpx.Response(
            200,
            json={"state": "200", "ChapterContent": _encoded_content(expected)},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await quark_client.get_quark_chapter_content(
            client,
            "46543",
            "2206013",
        )

    assert "\n" in result["text"]
    assert "<br" not in result["text"]
    assert result["chapter"]["chapterName"] == "第一章"


@pytest.mark.asyncio
async def test_quark_rejects_nonfree_chapter_before_content_request(monkeypatch) -> None:
    monkeypatch.setattr(quark_client, "QUARK_PAGE_MIN_INTERVAL_SECONDS", 0)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=_reader_html(_chapters_info(public=False)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(quark_client.QuarkBookError, match="不是匿名免费章节"):
            await quark_client.get_quark_chapter_content(client, "46543", "2206013")

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_quark_rejects_untrusted_content_host(monkeypatch) -> None:
    monkeypatch.setattr(quark_client, "QUARK_PAGE_MIN_INTERVAL_SECONDS", 0)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=_reader_html(_chapters_info(prefix="https://attacker.example/contentfree/")),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(quark_client.QuarkBookError, match="非官方免费正文地址"):
            await quark_client.get_quark_chapter_content(client, "46543", "2206013")

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_quark_catalog_retries_429_with_bounded_backoff(monkeypatch) -> None:
    monkeypatch.setattr(quark_client, "QUARK_PAGE_MIN_INTERVAL_SECONDS", 0)
    delays: list[float] = []
    calls = 0

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429)
        return httpx.Response(200, text=_reader_html(_chapters_info()))

    monkeypatch.setattr(quark_client.asyncio, "sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, chapters = await quark_client.get_quark_catalog(client, "46543")

    assert len(chapters) == 1
    assert calls == 3
    assert delays == [8, 16]


@pytest.mark.asyncio
async def test_disabled_quark_plugin_blocks_search_before_network(monkeypatch) -> None:
    source = BookSourceRecord(
        id="source-builtin-quark",
        name="夸克小说",
        baseUrl="https://www.shuqi.com",
        bookKind="长小说",
        language="中文",
        origin="builtin",
    )
    called = False

    async def unexpected_search(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled plugin must not search")

    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: False)
    monkeypatch.setattr(scraper, "_search_quark_works", unexpected_search)

    with pytest.raises(ValueError, match="夸克小说"):
        await scraper.search_builtin_site_books(source, "测试")

    assert called is False
