from __future__ import annotations

import math
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

EHENTAI_ORIGIN = "https://e-hentai.org"
EHENTAI_API_URL = "https://api.e-hentai.org/api.php"
GALLERY_PATH_PATTERN = re.compile(r"^/g/(\d+)/([0-9a-f]{10})(?:/|$)", re.IGNORECASE)
SHOW_PATH_PATTERN = re.compile(r"^/s/([0-9a-f]{10})/(\d+)-(\d+)(?:/|$)", re.IGNORECASE)
LENGTH_PATTERN = re.compile(r"Length:?\s*</td>\s*<td[^>]*>\s*(\d+)\s*pages?", re.IGNORECASE)


def gallery_ids_from_url(url: str) -> tuple[str, str] | None:
    match = GALLERY_PATH_PATTERN.match(urlparse(url).path)
    return (match.group(1), match.group(2).lower()) if match else None


def canonical_gallery_url(gid: str | int, token: str, *, origin: str = EHENTAI_ORIGIN) -> str:
    return f"{origin.rstrip('/')}/g/{gid}/{token.lower()}/"


def _origin_from_gallery_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_meta(meta: dict[str, Any]) -> dict[str, Any]:
    def integer(value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    tags = [str(item) for item in meta.get("tags") or [] if str(item).strip()]
    return {
        "gid": str(meta.get("gid") or ""),
        "token": str(meta.get("token") or "").lower(),
        "title": str(meta.get("title") or meta.get("title_jpn") or "").strip(),
        "title_jpn": str(meta.get("title_jpn") or "").strip(),
        "category": str(meta.get("category") or "").strip(),
        "cover": str(meta.get("thumb") or "").strip() or None,
        "author": str(meta.get("uploader") or "").strip(),
        "filecount": integer(meta.get("filecount")),
        "rating": meta.get("rating"),
        "tags": tags,
        "error": meta.get("error"),
    }


async def get_gallery_metadata(client: httpx.AsyncClient, gid: str, token: str) -> dict[str, Any]:
    response = await client.post(
        EHENTAI_API_URL,
        json={"method": "gdata", "gidlist": [[int(gid), token]], "namespace": 1},
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("gmetadata") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("E-Hentai 没有返回画廊元数据")
    result = normalize_meta(items[0])
    if result.get("error"):
        raise ValueError(f"E-Hentai 画廊不可用：{result['error']}")
    return result


def parse_gallery_page(html: str, gid: str, origin: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    pages: dict[int, dict[str, Any]] = {}
    for link in soup.select("a[href*='/s/']"):
        absolute = urljoin(origin, str(link.get("href") or ""))
        match = SHOW_PATH_PATTERN.match(urlparse(absolute).path)
        if not match or match.group(2) != gid:
            continue
        page = int(match.group(3))
        pages[page] = {
            "page": page,
            "key": match.group(1).lower(),
            "show_url": absolute,
        }
    length_match = LENGTH_PATTERN.search(html)
    description_node = soup.select_one("#gd5")
    if description_node:
        for control in description_node.select("p.gsp"):
            control.decompose()
    uploader_node = soup.select_one('#gdn a[href*="/uploader/"]')
    return {
        "filecount": int(length_match.group(1)) if length_match else None,
        "pages": [pages[key] for key in sorted(pages)],
        "description": description_node.get_text("\n", strip=True) if description_node else "",
        "uploader": uploader_node.get_text(" ", strip=True) if uploader_node else "",
    }


async def get_gallery_page(
    client: httpx.AsyncClient,
    gallery_url: str,
    page_group: int = 0,
) -> dict[str, Any]:
    url = gallery_url if page_group <= 0 else f"{gallery_url}?p={page_group}"
    response = await client.get(url)
    response.raise_for_status()
    ids = gallery_ids_from_url(gallery_url)
    if not ids:
        raise ValueError("无法识别 E-Hentai 画廊链接")
    return parse_gallery_page(response.text, ids[0], _origin_from_gallery_url(gallery_url))


def parse_search_page(html: str, origin: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in soup.select("table.itg tr"):
        link = row.select_one("a[href*='/g/']")
        absolute = urljoin(origin, str(link.get("href") or "")) if link else ""
        ids = gallery_ids_from_url(absolute)
        if not ids or ids[0] in seen:
            continue
        seen.add(ids[0])
        title_node = row.select_one(".glink") or link
        category_node = row.select_one(".glcat .cn, .gl1c .cn")
        image = row.select_one("img")
        tags = [
            str(tag.get("title") or tag.get_text(" ", strip=True)).strip()
            for tag in row.select(".gt, .gtl, .gtw")
        ]
        results.append(
            {
                "title": title_node.get_text(" ", strip=True) if title_node else f"Gallery {ids[0]}",
                "author": None,
                "synopsis": " · ".join(
                    item
                    for item in [category_node.get_text(" ", strip=True) if category_node else "", *tags[:6]]
                    if item
                ),
                "cover": urljoin(origin, str(image.get("src") or image.get("data-src") or ""))
                if image
                else None,
                "url": canonical_gallery_url(ids[0], ids[1], origin=origin),
            }
        )
    return results


async def search_galleries(
    client: httpx.AsyncClient,
    keyword: str,
    *,
    origin: str = EHENTAI_ORIGIN,
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{origin.rstrip('/')}/",
        params={"f_search": keyword, "f_apply": "Apply Filter"},
    )
    response.raise_for_status()
    return parse_search_page(response.text, origin)


async def get_gallery_image_entries(client: httpx.AsyncClient, gallery_url: str) -> list[dict[str, str]]:
    ids = gallery_ids_from_url(gallery_url)
    if not ids:
        raise ValueError("无法识别 E-Hentai 画廊链接")
    first = await get_gallery_page(client, gallery_url)
    filecount = int(first.get("filecount") or len(first.get("pages") or []))
    page_entries = list(first.get("pages") or [])
    groups = max(1, math.ceil(filecount / 20))
    for group in range(1, groups):
        part = await get_gallery_page(client, gallery_url, group)
        page_entries.extend(part.get("pages") or [])
    entries_by_page = {int(item["page"]): item for item in page_entries}
    image_entries: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for page in sorted(entries_by_page):
        entry = entries_by_page[page]
        response = await client.get(
            str(entry["show_url"]),
            headers={"Referer": gallery_url},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        image = soup.select_one("img#img")
        image_url = unescape(str(image.get("src") or "")).strip() if image else ""
        if image_url and urlparse(image_url).scheme == "https" and image_url not in seen_urls:
            seen_urls.add(image_url)
            image_entries.append({"image_url": image_url, "referer": str(entry["show_url"])})
    if not image_entries:
        raise ValueError("E-Hentai 画廊没有可访问的原图，可能已删除或需要登录")
    return image_entries


async def get_gallery_images(client: httpx.AsyncClient, gallery_url: str) -> list[str]:
    entries = await get_gallery_image_entries(client, gallery_url)
    return [item["image_url"] for item in entries]
