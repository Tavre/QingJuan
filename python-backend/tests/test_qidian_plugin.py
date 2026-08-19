from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main, scraper
from app.api.routers import plugins_router
from app.application import create_application
from app.models import BookRecord, BookSourceRecord, ChapterPreview, PreviewResponse
from app.site_plugins import get_site_plugin, qidian_client, qidian_runtime
from app.site_plugins.qidian_client import QidianApiError
from app.site_plugins.qidian_runtime import QidianRuntime


class _FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        text: str = "",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


def test_qidian_login_redirects_reject_untrusted_hosts() -> None:
    class _Session:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, **kwargs) -> _FakeResponse:
            self.calls.append(url)
            return _FakeResponse(
                status_code=302,
                headers={"Location": "http://127.0.0.1/private"},
            )

    session = _Session()

    with pytest.raises(QidianApiError, match="不受信任"):
        qidian_client._follow_login_redirects(session, "https://www.qidian.com/loginSuccess")

    assert session.calls == ["https://www.qidian.com/loginSuccess"]


def test_qidian_search_maps_mobile_ssr_results_without_account_state(monkeypatch) -> None:
    page_context = {
        "pageContext": {
            "pageProps": {
                "pageData": {
                    "kw": "斗破苍穹",
                    "bookInfo": {
                        "total": 1000,
                        "pageNum": 1,
                        "pageSize": 20,
                        "isLast": 0,
                        "records": [
                            {
                                "bid": 1209977,
                                "bName": "斗破苍穹",
                                "cid": 1019021,
                                "bAuth": "天蚕土豆",
                                "desc": "这里是属于斗气的世界",
                                "cat": "玄幻",
                                "subCateName": "异世大陆",
                                "imgUrl": "//bookcover.yuewen.com/qdbimg/349573/1209977/180",
                                "cnt": "533.23万字",
                            },
                            {"bid": 2, "bName": "超出限制"},
                        ],
                    },
                }
            }
        }
    }
    captured: dict[str, object] = {}

    def request_get(session, url, **kwargs):
        captured.update({"url": url, **kwargs})
        return _FakeResponse(
            text=f'<script id="vite-plugin-ssr_pageContext">{json.dumps(page_context)}</script>'
        )

    monkeypatch.setattr(qidian_client, "_request_get", request_get)

    result = qidian_client.search_books("斗破 苍穹", page_size=1)

    assert result["data"]["keyword"] == "斗破苍穹"
    assert result["data"]["books"] == [
        {
            "bookId": 1209977,
            "bookName": "斗破苍穹",
            "cbid": None,
            "authorId": 1019021,
            "authorName": "天蚕土豆",
            "desc": "这里是属于斗气的世界",
            "category": "玄幻",
            "subCategory": "异世大陆",
            "state": None,
            "signStatus": None,
            "coverUrl": "https://bookcover.yuewen.com/qdbimg/349573/1209977/180",
            "isVip": None,
            "wordCountText": "533.23万字",
            "recommendCnt": None,
            "favoriteCnt": None,
            "lastChapterName": None,
            "lastUpdateTime": None,
            "bookType": None,
            "isPub": None,
        }
    ]
    assert captured["url"] == ("https://m.qidian.com/so/%E6%96%97%E7%A0%B4%20%E8%8B%8D%E7%A9%B9.html")
    assert captured["params"] == {"pageNum": 1, "orderBy": 0}
    assert "cookies" not in captured


@pytest.mark.asyncio
async def test_qidian_builtin_search_maps_to_canonical_book_urls(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "search_qidian_books",
        lambda *args, **kwargs: {
            "data": {
                "books": [
                    {
                        "bookId": 1209977,
                        "bookName": "斗破苍穹",
                        "authorName": "天蚕土豆",
                        "desc": "这里是属于斗气的世界",
                        "coverUrl": "https://example.test/cover.jpg",
                    },
                    {"bookId": 1209977, "bookName": "重复作品"},
                    {"bookId": "invalid", "bookName": "无效作品"},
                ]
            }
        },
    )
    source = BookSourceRecord(
        id="source-builtin-qidian",
        name="起点中文网",
        baseUrl="https://www.qidian.com",
        bookKind="长小说",
        language="中文",
        origin="builtin",
    )

    results = await scraper._search_qidian_works(source, "斗破苍穹", 8)

    assert len(results) == 1
    assert results[0].title == "斗破苍穹"
    assert results[0].author == "天蚕土豆"
    assert results[0].synopsis == "这里是属于斗气的世界"
    assert results[0].sourceUrl == "https://www.qidian.com/book/1209977/"


def test_qidian_plugin_declares_search_capability() -> None:
    plugin = get_site_plugin("qidian")

    assert plugin is not None
    assert plugin.search_handler == "qidian"
    assert "search" in plugin.capabilities


def test_qidian_catalog_maps_volumes_and_access_state(monkeypatch) -> None:
    response = _FakeResponse(
        {
            "code": 0,
            "data": {
                "bookId": 123,
                "bookName": "测试作品",
                "vs": [
                    {
                        "cs": [
                            {"id": 11, "cN": "免费章", "cnt": 1000, "sS": 1},
                            {"id": 12, "cN": "付费章", "cnt": 1200, "sS": 2},
                        ]
                    }
                ],
            },
        }
    )
    monkeypatch.setattr(qidian_client, "_request_get", lambda *args, **kwargs: response)

    result = qidian_client.get_catalog("123")

    chapters = result["volumes"][0]["chapters"]
    assert result["chapterTotal"] == 2
    assert chapters[0]["isVip"] is False
    assert chapters[1]["isVip"] is True
    assert chapters[1]["chapterId"] == "12"


def test_qidian_protected_chapter_is_rejected_without_decryption(monkeypatch) -> None:
    page_context = {
        "pageContext": {
            "pageProps": {
                "pageData": {
                    "chapterInfo": {
                        "chapterId": "11",
                        "chapterName": "受保护章节",
                        "content": "encrypted",
                        "fkp": "protected-key-payload",
                    }
                }
            }
        }
    }
    html = f'<script id="vite-plugin-ssr_pageContext">{json.dumps(page_context)}</script>'
    monkeypatch.setattr(
        qidian_client,
        "_request_get",
        lambda *args, **kwargs: _FakeResponse(text=html),
    )

    with pytest.raises(QidianApiError, match="不处理受保护内容解密"):
        qidian_client.get_chapter("123", "11", cookies={"ywguid": "private"})


def test_qidian_free_chapter_normalizes_string_access_flags(monkeypatch) -> None:
    page_context = {
        "pageContext": {
            "pageProps": {
                "pageData": {
                    "chapterInfo": {
                        "chapterId": "11",
                        "chapterName": "公开章节",
                        "content": "<p>第一段</p><p>第二段</p>",
                        "freeStatus": "0",
                        "isBuy": "0",
                        "vipStatus": "0",
                    }
                }
            }
        }
    }
    html = f'<script id="vite-plugin-ssr_pageContext">{json.dumps(page_context)}</script>'
    monkeypatch.setattr(
        qidian_client,
        "_request_get",
        lambda *args, **kwargs: _FakeResponse(text=html),
    )

    result = qidian_client.get_chapter("123", "11")

    assert result["text"] == "第一段\n第二段"
    assert result["accessRestricted"] is False


def test_qidian_runtime_reads_all_groups_pages_and_deduplicates(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    def fake_page(cookies, *, group_id, page, page_size, sort=0):
        calls.append((group_id, page))
        payloads = {
            (-100, 1): {
                "groups": [{"groupId": -100}, {"groupId": 8}],
                "page": {"totalPage": 2, "isLast": 0},
                "books": [{"bid": "1", "bookName": "甲"}],
            },
            (-100, 2): {
                "groups": [],
                "page": {"totalPage": 2, "isLast": 1},
                "books": [{"bid": "2", "bookName": "乙"}],
            },
            (8, 1): {
                "groups": [],
                "page": {"totalPage": 1, "isLast": 1},
                "books": [
                    {"bid": "2", "bookName": "乙（重复）"},
                    {"bid": "3", "bookName": "丙"},
                ],
            },
        }
        return payloads[(group_id, page)]

    runtime = QidianRuntime()
    monkeypatch.setattr(runtime, "cookies", lambda: {"ywguid": "x", "ywkey": "y"})
    monkeypatch.setattr(qidian_runtime, "get_bookshelf_page", fake_page)

    books = runtime.list_bookshelf_books()

    assert [book["bid"] for book in books] == ["1", "2", "3"]
    assert calls == [(-100, 1), (-100, 2), (8, 1)]


def test_qidian_runtime_hides_upstream_session_and_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        qidian_runtime,
        "get_qrcode",
        lambda session: {
            "sessionKey": "upstream-secret-session",
            "qrImageBase64": "aW1hZ2U=",
            "expireSeconds": 180,
        },
    )
    monkeypatch.setattr(
        qidian_runtime,
        "poll_qrcode",
        lambda session, session_key: {
            "status": "success",
            "message": "登录成功",
            "cookies": {"ywguid": "private-guid", "ywkey": "private-key"},
        },
    )
    runtime = QidianRuntime()

    started = runtime.start_login()
    polled = runtime.poll_login(str(started["flowId"]))

    assert "sessionKey" not in started
    assert "cookies" not in polled
    assert "private" not in json.dumps(started | polled)
    assert polled == {"status": "success", "message": "登录成功", "loggedIn": True}


def test_qidian_login_routes_are_private_and_never_expose_upstream_state(monkeypatch) -> None:
    monkeypatch.setattr(main, "is_site_plugin_enabled", lambda plugin_id: plugin_id == "qidian")
    monkeypatch.setattr(
        main.QIDIAN_RUNTIME,
        "start_login",
        lambda: {
            "flowId": "opaque-flow",
            "qrImageBase64": "aW1hZ2U=",
            "expiresAt": "2030-01-01T00:03:00Z",
        },
    )
    monkeypatch.setattr(
        main.QIDIAN_RUNTIME,
        "poll_login",
        lambda flow_id: {
            "status": "success",
            "message": "登录成功",
            "loggedIn": True,
        },
    )
    application = create_application(routers=[plugins_router])

    with TestClient(application) as client:
        started = client.post("/plugins/qidian/account/login-qrcode")
        polled = client.get("/plugins/qidian/account/login-qrcode/opaque-flow")

    assert started.status_code == 200
    assert polled.status_code == 200
    assert started.headers["Cache-Control"] == "no-store"
    assert polled.headers["Cache-Control"] == "no-store"
    combined = json.dumps([started.json(), polled.json()])
    assert "sessionKey" not in combined
    assert "cookies" not in combined


@pytest.mark.asyncio
async def test_qidian_bookshelf_import_skips_existing_and_isolates_failure(monkeypatch) -> None:
    main.SITE_PLUGIN_IMPORT_JOB_STORE.clear()
    remote_books = [
        {"bid": "1", "bookName": "已有作品", "cateName": "玄幻"},
        {"bid": "2", "bookName": "新增作品", "cateName": "轻小说"},
        {"bid": "3", "bookName": "失败作品", "cateName": "都市"},
    ]
    existing = BookRecord(
        id="book-existing",
        title="已有作品",
        sourceUrl="https://book.qidian.com/info/1/",
        bookKind="长小说",
        language="中文",
        status="待处理",
        chapterCount=1,
        translated=False,
        localPath="中文/已有作品",
    )
    monkeypatch.setattr(main.QIDIAN_RUNTIME, "list_bookshelf_books", lambda: remote_books)
    monkeypatch.setattr(main, "list_books", lambda: [existing])

    async def fake_preview(payload):
        if qidian_client.qidian_book_id_from_url(str(payload.sourceUrl)) == "3":
            raise ValueError("目录不可用")
        return PreviewResponse(
            title=payload.title or "新增作品",
            author="作者",
            synopsis="简介",
            chapterCount=1,
            chapters=[
                ChapterPreview(
                    title="第一章",
                    url="https://m.qidian.com/chapter/2/20/",
                )
            ],
            bookKind=payload.bookKind,
        )

    async def fake_create(payload, preview):
        return BookRecord(
            id="book-new",
            title=preview.title,
            sourceUrl=str(payload.sourceUrl),
            bookKind=preview.bookKind,
            language=payload.language,
            status="待处理",
            chapterCount=1,
            translated=False,
            localPath="中文/新增作品",
        )

    monkeypatch.setattr(main, "preview_from_url", fake_preview)
    monkeypatch.setattr(main, "_create_imported_book", fake_create)
    job = main.SITE_PLUGIN_IMPORT_JOB_STORE.create("qidian")

    await main._run_site_plugin_bookshelf_import(job.id, "qidian")

    result = main.SITE_PLUGIN_IMPORT_JOB_STORE.get(job.id, "qidian")
    assert result.status == "completed"
    assert (result.importedCount, result.skippedCount, result.failedCount) == (1, 1, 1)
    assert [item.status for item in result.items] == ["skipped", "imported", "failed"]
    assert result.items[1].bookId == "book-new"
