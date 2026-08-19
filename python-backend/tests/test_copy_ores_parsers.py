from __future__ import annotations

import httpx
import pytest

from app import scraper
from app.models import AddBookPayload, BookSourceRecord
from app.site_plugins.comicores_client import (
    canonical_comicores_book_url,
    comicores_book_key_from_url,
    comicores_synopsis,
)
from app.site_plugins.copymanga_client import (
    canonical_mangacopy_book_url,
    mangacopy_chapter_ids_from_url,
)


def _copy_detail_payload() -> dict:
    return {
        "code": 200,
        "results": {
            "is_lock": False,
            "is_login": False,
            "is_vip": False,
            "comic": {
                "name": "测试漫画",
                "path_word": "test-comic",
                "brief": "作品简介",
                "cover": "https://sg.mangafunb.fun/t/test-comic/cover.jpg",
                "author": [{"name": "作者甲"}],
            },
            "groups": {
                "default": {"path_word": "default", "name": "默認", "count": 1},
                "other": {"path_word": "other", "name": "其他版本", "count": 1},
            },
        },
    }


def _copy_transport(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v3/comic2/test-comic":
        return httpx.Response(200, json=_copy_detail_payload())
    if request.url.path.endswith("/group/default/chapters"):
        return httpx.Response(
            200,
            json={
                "code": 200,
                "results": {
                    "total": 1,
                    "list": [{"uuid": "chapter-1", "name": "第一卷", "size": 2, "type": 2}],
                },
            },
        )
    if request.url.path.endswith("/group/other/chapters"):
        return httpx.Response(
            200,
            json={
                "code": 200,
                "results": {
                    "total": 1,
                    "list": [{"uuid": "chapter-2", "name": "第一话", "size": 1, "type": 1}],
                },
            },
        )
    if request.url.path.endswith("/chapter/chapter-1"):
        return httpx.Response(
            200,
            json={
                "code": 200,
                "results": {
                    "is_lock": False,
                    "is_login": False,
                    "is_vip": False,
                    "chapter": {
                        "contents": [
                            {"url": "https://sg.mangafunb.fun/t/test-comic/001.jpg"},
                            {"url": "https://sg.mangafunb.fun/t/test-comic/002.jpg"},
                        ]
                    },
                },
            },
        )
    if request.url.path == "/api/v3/search/comic":
        return httpx.Response(
            200,
            json={
                "code": 200,
                "results": {
                    "list": [
                        {
                            "name": "测试漫画",
                            "path_word": "test-comic",
                            "alias": "测试别名",
                            "cover": "https://sg.mangafunb.fun/t/test-comic/cover.jpg",
                            "author": [{"name": "作者甲"}],
                        }
                    ]
                },
            },
        )
    raise AssertionError(f"unexpected request: {request.url}")


@pytest.mark.asyncio
async def test_copymanga_preview_uses_public_api_and_preserves_groups(monkeypatch) -> None:
    transport = httpx.MockTransport(_copy_transport)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )

    preview = await scraper._preview_copymanga(
        "https://www.mangacopy.com/comic/test-comic",
        AddBookPayload(
            sourceUrl="https://www.mangacopy.com/comic/test-comic",
            bookKind="漫画",
            language="中文",
        ),
    )

    assert preview.title == "测试漫画"
    assert preview.author == "作者甲"
    assert preview.chapterCount == 2
    assert [chapter.title for chapter in preview.chapters] == ["第一卷", "其他版本 - 第一话"]
    assert preview.chapters[0].pageCount == 2
    assert mangacopy_chapter_ids_from_url(preview.chapters[0].url) == (
        "test-comic",
        "chapter-1",
    )


@pytest.mark.asyncio
async def test_copymanga_chapter_returns_only_official_https_images() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_copy_transport)) as client:
        result = await scraper._fetch_copymanga_chapter_data(
            client,
            "https://www.mangacopy.com/comic/test-comic/chapter/chapter-1",
            "第一卷",
        )

    assert result.content_source == "mangacopy-public-api"
    assert result.authorization_method == "public-api"
    assert result.image_urls == [
        "https://sg.mangafunb.fun/t/test-comic/001.jpg",
        "https://sg.mangafunb.fun/t/test-comic/002.jpg",
    ]


@pytest.mark.asyncio
async def test_copymanga_builtin_search(monkeypatch) -> None:
    transport = httpx.MockTransport(_copy_transport)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda _plugin_id: True)
    source = BookSourceRecord(
        id="source-builtin-copymanga",
        name="拷贝漫画",
        baseUrl="https://www.mangacopy.com",
        bookKind="漫画",
        language="中文",
        origin="builtin",
    )

    results = await scraper.search_builtin_site_books(source, "测试")

    assert len(results) == 1
    assert results[0].author == "作者甲"
    assert results[0].sourceUrl == canonical_mangacopy_book_url("test-comic")


def _comicores_post() -> dict:
    return {
        "id": 11515,
        "slug": "test-book",
        "link": "https://www.comicores.cc/test-book/.html",
        "title": {"rendered": "[作者甲] 测试作品"},
        "content": {
            "rendered": (
                "<p>公开作品简介</p>"
                "<div class='su-members'>您需要登录来查看全部内容。受保护下载信息</div>"
            )
        },
        "_embedded": {
            "wp:featuredmedia": [{"source_url": "https://img.comicores.cc/cover.png"}],
            "wp:term": [
                [{"name": "作者甲", "link": "https://www.comicores.cc/category/mangaka/a"}]
            ],
        },
    }


def _comicores_transport(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/wp-json/wp/v2/posts":
        return httpx.Response(200, json=[_comicores_post()], request=request)
    raise AssertionError(f"unexpected request: {request.url}")


def test_comicores_url_and_public_synopsis_boundary() -> None:
    assert comicores_book_key_from_url("https://www.comicores.cc/test-book/.html") == "test-book"
    assert canonical_comicores_book_url("test-book").endswith("/test-book/.html")
    assert comicores_synopsis(_comicores_post()) == "公开作品简介"


@pytest.mark.asyncio
async def test_comicores_preview_is_metadata_only(monkeypatch) -> None:
    transport = httpx.MockTransport(_comicores_transport)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )

    preview = await scraper._preview_comicores(
        "https://www.comicores.cc/test-book/.html",
        AddBookPayload(
            sourceUrl="https://www.comicores.cc/test-book/.html",
            bookKind="漫画",
            language="中文",
        ),
    )

    assert preview.title == "[作者甲] 测试作品"
    assert preview.author == "作者甲"
    assert preview.chapterCount == 0
    assert preview.chapters == []
    assert "仅展示公开作品元数据" in preview.synopsis
    assert "受保护下载信息" not in preview.synopsis


@pytest.mark.asyncio
async def test_comicores_chapter_access_is_not_implemented(monkeypatch) -> None:
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda _plugin_id: True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(_comicores_transport)) as client:
        with pytest.raises(ValueError, match="网盘或付费下载资源"):
            await scraper._fetch_chapter_data(
                client,
                "https://www.comicores.cc/test-book/.html",
                "受保护资源",
            )
