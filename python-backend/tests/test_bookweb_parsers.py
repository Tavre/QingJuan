from __future__ import annotations

import json
from io import BytesIO

import httpx
import pytest
from PIL import Image, ImageDraw

from app import scraper
from app.kakuyomu_parser import parse_kakuyomu_episode_page, parse_kakuyomu_work_response
from app.models import AddBookPayload
from app.yanmaga_parser import (
    descramble_yanmaga_image,
    parse_yanmaga_book_page,
    parse_yanmaga_episode_fragment,
    yanmaga_resource_from_url,
)


def _kakuyomu_graphql_payload() -> dict:
    return {
        "data": {
            "work": {
                "id": "1177354054882739112",
                "title": "测试作品",
                "catchphrase": "一句话简介",
                "introduction": "完整简介",
                "adminCoverImageUrl": "https://cdn.example.test/cover.jpg",
                "author": {
                    "id": "author-1",
                    "name": "作者名",
                    "activityName": "活动名",
                    "screenName": "author",
                },
                "tableOfContentsV2": [
                    {
                        "id": "toc-1",
                        "chapter": {"id": "chapter-1", "level": 1, "title": "第一部"},
                        "episodeUnions": [
                            {"__typename": "Episode", "id": "101", "title": "第一话"},
                            {"__typename": "EmptyEpisode", "id": "102", "title": "未公开"},
                        ],
                    }
                ],
            }
        }
    }


def test_kakuyomu_graphql_payload_builds_public_catalog() -> None:
    work = parse_kakuyomu_work_response(_kakuyomu_graphql_payload(), "1177354054882739112")

    assert work.title == "测试作品"
    assert work.author == "活动名"
    assert work.synopsis == "一句话简介\n\n完整简介"
    assert work.cover == "https://cdn.example.test/cover.jpg"
    assert [(episode.id, episode.title) for episode in work.episodes] == [
        ("101", "第一部 - 第一话")
    ]


def test_kakuyomu_episode_parser_preserves_blank_lines_ruby_and_images() -> None:
    parsed = parse_kakuyomu_episode_page(
        """
        <div class="widget-episodeBody js-episode-body">
          <p>　<ruby><rb>橋本</rb><rp>（</rp><rt>はしもと</rt><rp>）</rp></ruby></p>
          <p class="blank"><br></p>
          <p>次の段落<img data-src="/images/illustration.jpg"></p>
        </div>
        """
    )

    assert parsed.text == "　橋本（はしもと）\n\n次の段落"
    assert parsed.image_sources == ("/images/illustration.jpg",)


@pytest.mark.asyncio
async def test_kakuyomu_preview_uses_graphql_api(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_kakuyomu_graphql_payload())

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )

    result = await scraper._preview_kakuyomu(
        "https://kakuyomu.jp/works/1177354054882739112",
        AddBookPayload(
            sourceUrl="https://kakuyomu.jp/works/1177354054882739112",
            bookKind="轻小说",
            language="日文",
        ),
    )

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url == httpx.URL("https://kakuyomu.jp/graphql")
    assert json.loads(requests[0].content)["operationName"] == "GetQingJuanWork"
    assert result.title == "测试作品"
    assert result.chapters[0].url.endswith("/works/1177354054882739112/episodes/101")


def _yanmaga_book_html() -> str:
    return """
    <h1 class="detailv2-outline-title">测试漫画</h1>
    <ul class="detailv2-outline-author"><li><a>作者甲</a></li></ul>
    <p class="detailv2-description">作品简介</p>
    <div class="detailv2-thumbnail-image"><img src="/cover.jpg"></div>
    <div id="contents" data-count="3"></div>
    <ul class="mod-episode-list">
      <li class="mod-episode-item" data-episode-title="第一话" data-is-free="false"
          data-original-url="/comics/Test/e1" data-modal="registration">
        <span class="mod-episode-point--free">無料</span>
      </li>
    </ul>
    <ul class="mod-episode-list mod-episode-list--close"></ul>
    <button class="mod-episode-more-button" data-offset="1" data-path="/comics/Test/episodes"></button>
    """


def _yanmaga_fragment() -> str:
    return """
    <li class="mod-episode-item" data-episode-title="第二话" data-is-free="true"
        data-original-url="/comics/Test/e2" data-modal="registration">
      <span class="mod-episode-point--free">初回無料</span>
    </li>
    <li class="mod-episode-item" data-episode-title="第三话" data-is-free="true"
        data-original-url="/comics/Test/e3">
      <span class="mod-episode-point--free">無料</span>
    </li>
    """


def test_yanmaga_page_parser_preserves_access_boundary() -> None:
    page = parse_yanmaga_book_page(_yanmaga_book_html(), "https://yanmaga.jp/comics/Test")
    fragment = parse_yanmaga_episode_fragment(_yanmaga_fragment(), "Test")

    assert page.title == "测试漫画"
    assert page.author == "作者甲"
    assert page.cover == "https://yanmaga.jp/cover.jpg"
    assert page.episode_count == 3
    assert page.episodes[0].publicly_readable is True
    assert page.next_path == "/comics/Test/episodes"
    assert fragment[0].publicly_readable is False
    assert "单次免费" in (fragment[0].restriction or "")
    assert fragment[1].publicly_readable is True
    assert yanmaga_resource_from_url("https://yanmaga.jp/comics/Test/e3") == ("Test", "e3")


@pytest.mark.asyncio
async def test_yanmaga_preview_keeps_all_catalog_episodes(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/comics/Test":
            return httpx.Response(200, text=_yanmaga_book_html())
        if request.url.path == "/comics/Test/episodes":
            assert request.headers["X-Requested-With"] == "XMLHttpRequest"
            return httpx.Response(200, text=_yanmaga_fragment())
        raise AssertionError(f"unexpected request: {request.url}")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )

    result = await scraper._preview_yanmaga(
        "https://yanmaga.jp/comics/Test",
        AddBookPayload(
            sourceUrl="https://yanmaga.jp/comics/Test",
            bookKind="漫画",
            language="日文",
        ),
    )

    assert result.bookKind == "漫画"
    assert [chapter.title for chapter in result.chapters] == ["第一话", "第二话", "第三话"]
    assert [chapter.url for chapter in result.chapters] == [
        "https://yanmaga.jp/comics/Test/e1",
        "https://yanmaga.jp/comics/Test/e2",
        "https://yanmaga.jp/comics/Test/e3",
    ]
    assert [chapter.accessRestricted for chapter in result.chapters] == [False, True, False]


def _synthetic_scrambled_page() -> bytes:
    image = Image.new("RGB", (400, 400))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 199, 199), fill=(0, 255, 0))
    draw.rectangle((200, 0, 399, 199), fill=(255, 0, 0))
    draw.rectangle((0, 200, 199, 399), fill=(255, 255, 0))
    draw.rectangle((200, 200, 399, 399), fill=(0, 0, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_yanmaga_speedbinb_restores_page_tiles() -> None:
    restored_bytes = descramble_yanmaga_image(
        _synthetic_scrambled_page(),
        "=2-2-0-ABABABCD",
        "=2-2+0-ABABBADC",
    )

    with Image.open(BytesIO(restored_bytes)) as restored:
        assert restored.size == (400, 400)
        assert restored.getpixel((100, 100))[0] > 240
        assert restored.getpixel((300, 100))[1] > 240
        assert restored.getpixel((100, 300))[2] > 240
        bottom_right = restored.getpixel((300, 300))
        assert bottom_right[0] > 240 and bottom_right[1] > 240


@pytest.mark.asyncio
async def test_yanmaga_chapter_registers_public_viewer_pages(monkeypatch) -> None:
    viewer_url = "https://yanmaga.jp/viewer/comics/Test/e1?cid=CID123"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/comics/Test/e1":
            return httpx.Response(302, headers={"Location": viewer_url})
        if request.url.path == "/viewer/bibGetCntntInfo":
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "items": [
                        {
                            "ServerType": 2,
                            "ContentsServer": "https://sbc.yanmaga.jp/books/test/1",
                            "ContentDate": "20260816",
                            "ctbl": "content-table",
                            "ptbl": "position-table",
                        }
                    ],
                },
            )
        if request.url.path == "/books/test/1/content":
            return httpx.Response(
                200,
                json={
                    "ContentDate": "20260816",
                    "ttx": "<t-case><t-img src='pages/001.jpg'/></t-case>",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    monkeypatch.setattr(scraper, "speedbinb_request_key", lambda *_: "request-key")
    monkeypatch.setattr(
        scraper,
        "decode_speedbinb_table",
        lambda _cid, _key, encrypted: (
            ["=2-2+0-ABABBADC"] * 8
            if encrypted == "content-table"
            else ["=2-2-0-ABABABCD"] * 8
        ),
    )
    scraper._YANMAGA_PAGE_KEYS.clear()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = await scraper._fetch_yanmaga_chapter_data(
            client,
            "https://yanmaga.jp/comics/Test/e1",
            "第一话",
        )

    assert result.content_source == "yanmaga_viewer"
    assert result.authorization_method == "upstream-viewer"
    assert len(result.image_urls) == 1
    image_url = result.image_urls[0]
    assert image_url.startswith("https://sbc.yanmaga.jp/books/test/1/img/pages/001.jpg?")
    assert scraper._YANMAGA_PAGE_KEYS[image_url][2] == viewer_url


@pytest.mark.asyncio
async def test_yanmaga_chapter_rejects_non_viewer_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="registration required")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="未向匿名访问跳转"):
            await scraper._fetch_yanmaga_chapter_data(
                client,
                "https://yanmaga.jp/comics/Test/restricted",
                "受限章节",
            )
