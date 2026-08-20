from __future__ import annotations

import base64
import re
from html import unescape
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from Crypto.Cipher import AES

CIWEIMAO_ORIGIN = "https://www.ciweimao.com"
BOOK_PATH_PATTERN = re.compile(r"^/(?:book|chapter-list)/(\d+)(?:/|$)", re.IGNORECASE)
CHAPTER_PATH_PATTERN = re.compile(r"^/chapter/(\d+)(?:/|$)", re.IGNORECASE)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def book_id_from_url(url: str) -> str | None:
    match = BOOK_PATH_PATTERN.match(urlparse(url).path)
    return match.group(1) if match else None


def chapter_id_from_url(url: str) -> str | None:
    match = CHAPTER_PATH_PATTERN.match(urlparse(url).path)
    return match.group(1) if match else None


def canonical_book_url(book_id: str | int) -> str:
    return f"{CIWEIMAO_ORIGIN}/book/{book_id}"


def canonical_chapter_url(chapter_id: str | int) -> str:
    return f"{CIWEIMAO_ORIGIN}/chapter/{chapter_id}"


def parse_book_page(html: str, book_id: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    values: dict[str, Any] = {"book_id": book_id, "chapters": []}
    for prop, key in (
        ("og:novel:book_name", "title"),
        ("og:novel:author", "author"),
        ("og:description", "description"),
        ("og:image", "cover"),
    ):
        tag = soup.find("meta", {"property": prop})
        if tag:
            values[key] = _clean(tag.get("content"))
    if not values.get("title"):
        title = soup.select_one("h1, .book-info h1, .book-info .title")
        values["title"] = _clean(title.get_text(" ", strip=True) if title else "")
    return values


def parse_catalogue(html: str, book_id: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one(".book-chapter-box, .book-chapter") or soup
    chapters: list[dict[str, Any]] = []
    volume = ""
    for node in container.select("h4.sub-tit, li a[href*='/chapter/']"):
        if node.name == "h4":
            volume = _clean(node.get_text(" ", strip=True))
            continue
        match = re.search(r"/chapter/(\d+)", str(node.get("href") or ""))
        if not match:
            continue
        title = _clean(node.get_text(" ", strip=True)) or f"章节 {match.group(1)}"
        parent = node.find_parent("li")
        classes = " ".join(parent.get("class", [])) if parent else ""
        chapters.append(
            {
                "id": match.group(1),
                "title": f"{volume} · {title}" if volume else title,
                "url": canonical_chapter_url(match.group(1)),
                "access_restricted": bool(re.search(r"vip|lock|paid", classes, re.IGNORECASE)),
                "book_id": book_id,
            }
        )
    return chapters


def parse_search_page(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in soup.select("li[data-book-id]"):
        link = item.select_one("a[href*='/book/']")
        match = re.search(r"/book/(\d+)", str(link.get("href") or "")) if link else None
        if not match or match.group(1) in seen:
            continue
        book_id = match.group(1)
        seen.add(book_id)
        title_node = item.select_one(".tit a, h3.title a")
        author_node = item.select_one("a[href*='/reader/']")
        intro_node = item.select_one(".desc, .book-desc, .intro")
        image = item.select_one("img")
        cover = ""
        if image:
            cover = str(image.get("data-original") or image.get("data-src") or image.get("src") or "")
        results.append(
            {
                "title": _clean(title_node.get_text(" ", strip=True) if title_node else ""),
                "author": _clean(author_node.get_text(" ", strip=True) if author_node else ""),
                "synopsis": _clean(intro_node.get_text(" ", strip=True) if intro_node else ""),
                "cover": urljoin(CIWEIMAO_ORIGIN, cover) if cover else None,
                "url": canonical_book_url(book_id),
            }
        )
    return [item for item in results if item["title"]]


def _decrypt_blob(blob: bytes, key_b64: str) -> bytes:
    if len(blob) < 16:
        raise ValueError("刺猬猫章节密文长度无效")
    iv, payload = blob[:16], blob[16:]
    if payload[:8] == b"Salted__":
        payload = payload[16:]
    key = base64.b64decode(key_b64)
    plain = AES.new(key, AES.MODE_CBC, iv).decrypt(payload)
    padding = plain[-1]
    return plain[:-padding] if 0 < padding <= 16 else plain


def decrypt_chapter(content: str, keys: list[str], access_key: str) -> str:
    if not content or not keys or not access_key:
        raise ValueError("刺猬猫章节响应缺少解密参数")
    first_key = keys[ord(access_key[-1]) % len(keys)]
    second_key = keys[ord(access_key[0]) % len(keys)]
    inner_encoded = _decrypt_blob(base64.b64decode(content), first_key)
    plain = _decrypt_blob(base64.b64decode(inner_encoded), second_key)
    return plain.decode("utf-8", errors="replace")


def parse_chapter_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    paragraphs: list[str] = []
    for paragraph in soup.select("p"):
        for watermark in paragraph.select("span"):
            watermark.decompose()
        text = paragraph.get_text(" ", strip=True)
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


async def get_book(client: httpx.AsyncClient, book_id: str) -> dict[str, Any]:
    response = await client.get(canonical_book_url(book_id))
    response.raise_for_status()
    return parse_book_page(response.text, book_id)


async def get_catalogue(client: httpx.AsyncClient, book_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"{CIWEIMAO_ORIGIN}/chapter-list/{book_id}")
    response.raise_for_status()
    return parse_catalogue(response.text, book_id)


async def search_books(client: httpx.AsyncClient, keyword: str) -> list[dict[str, Any]]:
    path = f"/get-search-book-list/0-0-0-0-0-0/{quote('全部')}/{quote(keyword)}/1"
    response = await client.get(f"{CIWEIMAO_ORIGIN}{path}")
    response.raise_for_status()
    return parse_search_page(response.text)


async def get_chapter(client: httpx.AsyncClient, chapter_id: str) -> str:
    chapter_url = canonical_chapter_url(chapter_id)
    headers = {"Referer": chapter_url, "X-Requested-With": "XMLHttpRequest"}
    key_response = await client.get(
        f"{CIWEIMAO_ORIGIN}/chapter/ajax_get_session_code",
        params={"chapter_id": chapter_id},
        headers=headers,
    )
    key_response.raise_for_status()
    access_key = str(key_response.json().get("chapter_access_key") or "")
    detail_response = await client.post(
        f"{CIWEIMAO_ORIGIN}/chapter/get_book_chapter_detail_info",
        data={"chapter_id": chapter_id, "chapter_access_key": access_key},
        headers=headers,
    )
    detail_response.raise_for_status()
    payload = detail_response.json()
    if int(payload.get("code") or 0) != 100000:
        raise ValueError(str(payload.get("tip") or "刺猬猫章节需要登录、订阅或已被限制访问"))
    plain = decrypt_chapter(
        str(payload.get("chapter_content") or ""),
        [str(item) for item in payload.get("encryt_keys") or []],
        access_key,
    )
    text = parse_chapter_html(plain)
    if not text:
        raise ValueError("刺猬猫章节解密成功，但没有解析到正文")
    return text
