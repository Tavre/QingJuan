from __future__ import annotations

import hashlib
import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

SFACG_API_ORIGIN = "https://api.sfacg.com"
SFACG_BOOK_ORIGIN = "https://book.sfacg.com"
SFACG_BASIC_AUTH = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
SFACG_APP_VERSION = "4.8.42(android;25)"
SFACG_CHANNEL = "HomePage"
SFACG_APP_KEY = "FMLxgOdsfxmN!Dt4"
BOOK_PATH_PATTERNS = (
    re.compile(r"^/Novel/(\d+)(?:/|$)", re.IGNORECASE),
    re.compile(r"^/novels/(\d+)(?:/|$)", re.IGNORECASE),
)
CHAPTER_PATH_PATTERN = re.compile(r"^/Novel/(\d+)/(\d+)(?:/|$)", re.IGNORECASE)


def book_id_from_url(url: str) -> str | None:
    path = urlparse(url).path
    for pattern in BOOK_PATH_PATTERNS:
        match = pattern.match(path)
        if match:
            return match.group(1)
    return None


def chapter_ids_from_url(url: str) -> tuple[str, str] | None:
    match = CHAPTER_PATH_PATTERN.match(urlparse(url).path)
    return (match.group(1), match.group(2)) if match else None


def canonical_book_url(novel_id: str | int) -> str:
    return f"{SFACG_BOOK_ORIGIN}/Novel/{novel_id}/"


def canonical_chapter_url(novel_id: str | int, chapter_id: str | int) -> str:
    return f"{SFACG_BOOK_ORIGIN}/Novel/{novel_id}/{chapter_id}/"


def _security_headers() -> dict[str, str]:
    nonce = str(uuid.uuid4()).upper()
    timestamp = int(time.time() * 1000)
    device_token = str(uuid.uuid4()).upper()
    source = f"{nonce}{timestamp}{device_token}{SFACG_APP_KEY}"
    signature = hashlib.md5(source.encode("utf-8")).hexdigest().upper()
    security = f"nonce={nonce}&timestamp={timestamp}&devicetoken={device_token}&sign={signature}"
    return {
        "Accept": "application/vnd.sfacg.api+json;version=1",
        "Accept-Charset": "UTF-8",
        "Authorization": SFACG_BASIC_AUTH,
        "User-Agent": f"boluobao/{SFACG_APP_VERSION}/{SFACG_CHANNEL}/{device_token.lower()}",
        "SFSecurity": security,
    }


async def _request(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    last_message = "SF 轻小说上游请求失败"
    for attempt in range(3):
        response = await client.get(
            f"{SFACG_API_ORIGIN}{path}",
            params=params,
            headers=_security_headers(),
        )
        try:
            payload = response.json()
        except ValueError as exc:
            response.raise_for_status()
            raise ValueError("SF 轻小说返回了无效 JSON") from exc
        status = payload.get("status") if isinstance(payload, dict) else None
        code = (
            int(status.get("httpCode") or response.status_code)
            if isinstance(status, dict)
            else response.status_code
        )
        last_message = (
            str(status.get("msg") or f"HTTP {code}") if isinstance(status, dict) else f"HTTP {code}"
        )
        if code == 417 and attempt < 2:
            continue
        if code != 200:
            if code in {401, 403}:
                raise ValueError(f"SF 轻小说章节需要登录且账号须有访问权限：{last_message}")
            raise ValueError(f"SF 轻小说上游错误：{last_message}")
        return payload.get("data", payload) if isinstance(payload, dict) else payload
    raise ValueError(last_message)


async def get_book(client: httpx.AsyncClient, novel_id: str) -> dict[str, Any]:
    expand = (
        "chapterCount,bigBgBanner,bigNovelCover,typeName,intro,fav,ticket,pointCount,"
        "tags,sysTags,signlevel,discount,discountExpireDate,totalNeedFireMoney,"
        "firstchapter,latestchapter"
    )
    data = await _request(client, f"/novels/{novel_id}", params={"expand": expand})
    if not isinstance(data, dict):
        raise ValueError("SF 轻小说作品响应格式无效")
    return data


async def get_catalogue(client: httpx.AsyncClient, novel_id: str) -> list[dict[str, Any]]:
    data = await _request(
        client,
        f"/novels/{novel_id}/dirs",
        params={"expand": "originNeedFireMoney"},
    )
    if not isinstance(data, dict):
        raise ValueError("SF 轻小说目录响应格式无效")
    chapters: list[dict[str, Any]] = []
    for volume in data.get("volumeList") or []:
        volume_title = str(volume.get("title") or "").strip()
        for chapter in volume.get("chapterList") or []:
            chapter_id = str(chapter.get("chapId") or "").strip()
            if not chapter_id.isdigit():
                continue
            title = str(chapter.get("title") or f"章节 {chapter_id}").strip()
            restricted = (
                bool(chapter.get("isVip"))
                or int(chapter.get("needFireMoney") or chapter.get("originNeedFireMoney") or 0) > 0
            )
            chapters.append(
                {
                    "id": chapter_id,
                    "title": f"{volume_title} · {title}" if volume_title else title,
                    "url": canonical_chapter_url(novel_id, chapter_id),
                    "access_restricted": restricted,
                }
            )
    return chapters


def _book_value(item: dict[str, Any], key: str, *fallbacks: str) -> Any:
    value = item.get(key)
    if value is not None and value != "":
        return value
    expand = item.get("expand")
    if isinstance(expand, dict):
        value = expand.get(key)
        if value is not None and value != "":
            return value
    for fallback in fallbacks:
        value = item.get(fallback)
        if value is not None and value != "":
            return value
        if isinstance(expand, dict):
            value = expand.get(fallback)
            if value is not None and value != "":
                return value
    return None


def normalize_book(item: dict[str, Any]) -> dict[str, Any]:
    novel_id = str(_book_value(item, "novelId", "id") or "").strip()
    return {
        "id": novel_id,
        "title": str(_book_value(item, "novelName", "title") or "").strip(),
        "author": str(_book_value(item, "authorName") or "").strip(),
        "synopsis": str(_book_value(item, "intro", "description") or "").strip(),
        "cover": str(_book_value(item, "bigNovelCover", "novelCover") or "").strip() or None,
        "url": canonical_book_url(novel_id) if novel_id else "",
    }


async def search_books(client: httpx.AsyncClient, keyword: str) -> list[dict[str, Any]]:
    data = await _request(
        client,
        "/search/novels/result",
        params={"q": keyword, "page": 0, "size": 20},
    )
    if isinstance(data, dict):
        items = data.get("novels") or data.get("list") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [normalize_book(item) for item in items if isinstance(item, dict)]


async def get_chapter(client: httpx.AsyncClient, chapter_id: str) -> str:
    data = await _request(
        client,
        f"/Chaps/{chapter_id}",
        params={"expand": "content,expand.content"},
    )
    if not isinstance(data, dict):
        raise ValueError("SF 轻小说章节响应格式无效")
    content = data.get("content")
    if not content and isinstance(data.get("expand"), dict):
        content = data["expand"].get("content")
    text = str(content or "").replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("SF 轻小说章节响应没有返回可解析正文")
    return text
