from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from hashlib import md5
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import AddBookPayload, ChapterPreview, PreviewResponse, TranslationSettings

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - 环境可选依赖
    curl_requests = None

try:
    import requests
except Exception:  # pragma: no cover - 环境可选依赖
    requests = None

try:
    import websockets
except Exception:  # pragma: no cover - 环境可选依赖
    websockets = None

CHAPTER_PATTERN = re.compile(r"(chapter|episode|第.{0,6}[章节话卷篇])", re.IGNORECASE)
GENERIC_CHAPTER_CONTAINER_SELECTORS = (
    ".chapter-list a[href]",
    ".chapters a[href]",
    ".episode-list a[href]",
    ".episodes a[href]",
    ".toc a[href]",
    ".table-of-contents a[href]",
    "[id*='chapter'] a[href]",
    "[class*='chapter'] a[href]",
    "[id*='episode'] a[href]",
    "[class*='episode'] a[href]",
)
KAKUYOMU_HOST_KEYWORDS = ("kakuyomu.jp",)
SYOSETU_HOST_KEYWORDS = ("syosetu.com",)
PIXIV_HOST_KEYWORDS = ("pixiv.net",)
NOVELUP_HOST_KEYWORDS = ("novelup.plus",)
ALPHAPOLIS_HOST_KEYWORDS = ("alphapolis.co.jp",)
HAMELN_HOST_KEYWORDS = ("syosetu.org",)
LINOVELIB_HOST_KEYWORDS = ("linovelib.com", "bilinovel.com")
LINOVELIB_PREFERRED_HOSTS = ("tw.linovelib.com", "www.bilinovel.com", "www.linovelib.com")
LINOVELIB_BOOK_PATH_PATTERN = re.compile(r"/novel/(?P<book_id>\d+)(?:\.html|/catalog|/\d+(?:_\d+)?\.html)?/?$")
LINOVELIB_CHAPTER_PATH_PATTERN = re.compile(r"/novel/(?P<book_id>\d+)/(?P<chapter_id>\d+)(?:_(?P<page>\d+))?\.html$")
KAKUYOMU_WORK_PATH_PATTERN = re.compile(r"^/works/(?P<work_id>\d+)(?:/episodes/(?P<episode_id>\d+))?/?$")
SYOSETU_BOOK_PATH_PATTERN = re.compile(r"^/(?P<book_code>[a-z0-9]+)(?:/(?P<chapter_no>\d+)/?)?$", re.IGNORECASE)
HAMELN_BOOK_PATH_PATTERN = re.compile(r"^/novel/(?P<book_id>\d+)(?:/(?P<chapter_no>\d+)\.html)?/?$")
PIXIV_SERIES_PATH_PATTERN = re.compile(r"^/novel/series/(?P<series_id>\d+)/?$")
NOVELUP_STORY_PATH_PATTERN = re.compile(r"^/story/(?P<story_id>\d+)(?:/.*)?$")
ALPHAPOLIS_WORK_PATH_PATTERN = re.compile(
    r"^/novel/(?P<author_id>\d+)/(?P<content_id>\d+)(?:/episode/(?P<episode_id>\d+))?/?$"
)
LINOVELIB_BLOCK_MARKERS = (
    "Attention Required! | Cloudflare",
    "Sorry, you have been blocked",
)
NOISE_LINE_MARKERS = (
    "内容加载失败",
    "內容加載失敗",
    "請重載或更換瀏覽器",
    "请重载或更换浏览器",
    "翻页模式",
    "翻上页",
    "翻下页",
    "上一页",
    "下一页",
    "上一頁",
    "下一頁",
    "目录",
    "目錄",
    "书页",
    "書頁",
    "建议使用上下翻页",
    "建議使用上下翻頁",
    "章评",
)
LINOVELIB_MIN_REQUEST_INTERVAL = 1.2
LINOVELIB_MAX_RETRIES = 5
LINOVELIB_RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
_HOST_LAST_REQUEST_AT: dict[str, float] = {}
EDGE_BROWSER_PATHS = tuple(
    path
    for path in (
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe"
        if os.environ.get("PROGRAMFILES(X86)")
        else None,
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe"
        if os.environ.get("PROGRAMFILES")
        else None,
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    if path is not None
)
EDGE_CDP_BOOT_TIMEOUT_SECONDS = 15.0
EDGE_CDP_PAGE_TIMEOUT_SECONDS = 45.0
EDGE_CDP_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
}


@dataclass
class DownloadResult:
    title: str
    synopsis: str
    cover: str | None
    chapters: list[ChapterPreview]
    local_path: Path


@dataclass
class ChapterFetchResult:
    text: str
    image_urls: list[str]
    illustration: bool = False
    image_files: list[str] | None = None


@dataclass
class SyncFetchResult:
    text: str
    resolved_url: str
    status_code: int


@dataclass
class EdgeSnapshot:
    html: str
    resolved_url: str


def _host_matches(url: str, keywords: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == keyword or host.endswith(f".{keyword}") for keyword in keywords)


def _is_kakuyomu_url(url: str) -> bool:
    return _host_matches(url, KAKUYOMU_HOST_KEYWORDS)


def _is_syosetu_url(url: str) -> bool:
    return _host_matches(url, SYOSETU_HOST_KEYWORDS) and "novel18" not in (urlparse(url).hostname or "").lower()


def _is_novel18_url(url: str) -> bool:
    return "novel18.syosetu.com" in (urlparse(url).hostname or "").lower()


def _is_pixiv_url(url: str) -> bool:
    return _host_matches(url, PIXIV_HOST_KEYWORDS)


def _is_novelup_url(url: str) -> bool:
    return _host_matches(url, NOVELUP_HOST_KEYWORDS)


def _is_alphapolis_url(url: str) -> bool:
    return _host_matches(url, ALPHAPOLIS_HOST_KEYWORDS)


def _is_hameln_url(url: str) -> bool:
    return _host_matches(url, HAMELN_HOST_KEYWORDS)


def _clean_title_suffix(title: str, suffixes: tuple[str, ...]) -> str:
    value = title.strip()
    for suffix in suffixes:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value.strip() or title.strip()


def _build_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _append_prefixed_text(prefix: str | None, body: str | None) -> str:
    prefix_value = (prefix or "").strip()
    body_value = (body or "").strip()
    if prefix_value and body_value and prefix_value not in body_value:
        return f"{prefix_value}\n\n{body_value}"
    return body_value or prefix_value


def _is_linovelib_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(keyword in host for keyword in LINOVELIB_HOST_KEYWORDS)


def _normalize_source_url(url: str) -> str:
    parsed = urlparse(url)
    if _is_linovelib_url(url):
        match = LINOVELIB_BOOK_PATH_PATTERN.match(parsed.path)
        if not match:
            return url
        book_id = match.group("book_id")
        return f"{parsed.scheme}://{parsed.netloc}/novel/{book_id}/catalog"

    if _is_kakuyomu_url(url):
        match = KAKUYOMU_WORK_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/works/{match.group('work_id')}"
        return url

    if _is_syosetu_url(url) or _is_novel18_url(url):
        match = SYOSETU_BOOK_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/{match.group('book_code').lower()}/"
        return url

    if _is_hameln_url(url):
        match = HAMELN_BOOK_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/novel/{match.group('book_id')}/"
        return url

    if _is_pixiv_url(url):
        series_match = PIXIV_SERIES_PATH_PATTERN.match(parsed.path)
        if series_match:
            return f"{parsed.scheme}://{parsed.netloc}/novel/series/{series_match.group('series_id')}"
        novel_id = parse_qs(parsed.query).get("id", [""])[0].strip()
        if parsed.path == "/novel/show.php" and novel_id:
            return f"{parsed.scheme}://{parsed.netloc}/novel/show.php?id={novel_id}"

    if _is_novelup_url(url):
        match = NOVELUP_STORY_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/story/{match.group('story_id')}"
        return url

    if _is_alphapolis_url(url):
        match = ALPHAPOLIS_WORK_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/novel/{match.group('author_id')}/{match.group('content_id')}"
        return url

    return url


def _linovelib_candidate_urls(url: str) -> list[str]:
    normalized = _normalize_source_url(url)
    parsed = urlparse(normalized)
    match = LINOVELIB_BOOK_PATH_PATTERN.match(parsed.path)
    if not match:
        return [normalized]

    book_id = match.group("book_id")
    path = f"/novel/{book_id}/catalog"
    candidates = [f"{parsed.scheme}://{host}{path}" for host in LINOVELIB_PREFERRED_HOSTS]
    candidates.append(f"{parsed.scheme}://{parsed.netloc}{path}")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    if _is_probable_linovelib_page(soup):
        h1 = soup.select_one("h1")
        if h1 and h1.get_text(" ", strip=True):
            return h1.get_text(" ", strip=True)

        og_title = soup.select_one("[property='og:novel:book_name'], [property='og:title']")
        if og_title and og_title.get("content"):
            return str(og_title.get("content")).strip()

    title_node = soup.title.string.strip() if soup.title and soup.title.string else None
    if title_node:
        return title_node

    og_title = soup.select_one("meta[property='og:title']")
    if og_title and og_title.get("content"):
        return og_title.get("content").strip()

    h1 = soup.select_one("h1")
    if h1 and h1.get_text(" ", strip=True):
        return h1.get_text(" ", strip=True)

    return fallback


def _extract_synopsis(soup: BeautifulSoup) -> str:
    for selector in ["meta[name='description']", "meta[property='og:description']", ".intro", ".summary", "#intro"]:
        item = soup.select_one(selector)
        if item is None:
            continue
        if item.get("content"):
            return item.get("content").strip()
        text = item.get_text(" ", strip=True)
        if text:
            return text[:300]

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.select("p")
        if len(p.get_text(" ", strip=True)) > 30
    ]
    return paragraphs[0][:300] if paragraphs else "未抓取到简介，建议后续针对目标站点补充规则。"


def _extract_author(soup: BeautifulSoup) -> str | None:
    for selector in (
        "[property='og:novel:author']",
        "[property='og:author']",
        "meta[name='author']",
        ".author",
    ):
        item = soup.select_one(selector)
        if item is None:
            continue
        if item.get("content"):
            value = str(item.get("content")).strip()
        else:
            value = item.get_text(" ", strip=True)
        if value:
            return value

    body_text = soup.get_text(" ", strip=True)
    match = re.search(r"作者[:：]\s*([^\s]+)", body_text)
    if match:
        return match.group(1).strip()
    return None


def _extract_cover(soup: BeautifulSoup, base_url: str) -> str | None:
    selectors = (
        "[property='og:image']",
        "[property='og:image:url']",
        "meta[name='twitter:image']",
        "img[data-original*='/cover/']",
        "img[data-src*='/cover/']",
        "img[src*='/cover/']",
        ".book-img img",
        ".book-cover img",
        ".cover img",
        ".book-rand-a img",
        "img[alt*='封面']",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue
        value = ""
        for key in ("content", "data-src", "data-original", "src"):
            candidate = node.get(key)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate.strip()
                break
        if value:
            return urljoin(base_url, value)
    return None


def _extract_chapters(soup: BeautifulSoup, base_url: str) -> list[ChapterPreview]:
    if _is_probable_linovelib_page(soup):
        chapters = _extract_linovelib_chapters(soup, base_url)
        if chapters:
            return chapters

    items = _collect_generic_chapter_links(soup.select(", ".join(GENERIC_CHAPTER_CONTAINER_SELECTORS)), base_url)
    if len(items) >= 2:
        return items

    items: list[ChapterPreview] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "").strip()
        if not href or len(text) < 2 or not CHAPTER_PATTERN.search(text):
            continue

        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue

        seen.add(absolute_url)
        items.append(ChapterPreview(title=text[:120], url=absolute_url))

    return items[:500]


def _collect_generic_chapter_links(anchors: list[Any], base_url: str) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()
    base_host = (urlparse(base_url).hostname or "").lower()

    for anchor in anchors:
        href = str(anchor.get("href") or "").strip()
        text = anchor.get_text(" ", strip=True)
        if not href or not text or href.startswith(("javascript:", "#")):
            continue
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        if base_host and (parsed.hostname or "").lower() != base_host:
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        items.append(ChapterPreview(title=text[:180], url=absolute_url))

    return items


def _extract_linovelib_chapters(soup: BeautifulSoup, base_url: str) -> list[ChapterPreview]:
    items = _extract_linovelib_volume_blocks(soup, base_url)
    if items:
        return items

    items: list[ChapterPreview] = []
    seen: set[str] = set()
    current_volume = ""

    for node in soup.select("#volumes li"):
        classes = node.get("class") or []
        text = node.get_text(" ", strip=True)
        if not text:
            continue

        if "chapter-bar" in classes:
            current_volume = text
            continue

        anchor = node.find("a", href=True)
        if anchor is None:
            continue

        href = str(anchor.get("href", "")).strip()
        chapter_title = anchor.get_text(" ", strip=True) or text
        if not href or len(chapter_title) < 1:
            continue

        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue

        seen.add(absolute_url)
        if current_volume:
            chapter_title = f"{current_volume} - {chapter_title}"
        items.append(ChapterPreview(title=chapter_title[:160], url=absolute_url))

    return items


def _extract_linovelib_volume_blocks(soup: BeautifulSoup, base_url: str) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()

    for volume in soup.select(".volume-list .volume"):
        volume_title = ""
        title_node = volume.select_one(".volume-info h2, h2.v-line, h3")
        if title_node and title_node.get_text(" ", strip=True):
            volume_title = title_node.get_text(" ", strip=True)

        for anchor in volume.select(".chapter-list a[href], ul.chapter-list a[href]"):
            href = str(anchor.get("href", "")).strip()
            chapter_title = anchor.get_text(" ", strip=True)
            if not href or not chapter_title or href.startswith("javascript:"):
                continue

            absolute_url = urljoin(base_url, href)
            if absolute_url in seen:
                continue

            seen.add(absolute_url)
            if volume_title:
                chapter_title = f"{volume_title} - {chapter_title}"
            items.append(ChapterPreview(title=chapter_title[:160], url=absolute_url))

    return items


def _kakuyomu_state_from_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("#__NEXT_DATA__")
    if script is None or not script.string:
        raise ValueError("Kakuyomu 页面缺少 __NEXT_DATA__ 数据")
    payload = json.loads(script.string)
    page_props = payload.get("props", {}).get("pageProps", {})
    state = page_props.get("__APOLLO_STATE__")
    if not isinstance(state, dict) or not state:
        raise ValueError("Kakuyomu 页面缺少 __APOLLO_STATE__ 数据")
    return state


def _kakuyomu_work_id_from_url(url: str) -> str | None:
    match = KAKUYOMU_WORK_PATH_PATTERN.match(urlparse(url).path)
    return match.group("work_id") if match else None


def _kakuyomu_work_from_state(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    work = state.get(f"Work:{work_id}")
    if not isinstance(work, dict):
        raise ValueError("未能在 Kakuyomu 页面中定位作品信息")
    return work


def _kakuyomu_author_from_state(state: dict[str, Any], work: dict[str, Any]) -> str | None:
    author_ref = work.get("author", {})
    if isinstance(author_ref, dict):
        author = state.get(str(author_ref.get("__ref") or ""))
        if isinstance(author, dict):
            for key in ("activityName", "name", "screenName"):
                value = str(author.get(key) or "").strip()
                if value:
                    return value
    return None


def _kakuyomu_synopsis_from_work(work: dict[str, Any]) -> str:
    catchphrase = str(work.get("catchphrase") or "").strip()
    introduction = str(work.get("introduction") or "").strip()
    return _append_prefixed_text(catchphrase, introduction)


def _kakuyomu_chapters_from_state(state: dict[str, Any], work_id: str, work: dict[str, Any]) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()
    origin = "https://kakuyomu.jp"

    for toc_ref in work.get("tableOfContents", []):
        ref_key = toc_ref.get("__ref") if isinstance(toc_ref, dict) else None
        toc = state.get(str(ref_key or ""))
        if not isinstance(toc, dict):
            continue

        chapter_title = ""
        chapter_ref = toc.get("chapter")
        if isinstance(chapter_ref, dict):
            chapter_meta = state.get(str(chapter_ref.get("__ref") or ""))
            if isinstance(chapter_meta, dict):
                chapter_title = str(chapter_meta.get("title") or chapter_meta.get("name") or "").strip()

        for episode_ref in toc.get("episodeUnions", []):
            episode_key = episode_ref.get("__ref") if isinstance(episode_ref, dict) else None
            episode = state.get(str(episode_key or ""))
            if not isinstance(episode, dict):
                continue
            episode_id = str(episode.get("id") or "").strip()
            episode_title = str(episode.get("title") or "").strip()
            if not episode_id or not episode_title:
                continue
            title = f"{chapter_title} - {episode_title}" if chapter_title else episode_title
            chapter_url = f"{origin}/works/{work_id}/episodes/{episode_id}"
            if chapter_url in seen:
                continue
            seen.add(chapter_url)
            items.append(ChapterPreview(title=title[:180], url=chapter_url))

    return items


def _pixiv_novel_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.path != "/novel/show.php":
        return None
    novel_id = parse_qs(parsed.query).get("id", [""])[0].strip()
    return novel_id or None


def _pixiv_series_id_from_url(url: str) -> str | None:
    match = PIXIV_SERIES_PATH_PATTERN.match(urlparse(url).path)
    return match.group("series_id") if match else None


def _pixiv_api_headers(referer: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ja,en;q=0.9",
        "Referer": referer or "https://www.pixiv.net/",
    }


async def _fetch_json(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(str(payload.get("message") or "目标站点返回错误"))
    body = payload.get("body")
    if not isinstance(body, (dict, list)):
        raise ValueError("目标站点返回了不可识别的数据结构")
    return {"body": body, "url": str(response.url)}


def _pixiv_content_to_text(content: str) -> str:
    value = content.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("[newpage]", "\n\n")
    value = re.sub(r"\[\[rb:([^>]+)\s*>\s*([^\]]+)\]\]", r"\1（\2）", value)
    value = re.sub(r"\[\[jumpuri:([^>]+)\s*>\s*([^\]]+)\]\]", r"\1（\2）", value)
    value = re.sub(r"\[jump:(\d+)\]", "", value)
    value = re.sub(r"\[chapter:[^\]]+\]", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _extract_pixiv_image_urls(body: dict[str, Any]) -> list[str]:
    image_urls: list[str] = []
    for bucket_key in ("textEmbeddedImages", "contentImages"):
        bucket = body.get(bucket_key)
        if not isinstance(bucket, dict):
            continue
        for item in bucket.values():
            if not isinstance(item, dict):
                continue
            urls = item.get("urls")
            if isinstance(urls, dict):
                for key in ("original", "1200x1200", "regular", "small"):
                    candidate = str(urls.get(key) or "").strip()
                    if candidate and candidate not in image_urls:
                        image_urls.append(candidate)
                        break
            else:
                candidate = str(item.get("originalUrl") or item.get("url") or "").strip()
                if candidate and candidate not in image_urls:
                    image_urls.append(candidate)
    return image_urls


def _syosetu_chapters_from_soup(soup: BeautifulSoup, base_url: str) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()
    current_heading = ""

    for node in soup.select(".p-eplist > *"):
        classes = node.get("class") or []
        if "p-eplist__chapter-title" in classes:
            current_heading = node.get_text(" ", strip=True)
            continue
        if "p-eplist__sublist" not in classes:
            continue
        anchor = node.select_one("a[href]")
        if anchor is None:
            continue
        href = str(anchor.get("href") or "").strip()
        title = anchor.get_text(" ", strip=True)
        if not href or not title:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        if current_heading:
            title = f"{current_heading} - {title}"
        items.append(ChapterPreview(title=title[:180], url=absolute_url))

    if items:
        return items

    current_heading = ""
    for node in soup.select(".index_box > *, .novel_sublist2, .novel_sublist, .chapter_title"):
        classes = node.get("class") or []
        class_text = " ".join(classes)
        if "chapter_title" in class_text:
            current_heading = node.get_text(" ", strip=True)
            continue

        anchor = node.select_one("a[href]")
        if anchor is None:
            continue
        href = str(anchor.get("href") or "").strip()
        title = anchor.get_text(" ", strip=True)
        if not href or not title:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        if current_heading and current_heading not in title:
            title = f"{current_heading} - {title}"
        items.append(ChapterPreview(title=title[:180], url=absolute_url))

    return items


def _hameln_chapters_from_soup(soup: BeautifulSoup, base_url: str) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()

    for anchor in soup.select("table tr a[href$='.html']"):
        href = str(anchor.get("href") or "").strip()
        title = anchor.get_text(" ", strip=True)
        if not href or not title:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        items.append(ChapterPreview(title=title[:180], url=absolute_url))

    return items


def _hameln_author_from_soup(soup: BeautifulSoup) -> str | None:
    first_info = soup.select_one("#maind .ss p")
    if first_info is None:
        return None
    text = first_info.get_text(" ", strip=True)
    match = re.search(r"作：\s*([^\s×]+)", text)
    return match.group(1).strip() if match else None


def _hameln_chapter_text(soup: BeautifulSoup) -> str:
    body = soup.select_one("#honbun")
    if body is None:
        return ""
    parts = [body.get_text("\n", strip=True)]
    afterword = soup.select_one("#atogaki")
    if afterword is not None:
        afterword_text = afterword.get_text("\n", strip=True)
        if afterword_text:
            parts.append(f"【后记】\n{afterword_text}")
    return "\n\n".join(part.strip() for part in parts if part.strip()).strip()


def load_manifest(book_dir: Path) -> dict:
    manifest_path = book_dir / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_manifest(book_dir: Path, manifest: dict) -> None:
    (book_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def build_translated_filename(filename: str) -> str:
    chapter_path = Path(filename)
    return f"{chapter_path.stem}.translated.txt"


def chapter_text_path(book_dir: Path, filename: str) -> Path:
    return book_dir / filename


def translated_text_path(book_dir: Path, filename: str) -> Path:
    return book_dir / build_translated_filename(filename)


async def download_selected_chapters(
    book_dir: Path,
    manifest: dict,
    chapter_indexes: list[int],
    concurrency: int = 1,
    progress_callback: Callable[[int, int, list[str]], Awaitable[None] | None] | None = None,
) -> dict:
    chapter_lookup = _chapter_lookup(manifest)
    selected_indexes = [chapter_index for chapter_index in chapter_indexes if chapter_lookup.get(chapter_index)]
    if not selected_indexes:
        return manifest

    concurrency = max(1, concurrency)
    updated = False
    completed_count = 0
    total_count = len(selected_indexes)
    active_titles: dict[int, str] = {}
    semaphore = asyncio.Semaphore(concurrency)

    async with _build_http_client() as client:
        async def worker(chapter_index: int) -> dict:
            chapter = chapter_lookup[chapter_index]
            chapter_title = str(chapter.get("title") or f"第{chapter_index}章")
            async with semaphore:
                active_titles[chapter_index] = chapter_title
                await _notify_download_progress(progress_callback, completed_count, total_count, list(active_titles.values()))
                try:
                    return await _download_single_chapter(client, book_dir, chapter_index, chapter)
                finally:
                    active_titles.pop(chapter_index, None)

        pending_tasks = [asyncio.create_task(worker(chapter_index)) for chapter_index in selected_indexes]
        try:
            for pending_task in asyncio.as_completed(pending_tasks):
                payload = await pending_task
                chapter = chapter_lookup[payload["index"]]
                chapter["file_name"] = payload["file_name"]
                chapter["downloaded"] = payload["downloaded"]
                chapter["illustration"] = payload["illustration"]
                chapter["image_urls"] = payload["image_urls"]
                chapter["image_files"] = payload["image_files"]
                completed_count += 1
                updated = True
                save_manifest(book_dir, manifest)
                await _notify_download_progress(progress_callback, completed_count, total_count, list(active_titles.values()))
        except Exception:
            for task in pending_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            raise

    if updated:
        save_manifest(book_dir, manifest)

    return manifest


async def _notify_download_progress(
    progress_callback: Callable[[int, int, list[str]], Awaitable[None] | None] | None,
    completed_count: int,
    total_count: int,
    active_titles: list[str],
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(completed_count, total_count, active_titles)
    if result is not None:
        await result


async def _download_single_chapter(
    client: httpx.AsyncClient,
    book_dir: Path,
    chapter_index: int,
    chapter: dict,
) -> dict:
    filename = str(chapter.get("file_name") or f"{chapter_index:04d}-chapter-{chapter_index}.txt")
    source_url = str(chapter.get("url") or "").strip()
    chapter_title = str(chapter.get("title") or f"第{chapter_index}章")
    existing_path = chapter_text_path(book_dir, filename)

    if not source_url:
        return {
            "index": chapter_index,
            "file_name": filename,
            "downloaded": existing_path.exists(),
            "illustration": bool(chapter.get("illustration")),
            "image_urls": [item for item in chapter.get("image_urls", []) if isinstance(item, str)],
            "image_files": [item for item in chapter.get("image_files", []) if isinstance(item, str)],
        }

    result = await _fetch_chapter_data(client, source_url, chapter_title)
    image_files = await _download_chapter_images(client, book_dir, chapter_index, result.image_urls, source_url)
    existing_path.write_text(result.text, encoding="utf-8")
    return {
        "index": chapter_index,
        "file_name": filename,
        "downloaded": True,
        "illustration": result.illustration,
        "image_urls": result.image_urls,
        "image_files": image_files,
    }


async def translate_selected_chapters(
    book_dir: Path,
    manifest: dict,
    chapter_indexes: list[int],
    language: str,
    settings: TranslationSettings,
) -> dict:
    provider = settings.defaultProvider
    provider_config = settings.providers[provider]
    if not provider_config.enabled:
        raise ValueError(f"当前翻译提供商未启用：{provider}")
    if not provider_config.baseUrl.strip():
        raise ValueError("翻译 API 地址未配置")
    if not provider_config.apiKey.strip():
        raise ValueError("翻译 API 密钥未配置")
    if not provider_config.model.strip():
        raise ValueError("翻译模型未配置")

    chapter_lookup = _chapter_lookup(manifest)
    updated = False

    async with httpx.AsyncClient(timeout=120.0) as client:
        for chapter_index in chapter_indexes:
            chapter = chapter_lookup.get(chapter_index)
            if not chapter:
                continue

            filename = str(chapter.get("file_name") or f"{chapter_index:04d}-chapter-{chapter_index}.txt")
            source_path = chapter_text_path(book_dir, filename)
            if not source_path.exists():
                raise ValueError(f"章节未下载，无法翻译：{chapter_index}")

            source_text = source_path.read_text(encoding="utf-8")
            translated_text = await _translate_text(
                client=client,
                settings=settings,
                source_language=language,
                title=str(chapter.get("title") or f"第{chapter_index}章"),
                content=source_text,
            )

            translated_filename = build_translated_filename(filename)
            translated_text_path(book_dir, filename).write_text(translated_text, encoding="utf-8")
            chapter["translated"] = True
            chapter["translated_file_name"] = translated_filename
            updated = True

    if updated:
        save_manifest(book_dir, manifest)

    return manifest


def _sync_fetch_with_httpx(url: str, referer: str | None = None) -> SyncFetchResult:
    headers = dict(DEFAULT_HEADERS)
    headers["Accept-Encoding"] = "identity"
    headers["Accept-Language"] = "ja,en;q=0.9"
    if referer:
        headers["Referer"] = referer
    with httpx.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
        client.cookies.set("over18", "yes", domain=".syosetu.com")
        client.cookies.set("over18", "yes", domain=".novel18.syosetu.com")
        response = client.get(url)
        response.raise_for_status()
        return SyncFetchResult(text=response.text, resolved_url=str(response.url), status_code=response.status_code)


def _sync_fetch_with_requests(url: str, referer: str | None = None) -> SyncFetchResult:
    if requests is None:
        raise RuntimeError("requests 不可用")
    session = requests.Session()
    session.cookies.set("over18", "yes", domain=".syosetu.com")
    session.cookies.set("over18", "yes", domain=".novel18.syosetu.com")
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": DEFAULT_HEADERS["Accept"],
        "Accept-Language": "ja,en;q=0.9",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    response = session.get(url, headers=headers, timeout=40)
    response.raise_for_status()
    return SyncFetchResult(text=response.text, resolved_url=str(response.url), status_code=response.status_code)


def _sync_fetch_with_curl_cffi(url: str, referer: str | None = None) -> SyncFetchResult:
    if curl_requests is None:
        raise RuntimeError("curl_cffi 不可用")
    headers = {
        "Accept-Language": "ja,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    if referer:
        headers["Referer"] = referer
    cookies = {"over18": "yes"} if _is_novel18_url(url) else None
    response = curl_requests.get(url, impersonate="chrome124", timeout=40, headers=headers, cookies=cookies)
    response.raise_for_status()
    return SyncFetchResult(text=response.text, resolved_url=str(response.url), status_code=response.status_code)


def _raise_special_site_error(url: str, exc: Exception | None = None) -> None:
    error_text = str(exc or "")
    if _is_novelup_url(url):
        raise ValueError("Novelup 当前访问被 CloudFront 拦截（403），当前环境下即使使用浏览器会话也无法直接抓取该站点。") from exc
    if _is_alphapolis_url(url):
        raise ValueError("Alphapolis 当前直连会触发 AWS WAF challenge，需要走浏览器会话兜底抓取。") from exc
    if _is_hameln_url(url):
        if "404" in error_text:
            raise ValueError("Hameln 返回 404，请确认该作品仍然公开可访问。") from exc
        raise ValueError("Hameln 当前触发 Cloudflare 挑战，无法直接抓取该章节内容。") from exc
    raise exc or ValueError(f"读取页面失败：{url}")


def _looks_like_block_page(url: str, result: SyncFetchResult) -> bool:
    text = result.text
    if _is_novelup_url(url):
        return "The request could not be satisfied" in text or "Request blocked" in text
    if _is_alphapolis_url(url):
        return (
            result.status_code == 202
            or "window.gokuProps" in text
            or "window.awsWafCookieDomainList" in text
            or "JavaScript is disabled" in text
        )
    if _is_hameln_url(url):
        return "Just a moment..." in text or "cf-challenge" in text
    return False


async def _fetch_site_html(url: str, referer: str | None = None) -> tuple[str, str]:
    fetchers = []
    if _is_hameln_url(url) or _is_novel18_url(url):
        fetchers.append(_sync_fetch_with_curl_cffi)
    fetchers.append(_sync_fetch_with_httpx)
    if _is_syosetu_url(url) or _is_novel18_url(url):
        fetchers.append(_sync_fetch_with_requests)
    if curl_requests is not None and (_is_alphapolis_url(url) or _is_novelup_url(url)):
        fetchers.append(_sync_fetch_with_curl_cffi)

    last_error: Exception | None = None
    for fetcher in fetchers:
        try:
            result = await asyncio.to_thread(fetcher, url, referer)
            if _looks_like_block_page(url, result):
                raise ValueError("目标站点返回了拦截页面")
            return result.text, result.resolved_url
        except Exception as exc:
            last_error = exc

    _raise_special_site_error(url, last_error)


def _find_edge_executable() -> Path | None:
    for candidate in EDGE_BROWSER_PATHS:
        if candidate.exists():
            return candidate
    return None


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _list_edge_targets(port: int) -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
        payload = response.read().decode("utf-8", errors="replace")
    result = json.loads(payload)
    return result if isinstance(result, list) else []


async def _wait_for_edge_page_target(port: int, timeout_seconds: float) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            targets = await asyncio.to_thread(_list_edge_targets, port)
        except Exception:
            await asyncio.sleep(0.25)
            continue
        for target in targets:
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                return str(target["webSocketDebuggerUrl"])
        await asyncio.sleep(0.25)
    raise ValueError("未能连接到 Edge DevTools 页面目标")


async def _cdp_send_command(
    websocket: Any,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 20.0,
    _state: dict[str, int] = {"id": 0},
) -> dict[str, Any]:
    _state["id"] += 1
    command_id = _state["id"]
    await websocket.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(websocket.recv(), timeout=max(0.1, deadline - time.monotonic()))
        payload = json.loads(raw)
        if payload.get("id") == command_id:
            if "error" in payload:
                message = payload["error"].get("message") if isinstance(payload.get("error"), dict) else payload["error"]
                raise ValueError(f"Edge DevTools 调用失败：{method} -> {message}")
            return payload
    raise TimeoutError(f"等待 Edge DevTools 返回超时：{method}")


async def _cdp_evaluate(
    websocket: Any,
    expression: str,
    *,
    await_promise: bool = False,
) -> Any:
    response = await _cdp_send_command(
        websocket,
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        },
    )
    result = response.get("result", {}).get("result", {})
    if "value" in result:
        return result["value"]
    if result.get("type") == "undefined":
        return None
    return result.get("description")


async def _fetch_with_edge_cdp(
    url: str,
    *,
    ready_expression: str,
    headless: bool,
    timeout_seconds: float = EDGE_CDP_PAGE_TIMEOUT_SECONDS,
    blocked_message: str | None = None,
) -> EdgeSnapshot:
    edge_path = _find_edge_executable()
    if edge_path is None:
        raise ValueError("未找到 Microsoft Edge，无法启用浏览器会话兜底抓取。")
    if websockets is None:
        raise ValueError("当前环境缺少 websockets 依赖，无法启用浏览器会话兜底抓取。")

    port = _reserve_local_port()
    user_data_dir = Path(tempfile.mkdtemp(prefix="qingjuan-edge-cdp-"))
    launch_args = [
        str(edge_path),
        f"--remote-debugging-port={port}",
        "--disable-gpu",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        "about:blank",
    ]
    if headless:
        launch_args.insert(2, "--headless=new")
    else:
        launch_args.insert(2, "--start-minimized")

    process = subprocess.Popen(launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = await _wait_for_edge_page_target(port, EDGE_CDP_BOOT_TIMEOUT_SECONDS)
        async with websockets.connect(ws_url, max_size=100_000_000) as websocket:
            await _cdp_send_command(websocket, "Page.enable")
            await _cdp_send_command(websocket, "Runtime.enable")
            await _cdp_send_command(websocket, "Network.enable")
            await _cdp_send_command(websocket, "Page.navigate", {"url": url})

            deadline = time.monotonic() + timeout_seconds
            last_title = ""
            last_url = url
            while time.monotonic() < deadline:
                ready = bool(await _cdp_evaluate(websocket, ready_expression))
                last_title = str(await _cdp_evaluate(websocket, "document.title || ''") or "")
                last_url = str(await _cdp_evaluate(websocket, "location.href || ''") or url)
                if ready:
                    html = str(await _cdp_evaluate(websocket, "document.documentElement.outerHTML || ''") or "")
                    return EdgeSnapshot(html=html, resolved_url=last_url or url)
                await asyncio.sleep(EDGE_CDP_POLL_INTERVAL_SECONDS)

            html = str(await _cdp_evaluate(websocket, "document.documentElement.outerHTML || ''") or "")
            if "ERROR: The request could not be satisfied" in last_title or "403 ERROR" in html:
                raise ValueError(blocked_message or "浏览器会话仍然被目标站点拦截。")
            raise ValueError(f"浏览器会话抓取超时：{url}")
    finally:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=10)
        except Exception:
            pass
        shutil.rmtree(user_data_dir, ignore_errors=True)


def _alphapolis_cover_data_from_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("#app-cover-data")
    if node is None:
        raise ValueError("未在 Alphapolis 页面中找到目录数据")
    try:
        payload = json.loads(node.get_text(strip=True))
    except Exception as exc:
        raise ValueError("Alphapolis 目录数据解析失败") from exc
    if not isinstance(payload, dict):
        raise ValueError("Alphapolis 目录数据格式异常")
    return payload


def _alphapolis_chapters_from_cover_data(data: dict[str, Any], base_url: str) -> list[ChapterPreview]:
    items: list[ChapterPreview] = []
    seen: set[str] = set()
    for group in data.get("chapterEpisodes") or []:
        if not isinstance(group, dict):
            continue
        group_title = str(group.get("title") or "").strip()
        episodes = group.get("episodes") or []
        if not isinstance(episodes, list):
            continue
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            if episode.get("isPublic") is False:
                continue
            episode_title = str(episode.get("mainTitle") or episode.get("title") or "").strip()
            href = str(episode.get("url") or "").strip()
            if not episode_title or not href:
                continue
            title = episode_title
            if group_title and group_title not in episode_title:
                title = f"{group_title} / {episode_title}"
            absolute_url = urljoin(base_url, href)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            items.append(ChapterPreview(title=title[:120], url=absolute_url))
    return items


async def _preview_kakuyomu(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    html, resolved_url = await _fetch_preview_html(source_url)
    state = _kakuyomu_state_from_html(html)
    work_id = _kakuyomu_work_id_from_url(source_url)
    if not work_id:
        raise ValueError("无法识别 Kakuyomu 作品编号")
    work = _kakuyomu_work_from_state(state, work_id)
    title = str(work.get("title") or payload.title or "未命名小说").strip()
    author = _kakuyomu_author_from_state(state, work)
    synopsis = _kakuyomu_synopsis_from_work(work)
    cover = str(work.get("adminCoverImageUrl") or work.get("ogImageUrl") or "").strip() or None
    chapters = _kakuyomu_chapters_from_state(state, work_id, work)
    if not chapters and work.get("firstPublicEpisodeUnion"):
        first_ref = work["firstPublicEpisodeUnion"].get("__ref")
        first_episode = state.get(str(first_ref or ""))
        if isinstance(first_episode, dict):
            episode_id = str(first_episode.get("id") or "").strip()
            episode_title = str(first_episode.get("title") or title).strip()
            if episode_id:
                chapters = [ChapterPreview(title=episode_title, url=f"{_build_origin(resolved_url)}/works/{work_id}/episodes/{episode_id}")]

    return PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def _preview_syosetu(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    html, resolved_url = await _fetch_site_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名小说"
    title = _clean_title_suffix(_extract_title(soup, fallback_title), (" - 小説家になろう",))
    synopsis_node = soup.select_one(".p-novel__summary")
    synopsis = synopsis_node.get_text(" ", strip=True) if synopsis_node else _extract_synopsis(soup)
    author = None
    for selector in ("meta[name='twitter:creator']", ".p-novel__author", ".novel_writername"):
        node = soup.select_one(selector)
        if node is None:
            continue
        author = (str(node.get("content") or "").strip() if node.name == "meta" else node.get_text(" ", strip=True))
        if author:
            break
    cover = _extract_cover(soup, resolved_url)
    chapters = _syosetu_chapters_from_soup(soup, resolved_url)
    if not chapters:
        chapters = [ChapterPreview(title=title, url=resolved_url)]

    return PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def _preview_pixiv(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    normalized = _normalize_source_url(source_url)
    async with _build_http_client() as client:
        series_id = _pixiv_series_id_from_url(normalized)
        if series_id:
            series_result = await _fetch_json(
                client,
                f"https://www.pixiv.net/ajax/novel/series/{series_id}",
                _pixiv_api_headers(normalized),
            )
            titles_result = await _fetch_json(
                client,
                f"https://www.pixiv.net/ajax/novel/series/{series_id}/content_titles",
                _pixiv_api_headers(normalized),
            )
            body = series_result["body"]
            title_items = titles_result["body"]
            if not isinstance(body, dict) or not isinstance(title_items, list):
                raise ValueError("Pixiv 系列接口返回异常")
            chapters = [
                ChapterPreview(
                    title=str(item.get("title") or f"章节 {index}"),
                    url=f"https://www.pixiv.net/novel/show.php?id={item.get('id')}",
                )
                for index, item in enumerate(title_items, start=1)
                if isinstance(item, dict) and item.get("available") and str(item.get("id") or "").strip()
            ]
            return PreviewResponse(
                title=str(body.get("title") or payload.title or "未命名小说").strip(),
                author=str(body.get("userName") or "").strip() or None,
                synopsis=str(body.get("caption") or "").strip(),
                cover=(
                    str(body.get("cover", {}).get("urls", {}).get("original") or "")
                    or str(body.get("cover", {}).get("urls", {}).get("1200x1200") or "")
                    or str(body.get("firstEpisode", {}).get("url") or "")
                    or None
                ),
                chapterCount=len(chapters),
                chapters=chapters or [ChapterPreview(title=str(body.get("title") or "未命名小说"), url=normalized)],
            )

        novel_id = _pixiv_novel_id_from_url(normalized)
        if not novel_id:
            raise ValueError("无法识别 Pixiv 小说编号")
        novel_result = await _fetch_json(
            client,
            f"https://www.pixiv.net/ajax/novel/{novel_id}",
            _pixiv_api_headers(normalized),
        )
        body = novel_result["body"]
        if not isinstance(body, dict):
            raise ValueError("Pixiv 小说接口返回异常")
        title = str(body.get("title") or payload.title or "未命名小说").strip()
        return PreviewResponse(
            title=title,
            author=str(body.get("userName") or "").strip() or None,
            synopsis=str(body.get("description") or "").strip(),
            cover=str(body.get("coverUrl") or "").strip() or None,
            chapterCount=1,
            chapters=[ChapterPreview(title=title, url=normalized)],
        )


async def _preview_hameln(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    html, resolved_url = await _fetch_site_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名小说"
    title = _clean_title_suffix(_extract_title(soup, fallback_title), (" - ハーメルン",))
    synopsis = _extract_synopsis(soup)
    author = _hameln_author_from_soup(soup) or _extract_author(soup)
    cover = _extract_cover(soup, resolved_url)
    chapters = _hameln_chapters_from_soup(soup, resolved_url)
    if not chapters:
        chapters = [ChapterPreview(title=title, url=resolved_url)]
    return PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def _preview_novelup(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    try:
        html, resolved_url = await _fetch_site_html(source_url)
    except Exception as exc:
        try:
            snapshot = await _fetch_with_edge_cdp(
                source_url,
                headless=True,
                ready_expression="""
                    (() => {
                        const title = document.title || '';
                        const bodyText = document.body?.innerText || '';
                        return Boolean(title) && !title.includes('ERROR: The request could not be satisfied') && !bodyText.includes('403 ERROR');
                    })()
                """,
                blocked_message="Novelup 当前访问被 CloudFront 拦截（403），当前环境下即使使用浏览器会话也无法直接访问该站点。",
            )
            html, resolved_url = snapshot.html, snapshot.resolved_url
        except Exception as browser_exc:
            raise ValueError("Novelup 当前访问被 CloudFront 拦截（403），当前环境下即使使用浏览器会话也无法直接访问该站点。") from browser_exc
    soup = BeautifulSoup(html, "html.parser")
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名小说"
    title = _extract_title(soup, fallback_title)
    chapters = _extract_chapters(soup, resolved_url) or [ChapterPreview(title=title, url=resolved_url)]
    return PreviewResponse(
        title=title,
        author=_extract_author(soup),
        synopsis=_extract_synopsis(soup),
        cover=_extract_cover(soup, resolved_url),
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def _fetch_alphapolis_preview_html(source_url: str) -> tuple[str, str]:
    snapshot = await _fetch_with_edge_cdp(
        source_url,
        headless=True,
        ready_expression="""
            (() => {
                const html = document.documentElement.outerHTML || '';
                return Boolean(document.querySelector('#app-cover-data')) && !html.includes('window.gokuProps');
            })()
        """,
        blocked_message="Alphapolis 当前浏览器会话仍被 AWS WAF 拦截，暂时无法抓取该作品目录。",
    )
    return snapshot.html, snapshot.resolved_url


async def _fetch_alphapolis_chapter_html(chapter_url: str) -> tuple[str, str]:
    snapshot = await _fetch_with_edge_cdp(
        chapter_url,
        headless=False,
        ready_expression="""
            (() => {
                const html = document.documentElement.outerHTML || '';
                if (html.includes('window.gokuProps')) return false;
                const body = document.querySelector('#novelBody');
                if (!body) return false;
                const inner = body.innerHTML || '';
                const text = body.innerText || '';
                const imageCount = body.querySelectorAll('img').length;
                const blocked = inner.includes('g-recaptcha') || inner.includes('LoadingEpisode');
                return !blocked && (text.trim().length >= 20 || imageCount > 0);
            })()
        """,
        blocked_message="Alphapolis 章节正文当前仍然触发验证码或防护，暂时无法自动抓取。",
    )
    return snapshot.html, snapshot.resolved_url


async def _preview_alphapolis(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    html, resolved_url = await _fetch_alphapolis_preview_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    cover_data = _alphapolis_cover_data_from_html(html)
    content = cover_data.get("content") if isinstance(cover_data.get("content"), dict) else {}
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名小说"
    title = str(content.get("title") or "").strip() or _clean_title_suffix(
        _extract_title(soup, fallback_title),
        (" | 小説投稿サイトのアルファポリス",),
    )
    author = None
    user = content.get("user") if isinstance(content, dict) else None
    if isinstance(user, dict):
        author = str(user.get("name") or "").strip() or None
    if not author:
        author = _extract_author(soup)
    cover = str(content.get("coverImageUrl") or "").strip() if isinstance(content, dict) else ""
    cover = urljoin(resolved_url, cover) if cover else _extract_cover(soup, resolved_url)
    chapters = _alphapolis_chapters_from_cover_data(cover_data, resolved_url) or [ChapterPreview(title=title, url=resolved_url)]
    return PreviewResponse(
        title=title,
        author=author,
        synopsis=_extract_synopsis(soup),
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def preview_from_url(payload: AddBookPayload) -> PreviewResponse:
    source_url = _normalize_source_url(str(payload.sourceUrl))
    if _is_kakuyomu_url(source_url):
        return await _preview_kakuyomu(source_url, payload)
    if _is_syosetu_url(source_url) or _is_novel18_url(source_url):
        return await _preview_syosetu(source_url, payload)
    if _is_pixiv_url(source_url):
        return await _preview_pixiv(source_url, payload)
    if _is_hameln_url(source_url):
        return await _preview_hameln(source_url, payload)
    if _is_novelup_url(source_url):
        return await _preview_novelup(source_url, payload)
    if _is_alphapolis_url(source_url):
        return await _preview_alphapolis(source_url, payload)

    html, resolved_url = await _fetch_preview_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名小说"
    title = _extract_title(soup, fallback_title)
    synopsis = _extract_synopsis(soup)
    author = _extract_author(soup)
    cover = _extract_cover(soup, resolved_url)
    chapters = _extract_chapters(soup, resolved_url)

    if not chapters:
        chapters = [ChapterPreview(title=title, url=resolved_url)]

    return PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def download_book(payload: AddBookPayload, preview: PreviewResponse, root_dir: Path) -> DownloadResult:
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', preview.title).strip() or "未命名小说"
    book_dir = root_dir / payload.language / safe_title
    book_dir.mkdir(parents=True, exist_ok=True)
    chapter_manifest: list[dict[str, str | int]] = []

    async with _build_http_client() as client:
        cover_file = await _download_cover_image(client, book_dir, preview.cover, str(payload.sourceUrl))
        if preview.chapters and _is_linovelib_url(preview.chapters[0].url):
            await _prime_linovelib_session(client, preview.chapters[0].url)
        for index, chapter in enumerate(preview.chapters, start=1):
            try:
                result = await _fetch_chapter_data(client, chapter.url, chapter.title)
                image_files = await _download_chapter_images(client, book_dir, index, result.image_urls, chapter.url)
            except Exception as exc:
                result = ChapterFetchResult(
                    text=f"章节抓取失败：{exc}\n原始链接：{chapter.url}",
                    image_urls=[],
                    illustration=False,
                )
                image_files = []

            safe_chapter_title = re.sub(r'[\\/:*?"<>|]', '_', chapter.title)[:80]
            filename = f"{index:04d}-{safe_chapter_title}.txt"
            (book_dir / filename).write_text(result.text, encoding="utf-8")
            chapter_manifest.append(
                {
                    "index": index,
                    "title": chapter.title,
                    "url": chapter.url,
                    "file_name": filename,
                    "downloaded": True,
                    "translated": False,
                    "translated_file_name": None,
                    "illustration": result.illustration,
                    "image_urls": result.image_urls,
                    "image_files": image_files,
                }
            )

    manifest = {
        "title": preview.title,
        "author": preview.author,
        "source_url": str(payload.sourceUrl),
        "book_kind": payload.bookKind,
        "language": payload.language,
        "need_translation": payload.needTranslation,
        "synopsis": preview.synopsis,
        "cover_url": preview.cover,
        "cover_file": cover_file,
        "chapter_count": len(chapter_manifest),
        "chapters": chapter_manifest,
    }
    save_manifest(book_dir, manifest)

    return DownloadResult(
        title=preview.title,
        synopsis=preview.synopsis,
        cover=cover_file or preview.cover,
        chapters=preview.chapters,
        local_path=book_dir,
    )


def _chapter_lookup(manifest: dict) -> dict[int, dict]:
    chapters = manifest.get("chapters", [])
    if not isinstance(chapters, list):
        return {}

    lookup: dict[int, dict] = {}
    for item in chapters:
        if not isinstance(item, dict):
            continue
        chapter_index = item.get("index")
        if isinstance(chapter_index, int):
            lookup[chapter_index] = item
    return lookup


def _extract_text_from_blocks(nodes: list[BeautifulSoup]) -> str:
    blocks: list[str] = []
    for node in nodes:
        text = node.get_text("\n", strip=True)
        if not text:
            continue
        blocks.append(text)
    return "\n\n".join(block.strip() for block in blocks if block.strip()).strip()


async def _fetch_kakuyomu_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    response = await _get_html_response(client, chapter_url, referer=chapter_url)
    soup = BeautifulSoup(response.text, "html.parser")
    body = soup.select_one(".widget-episodeBody, .js-episode-body")
    if body is None:
        raise ValueError("未能从 Kakuyomu 页面提取出正文内容")
    for selector in ("script", "style", ".widget-toc", ".widget-episodeTitle"):
        for node in body.select(selector):
            node.decompose()
    text = body.get_text("\n", strip=True)
    image_urls: list[str] = []
    for image in body.select("img"):
        for key in ("data-src", "src"):
            value = str(image.get(key) or "").strip()
            if value:
                absolute = urljoin(str(response.url), value)
                if absolute not in image_urls:
                    image_urls.append(absolute)
                break
    if not text and not image_urls:
        raise ValueError("未能从 Kakuyomu 页面提取出正文内容")
    illustration = _is_illustration_chapter(chapter_title)
    if not text and image_urls:
        text = _format_illustration_text(chapter_title or "插图", image_urls)
        illustration = True
    elif image_urls and illustration:
        text = _append_image_links(text, image_urls)
    return ChapterFetchResult(text=text, image_urls=image_urls, illustration=illustration)


async def _fetch_syosetu_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    html, resolved_url = await _fetch_site_html(chapter_url, referer=_normalize_source_url(chapter_url))
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select(".p-novel__text")
    if not blocks:
        body = soup.select_one("#novel_honbun")
        if body is not None:
            blocks = [body]
    text = _extract_text_from_blocks(blocks)
    if not text:
        raise ValueError("未能从成为小说家吧页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=[], illustration=False)


async def _fetch_hameln_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    html, _ = await _fetch_site_html(chapter_url, referer=_normalize_source_url(chapter_url))
    soup = BeautifulSoup(html, "html.parser")
    text = _hameln_chapter_text(soup)
    if not text:
        raise ValueError("未能从 Hameln 页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=[], illustration=False)


async def _fetch_pixiv_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    novel_id = _pixiv_novel_id_from_url(chapter_url)
    if not novel_id:
        raise ValueError("无法识别 Pixiv 小说编号")
    payload = await _fetch_json(client, f"https://www.pixiv.net/ajax/novel/{novel_id}", _pixiv_api_headers(chapter_url))
    body = payload["body"]
    if not isinstance(body, dict):
        raise ValueError("Pixiv 小说接口返回异常")
    text = _pixiv_content_to_text(str(body.get("content") or ""))
    image_urls = _extract_pixiv_image_urls(body)
    illustration = _is_illustration_chapter(chapter_title)
    if not text and image_urls:
        text = _format_illustration_text(chapter_title or str(body.get("title") or "插图"), image_urls)
        illustration = True
    elif image_urls and illustration:
        text = _append_image_links(text, image_urls)
    if not text:
        raise ValueError("未能从 Pixiv 页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=image_urls, illustration=illustration)


async def _fetch_alphapolis_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    html, resolved_url = await _fetch_alphapolis_chapter_html(chapter_url)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("#novelBody")
    if body is None:
        raise ValueError("未能在 Alphapolis 页面中找到正文容器")

    for selector in ("script", "style", ".dots-indicator", ".g-recaptcha", "#LoadingEpisode"):
        for node in body.select(selector):
            node.decompose()

    image_urls: list[str] = []
    for image in body.select("img"):
        for key in ("data-src", "data-original", "src"):
            value = str(image.get(key) or "").strip()
            if value:
                absolute_url = urljoin(resolved_url, value)
                if absolute_url not in image_urls:
                    image_urls.append(absolute_url)
                break

    text = body.get_text("\n", strip=True)
    illustration = _is_illustration_chapter(chapter_title)
    if not text and image_urls:
        text = _format_illustration_text(chapter_title or "插图", image_urls)
        illustration = True
    elif image_urls and illustration:
        text = _append_image_links(text, image_urls)
    if not text and not image_urls:
        raise ValueError("未能从 Alphapolis 页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=image_urls, illustration=illustration)


async def _fetch_chapter_data(client: httpx.AsyncClient, chapter_url: str, chapter_title: str = "") -> ChapterFetchResult:
    try:
        if _is_linovelib_url(chapter_url):
            return await _fetch_linovelib_chapter_data(client, chapter_url, chapter_title)
        if _is_kakuyomu_url(chapter_url):
            return await _fetch_kakuyomu_chapter_data(client, chapter_url, chapter_title)
        if _is_syosetu_url(chapter_url) or _is_novel18_url(chapter_url):
            return await _fetch_syosetu_chapter_data(client, chapter_url, chapter_title)
        if _is_pixiv_url(chapter_url):
            return await _fetch_pixiv_chapter_data(client, chapter_url, chapter_title)
        if _is_hameln_url(chapter_url):
            return await _fetch_hameln_chapter_data(client, chapter_url, chapter_title)
        if _is_novelup_url(chapter_url):
            raise ValueError("Novelup 当前访问被 CloudFront 拦截（403），当前环境下即使使用浏览器会话也无法直接抓取章节。")
        if _is_alphapolis_url(chapter_url):
            return await _fetch_alphapolis_chapter_data(client, chapter_url, chapter_title)

        response = await client.get(chapter_url, headers=_request_headers(chapter_url))
        response.raise_for_status()
        _raise_if_blocked(response.text, chapter_url)
        soup = BeautifulSoup(response.text, "html.parser")
        text = "\n".join(
            item.get_text(" ", strip=True)
            for item in soup.select("p")
            if item.get_text(" ", strip=True)
        ).strip()
        if text:
            return ChapterFetchResult(text=text, image_urls=[], illustration=False)
        return ChapterFetchResult(text=soup.get_text("\n", strip=True)[:15000], image_urls=[], illustration=False)
    except Exception as exc:
        return ChapterFetchResult(
            text=f"章节抓取失败：{exc}\n原始链接：{chapter_url}",
            image_urls=[],
            illustration=False,
        )


def _is_probable_linovelib_page(soup: BeautifulSoup) -> bool:
    return bool(
        soup.select_one("#volumes")
        or soup.select_one("#volume-list")
        or soup.select_one(".volume-list")
        or soup.select_one("#acontent")
        or soup.select_one("#TextContent")
        or soup.select_one("[property='og:novel:book_name']")
    )


def _request_headers(url: str, referer: str | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    parsed = urlparse(url)
    headers["Referer"] = referer or f"{parsed.scheme}://{parsed.netloc}/"
    headers["Sec-Fetch-Site"] = "same-origin" if referer else "none"
    if _is_syosetu_url(url) or _is_novel18_url(url) or _is_hameln_url(url):
        headers["Accept-Encoding"] = "identity"
        headers["Accept-Language"] = "ja,en;q=0.9"
    if _is_pixiv_url(url):
        headers["Accept-Language"] = "ja,en;q=0.9"
    return headers


def _build_http_client() -> httpx.AsyncClient:
    try:
        client = httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=DEFAULT_HEADERS, http2=True)
    except ImportError:
        client = httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=DEFAULT_HEADERS)
    client.cookies.set("over18", "yes", domain=".syosetu.com")
    client.cookies.set("over18", "yes", domain=".novel18.syosetu.com")
    return client


async def _throttle_linovelib_request(url: str) -> None:
    if not _is_linovelib_url(url):
        return

    host = (urlparse(url).hostname or "").lower()
    last_request_at = _HOST_LAST_REQUEST_AT.get(host)
    now = time.monotonic()
    if last_request_at is not None:
        wait_seconds = LINOVELIB_MIN_REQUEST_INTERVAL - (now - last_request_at)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
    _HOST_LAST_REQUEST_AT[host] = time.monotonic()


def _retry_wait_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "").strip()
    if retry_after:
        try:
            return max(1.0, min(30.0, float(int(retry_after))))
        except ValueError:
            try:
                retry_after_at = parsedate_to_datetime(retry_after)
                wait_seconds = retry_after_at.timestamp() - time.time()
                if wait_seconds > 0:
                    return min(30.0, wait_seconds)
            except Exception:
                pass

    return min(12.0, 1.5 * (2**attempt))


async def _prime_linovelib_session(client: httpx.AsyncClient, url: str) -> None:
    if not _is_linovelib_url(url):
        return

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}/"
    try:
        await _throttle_linovelib_request(origin)
        await client.get(origin, headers=_request_headers(origin))
    except Exception:
        return


async def _get_html_response(
    client: httpx.AsyncClient,
    url: str,
    referer: str | None = None,
) -> httpx.Response:
    if not _is_linovelib_url(url):
        response = await client.get(url, headers=_request_headers(url, referer=referer))
        response.raise_for_status()
        _raise_if_blocked(response.text, str(response.url))
        return response

    last_response: httpx.Response | None = None
    for attempt in range(LINOVELIB_MAX_RETRIES):
        await _throttle_linovelib_request(url)
        response = await client.get(url, headers=_request_headers(url, referer=referer))
        last_response = response

        if response.status_code == 403:
            await _prime_linovelib_session(client, url)

        if response.status_code in LINOVELIB_RETRYABLE_STATUS_CODES and attempt < LINOVELIB_MAX_RETRIES - 1:
            await asyncio.sleep(_retry_wait_seconds(response, attempt))
            continue

        response.raise_for_status()
        _raise_if_blocked(response.text, str(response.url))
        return response

    if last_response is not None:
        last_response.raise_for_status()
    raise ValueError(f"请求失败：{url}")


async def _get_binary_response(
    client: httpx.AsyncClient,
    url: str,
    referer: str | None = None,
) -> httpx.Response:
    if not _is_linovelib_url(url):
        response = await client.get(url, headers=_image_request_headers(url, referer or url))
        response.raise_for_status()
        return response

    last_response: httpx.Response | None = None
    for attempt in range(LINOVELIB_MAX_RETRIES):
        await _throttle_linovelib_request(url)
        response = await client.get(url, headers=_image_request_headers(url, referer or url))
        last_response = response

        if response.status_code in LINOVELIB_RETRYABLE_STATUS_CODES and attempt < LINOVELIB_MAX_RETRIES - 1:
            await asyncio.sleep(_retry_wait_seconds(response, attempt))
            continue

        response.raise_for_status()
        return response

    if last_response is not None:
        last_response.raise_for_status()
    raise ValueError(f"资源请求失败：{url}")


def _raise_if_blocked(html: str, url: str) -> None:
    if any(marker in html for marker in LINOVELIB_BLOCK_MARKERS):
        raise ValueError(
            "目标站点启用了 Cloudflare 防护，当前请求被拦截。"
            f"链接：{url}。建议先在浏览器中确认该页面可访问，或改用可直接访问的目录页。"
        )


async def _fetch_preview_html(source_url: str) -> tuple[str, str]:
    candidates = _linovelib_candidate_urls(source_url) if _is_linovelib_url(source_url) else [source_url]
    last_error: Exception | None = None

    async with _build_http_client() as client:
        for candidate in candidates:
            try:
                response = await _get_html_response(client, candidate)
                return response.text, str(response.url)
            except Exception as exc:
                last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError(f"无法读取目录页：{source_url}")


async def _fetch_linovelib_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    page_url = chapter_url
    parts: list[str] = []
    image_urls: list[str] = []
    visited: set[str] = set()

    while page_url and page_url not in visited:
        visited.add(page_url)
        response = await _get_html_response(client, page_url, referer=chapter_url)
        soup = BeautifulSoup(response.text, "html.parser")
        text = _extract_linovelib_page_text(soup)
        if text:
            parts.append(text)
        for image_url in _extract_linovelib_image_urls(soup, str(response.url)):
            if image_url not in image_urls:
                image_urls.append(image_url)

        next_page = _extract_linovelib_next_page(response.text, str(response.url))
        if not next_page or not _same_linovelib_chapter(chapter_url, next_page):
            break
        page_url = next_page

    merged = "\n\n".join(part for part in parts if part.strip()).strip()
    illustration = _is_illustration_chapter(chapter_title)
    if not merged and image_urls:
        merged = _format_illustration_text(chapter_title or "插图", image_urls)
        illustration = True
    elif image_urls and illustration:
        merged = _append_image_links(merged, image_urls)

    if merged:
        return ChapterFetchResult(text=merged, image_urls=image_urls, illustration=illustration)

    raise ValueError("未能从轻小说页面提取出正文内容")


def _extract_linovelib_page_text(soup: BeautifulSoup) -> str:
    content_node = soup.select_one("#acontent, #TextContent, .read-content")
    if content_node is None:
        return ""

    for selector in (".cgo", "script", "style", "#footlink", ".mlfy_page"):
        for node in content_node.select(selector):
            node.decompose()

    text = content_node.get_text("\n", strip=True)
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if any(marker in line for marker in NOISE_LINE_MARKERS):
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def _extract_linovelib_image_urls(soup: BeautifulSoup, current_url: str) -> list[str]:
    content_node = soup.select_one("#acontent, #TextContent, .read-content")
    if content_node is None:
        return []

    urls: list[str] = []
    for image in content_node.select("img"):
        for key in ("data-src", "data-original", "src"):
            value = image.get(key)
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized or normalized.endswith("sloading.svg"):
                continue
            absolute_url = urljoin(current_url, normalized)
            if absolute_url not in urls:
                urls.append(absolute_url)
            break
    return urls


def _extract_linovelib_next_page(html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select(".mlfy_page a[href], #footlink a[href]"):
        label = anchor.get_text(" ", strip=True)
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        if label in {"下一页", "下一頁"}:
            return urljoin(current_url, href)

    match = re.search(r"url_next\s*[:=]\s*'([^']+)'", html)
    if not match:
        match = re.search(r'url_next\s*[:=]\s*"([^"]+)"', html)
    if not match:
        return None

    candidate = match.group(1).strip()
    if not candidate:
        return None
    return urljoin(current_url, candidate)


def _same_linovelib_chapter(source_url: str, candidate_url: str) -> bool:
    source_match = LINOVELIB_CHAPTER_PATH_PATTERN.match(urlparse(source_url).path)
    candidate_match = LINOVELIB_CHAPTER_PATH_PATTERN.match(urlparse(candidate_url).path)
    if not source_match or not candidate_match:
        return False

    return (
        source_match.group("book_id") == candidate_match.group("book_id")
        and source_match.group("chapter_id") == candidate_match.group("chapter_id")
    )


def _is_illustration_chapter(chapter_title: str) -> bool:
    normalized = chapter_title.strip().lower()
    return any(keyword in normalized for keyword in ("插图", "插畫", "illustration"))


def _format_illustration_text(chapter_title: str, image_urls: list[str]) -> str:
    lines = [f"{chapter_title}（插图章节）", "", f"共收集到 {len(image_urls)} 张图片链接：", ""]
    lines.extend(image_urls)
    return "\n".join(lines).strip()


def _append_image_links(text: str, image_urls: list[str]) -> str:
    if not image_urls:
        return text
    if not text.strip():
        return "插图链接：\n" + "\n".join(image_urls)
    return f"{text.rstrip()}\n\n插图链接：\n" + "\n".join(image_urls)


async def _download_chapter_images(
    client: httpx.AsyncClient,
    book_dir: Path,
    chapter_index: int,
    image_urls: list[str],
    referer: str,
) -> list[str]:
    if not image_urls:
        return []

    images_dir = book_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    for image_number, image_url in enumerate(image_urls, start=1):
        extension = _image_extension_from_url(image_url)
        file_hash = md5(image_url.encode("utf-8")).hexdigest()[:10]
        filename = f"{chapter_index:04d}-{image_number:02d}-{file_hash}{extension}"
        target_path = images_dir / filename
        if not target_path.exists():
            response = await _get_binary_response(client, image_url, referer=referer)
            target_path.write_bytes(response.content)
        files.append(f"images/{filename}")

    return files


async def _download_cover_image(
    client: httpx.AsyncClient,
    book_dir: Path,
    cover_url: str | None,
    referer: str,
) -> str | None:
    if not cover_url:
        return None

    covers_dir = book_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    extension = _image_extension_from_url(cover_url)
    filename = f"cover{extension}"
    target_path = covers_dir / filename
    if not target_path.exists():
        response = await _get_binary_response(client, cover_url, referer=referer)
        target_path.write_bytes(response.content)
    return f"covers/{filename}"


def _image_extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return suffix
    return ".jpg"


def _image_request_headers(url: str, referer: str) -> dict[str, str]:
    headers = _request_headers(url, referer=referer)
    headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    return headers


async def _translate_text(
    client: httpx.AsyncClient,
    settings: TranslationSettings,
    source_language: str,
    title: str,
    content: str,
) -> str:
    provider = settings.defaultProvider
    provider_config = settings.providers[provider]
    prompt = (
        f"章节标题：{title}\n"
        f"原始语言：{source_language}\n"
        "正文如下：\n\n"
        f"{content}"
    )

    if provider == "anthropic":
        base_url = provider_config.baseUrl.rstrip("/")
        response = await client.post(
            f"{base_url}/messages",
            headers={
                "x-api-key": provider_config.apiKey,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": provider_config.model,
                "max_tokens": 8192,
                "system": settings.systemPrompt,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        payload = response.json()
        blocks = payload.get("content", [])
        parts = [block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
        text = "\n".join(part for part in parts if part).strip()
        if not text:
            raise ValueError("Anthropic 返回了空翻译结果")
        return text

    base_url = provider_config.baseUrl.rstrip("/")
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {provider_config.apiKey}",
            "Content-Type": "application/json",
        },
        json={
            "model": provider_config.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": settings.systemPrompt},
                {"role": "user", "content": prompt},
            ],
        },
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("翻译服务返回了空响应")

    message = choices[0].get("message", {})
    content_value = message.get("content", "")
    if isinstance(content_value, list):
        parts = [item.get("text", "") for item in content_value if isinstance(item, dict)]
        content_value = "\n".join(part for part in parts if part)
    text = str(content_value).strip()
    if not text:
        raise ValueError("翻译服务返回了空翻译结果")
    return text


