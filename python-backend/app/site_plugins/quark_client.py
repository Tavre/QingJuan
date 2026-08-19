from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import hashlib
import html
import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

QUARK_WEB_ORIGIN = "https://www.shuqi.com"
QUARK_RENDER_SEARCH_URL = "https://render.shuqireader.com/render/search"
QUARK_BOOK_INFO_URL = "https://content.shuqireader.com/xapi/book/info"
QUARK_RENDER_SKEY = "asdiof9ad8f02587djkb895d0q3422"
QUARK_CONTENT_SKEY = "37e81a9d8f02596e1b895d07c171d5c9"
QUARK_ANONYMOUS_USER_ID = "8000000"
QUARK_PAGE_MIN_INTERVAL_SECONDS = 5.0
QUARK_CATALOG_CACHE_SECONDS = 180.0
_QUARK_TRANSIENT_PAGE_STATUSES = frozenset({429, 502, 503, 504})
QUARK_BOOK_PATH = re.compile(r"^/book/(?P<book_id>\d+)(?:\.html)?/?$", re.IGNORECASE)
_PAGE_DATA_RE = re.compile(
    r'class=["\'][^"\']*\bjs-dataChapters\b[^"\']*["\'][^>]*>(.*?)</i>',
    re.IGNORECASE | re.DOTALL,
)
_last_page_request_at = 0.0
_page_request_lock = asyncio.Lock()
_catalog_fetch_lock = asyncio.Lock()
_catalog_cache: dict[
    str,
    tuple[float, dict[str, Any], list[dict[str, Any]]],
] = {}


class QuarkBookError(ValueError):
    pass


def clear_quark_catalog_cache() -> None:
    """Clear the public catalog cache; primarily used by deterministic tests."""
    _catalog_cache.clear()


def _cached_quark_catalog(
    book_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    cached = _catalog_cache.get(book_id)
    if cached is None:
        return None
    expires_at, chapters_info, chapters = cached
    if expires_at <= time.monotonic():
        _catalog_cache.pop(book_id, None)
        return None
    return copy.deepcopy(chapters_info), copy.deepcopy(chapters)


def _make_sign_only_value(params: dict[str, Any], skey: str) -> str:
    values = "".join(str(params[key]) for key in sorted(params))
    return hashlib.md5(f"{values}{skey}".encode(), usedforsecurity=False).hexdigest()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _plain_text(value: Any) -> str:
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def _https_url(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://"):
        return f"https://{url.removeprefix('http://')}"
    return url if url.startswith("https://") else None


def _is_quark_web_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (host == "shuqi.com" or host.endswith(".shuqi.com"))


def _is_free_content_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme == "https"
        and (host == "shuqireader.com" or host.endswith(".shuqireader.com"))
        and parsed.path.startswith("/pcapi/chapter/contentfree/")
    )


def canonical_quark_book_url(book_id: str) -> str:
    normalized = str(book_id).strip()
    if not normalized.isdigit():
        raise QuarkBookError("夸克小说作品编号无效")
    return f"{QUARK_WEB_ORIGIN}/book/{normalized}.html"


def canonical_quark_chapter_url(book_id: str, chapter_id: str) -> str:
    normalized_book_id = str(book_id).strip()
    normalized_chapter_id = str(chapter_id).strip()
    if not normalized_book_id.isdigit() or not normalized_chapter_id.isdigit():
        raise QuarkBookError("夸克小说章节编号无效")
    return f"{QUARK_WEB_ORIGIN}/reader?{urlencode({'bid': normalized_book_id, 'cid': normalized_chapter_id})}"


def quark_book_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    match = QUARK_BOOK_PATH.match(parsed.path)
    if match:
        return match.group("book_id")
    book_id = parse_qs(parsed.query).get("bid", [""])[0].strip()
    return book_id if book_id.isdigit() else None


def quark_chapter_ids_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    book_id = query.get("bid", [""])[0].strip()
    chapter_id = query.get("cid", [""])[0].strip()
    if parsed.path.rstrip("/").lower() != "/reader":
        return None
    if not book_id.isdigit() or not chapter_id.isdigit():
        return None
    return book_id, chapter_id


async def _response_json(response: httpx.Response, stage: str) -> dict[str, Any]:
    if response.status_code == 429:
        raise QuarkBookError(f"夸克小说{stage}请求过于频繁，请稍后重试")
    if response.status_code >= 400:
        raise QuarkBookError(f"夸克小说{stage}请求失败（HTTP {response.status_code}）")
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuarkBookError(f"夸克小说{stage}返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise QuarkBookError(f"夸克小说{stage}返回格式异常")
    return payload


async def search_quark_books(
    client: httpx.AsyncClient,
    keyword: str,
    limit: int,
) -> list[dict[str, Any]]:
    query = keyword.strip()
    if not query:
        return []
    page_size = max(1, min(limit, 50))
    params = json.dumps(
        {
            "page": "simpleSearch",
            "pagination": {"page": 1, "pageSize": page_size},
            "query": query,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fields: dict[str, Any] = {
        "timeStamp": str(int(time.time())),
        "userId": QUARK_ANONYMOUS_USER_ID,
        "params": params,
    }
    fields["sign"] = _make_sign_only_value(fields, QUARK_RENDER_SKEY)
    fields.update(
        {
            "sn": "",
            "imei": "",
            "appVer": "",
            "ver": "",
            "uid": "",
            "utdid": "",
            "platform": "1",
        }
    )
    try:
        response = await client.post(
            QUARK_RENDER_SEARCH_URL,
            data=fields,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise QuarkBookError("夸克小说搜索请求失败") from exc
    payload = await _response_json(response, "搜索")
    if payload.get("status") is not None and str(payload.get("status")) != "200":
        raise QuarkBookError("夸克小说搜索返回业务错误")
    data = payload.get("data")
    modules = data.get("modulesInfos") if isinstance(data, dict) else None
    if not isinstance(modules, list):
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for module in modules:
        item = module.get("data") if isinstance(module, dict) else None
        if not isinstance(item, dict):
            continue
        book_id = str(item.get("bookId") or "").strip()
        title = _plain_text(item.get("bookName") or item.get("displayBookName"))
        if not book_id.isdigit() or not title or book_id in seen:
            continue
        seen.add(book_id)
        results.append(
            {
                "bookId": book_id,
                "title": title,
                "author": _plain_text(item.get("authorName") or item.get("displayAuthorName")),
                "synopsis": _plain_text(item.get("desc")),
                "cover": _https_url(item.get("imgUrl")),
                "sourceUrl": canonical_quark_book_url(book_id),
            }
        )
        if len(results) >= limit:
            break
    return results


async def get_quark_book_info(
    client: httpx.AsyncClient,
    book_id: str,
) -> dict[str, Any]:
    normalized = str(book_id).strip()
    if not normalized.isdigit():
        raise QuarkBookError("夸克小说作品编号无效")
    fields: dict[str, Any] = {
        "timestamp": str(int(time.time())),
        "bookIds": json.dumps([normalized], ensure_ascii=False),
    }
    fields["sign"] = _make_sign_only_value(fields, QUARK_CONTENT_SKEY)
    try:
        response = await client.post(
            QUARK_BOOK_INFO_URL,
            data=fields,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise QuarkBookError("夸克小说作品信息请求失败") from exc
    payload = await _response_json(response, "作品信息")
    if str(payload.get("state")) != "200":
        raise QuarkBookError("夸克小说作品信息返回业务错误")
    data = payload.get("data")
    item = data.get(normalized) if isinstance(data, dict) else None
    if not isinstance(item, dict):
        raise QuarkBookError("未找到夸克小说作品信息")
    return item


def parse_quark_reader_page(html_text: str) -> dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    tag = soup.select_one("i.page-data.js-dataChapters")
    raw = tag.get_text() if tag is not None else ""
    if not raw:
        match = _PAGE_DATA_RE.search(html_text)
        raw = match.group(1) if match else ""
    if not raw:
        raise QuarkBookError("夸克小说阅读页缺少目录数据")
    try:
        parsed = json.loads(html.unescape(raw))
    except json.JSONDecodeError as exc:
        raise QuarkBookError("夸克小说阅读页目录数据无效") from exc
    if not isinstance(parsed, dict):
        raise QuarkBookError("夸克小说阅读页目录格式异常")
    return parsed


def flatten_quark_chapters(chapters_info: dict[str, Any]) -> list[dict[str, Any]]:
    volumes = chapters_info.get("chapterList")
    if not isinstance(volumes, list):
        return []
    chapters: list[dict[str, Any]] = []
    for volume in volumes:
        if not isinstance(volume, dict):
            continue
        raw_items = volume.get("volumeList")
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            chapter_id = str(raw_item.get("chapterId") or "").strip()
            if not chapter_id.isdigit():
                continue
            chapters.append({**raw_item, "_index": len(chapters) + 1})
    return chapters


def quark_chapter_is_public(chapter: dict[str, Any]) -> bool:
    return _truthy(chapter.get("isFreeRead"))


async def _throttle_reader_page() -> None:
    global _last_page_request_at
    async with _page_request_lock:
        wait = _last_page_request_at + QUARK_PAGE_MIN_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_page_request_at = time.monotonic()


async def get_quark_catalog(
    client: httpx.AsyncClient,
    book_id: str,
    *,
    chapter_id: str = "0",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized_book_id = str(book_id).strip()
    normalized_chapter_id = str(chapter_id).strip()
    if not normalized_book_id.isdigit() or not normalized_chapter_id.isdigit():
        raise QuarkBookError("夸克小说作品或章节编号无效")
    cached = _cached_quark_catalog(normalized_book_id)
    if cached is not None:
        return cached

    async with _catalog_fetch_lock:
        cached = _cached_quark_catalog(normalized_book_id)
        if cached is not None:
            return cached

        response: httpx.Response | None = None
        for attempt in range(3):
            await _throttle_reader_page()
            try:
                response = await client.get(
                    f"{QUARK_WEB_ORIGIN}/reader",
                    # cid only selects the initially visible chapter. cid=0 keeps one
                    # reusable catalog request for preview, import, and on-demand reads.
                    params={"bid": normalized_book_id, "cid": "0"},
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise QuarkBookError("夸克小说目录请求失败") from exc
            if response.status_code not in _QUARK_TRANSIENT_PAGE_STATUSES:
                break
            if attempt < 2:
                delay = (
                    8 * (attempt + 1)
                    if response.status_code == 429
                    else 2 * (attempt + 1)
                )
                await asyncio.sleep(delay)
        if response is None or response.status_code == 429:
            raise QuarkBookError("夸克小说目录请求过于频繁，请稍后重试")
        if response.status_code >= 400:
            raise QuarkBookError(f"夸克小说目录请求失败（HTTP {response.status_code}）")
        if not _is_quark_web_url(str(response.url)):
            raise QuarkBookError("夸克小说目录请求跳转到了非官方网站")
        chapters_info = parse_quark_reader_page(response.text)
        if str(chapters_info.get("bookId") or normalized_book_id) != normalized_book_id:
            raise QuarkBookError("夸克小说目录返回的作品编号不匹配")
        chapters = flatten_quark_chapters(chapters_info)
        if not chapters:
            raise QuarkBookError("夸克小说作品目录为空")
        _catalog_cache[normalized_book_id] = (
            time.monotonic() + QUARK_CATALOG_CACHE_SECONDS,
            copy.deepcopy(chapters_info),
            copy.deepcopy(chapters),
        )
        return copy.deepcopy(chapters_info), copy.deepcopy(chapters)


def _free_content_url(
    chapters_info: dict[str, Any],
    chapter: dict[str, Any],
) -> str:
    if not quark_chapter_is_public(chapter):
        raise QuarkBookError("该夸克小说章节不是匿名免费章节，青卷不抓取付费或试读正文")
    prefix = str(chapters_info.get("freeContUrlPrefix") or "").strip()
    suffix = str(chapter.get("contUrlSuffix") or "").strip()
    url = f"{prefix}{suffix}"
    if not _is_free_content_url(url):
        raise QuarkBookError("夸克小说章节返回了非 HTTPS 或非官方免费正文地址")
    return url


def decode_quark_chapter_content(encoded: str) -> str:
    shifted: list[str] = []
    for character in encoded:
        if "a" <= character <= "z":
            shifted.append(chr((ord(character) - ord("a") + 13) % 26 + ord("a")))
        elif "A" <= character <= "Z":
            shifted.append(chr((ord(character) - ord("A") + 13) % 26 + ord("A")))
        else:
            shifted.append(character)
    cleaned = re.sub(r"[^A-Za-z0-9+/=]", "", "".join(shifted))
    try:
        decoded = base64.b64decode(cleaned).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise QuarkBookError("夸克小说章节正文还原失败") from exc
    normalized = re.sub(r"<br\s*/?>", "\n", html.unescape(decoded), flags=re.IGNORECASE)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized.replace("\r", "\n"))
    return normalized.strip()


async def get_quark_chapter_content(
    client: httpx.AsyncClient,
    book_id: str,
    chapter_id: str,
) -> dict[str, Any]:
    chapters_info, chapters = await get_quark_catalog(
        client,
        book_id,
        chapter_id=chapter_id,
    )
    chapter = next(
        (item for item in chapters if str(item.get("chapterId")) == str(chapter_id)),
        None,
    )
    if chapter is None:
        raise QuarkBookError("夸克小说目录中未找到该章节")
    content_url = _free_content_url(chapters_info, chapter)
    try:
        response = await client.get(content_url, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise QuarkBookError("夸克小说章节正文请求失败") from exc
    if not _is_free_content_url(str(response.url)):
        raise QuarkBookError("夸克小说章节正文请求跳转到了非官方地址")
    payload = await _response_json(response, "章节正文")
    if str(payload.get("state")) != "200":
        raise QuarkBookError("夸克小说章节正文返回业务错误")
    text = decode_quark_chapter_content(str(payload.get("ChapterContent") or ""))
    if not text:
        raise QuarkBookError("夸克小说章节正文为空")
    try:
        declared_length = int(chapter.get("wordCount") or 0)
    except (TypeError, ValueError):
        declared_length = 0
    actual_length = len(re.sub(r"\s+", "", text))
    if declared_length >= 80 and actual_length < max(20, int(declared_length * 0.3)):
        raise QuarkBookError("夸克小说免费章节正文疑似不完整，请稍后重试")
    return {
        "text": text,
        "chapter": chapter,
    }
