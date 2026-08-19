from __future__ import annotations

import json

import pytest
import requests
from fastapi.testclient import TestClient

from app import main, scraper
from app.api.routers import plugins_router
from app.application import create_application
from app.models import BookRecord, BookSourceRecord, PreviewResponse
from app.site_plugins import fanqie_client, fanqie_runtime, get_site_plugin
from app.site_plugins.fanqie_client import FanqieApiError
from app.site_plugins.fanqie_runtime import FanqieRuntime


def _json_response(payload: dict, status_code: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.encoding = "utf-8"
    response._content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return response


def test_cookie_header_parser_preserves_values_and_rejects_header_injection() -> None:
    assert fanqie_client.parse_cookie_header("sessionid=abc==; sid_tt=xyz") == {
        "sessionid": "abc==",
        "sid_tt": "xyz",
    }

    with pytest.raises(FanqieApiError, match="格式无效") as caught:
        fanqie_client.parse_cookie_header("sessionid=private-value\r\nX-Test: injected")

    assert "private-value" not in str(caught.value)


def test_bookshelf_mapping_deduplicates_ids_and_preserves_book_type(monkeypatch) -> None:
    session = requests.Session()
    monkeypatch.setattr(fanqie_client, "session_from_cookies", lambda _: session)
    monkeypatch.setattr(fanqie_client, "get_user_info", lambda _: {"id": "account-id"})
    monkeypatch.setattr(
        fanqie_client,
        "_request_get",
        lambda *args, **kwargs: _json_response(
            {
                "code": 0,
                "data": {
                    "book_shelf_info": [
                        {"book_id": "1001", "book_type": 0, "group_name": "小说"},
                        {"book_id": "1001", "book_type": 0, "group_name": "重复"},
                        {"book_id": "2002", "book_type": 1},
                        {"book_id": "not-a-number", "book_type": 0},
                    ],
                    "group_data": [{"group_id": "1", "group_name": "小说"}],
                },
            }
        ),
    )

    result = fanqie_client.get_bookshelf({"sessionid": "secret"})

    assert [book["bookId"] for book in result["books"]] == ["1001", "2002"]
    assert result["books"][1]["bookType"] == 1
    assert result["groups"] == [{"group_id": "1", "group_name": "小说"}]


def test_signed_search_filters_non_book_cells_and_normalizes_results(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def request_get(session, url, *, stage, params=None, headers=None):
        captured.update({"url": url, "stage": stage, "params": params, "headers": headers})
        return _json_response(
            {
                "code": 0,
                "search_tabs": [
                    {
                        "tab_type": 1,
                        "data": [
                            {"show_type": 112, "book_data": [{"book_id": "999", "book_name": "插入位"}]},
                            {
                                "show_type": 110,
                                "search_high_light": {
                                    "title": {"rich_text": "<em>测试</em><script>作品</script>"},
                                    "abstract": {"rich_text": "<em>简介</em>"},
                                },
                                "book_data": [
                                    {
                                        "book_id": "7080092010052324352",
                                        "book_name": "测试作品",
                                        "author": "测试作者",
                                        "abstract": "作品简介",
                                        "thumb_url": "https://example.test/cover.jpg",
                                        "serial_count": 12,
                                    },
                                    {
                                        "book_id": "7080092010052324352",
                                        "book_name": "重复作品",
                                    },
                                    {"book_id": "invalid", "book_name": "无效作品"},
                                ],
                            },
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(fanqie_client, "_request_get", request_get)

    results = fanqie_client.search_books("测试作品", 20)

    assert len(results) == 1
    assert results[0] == {
        "book_id": "7080092010052324352",
        "title": "测试作品",
        "author": "测试作者",
        "cover_url": "https://example.test/cover.jpg",
        "summary": "作品简介",
        "status": "",
        "word_count": 0,
        "sub_info": "12章",
        "read_count": 0,
        "score": "",
        "category": "",
        "chapter_count": 12,
        "last_chapter_title": "",
        "in_bookshelf": False,
        "highlight_title": "<em>测试</em>作品",
        "highlight_summary": "<em>简介</em>",
    }
    assert str(captured["url"]).startswith(f"{fanqie_client.SEARCH_ENDPOINT}?")
    assert "query=%E6%B5%8B%E8%AF%95%E4%BD%9C%E5%93%81" in str(captured["url"])
    assert "tab_type=1" in str(captured["url"])
    assert captured["stage"] == "作品搜索"
    assert captured["params"] is None
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert {"x-argus", "x-ladon", "x-khronos", "x-ss-req-ticket"} <= headers.keys()


def test_qr_runtime_never_returns_upstream_token_or_cookies(monkeypatch) -> None:
    runtime = FanqieRuntime()
    monkeypatch.setattr(
        fanqie_runtime,
        "get_qrcode",
        lambda _: {
            "qrcodeToken": "upstream-qrcode-token",
            "qrImageBase64": "aW1hZ2U=",
        },
    )
    monkeypatch.setattr(
        fanqie_runtime,
        "poll_qrcode",
        lambda *_: {
            "status": "success",
            "message": "登录成功",
            "cookies": {"sessionid": "private-session-cookie"},
        },
    )

    started = runtime.start_login()
    completed = runtime.poll_login(str(started["flowId"]))
    status = runtime.account_status()

    public_text = f"{started}{completed}{status}"
    assert started["flowId"] != "upstream-qrcode-token"
    assert "upstream-qrcode-token" not in public_text
    assert "private-session-cookie" not in public_text
    assert completed == {"status": "success", "message": "登录成功", "loggedIn": True}
    assert status["loggedIn"] is True
    runtime.logout()


def test_cookie_login_public_status_does_not_echo_secret(monkeypatch) -> None:
    runtime = FanqieRuntime()
    monkeypatch.setattr(
        fanqie_runtime,
        "login_with_cookies",
        lambda _: {"cookies": {"sessionid": "private-session-cookie"}},
    )

    result = runtime.login_cookies("sessionid=private-session-cookie")

    assert result["loggedIn"] is True
    assert "private-session-cookie" not in str(result)
    runtime.logout()


@pytest.mark.asyncio
async def test_fanqie_builtin_search_maps_results_to_canonical_book_urls(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "search_fanqie_books",
        lambda *args, **kwargs: [
            {
                "book_id": "7080092010052324352",
                "title": "测试作品",
                "author": "测试作者",
                "summary": "作品简介",
                "cover_url": "https://example.test/cover.jpg",
            }
        ],
    )
    source = BookSourceRecord(
        id="source-builtin-fanqie",
        name="番茄小说",
        baseUrl="https://fanqienovel.com",
        bookKind="长小说",
        language="中文",
        origin="builtin",
    )

    results = await scraper._search_fanqie_works(source, "测试", 8)

    assert len(results) == 1
    assert results[0].title == "测试作品"
    assert results[0].synopsis == "作品简介"
    assert results[0].cover == "https://example.test/cover.jpg"
    assert results[0].sourceUrl == "https://fanqienovel.com/page/7080092010052324352"


def test_cookie_login_api_never_echoes_cookie(monkeypatch) -> None:
    received: list[str] = []
    monkeypatch.setattr(
        main.FANQIE_RUNTIME,
        "login_cookies",
        lambda value: received.append(value) or {"loggedIn": True, "expiresAt": None},
    )
    application = create_application(routers=[plugins_router])

    with TestClient(application) as client:
        response = client.post(
            "/plugins/fanqie/account/login-cookies",
            json={"cookies": "sessionid=private-cookie-value"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"loggedIn": True, "expiresAt": None}
    assert received == ["sessionid=private-cookie-value"]
    assert "private-cookie-value" not in response.text


def test_disabled_plugin_blocks_qr_poll_before_network(monkeypatch) -> None:
    called = False

    def unexpected_poll(_: str) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("disabled plugin must not poll its login provider")

    monkeypatch.setattr(main, "is_site_plugin_enabled", lambda _: False)
    monkeypatch.setattr(main.FANQIE_RUNTIME, "poll_login", unexpected_poll)
    application = create_application(routers=[plugins_router])

    with TestClient(application) as client:
        response = client.get("/plugins/fanqie/account/login-qrcode/local-flow")

    assert response.status_code == 400
    assert "已停用" in response.json()["detail"]
    assert called is False


def test_plugin_without_cookie_capability_rejects_cookie_login(monkeypatch) -> None:
    called = False

    def unexpected_login(_: str) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("plugin without capability must not receive credentials")

    monkeypatch.setattr(main.QIDIAN_RUNTIME, "login_cookies", unexpected_login, raising=False)
    application = create_application(routers=[plugins_router])

    with TestClient(application) as client:
        response = client.post(
            "/plugins/qidian/account/login-cookies",
            json={"cookies": "sessionid=private-cookie-value"},
        )

    assert response.status_code == 404
    assert "private-cookie-value" not in response.text
    assert called is False


def test_bookshelf_job_store_rejects_duplicate_active_imports() -> None:
    main.SITE_PLUGIN_IMPORT_JOB_STORE.clear()
    first = main.SITE_PLUGIN_IMPORT_JOB_STORE.create("fanqie")

    with pytest.raises(ValueError, match="正在运行"):
        main.SITE_PLUGIN_IMPORT_JOB_STORE.create("fanqie")

    main.SITE_PLUGIN_IMPORT_JOB_STORE.complete(first.id)
    second = main.SITE_PLUGIN_IMPORT_JOB_STORE.create("fanqie")
    assert second.id != first.id
    main.SITE_PLUGIN_IMPORT_JOB_STORE.clear()


@pytest.mark.asyncio
async def test_disabled_plugin_blocks_bookshelf_job_before_network(monkeypatch) -> None:
    plugin = get_site_plugin("fanqie")
    assert plugin is not None
    called = False

    def unexpected_bookshelf() -> list[dict[str, object]]:
        nonlocal called
        called = True
        raise AssertionError("disabled plugin must not read its remote bookshelf")

    main.SITE_PLUGIN_IMPORT_JOB_STORE.clear()
    monkeypatch.setattr(main, "get_site_plugin", lambda _: plugin)
    monkeypatch.setattr(main, "is_site_plugin_enabled", lambda _: False)
    monkeypatch.setattr(main.FANQIE_RUNTIME, "list_bookshelf_books", unexpected_bookshelf)
    job = main.SITE_PLUGIN_IMPORT_JOB_STORE.create("fanqie")

    await main._run_site_plugin_bookshelf_import(job.id, "fanqie")
    result = main.SITE_PLUGIN_IMPORT_JOB_STORE.get(job.id, "fanqie")

    assert result.status == "failed"
    assert "已停用" in result.message
    assert called is False


@pytest.mark.asyncio
async def test_bookshelf_import_skips_existing_and_unsupported_books(monkeypatch) -> None:
    plugin = get_site_plugin("fanqie")
    assert plugin is not None
    main.SITE_PLUGIN_IMPORT_JOB_STORE.clear()
    monkeypatch.setattr(main, "get_site_plugin", lambda plugin_id: plugin if plugin_id == "fanqie" else None)
    monkeypatch.setattr(
        main.FANQIE_RUNTIME,
        "list_bookshelf_books",
        lambda: [
            {"bookId": "1001", "bookType": 0},
            {"bookId": "2002", "bookType": 0},
            {"bookId": "3003", "bookType": 1},
            {"bookId": "4004", "bookType": 0},
        ],
    )
    monkeypatch.setattr(
        main,
        "list_books",
        lambda: [
            BookRecord(
                id="book-existing",
                title="已有作品",
                sourceUrl="https://fanqienovel.com/page/1001",
                bookKind="长小说",
                language="中文",
                status="待处理",
                chapterCount=1,
                translated=False,
                localPath="library/existing",
            )
        ],
    )

    async def preview(payload):
        source_id = str(payload.sourceUrl).rstrip("/").split("/")[-1]
        if source_id == "4004":
            raise ValueError("作品页暂时不可用")
        return PreviewResponse(
            title=f"作品 {source_id}",
            chapterCount=1,
            chapters=[],
            bookKind="长小说",
        )

    async def create_book(payload, preview_result):
        return BookRecord(
            id="book-imported",
            title=preview_result.title,
            sourceUrl=str(payload.sourceUrl),
            bookKind="长小说",
            language="中文",
            status="待处理",
            chapterCount=preview_result.chapterCount,
            translated=False,
            localPath="library/imported",
        )

    monkeypatch.setattr(main, "preview_from_url", preview)
    monkeypatch.setattr(main, "_create_imported_book", create_book)
    job = main.SITE_PLUGIN_IMPORT_JOB_STORE.create("fanqie")

    await main._run_site_plugin_bookshelf_import(job.id, "fanqie")
    result = main.SITE_PLUGIN_IMPORT_JOB_STORE.get(job.id, "fanqie")

    assert result.status == "completed"
    assert result.importedCount == 1
    assert result.skippedCount == 1
    assert result.unsupportedCount == 1
    assert result.failedCount == 1
    assert [item.status for item in result.items] == [
        "skipped",
        "imported",
        "unsupported",
        "failed",
    ]
