from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx
from bs4 import BeautifulSoup

COMICORES_ORIGIN = "https://www.comicores.cc"
COMICORES_REST_ORIGIN = f"{COMICORES_ORIGIN}/wp-json/wp/v2"
COMICORES_RESERVED_PATHS = {
    "author",
    "category",
    "feed",
    "page",
    "tag",
    "wp-admin",
    "wp-content",
    "wp-json",
}


class ComicoresError(ValueError):
    pass


def comicores_book_key_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    post_id = parse_qs(parsed.query).get("p", [""])[0].strip()
    if post_id.isdigit():
        return post_id
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    slug = parts[0].strip()
    if slug.lower() in COMICORES_RESERVED_PATHS:
        return None
    return slug if re.fullmatch(r"[A-Za-z0-9_-]+", slug) else None


def canonical_comicores_book_url(book_key: str) -> str:
    if book_key.isdigit():
        return f"{COMICORES_ORIGIN}/?p={book_key}"
    return f"{COMICORES_ORIGIN}/{quote(book_key, safe='-_')}/.html"


def _ensure_rest_response(response: httpx.Response, stage: str) -> Any:
    host = (response.url.host or "").lower()
    if host != "comicores.cc" and not host.endswith(".comicores.cc"):
        raise ComicoresError(f"COMICORES {stage}发生了不受信任的跨站重定向")
    if response.status_code == 404:
        raise ComicoresError(f"COMICORES {stage}未找到")
    if response.status_code >= 400:
        raise ComicoresError(f"COMICORES {stage}请求失败（HTTP {response.status_code}）")
    try:
        return response.json()
    except ValueError as exc:
        raise ComicoresError(f"COMICORES {stage}返回了无效 JSON") from exc


async def _rest_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    stage: str,
    params: dict[str, Any] | None = None,
) -> Any:
    response = await client.get(
        f"{COMICORES_REST_ORIGIN}{path}",
        params=params or {},
        headers={"Accept": "application/json", "Referer": f"{COMICORES_ORIGIN}/"},
    )
    return _ensure_rest_response(response, stage)


async def get_comicores_book(client: httpx.AsyncClient, book_key: str) -> dict[str, Any]:
    if book_key.isdigit():
        result = await _rest_get(
            client,
            f"/posts/{book_key}",
            stage="作品详情",
            params={"_embed": 1},
        )
        if not isinstance(result, dict):
            raise ComicoresError("COMICORES 作品详情返回格式异常")
        return result
    result = await _rest_get(
        client,
        "/posts",
        stage="作品详情",
        params={"slug": book_key, "_embed": 1},
    )
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise ComicoresError("COMICORES 作品不存在")
    return result[0]


async def search_comicores(
    client: httpx.AsyncClient,
    keyword: str,
    limit: int,
) -> list[dict[str, Any]]:
    result = await _rest_get(
        client,
        "/posts",
        stage="作品搜索",
        params={"search": keyword, "page": 1, "per_page": limit, "_embed": 1},
    )
    if not isinstance(result, list):
        raise ComicoresError("COMICORES 搜索返回格式异常")
    return [item for item in result if isinstance(item, dict)]


def comicores_title(post: dict[str, Any]) -> str:
    title = post.get("title")
    rendered = title.get("rendered") if isinstance(title, dict) else title
    return html.unescape(BeautifulSoup(str(rendered or ""), "html.parser").get_text(" ", strip=True))


def comicores_cover(post: dict[str, Any]) -> str | None:
    embedded = post.get("_embedded")
    media = embedded.get("wp:featuredmedia") if isinstance(embedded, dict) else None
    if not isinstance(media, list) or not media or not isinstance(media[0], dict):
        return None
    value = str(media[0].get("source_url") or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.hostname else None


def comicores_authors(post: dict[str, Any]) -> list[str]:
    embedded = post.get("_embedded")
    term_groups = embedded.get("wp:term") if isinstance(embedded, dict) else None
    if not isinstance(term_groups, list):
        return []
    authors: list[str] = []
    for group in term_groups:
        if not isinstance(group, list):
            continue
        for term in group:
            if not isinstance(term, dict) or "mangaka" not in str(term.get("link") or ""):
                continue
            name = html.unescape(str(term.get("name") or "")).strip()
            if name and name not in authors:
                authors.append(name)
    return authors


def comicores_synopsis(post: dict[str, Any]) -> str:
    content = post.get("content")
    rendered = content.get("rendered") if isinstance(content, dict) else content
    soup = BeautifulSoup(str(rendered or ""), "html.parser")
    for node in soup.select("fieldset#erphpdown, fieldset.erphpdown-default, .su-members"):
        node.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    for notice in ("您需要登录来查看全部内容。", "资源下载", "付费资源", "免费资源"):
        text = text.replace(notice, "")
    return text.strip()[:2000]
