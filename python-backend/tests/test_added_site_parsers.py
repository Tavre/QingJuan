from __future__ import annotations

import base64

import httpx
import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from app import scraper
from app.models import AddBookPayload, BookSourceRecord
from app.site_plugins import ciweimao_client, ehentai_client, sfacg_client, shaoniandream_client


def _encrypted_blob(value: bytes, key: bytes, iv: bytes) -> bytes:
    return iv + AES.new(key, AES.MODE_CBC, iv).encrypt(pad(value, 16))


def test_ciweimao_parses_book_catalogue_and_search() -> None:
    book_html = """
    <meta property="og:novel:book_name" content="测试轻小说">
    <meta property="og:novel:author" content="作者甲">
    <meta property="og:description" content="作品简介">
    <meta property="og:image" content="https://img.test/cover.jpg">
    """
    catalogue_html = """
    <div class="book-chapter-box">
      <h4 class="sub-tit">第一卷</h4>
      <li><a href="/chapter/11">序章</a></li>
      <li class="vip"><a href="/chapter/12">付费章</a></li>
    </div>
    """
    search_html = """
    <li data-book-id="1"><a href="/book/1"><img data-original="/cover.jpg"></a>
      <h3 class="title"><a href="/book/1">测试轻小说</a></h3>
      <a href="/reader/9">作者甲</a><div class="desc">作品简介</div>
    </li>
    """

    book = ciweimao_client.parse_book_page(book_html, "1")
    chapters = ciweimao_client.parse_catalogue(catalogue_html, "1")
    results = ciweimao_client.parse_search_page(search_html)

    assert book["title"] == "测试轻小说"
    assert [item["title"] for item in chapters] == ["第一卷 · 序章", "第一卷 · 付费章"]
    assert chapters[1]["access_restricted"] is True
    assert results[0]["url"] == "https://www.ciweimao.com/book/1"


@pytest.mark.asyncio
async def test_ciweimao_decrypts_public_chapter() -> None:
    keys = [b"0123456789abcdef", b"fedcba9876543210"]
    encoded_keys = [base64.b64encode(item).decode() for item in keys]
    access_key = "AB"
    inner = _encrypted_blob("<p>第一段<span>水印</span></p><p>第二段</p>".encode(), keys[1], b"1" * 16)
    outer = _encrypted_blob(base64.b64encode(inner), keys[0], b"2" * 16)

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ajax_get_session_code"):
            return httpx.Response(200, json={"chapter_access_key": access_key}, request=request)
        if request.url.path.endswith("/get_book_chapter_detail_info"):
            return httpx.Response(
                200,
                json={
                    "code": 100000,
                    "chapter_content": base64.b64encode(outer).decode(),
                    "encryt_keys": encoded_keys,
                },
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        text = await ciweimao_client.get_chapter(client, "11")

    assert text == "第一段\n\n第二段"


def test_shaoniandream_parses_book_catalogue_and_search() -> None:
    book_html = """
    <div class="bookdetail-name"><span class="title">少年梦作品</span>
      <span class="penName"><a href="/author/index/id/7">作者乙</a></span></div>
    <div class="bookdetail-top"><div class="cover"><img src="/cover.png"></div></div>
    <div class="bookdetial-jianjie">作品简介</div>
    """
    catalogue = {
        "readdir": [
            {
                "title": "正文卷",
                "list": [
                    {"id": 21, "title": "第一章", "isFree": 1},
                    {"id": 22, "title": "订阅章", "isFree": 0},
                ],
            }
        ]
    }
    search_html = """
    <div class="BookPicList"><ul><li><dl>
      <dd class="img"><img src="/s.jpg"></dd>
      <dd class="title"><a href="/book_detail/3490" title="少年梦作品">作品</a></dd>
      <dd class="author"><a href="/author/index/id/7">作者乙</a> / 奇幻 / 连载</dd>
      <dd class="jianjie">作品简介</dd>
    </dl></li></ul></div>
    """

    book = shaoniandream_client.parse_book_page(book_html, "3490")
    chapters = shaoniandream_client.parse_catalogue(catalogue, "3490")
    results = shaoniandream_client.parse_search_page(search_html)

    assert book["author"] == "作者乙"
    assert chapters[0]["url"].endswith("/readchapter/21")
    assert chapters[1]["access_restricted"] is True
    assert results[0]["title"] == "少年梦作品"


@pytest.mark.asyncio
async def test_shaoniandream_decrypts_public_chapter() -> None:
    key = b"0123456789abcdef0123456789abcdef"
    iv = b"abcdef0123456789"
    encrypted = base64.b64encode(
        AES.new(key, AES.MODE_CBC, iv).encrypt(pad("正文段落".encode(), 16))
    ).decode()

    def transport(request: httpx.Request) -> httpx.Response:
        if "membersinglechaptersign" in request.url.path:
            return httpx.Response(200, json={"data": {"chapter_access_key": "access"}}, request=request)
        if "membersinglechapter" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "status": 1,
                    "data": {
                        "encryt_keys": [
                            base64.b64encode(key.decode().encode()).decode(),
                            base64.b64encode(iv.decode().encode()).decode(),
                        ],
                        "show_content": [{"content": encrypted}],
                    },
                },
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        text = await shaoniandream_client.get_chapter(client, "21")

    assert text == "正文段落"


@pytest.mark.asyncio
async def test_sfacg_signed_api_maps_book_catalogue_search_and_chapter() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == sfacg_client.SFACG_BASIC_AUTH
        assert set(item.split("=", 1)[0] for item in request.headers["sfsecurity"].split("&")) == {
            "nonce",
            "timestamp",
            "devicetoken",
            "sign",
        }
        if request.url.path == "/novels/465469":
            data = {
                "novelId": 465469,
                "novelName": "SF 测试作品",
                "authorName": "作者丙",
                "novelCover": "https://img.test/sf.jpg",
                "expand": {"intro": "作品简介"},
            }
        elif request.url.path == "/novels/465469/dirs":
            data = {
                "volumeList": [
                    {
                        "title": "第一卷",
                        "chapterList": [
                            {"chapId": 31, "title": "第一章", "isVip": False},
                            {"chapId": 32, "title": "VIP章", "isVip": True},
                        ],
                    }
                ]
            }
        elif request.url.path == "/search/novels/result":
            data = {"novels": [{"novelId": 465469, "novelName": "SF 测试作品"}]}
        elif request.url.path == "/Chaps/31":
            data = {"expand": {"content": "章节正文"}}
        else:
            raise AssertionError(f"unexpected request: {request.url}")
        return httpx.Response(200, json={"status": {"httpCode": 200}, "data": data}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        book = sfacg_client.normalize_book(await sfacg_client.get_book(client, "465469"))
        chapters = await sfacg_client.get_catalogue(client, "465469")
        results = await sfacg_client.search_books(client, "测试")
        content = await sfacg_client.get_chapter(client, "31")

    assert book["author"] == "作者丙"
    assert book["synopsis"] == "作品简介"
    assert chapters[1]["access_restricted"] is True
    assert results[0]["url"].endswith("/Novel/465469/")
    assert content == "章节正文"


def test_ehentai_parses_search_and_gallery_pages() -> None:
    search_html = """
    <table class="itg"><tr>
      <td class="gl1c"><div class="cn">Manga</div></td>
      <td><img src="https://ehgt.test/thumb.webp"></td>
      <td class="gl3c"><a href="/g/123/0123456789/"><div class="glink">测试画廊</div>
        <div class="gt" title="language:chinese">中文</div></a></td>
    </tr></table>
    """
    gallery_html = """
    <div id="gdd"><table><tr><td>Length:</td><td>2 pages</td></tr></table></div>
    <div id="gdn"><a href="/uploader/tester">tester</a></div>
    <div id="gd5"><p class="gsp">Report Gallery</p><p>画廊说明</p></div>
    <a href="/s/aaaaaaaaaa/123-1">1</a><a href="/s/bbbbbbbbbb/123-2">2</a>
    """

    results = ehentai_client.parse_search_page(search_html, "https://e-hentai.org")
    gallery = ehentai_client.parse_gallery_page(gallery_html, "123", "https://e-hentai.org")

    assert results[0]["url"] == "https://e-hentai.org/g/123/0123456789/"
    assert gallery["filecount"] == 2
    assert gallery["description"] == "画廊说明"
    assert [item["page"] for item in gallery["pages"]] == [1, 2]


@pytest.mark.asyncio
async def test_ehentai_preview_search_and_gallery_images(monkeypatch) -> None:
    gallery_html = """
    <div id="gdd"><table><tr><td>Length:</td><td>2 pages</td></tr></table></div>
    <div id="gd5"><p>画廊说明</p></div>
    <a href="/s/aaaaaaaaaa/123-1">1</a><a href="/s/bbbbbbbbbb/123-2">2</a>
    """

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.e-hentai.org":
            return httpx.Response(
                200,
                json={
                    "gmetadata": [
                        {
                            "gid": 123,
                            "token": "0123456789",
                            "title": "测试画廊",
                            "uploader": "tester",
                            "thumb": "https://ehgt.test/cover.webp",
                            "filecount": "2",
                            "category": "Manga",
                            "tags": ["language:chinese"],
                        }
                    ]
                },
                request=request,
            )
        if request.url.path == "/g/123/0123456789/":
            return httpx.Response(200, text=gallery_html, request=request)
        if request.url.path == "/s/aaaaaaaaaa/123-1":
            return httpx.Response(200, text='<img id="img" src="https://cdn.test/1.webp">', request=request)
        if request.url.path == "/s/bbbbbbbbbb/123-2":
            return httpx.Response(200, text='<img id="img" src="https://cdn.test/2.webp">', request=request)
        raise AssertionError(f"unexpected request: {request.url}")

    transport_instance = httpx.MockTransport(transport)
    monkeypatch.setattr(
        scraper,
        "_build_http_client",
        lambda: httpx.AsyncClient(transport=transport_instance, follow_redirects=True),
    )
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda _plugin_id: True)

    preview = await scraper.preview_from_url(
        AddBookPayload(
            sourceUrl="https://e-hentai.org/g/123/0123456789/",
            bookKind="漫画",
            language="日文",
        )
    )
    async with httpx.AsyncClient(transport=transport_instance) as client:
        chapter = await scraper._fetch_chapter_data(
            client,
            "https://e-hentai.org/g/123/0123456789/",
            "测试画廊",
        )

    assert preview.title == "测试画廊"
    assert preview.chapters[0].pageCount == 2
    assert chapter.image_urls == ["https://cdn.test/1.webp", "https://cdn.test/2.webp"]
    assert chapter.content_source == "ehentai-public-gallery"
    assert scraper._EHENTAI_IMAGE_REFERERS["https://cdn.test/1.webp"].endswith("/s/aaaaaaaaaa/123-1")


@pytest.mark.asyncio
async def test_new_builtin_sources_use_their_search_handlers(monkeypatch) -> None:
    async def fake_search(client: httpx.AsyncClient, keyword: str):
        return [
            {
                "title": f"{keyword}作品",
                "author": "作者",
                "synopsis": "简介",
                "cover": None,
                "url": "https://www.ciweimao.com/book/1",
            }
        ]

    monkeypatch.setattr(scraper, "search_ciweimao_books", fake_search)
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda _plugin_id: True)
    source = BookSourceRecord(
        id="source-builtin-ciweimao",
        name="刺猬猫阅读",
        baseUrl="https://www.ciweimao.com",
        bookKind="轻小说",
        language="中文",
        origin="builtin",
    )

    results = await scraper.search_builtin_site_books(source, "测试")

    assert results[0].title == "测试作品"
    assert results[0].sourceUrl == "https://www.ciweimao.com/book/1"
