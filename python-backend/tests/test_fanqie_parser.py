from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app import scraper
from app.fanqie_parser import (
    FanqieParseError,
    canonical_fanqie_book_url,
    decode_fanqie_text,
    fanqie_book_id_from_url,
    fanqie_item_id_from_url,
    is_fanqie_url,
    parse_fanqie_book_page,
    parse_fanqie_reader_page,
)
from app.models import AddBookPayload, ChapterPreview, PreviewResponse, TranslationSettings

BOOK_ID = "7143038691944959011"
BOOK_URL = f"https://fanqienovel.com/page/{BOOK_ID}"


def _state_html(state: dict[str, object]) -> str:
    serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    # 真实阅读页状态含有 JavaScript undefined；适配器只能归一化它，不能执行脚本。
    serialized = serialized[:-1] + ',"libra":{"value":undefined}}'
    return f"<html><script>(function(){{window.__INITIAL_STATE__={serialized};}})()</script></html>"


def _book_html(*, book_id: str = BOOK_ID) -> str:
    chapters = [
        {
            "itemId": "10001",
            "title": "第2章 雨夜",
            "realChapterOrder": "2",
            "volume_name": "第一卷",
            "isChapterLock": False,
            "needPay": 0,
        },
        {
            "itemId": "10002",
            "title": "第1章 启程",
            "realChapterOrder": "1",
            "volume_name": "第一卷",
            "isChapterLock": False,
            "needPay": 0,
        },
        {
            "itemId": "10003",
            "title": "第3章 门后",
            "realChapterOrder": "3",
            "volume_name": "第二卷",
            "isChapterLock": True,
            "needPay": 0,
        },
    ]
    return _state_html(
        {
            "page": {
                "bookId": book_id,
                "bookName": "测试小说",
                "authorName": "测试作者",
                "abstract": "字面 undefined 必须保持不变",
                "thumbUrl": "https://example.test/cover.jpg",
                "chapterTotal": 3,
                "chapterListWithVolume": [chapters[:2], {"chapters": chapters[2:]}],
            }
        }
    )


def _reader_html(
    *,
    locked: bool = False,
    item_id: str = "10002",
    content: str | None = None,
    declared_word_count: int | None = None,
) -> str:
    resolved_content = content or (
        '<p><img src="{{image_domain}}{占位描述}"></p>'
        "<p>这是第段。</p><p>这是第二段。</p>"
        '<p><img src="/public/illustration.png"></p>'
    )
    visible_text = "这是第一段。这是第二段。"
    return _state_html(
        {
            "reader": {
                "chapterData": {
                    "itemId": item_id,
                    "bookId": BOOK_ID,
                    "title": "第1章 启程",
                    "isChapterLock": locked,
                    "isPaidPublication": False,
                    "isPaidStory": False,
                    "needPay": 0,
                    "chapterWordNumber": declared_word_count or len(visible_text),
                    "content": resolved_content,
                }
            }
        }
    )


def test_url_recognition_is_limited_to_fanqie_http_pages() -> None:
    assert is_fanqie_url(BOOK_URL)
    assert fanqie_book_id_from_url(f"{BOOK_URL}/?enter_from=search") == BOOK_ID
    assert fanqie_item_id_from_url("https://www.fanqienovel.com/reader/10002") == "10002"
    assert canonical_fanqie_book_url(BOOK_ID) == BOOK_URL
    assert not is_fanqie_url("file:///page/7143038691944959011")
    assert not is_fanqie_url("https://fanqienovel.com.evil.test/page/7143038691944959011")
    assert fanqie_book_id_from_url("https://fanqienovel.com/search/7143038691944959011") is None


def test_font_obfuscation_is_decoded_without_touching_normal_text() -> None:
    assert decode_fanqie_text("第章 normal") == "第一章 normal"


def test_book_parser_flattens_volumes_orders_chapters_and_preserves_locks() -> None:
    book = parse_fanqie_book_page(_book_html(), BOOK_URL)

    assert book.title == "测试小说"
    assert book.author == "测试作者"
    assert book.synopsis == "字面 undefined 必须保持不变"
    assert book.total_chapter_count == 3
    assert [chapter.item_id for chapter in book.chapters] == ["10002", "10001", "10003"]
    assert [chapter.item_id for chapter in book.public_chapters] == ["10002", "10001"]
    assert book.chapters[-1].is_locked is True


def test_book_parser_rejects_mismatched_or_missing_state() -> None:
    with pytest.raises(FanqieParseError, match="页面作品编号与链接不一致"):
        parse_fanqie_book_page(_book_html(book_id="999"), BOOK_URL)
    with pytest.raises(FanqieParseError, match="缺少 __INITIAL_STATE__"):
        parse_fanqie_book_page("<html></html>", BOOK_URL)


def test_reader_parser_extracts_public_text_without_placeholder_images() -> None:
    chapter_url = "https://fanqienovel.com/reader/10002"
    chapter = parse_fanqie_reader_page(_reader_html(), chapter_url)

    assert chapter.title == "第1章 启程"
    assert chapter.text == "这是第一段。\n\n这是第二段。"
    assert chapter.image_urls == ("https://fanqienovel.com/public/illustration.png",)
    assert chapter.content_source == "web_initial_state"
    assert chapter.authorization_method == "public_web"
    assert chapter.access_restricted is False


def test_reader_parser_accepts_complete_content_despite_lock_hint() -> None:
    chapter = parse_fanqie_reader_page(
        _reader_html(locked=True),
        "https://fanqienovel.com/reader/10002",
    )

    assert chapter.text == "这是第一段。\n\n这是第二段。"
    assert chapter.access_restricted is True
    assert chapter.authorization_method == "authorized_web_session"


def test_reader_parser_refuses_incomplete_locked_preview_content() -> None:
    with pytest.raises(FanqieParseError, match="只返回了试读片段"):
        parse_fanqie_reader_page(
            _reader_html(
                locked=True,
                content="<p>这是一小段试读内容。</p>",
                declared_word_count=2000,
            ),
            "https://fanqienovel.com/reader/10002",
        )


@pytest.mark.asyncio
async def test_preview_dispatch_keeps_restricted_chapters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(url: str) -> tuple[str, str]:
        assert url == BOOK_URL
        return _book_html(), BOOK_URL

    monkeypatch.setattr(scraper, "_fetch_fanqie_html", fake_fetch)
    preview = await scraper.preview_from_url(
        AddBookPayload(
            sourceUrl=f"https://www.fanqienovel.com/page/{BOOK_ID}/?from=test",
            bookKind="长小说",
            language="中文",
        )
    )

    assert preview.title == "测试小说"
    assert preview.chapterCount == 3
    assert [chapter.url for chapter in preview.chapters] == [
        "https://fanqienovel.com/reader/10002",
        "https://fanqienovel.com/reader/10001",
        "https://fanqienovel.com/reader/10003",
    ]
    assert [chapter.accessRestricted for chapter in preview.chapters] == [False, False, True]


@pytest.mark.asyncio
async def test_initial_import_attempts_restricted_chapters_without_dropping_them(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fetched_urls: list[str] = []

    async def fake_fetch(_: object, url: str, title: str = "") -> scraper.ChapterFetchResult:
        fetched_urls.append(url)
        return scraper.ChapterFetchResult(
            text=f"{title}完整正文",
            image_urls=[],
            content_source="web_initial_state",
            authorization_method="public_web",
        )

    monkeypatch.setattr(scraper, "_fetch_chapter_data", fake_fetch)
    monkeypatch.setattr(scraper, "_load_runtime_settings", TranslationSettings)
    preview = PreviewResponse(
        title="测试小说",
        chapterCount=2,
        chapters=[
            ChapterPreview(title="公开章", url="https://fanqienovel.com/reader/10001"),
            ChapterPreview(
                title="受限章",
                url="https://fanqienovel.com/reader/10002",
                accessRestricted=True,
            ),
        ],
        bookKind="长小说",
    )
    payload = AddBookPayload(sourceUrl=BOOK_URL, bookKind="长小说", language="中文")

    result = await scraper.download_book(payload, preview, tmp_path)
    manifest = json.loads((result.local_path / "manifest.json").read_text(encoding="utf-8"))

    assert fetched_urls == [
        "https://fanqienovel.com/reader/10001",
        "https://fanqienovel.com/reader/10002",
    ]
    assert [item["downloaded"] for item in manifest["chapters"]] == [True, True]
    assert manifest["chapters"][0]["content_source"] == "web_initial_state"
    assert manifest["chapters"][1]["access_restricted"] is True
    assert (result.local_path / manifest["chapters"][1]["file_name"]).exists()


@pytest.mark.asyncio
async def test_initial_import_keeps_failed_restricted_chapter_pending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def fake_fetch(_: object, url: str, title: str = "") -> scraper.ChapterFetchResult:
        if url.endswith("10002"):
            raise ValueError("番茄 APP 全文接口暂时不可用")
        return scraper.ChapterFetchResult(text=f"{title}完整正文", image_urls=[])

    monkeypatch.setattr(scraper, "_fetch_chapter_data", fake_fetch)
    monkeypatch.setattr(scraper, "_load_runtime_settings", TranslationSettings)
    preview = PreviewResponse(
        title="测试小说",
        chapterCount=2,
        chapters=[
            ChapterPreview(title="公开章", url="https://fanqienovel.com/reader/10001"),
            ChapterPreview(
                title="受限章",
                url="https://fanqienovel.com/reader/10002",
                accessRestricted=True,
            ),
        ],
        bookKind="长小说",
    )

    result = await scraper.download_book(
        AddBookPayload(sourceUrl=BOOK_URL, bookKind="长小说", language="中文"),
        preview,
        tmp_path,
    )
    manifest = json.loads((result.local_path / "manifest.json").read_text(encoding="utf-8"))

    restricted = manifest["chapters"][1]
    assert restricted["downloaded"] is False
    assert restricted["download_error"] == "番茄 APP 全文接口暂时不可用"
    assert not (result.local_path / restricted["file_name"]).exists()


@pytest.mark.asyncio
async def test_on_demand_import_only_writes_chapter_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def reject_chapter_fetch(*_: object, **__: object) -> None:
        pytest.fail("边看边下导入阶段不应抓取章节正文")

    monkeypatch.setattr(scraper, "_fetch_chapter_data", reject_chapter_fetch)
    preview = PreviewResponse(
        title="超长测试小说",
        chapterCount=2,
        chapters=[
            ChapterPreview(title="第一章", url="https://fanqienovel.com/reader/10001"),
            ChapterPreview(title="第二章", url="https://fanqienovel.com/reader/10002"),
        ],
        bookKind="长小说",
    )
    payload = AddBookPayload(
        sourceUrl=BOOK_URL,
        bookKind="长小说",
        language="中文",
        downloadMode="on_demand",
    )

    result = await scraper.create_book_manifest_only(payload, preview, tmp_path)
    manifest = json.loads((result.local_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["download_mode"] == "on_demand"
    assert [chapter["downloaded"] for chapter in manifest["chapters"]] == [False, False]
    assert not list(result.local_path.glob("*.txt"))


@pytest.mark.asyncio
async def test_fanqie_network_retries_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        status = 503 if attempts < 3 else 200
        return httpx.Response(status, request=request, text=_book_html() if status == 200 else "busy")

    async def no_wait(_: object) -> None:
        return None

    monkeypatch.setattr(scraper, "_throttle_fanqie_request", no_wait)
    monkeypatch.setattr(scraper.asyncio, "sleep", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await scraper._get_fanqie_html_response(client, BOOK_URL)

    assert response.status_code == 200
    assert attempts == scraper.FANQIE_MAX_RETRIES


@pytest.mark.asyncio
async def test_fanqie_network_rejects_cross_site_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, request=request, headers={"Location": "http://127.0.0.1/private"})

    async def no_wait(_: object) -> None:
        return None

    monkeypatch.setattr(scraper, "_throttle_fanqie_request", no_wait)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="不受信任"):
            await scraper._get_fanqie_html_response(client, BOOK_URL)
