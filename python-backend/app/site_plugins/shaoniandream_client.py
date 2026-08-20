from __future__ import annotations

import base64
import random
import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from Crypto.Cipher import AES

SHAONIANDREAM_ORIGIN = "https://www.shaoniandream.com"
BOOK_PATH_PATTERN = re.compile(r"^/book_detail/(\d+)(?:/|$)", re.IGNORECASE)
CHAPTER_PATH_PATTERN = re.compile(r"^/readchapter/(\d+)(?:/|$)", re.IGNORECASE)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _random_value() -> str:
    return str(random.SystemRandom().random())[2:14]


def book_id_from_url(url: str) -> str | None:
    match = BOOK_PATH_PATTERN.match(urlparse(url).path)
    return match.group(1) if match else None


def chapter_id_from_url(url: str) -> str | None:
    match = CHAPTER_PATH_PATTERN.match(urlparse(url).path)
    return match.group(1) if match else None


def canonical_book_url(book_id: str | int) -> str:
    return f"{SHAONIANDREAM_ORIGIN}/book_detail/{book_id}"


def canonical_chapter_url(chapter_id: str | int) -> str:
    return f"{SHAONIANDREAM_ORIGIN}/readchapter/{chapter_id}"


def parse_book_page(html: str, book_id: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    def text(selector: str) -> str:
        node = soup.select_one(selector)
        return _clean(node.get_text(" ", strip=True) if node else "")

    author_node = soup.select_one(".bookdetail-name .penName a")
    cover_node = soup.select_one(".bookdetail-top .cover img")
    cover = ""
    if cover_node:
        cover = str(cover_node.get("data-original") or cover_node.get("src") or "")
    return {
        "id": book_id,
        "title": text(".bookdetail-name .title"),
        "author": _clean(author_node.get_text(" ", strip=True) if author_node else ""),
        "synopsis": text(".bookdetial-jianjie"),
        "cover": urljoin(SHAONIANDREAM_ORIGIN, cover) if cover else None,
    }


def parse_catalogue(payload: dict[str, Any], book_id: str) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for volume in payload.get("readdir") or []:
        volume_title = _clean(volume.get("title"))
        for item in volume.get("list") or []:
            chapter_id = str(item.get("id") or "").strip()
            if not chapter_id.isdigit():
                continue
            title = _clean(item.get("title")) or f"章节 {chapter_id}"
            chapters.append(
                {
                    "id": chapter_id,
                    "title": f"{volume_title} · {title}" if volume_title else title,
                    "url": canonical_chapter_url(chapter_id),
                    "access_restricted": str(item.get("isFree")) not in {"", "1", "True", "true"},
                    "book_id": book_id,
                }
            )
    return chapters


def parse_search_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    for item in soup.select(".BookPicList ul li dl"):
        link = item.select_one("dd.title a[href*='/book_detail/']")
        match = re.search(r"/book_detail/(\d+)", str(link.get("href") or "")) if link else None
        if not match:
            continue
        image = item.select_one("dd.img img")
        author = item.select_one("dd.author a[href*='/author/index/id/']")
        synopsis = item.select_one("dd.jianjie")
        cover = str(image.get("data-original") or image.get("src") or "") if image else ""
        results.append(
            {
                "title": _clean(link.get("title") or link.get_text(" ", strip=True)),
                "author": _clean(author.get_text(" ", strip=True) if author else ""),
                "synopsis": _clean(synopsis.get_text(" ", strip=True) if synopsis else ""),
                "cover": urljoin(SHAONIANDREAM_ORIGIN, cover) if cover else None,
                "url": canonical_book_url(match.group(1)),
            }
        )
    return [item for item in results if item["title"]]


async def _json_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any]:
    headers = {
        "Origin": SHAONIANDREAM_ORIGIN,
        "Referer": f"{SHAONIANDREAM_ORIGIN}/",
        "X-Requested-With": "XMLHttpRequest",
        **dict(kwargs.pop("headers", {})),
    }
    response = await client.request(method, f"{SHAONIANDREAM_ORIGIN}{path}", headers=headers, **kwargs)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("少年梦返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("少年梦返回的数据格式无效")
    return payload


async def _access_key(client: httpx.AsyncClient, path: str) -> str:
    payload = await _json_request(client, "POST", f"{path}?randoom={_random_value()}")
    key = str((payload.get("data") or {}).get("chapter_access_key") or "")
    if not key:
        raise ValueError(str(payload.get("msg") or "少年梦没有返回章节访问密钥"))
    return key


async def get_book(client: httpx.AsyncClient, book_id: str) -> dict[str, Any]:
    response = await client.get(canonical_book_url(book_id), headers={"Referer": f"{SHAONIANDREAM_ORIGIN}/"})
    response.raise_for_status()
    return parse_book_page(response.text, book_id)


async def get_catalogue(client: httpx.AsyncClient, book_id: str) -> list[dict[str, Any]]:
    key = await _access_key(client, f"/booklibrary/getbookdetaildirsign/book_id/{book_id}")
    payload = await _json_request(
        client,
        "POST",
        f"/booklibrary/getbookdetaildir/BookID/{book_id}?randomm={_random_value()}",
        data={"chapter_access_key": key},
    )
    status = payload.get("status")
    if status is not None and int(status) not in {1, 100000}:
        raise ValueError(str(payload.get("msg") or "少年梦目录获取失败"))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("少年梦目录响应缺少 data")
    return parse_catalogue(data, book_id)


async def search_books(client: httpx.AsyncClient, keyword: str) -> list[dict[str, Any]]:
    path = f"/library/str/0_0_0_0_0_0_0_1_{quote(keyword)}"
    response = await client.get(f"{SHAONIANDREAM_ORIGIN}{path}")
    response.raise_for_status()
    return parse_search_page(response.text)


def _decrypt(value: str, key: bytes, iv: bytes) -> str:
    raw = base64.b64decode(value)
    plain = AES.new(key, AES.MODE_CBC, iv).decrypt(raw)
    padding = plain[-1]
    if 0 < padding <= 16:
        plain = plain[:-padding]
    return plain.decode("utf-8", errors="replace")


async def get_chapter(client: httpx.AsyncClient, chapter_id: str) -> str:
    key = await _access_key(
        client,
        f"/booklibrary/membersinglechaptersign/chapter_id/{chapter_id}",
    )
    payload = await _json_request(
        client,
        "POST",
        f"/booklibrary/membersinglechapter/chapter_id/{chapter_id}?randomm={_random_value()}",
        data={"chapter_access_key": key, "isMarket": 1},
        headers={"Referer": canonical_chapter_url(chapter_id)},
    )
    if int(payload.get("status") or 0) != 1:
        raise ValueError(str(payload.get("msg") or "少年梦章节需要登录、订阅或已被限制访问"))
    data = payload.get("data") or {}
    encrypted_keys = data.get("encryt_keys") or []
    if len(encrypted_keys) < 2:
        raise ValueError("少年梦章节响应缺少解密密钥")
    aes_key = base64.b64decode(str(encrypted_keys[0])).decode("utf-8").encode("utf-8")
    aes_iv = base64.b64decode(str(encrypted_keys[1])).decode("utf-8").encode("utf-8")
    paragraphs = [
        _decrypt(str(item.get("content") or ""), aes_key, aes_iv)
        for item in data.get("show_content") or []
        if isinstance(item, dict) and item.get("content")
    ]
    text = "\n\n".join(item.strip() for item in paragraphs if item.strip())
    if not text:
        raise ValueError("少年梦章节解密成功，但没有解析到正文")
    return text
