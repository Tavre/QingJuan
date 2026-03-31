from __future__ import annotations

import asyncio
import base64
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import ssl
import tempfile
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from hashlib import md5, sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

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
COMIC_18_HOST_KEYWORDS = ("18comic.vip",)
BIKAWEBAPP_HOST_KEYWORDS = ("bikawebapp.com",)
BUILTIN_MANGA_IMAGE_TIMEOUT_SECONDS = 1800
BUILTIN_MANGA_IMAGE_SUPPORTED_PROVIDERS = {"openai", "newapi", "grok2api", "custom"}
CHAT_COMPLETION_IMAGE_MODEL_HINTS = (
    "gpt-",
    "grok-",
    "claude-",
    "gemini",
    "qwen",
    "glm",
    "internvl",
    "llava",
    "minicpm",
)
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
COMIC_18_PATH_PATTERN = re.compile(r"^/(?P<kind>album|photo)/(?P<album_id>\d+)(?:/[^/?#]*)?/?$")
BIKA_COMIC_PATH_PATTERN = re.compile(r"^/comic/(?P<comic_id>[0-9a-fA-F]+)(?:/.*)?$", re.IGNORECASE)
BIKA_READER_PATH_PATTERN = re.compile(
    r"^/comic/reader/(?P<comic_id>[0-9a-fA-F]+)/(?P<order>\d+)(?:/[^/?#]*)?/?$",
    re.IGNORECASE,
)
LINOVELIB_BLOCK_MARKERS = (
    "Attention Required! | Cloudflare",
    "Sorry, you have been blocked",
)
NOISE_LINE_MARKERS = (
    "鍐呭鍔犺浇澶辫触",
    "鍏у鍔犺級澶辨晽",
    "請重載或更換瀏覽器",
    "请重载或更换浏览器",
    "缈婚〉妯″紡",
    "翻上页",
    "翻下页",
    "上一页",
    "下一页",
    "上一頁",
    "下一頁",
    "鐩綍",
    "鐩寗",
    "涔﹂〉",
    "鏇搁爜",
    "寤鸿浣跨敤涓婁笅缈婚〉",
    "寤鸿浣跨敤涓婁笅缈婚爜",
    "绔犺瘎",
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
BIKA_API_BASE_URL = "https://picaapi.go2778.com"
BIKA_API_ACCEPT = "application/vnd.picacomic.com.v1+json"
BIKA_APP_CHANNEL = "1"
BIKA_APP_UUID = "webUUIDv2"
BIKA_APP_VERSION = "20251017"
BIKA_APP_PLATFORM = "android"
BIKA_IMAGE_QUALITY = "medium"
BIKA_WEB_ORIGIN = "https://bikawebapp.com"
BIKA_WEB_REFERER = f"{BIKA_WEB_ORIGIN}/"
BIKA_RANDOM_ALPHABET = string.ascii_lowercase + string.digits
BIKA_SIGNATURE_SUFFIX = "C69BAF41DA5ABD1FFEDC6D2FEA56B"
BIKA_SIGNATURE_KEY = "~d}$Q7$eIni=V)9\\RK/P.RM4;9[7|@/CA}b~OW!3?EV`:<>M7pddUBL5n|0/*Cn"
_BIKA_TOKEN_CACHE: dict[str, str] = {}
_COMIC_18_SCRAMBLE_ID_CACHE: dict[str, int] = {}
MANGA_RENDERER_VERSION = 5

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


def _is_18comic_url(url: str) -> bool:
    return _host_matches(url, COMIC_18_HOST_KEYWORDS)


def _is_bikawebapp_url(url: str) -> bool:
    return _host_matches(url, BIKAWEBAPP_HOST_KEYWORDS)


def _is_manga_source_url(url: str) -> bool:
    return _is_18comic_url(url) or _is_bikawebapp_url(url)


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

    if _is_18comic_url(url):
        match = COMIC_18_PATH_PATTERN.match(parsed.path)
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/album/{match.group('album_id')}"
        return url

    if _is_bikawebapp_url(url):
        reader_match = BIKA_READER_PATH_PATTERN.match(parsed.path)
        if reader_match:
            return f"{parsed.scheme}://{parsed.netloc}/comic/{reader_match.group('comic_id')}"
        comic_match = BIKA_COMIC_PATH_PATTERN.match(parsed.path)
        if comic_match:
            return f"{parsed.scheme}://{parsed.netloc}/comic/{comic_match.group('comic_id')}"
        return url

    return url


def _resolved_preview_book_kind(url: str, payload: AddBookPayload) -> str:
    return "漫画" if _is_manga_source_url(url) else payload.bookKind


def _18comic_album_id_from_url(url: str) -> str | None:
    match = COMIC_18_PATH_PATTERN.match(urlparse(url).path)
    return match.group("album_id") if match else None


def _18comic_album_url(url: str) -> str:
    parsed = urlparse(_normalize_source_url(url))
    album_id = _18comic_album_id_from_url(url)
    if not album_id:
        raise ValueError("鏃犳硶璇嗗埆 18Comic 婕敾缂栧彿")
    return f"{parsed.scheme}://{parsed.netloc}/album/{album_id}"


def _18comic_photo_url(url: str) -> str:
    parsed = urlparse(url)
    album_id = _18comic_album_id_from_url(url)
    if not album_id:
        raise ValueError("鏃犳硶璇嗗埆 18Comic 婕敾缂栧彿")
    return f"{parsed.scheme}://{parsed.netloc}/photo/{album_id}"

def _18comic_scramble_id_from_html(html: str) -> int | None:
    match = re.search(r"var\s+scramble_id\s*=\s*(\d+)", html)
    return int(match.group(1)) if match else None


def _18comic_cache_scramble_id(url: str, html: str) -> int | None:
    album_id = _18comic_album_id_from_url(url)
    scramble_id = _18comic_scramble_id_from_html(html)
    if album_id and scramble_id is not None:
        _COMIC_18_SCRAMBLE_ID_CACHE[album_id] = scramble_id
    return scramble_id


def _18comic_cached_scramble_id(url: str) -> int | None:
    album_id = _18comic_album_id_from_url(url)
    if not album_id:
        return None
    return _COMIC_18_SCRAMBLE_ID_CACHE.get(album_id)


def _18comic_ensure_scramble_id(url: str) -> int | None:
    cached = _18comic_cached_scramble_id(url)
    if cached is not None:
        return cached
    photo_url = url if '/photo/' in urlparse(url).path else _18comic_photo_url(url)
    album_url = _18comic_album_url(url)
    result = _sync_fetch_18comic_html(photo_url, album_url)
    return _18comic_cache_scramble_id(url, result.text)


def _18comic_image_token_from_url(url: str) -> str:
    return Path(urlparse(url).path).stem.split('.', 1)[0]


def _18comic_segment_count(album_id: str, image_token: str) -> int:
    default_segments = 10
    try:
        album_id_int = int(album_id)
    except ValueError:
        return default_segments
    digest_suffix = md5(f"{album_id}{image_token}".encode("utf-8")).hexdigest()[-1]
    value = ord(digest_suffix)
    if 268850 <= album_id_int <= 421925:
        value %= 10
    elif album_id_int >= 421926:
        value %= 8
    return {
        0: 2,
        1: 4,
        2: 6,
        3: 8,
        4: 10,
        5: 12,
        6: 14,
        7: 16,
        8: 18,
        9: 20,
    }.get(value, default_segments)


def _18comic_descramble_bytes(image_bytes: bytes, image_url: str, referer: str, scramble_id: int | None = None) -> bytes:
    if image_url.lower().endswith('.gif'):
        return image_bytes
    if "/media/photos/" not in urlparse(image_url).path:
        return image_bytes
    album_id = _18comic_album_id_from_url(referer)
    if not album_id:
        return image_bytes
    resolved_scramble_id = scramble_id if scramble_id is not None else _18comic_ensure_scramble_id(referer)
    if resolved_scramble_id is None:
        return image_bytes
    if int(album_id) < int(resolved_scramble_id):
        return image_bytes

    segment_count = _18comic_segment_count(album_id, _18comic_image_token_from_url(image_url))
    if segment_count <= 1:
        return image_bytes

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            source_format = (image.format or 'PNG').upper()
            working = image.copy()
    except UnidentifiedImageError:
        return image_bytes

    width, height = working.size
    block_height = height // segment_count
    remainder = height % segment_count
    if width <= 0 or height <= 0 or block_height <= 0:
        return image_bytes

    rebuilt = Image.new(working.mode, working.size)
    for index in range(segment_count):
        segment_height = block_height
        destination_y = block_height * index
        source_y = height - block_height * (index + 1) - remainder
        if index == 0:
            segment_height += remainder
        else:
            destination_y += remainder
        segment = working.crop((0, source_y, width, source_y + segment_height))
        rebuilt.paste(segment, (0, destination_y))

    output = BytesIO()
    save_kwargs: dict[str, Any] = {"format": source_format}
    if source_format == 'WEBP':
        save_kwargs.update({"lossless": True, "quality": 100, "method": 6})
    elif source_format in {'JPEG', 'JPG'}:
        if rebuilt.mode not in {'RGB', 'L'}:
            rebuilt = rebuilt.convert('RGB')
        save_kwargs.update({"quality": 95})
    rebuilt.save(output, **save_kwargs)
    return output.getvalue()


def repair_18comic_chapter_images(book_dir: Path, manifest: dict, chapter_index: int) -> bool:
    chapter = _chapter_lookup(manifest).get(chapter_index)
    if not chapter:
        return False

    chapter_url = str(chapter.get("url") or "").strip()
    if not _is_18comic_url(chapter_url):
        return False
    if chapter.get("images_repaired") is True:
        return False

    image_files = [item for item in chapter.get("image_files", []) if isinstance(item, str)]
    image_urls = [item for item in chapter.get("image_urls", []) if isinstance(item, str)]
    if not image_files or not image_urls:
        chapter["images_repaired"] = True
        save_manifest(book_dir, manifest)
        return True

    scramble_id = _18comic_ensure_scramble_id(chapter_url)
    if scramble_id is None:
        return False

    repaired = False
    for asset_path, image_url in zip(image_files, image_urls):
        target_path = (book_dir / asset_path).resolve()
        if not target_path.exists() or not target_path.is_file():
            continue
        original_bytes = target_path.read_bytes()
        descrambled_bytes = _18comic_descramble_bytes(original_bytes, image_url, chapter_url, scramble_id)
        if descrambled_bytes != original_bytes:
            target_path.write_bytes(descrambled_bytes)
            repaired = True

    chapter["images_repaired"] = True
    save_manifest(book_dir, manifest)
    return repaired



def _bika_comic_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    reader_match = BIKA_READER_PATH_PATTERN.match(parsed.path)
    if reader_match:
        return reader_match.group("comic_id")
    comic_match = BIKA_COMIC_PATH_PATTERN.match(parsed.path)
    return comic_match.group("comic_id") if comic_match else None


def _bika_order_from_url(url: str) -> str | None:
    match = BIKA_READER_PATH_PATTERN.match(urlparse(url).path)
    return match.group("order") if match else None


def _manga_placeholder_text(chapter_title: str, page_count: int) -> str:
    readable_count = max(page_count, 0)
    return f"{chapter_title}\n\n漫画章节，共 {readable_count} 页。"


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
    match = re.search(r"浣滆€匸:锛歖\s*([^\s]+)", body_text)
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
        "img[alt*='灏侀潰']",
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
        raise ValueError("Kakuyomu 椤甸潰缂哄皯 __NEXT_DATA__ 鏁版嵁")
    payload = json.loads(script.string)
    page_props = payload.get("props", {}).get("pageProps", {})
    state = page_props.get("__APOLLO_STATE__")
    if not isinstance(state, dict) or not state:
        raise ValueError("Kakuyomu 椤甸潰缂哄皯 __APOLLO_STATE__ 鏁版嵁")
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
        raise ValueError(str(payload.get("message") or "鐩爣绔欑偣杩斿洖閿欒"))
    body = payload.get("body")
    if not isinstance(body, (dict, list)):
        raise ValueError("鐩爣绔欑偣杩斿洖浜嗕笉鍙瘑鍒殑鏁版嵁缁撴瀯")
    return {"body": body, "url": str(response.url)}


def _pixiv_content_to_text(content: str) -> str:
    value = content.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("[newpage]", "\n\n")
    value = re.sub(r"\[\[rb:([^>]+)\s*>\s*([^\]]+)\]\]", r"\1(\2)", value)
    value = re.sub(r"\[\[jumpuri:([^>]+)\s*>\s*([^\]]+)\]\]", r"\1(\2)", value)
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
    match = re.search(r"浣滐細\s*([^\s脳]+)", text)
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
            parts.append(f"銆愬悗璁般€慭n{afterword_text}")
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


def build_translated_meta_filename(filename: str) -> str:
    chapter_path = Path(filename)
    return f"{chapter_path.stem}.translated.json"


def build_translated_image_asset_path(asset_path: str) -> str:
    image_path = Path(asset_path)
    translated_path = image_path.with_name(f"{image_path.stem}.translated.png")
    return translated_path.as_posix()


def chapter_text_path(book_dir: Path, filename: str) -> Path:
    return book_dir / filename


def translated_text_path(book_dir: Path, filename: str) -> Path:
    return book_dir / build_translated_filename(filename)


def translated_meta_path(book_dir: Path, filename: str) -> Path:
    return book_dir / build_translated_meta_filename(filename)


def _load_translated_page_metadata(book_dir: Path, filename: str) -> dict[str, Any]:
    payload_path = translated_meta_path(book_dir, filename)
    if not payload_path.exists():
        return {}
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_translated_page_payload(book_dir: Path, filename: str) -> list[str]:
    payload = _load_translated_page_metadata(book_dir, filename)
    page_translations = payload.get("page_translations")
    if not isinstance(page_translations, list):
        return []
    return [str(item).strip() for item in page_translations if isinstance(item, str)]


def translated_image_payload_is_current(book_dir: Path, filename: str) -> bool:
    payload = _load_translated_page_metadata(book_dir, filename)
    try:
        renderer_version = int(payload.get("renderer_version") or 0)
    except (TypeError, ValueError):
        renderer_version = 0
    return renderer_version >= MANGA_RENDERER_VERSION


def save_translated_page_payload(
    book_dir: Path,
    filename: str,
    page_translations: list[str],
    translated_image_files: list[str] | None = None,
) -> str:
    target_path = translated_meta_path(book_dir, filename)
    payload: dict[str, Any] = {
        "page_translations": page_translations,
        "renderer_version": MANGA_RENDERER_VERSION,
    }
    if translated_image_files:
        payload["translated_image_files"] = translated_image_files
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_path.name


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
    image_concurrency = _image_download_concurrency(str(manifest.get("source_url") or ""), concurrency)
    updated = False
    completed_count = 0
    total_count = len(selected_indexes)
    active_titles: dict[int, str] = {}
    semaphore = asyncio.Semaphore(concurrency)
    image_download_semaphore = asyncio.Semaphore(image_concurrency)

    async with _build_http_client() as client:
        async def worker(chapter_index: int) -> dict:
            chapter = chapter_lookup[chapter_index]
            chapter_title = str(chapter.get("title") or f"第{chapter_index}章")
            async with semaphore:
                active_titles[chapter_index] = chapter_title
                await _notify_download_progress(progress_callback, completed_count, total_count, list(active_titles.values()))
                try:
                    return await _download_single_chapter(
                        client,
                        book_dir,
                        chapter_index,
                        chapter,
                        image_download_semaphore=image_download_semaphore,
                    )
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
                chapter["translated_image_files"] = [
                    item for item in payload.get("translated_image_files", []) if isinstance(item, str)
                ]
                chapter["page_count"] = payload["page_count"]
                chapter["images_repaired"] = payload.get("images_repaired", chapter.get("images_repaired"))
                chapter["translated_file_name"] = chapter.get("translated_file_name") or build_translated_filename(
                    payload["file_name"]
                )
                chapter["translated_meta_file_name"] = chapter.get("translated_meta_file_name") or build_translated_meta_filename(
                    payload["file_name"]
                )
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
    *,
    image_download_semaphore: asyncio.Semaphore | None = None,
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
            "translated_image_files": [item for item in chapter.get("translated_image_files", []) if isinstance(item, str)],
            "page_count": int(chapter.get("page_count") or len(chapter.get("image_files", [])) or len(chapter.get("image_urls", [])) or 0),
            "images_repaired": bool(chapter.get("images_repaired")),
        }

    result = await _fetch_chapter_data(client, source_url, chapter_title)
    image_files = await _download_chapter_images(
        client,
        book_dir,
        chapter_index,
        result.image_urls,
        source_url,
        image_download_semaphore=image_download_semaphore,
    )
    existing_path.write_text(result.text, encoding="utf-8")
    return {
        "index": chapter_index,
        "file_name": filename,
        "downloaded": True,
        "illustration": result.illustration,
        "image_urls": result.image_urls,
        "image_files": image_files,
        "translated_image_files": [],
        "page_count": len(image_files) or len(result.image_urls),
        "images_repaired": _is_18comic_url(source_url),
    }


async def translate_selected_chapters(
    book_dir: Path,
    manifest: dict,
    chapter_indexes: list[int],
    language: str,
    settings: TranslationSettings,
    log_callback: Callable[[str, str], Awaitable[None] | None] | None = None,
) -> dict:
    chapter_lookup = _chapter_lookup(manifest)
    updated = False
    is_manga = str(manifest.get("book_kind") or "").strip() == "漫画"

    if is_manga:
        for chapter_index in chapter_indexes:
            chapter = chapter_lookup.get(chapter_index)
            if not chapter:
                continue
            filename = str(chapter.get("file_name") or f"{chapter_index:04d}-chapter-{chapter_index}.txt")
            source_path = chapter_text_path(book_dir, filename)
            if not source_path.exists():
                raise ValueError(f"章节未下载，无法翻译：{chapter_index}")
            translated_filename = build_translated_filename(filename)
            translated_meta_filename = build_translated_meta_filename(filename)
            source_title = str(chapter.get("title") or f"第{chapter_index}章")
            repair_18comic_chapter_images(book_dir, manifest, chapter_index)
            page_translations, translated_image_files = await _translate_manga_pages_with_command(
                settings=settings,
                target_language=language,
                chapter_index=chapter_index,
                title=source_title,
                image_files=[item for item in chapter.get("image_files", []) if isinstance(item, str)],
                book_dir=book_dir,
                log_callback=log_callback,
            )
            translated_text = _merge_page_translations(source_title, page_translations)
            save_translated_page_payload(book_dir, filename, page_translations, translated_image_files)
            chapter["translated_meta_file_name"] = translated_meta_filename
            chapter["translated_image_files"] = translated_image_files
            chapter["translated"] = True
            chapter["translated_file_name"] = translated_filename
            translated_text_path(book_dir, filename).write_text(translated_text, encoding="utf-8")
            updated = True
    else:
        provider = settings.defaultProvider
        provider_config = settings.providers[provider]
        if not provider_config.enabled:
            provider_config = provider_config.model_copy(update={"enabled": True})
        if not provider_config.baseUrl.strip():
            raise ValueError("翻译 API 地址未配置")
        if not provider_config.apiKey.strip():
            raise ValueError("翻译 API 密钥未配置")
        if not provider_config.model.strip():
            raise ValueError("翻译模型未配置")

        async with _create_async_http_client(timeout=120.0) as client:
            for chapter_index in chapter_indexes:
                chapter = chapter_lookup.get(chapter_index)
                if not chapter:
                    continue

                filename = str(chapter.get("file_name") or f"{chapter_index:04d}-chapter-{chapter_index}.txt")
                source_path = chapter_text_path(book_dir, filename)
                if not source_path.exists():
                    raise ValueError(f"章节未下载，无法翻译：{chapter_index}")

                translated_filename = build_translated_filename(filename)
                source_title = str(chapter.get("title") or f"第{chapter_index}章")
                source_text = source_path.read_text(encoding="utf-8")
                translated_text = await _translate_text(
                    client=client,
                    settings=settings,
                    target_language=language,
                    title=source_title,
                    content=source_text,
                )
                chapter["translated_image_files"] = []
                chapter["translated"] = True
                chapter["translated_file_name"] = translated_filename
                translated_text_path(book_dir, filename).write_text(translated_text, encoding="utf-8")
                updated = True

    if updated:
        save_manifest(book_dir, manifest)

    return manifest


async def _notify_task_log(
    log_callback: Callable[[str, str], Awaitable[None] | None] | None,
    level: str,
    message: str,
) -> None:
    if log_callback is None:
        return
    result = log_callback(level, message)
    if result is not None:
        await result


def _resolve_translation_target_language(language: str) -> str:
    normalized = str(language or "").strip()
    if normalized in {"中文", "英文", "日文"}:
        return normalized
    return "中文"


def _resolve_manga_image_provider_config(
    settings: TranslationSettings,
) -> tuple[str, str, str, str]:
    provider = str(settings.defaultProvider or "").strip() or "openai"
    if provider not in BUILTIN_MANGA_IMAGE_SUPPORTED_PROVIDERS:
        supported = " / ".join(sorted(BUILTIN_MANGA_IMAGE_SUPPORTED_PROVIDERS))
        raise ValueError(f"当前默认翻译提供商 {provider} 不支持漫画译图，请切换到 {supported}")

    provider_config = settings.providers.get(provider)
    if provider_config is None:
        raise ValueError(f"未找到翻译提供商配置：{provider}")

    base_url = str(provider_config.baseUrl or "").strip().rstrip("/")
    api_key = str(provider_config.apiKey or "").strip()
    configured_model = str(provider_config.model or "").strip()

    if provider == "openai" and not base_url:
        base_url = "https://api.openai.com/v1"
    if not base_url:
        raise ValueError("漫画译图接口地址未配置")
    if not api_key:
        raise ValueError("漫画译图 API 密钥未配置")
    if not configured_model:
        raise ValueError("漫画译图模型未配置")

    return provider, base_url, api_key, configured_model


def _build_manga_image_edit_prompt(
    *,
    target_language: str,
    chapter_title: str,
    chapter_index: int,
    page_number: int,
    total_pages: int,
) -> str:
    return (
        "Edit this manga page in place.\n"
        f"- Auto-detect the original language and translate all visible text into {target_language}.\n"
        "- Remove the original text completely and replace it with the translated text directly inside the image.\n"
        "- Keep panel layout, character art, bubble shapes, reading order, line art, screentone, and background unchanged.\n"
        "- Keep translated text inside the original bubble or caption region whenever possible.\n"
        "- Match the original text emphasis and approximate placement.\n"
        "- If a region has no readable text, keep that region unchanged.\n"
        "- Return exactly one fully edited manga page image.\n"
        f"Context: chapter_index={chapter_index}, chapter_title={chapter_title}, page={page_number}/{total_pages}"
    )


def _summarize_image_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            code = str(error.get("code") or "").strip()
            if message and code:
                return f"{message} ({code})"
            if message:
                return message
        detail = str(payload.get("detail") or payload.get("message") or "").strip()
        if detail:
            return detail

    text_value = response.text.strip()
    if text_value:
        return text_value[:400]
    return f"HTTP {response.status_code}"


def _decode_base64_image(value: str) -> bytes:
    raw_value = value.strip()
    if raw_value.startswith("data:") and "," in raw_value:
        raw_value = raw_value.split(",", 1)[1]
    return base64.b64decode(raw_value)


def _extract_image_bytes_from_payload(payload: dict[str, Any]) -> bytes | str:
    candidates: list[Any] = []
    for key in ("data", "images", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value is not None:
            candidates.append(value)

    for item in candidates:
        if isinstance(item, dict):
            b64_value = str(item.get("b64_json") or item.get("base64") or "").strip()
            if b64_value:
                return _decode_base64_image(b64_value)
            url_value = str(item.get("url") or "").strip()
            if url_value:
                return url_value
            result_value = str(item.get("result") or "").strip()
            if result_value:
                try:
                    return _decode_base64_image(result_value)
                except Exception:
                    if result_value.startswith("http://") or result_value.startswith("https://"):
                        return result_value
        elif isinstance(item, str):
            raw_item = item.strip()
            if not raw_item:
                continue
            try:
                return _decode_base64_image(raw_item)
            except Exception:
                if raw_item.startswith("http://") or raw_item.startswith("https://"):
                    return raw_item

    raise ValueError("漫画译图接口返回中未找到可用图片数据")


def _extract_image_bytes_from_text_body(body: str) -> bytes | str | None:
    value = str(body or "").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    try:
        return _decode_base64_image(value)
    except Exception:
        return None


def _should_use_chat_completions_image_fallback(model: str) -> bool:
    lowered = str(model or "").strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in ("image", "dall-e", "flux", "sd", "stable-diffusion", "wanx")):
        return False
    return any(token in lowered for token in CHAT_COMPLETION_IMAGE_MODEL_HINTS)


def _should_fallback_from_image_edit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "http 404" in message
        or "invalid url" in message
        or "/images/edits" in message
        or "bad_response_status_code" in message
        or "not found" in message
        or "405" in message
    )


def _strip_markdown_fences(value: str) -> str:
    text_value = str(value or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text_value)
        text_value = re.sub(r"\s*```$", "", text_value)
    return text_value.strip()


def _extract_json_object_from_text(value: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fences(value)
    if not cleaned:
        raise ValueError("模型未返回可解析的 JSON 内容")

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"模型返回不是有效 JSON：{cleaned[:240]}")
        payload = json.loads(cleaned[start : end + 1])

    if not isinstance(payload, dict):
        raise ValueError("模型返回的 JSON 顶层不是对象")
    return payload


def _normalize_region_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    width, height = image_size
    try:
        x1, y1, x2, y2 = [int(round(float(item))) for item in raw_bbox]
    except (TypeError, ValueError):
        return None

    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return x1, y1, x2, y2


def _parse_hex_color(value: Any) -> tuple[int, int, int] | None:
    text_value = str(value or "").strip()
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", text_value):
        return None
    normalized = text_value[1:] if text_value.startswith("#") else text_value
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))


def _sample_region_fill_color(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    preferred_color: Any = None,
) -> tuple[int, int, int]:
    parsed = _parse_hex_color(preferred_color)
    if parsed is not None:
        return parsed

    width, height = image.size
    x1, y1, x2, y2 = bbox
    padding = max(2, min((x2 - x1) // 8, (y2 - y1) // 8, 12))
    pixels: list[tuple[int, int, int]] = []
    rgb_image = image.convert("RGB")

    def append_strip(left: int, top: int, right: int, bottom: int) -> None:
        crop = rgb_image.crop((max(0, left), max(0, top), min(width, right), min(height, bottom)))
        pixels.extend(list(crop.getdata()))

    append_strip(x1 - padding, y1 - padding, x2 + padding, y1)
    append_strip(x1 - padding, y2, x2 + padding, y2 + padding)
    append_strip(x1 - padding, y1, x1, y2)
    append_strip(x2, y1, x2 + padding, y2)

    if not pixels:
        return (255, 255, 255)

    red = sum(color[0] for color in pixels) // len(pixels)
    green = sum(color[1] for color in pixels) // len(pixels)
    blue = sum(color[2] for color in pixels) // len(pixels)
    return red, green, blue


def _resolve_text_color(fill_color: tuple[int, int, int], preferred_color: Any = None) -> tuple[int, int, int]:
    parsed = _parse_hex_color(preferred_color)
    if parsed is not None:
        return parsed
    luminance = 0.299 * fill_color[0] + 0.587 * fill_color[1] + 0.114 * fill_color[2]
    return (24, 24, 24) if luminance >= 140 else (245, 245, 245)


def _local_render_font_paths() -> list[Path]:
    windows_fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return [
        windows_fonts_dir / "msyh.ttc",
        windows_fonts_dir / "msyhbd.ttc",
        windows_fonts_dir / "simhei.ttf",
        windows_fonts_dir / "simsun.ttc",
        windows_fonts_dir / "NotoSansCJK-Regular.ttc",
        windows_fonts_dir / "arial.ttf",
    ]


def _load_local_render_font(font_size: int) -> ImageFont.ImageFont:
    safe_size = max(10, int(font_size))
    for font_path in _local_render_font_paths():
        if not font_path.exists():
            continue
        try:
            return ImageFont.truetype(str(font_path), safe_size, encoding="utf-8")
        except Exception:
            continue
    return ImageFont.load_default()


VERTICAL_PUNCTUATION_MAP: dict[str, str] = {
    ",": "︐",
    "，": "︐",
    "、": "︑",
    ".": "︒",
    "。": "︒",
    ":": "︓",
    "：": "︓",
    ";": "︔",
    "；": "︔",
    "!": "︕",
    "！": "︕",
    "?": "︖",
    "？": "︖",
    "(": "︵",
    "（": "︵",
    ")": "︶",
    "）": "︶",
    "[": "﹇",
    "【": "︻",
    "]": "﹈",
    "】": "︼",
    "{": "︷",
    "}": "︸",
    "<": "︿",
    "《": "︽",
    ">": "﹀",
    "》": "︾",
    "「": "﹁",
    "」": "﹂",
    "『": "﹃",
    "』": "﹄",
    "“": "﹁",
    "”": "﹂",
    "‘": "﹃",
    "’": "﹄",
    "—": "︱",
    "－": "︱",
    "-": "︱",
    "_": "︳",
    "…": "︙",
}

VERTICAL_PUNCTUATION_OFFSET_RATIOS: dict[str, tuple[float, float]] = {
    "︐": (0.0, -0.10),
    "︑": (0.0, -0.10),
    "︒": (0.0, -0.14),
    "︓": (0.0, -0.08),
    "︔": (0.0, -0.08),
    "︕": (0.0, -0.06),
    "︖": (0.0, -0.06),
    "︙": (0.0, -0.05),
    "︱": (0.0, -0.02),
    "︳": (0.0, -0.02),
}


def _split_text_paragraphs(text: str) -> list[str]:
    content = str(text or "").replace("\r", "").strip()
    if not content:
        return []
    return [item.strip() for item in content.split("\n") if item.strip()]


def _normalize_vertical_text(text: str) -> str:
    content = str(text or "")
    if not content:
        return ""
    content = re.sub(r"(?:\.|．|。){3,}", "︙", content)
    content = content.replace("……", "︙")
    content = content.replace("...", "︙")
    normalized_chars: list[str] = []
    for raw_char in content:
        if raw_char == "\n":
            normalized_chars.append(raw_char)
            continue
        if raw_char.isspace():
            normalized_chars.append("　")
            continue
        normalized_chars.append(VERTICAL_PUNCTUATION_MAP.get(raw_char, raw_char))
    return "".join(normalized_chars)


def _measure_text_token(
    draw: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.ImageFont,
) -> dict[str, Any]:
    bbox = draw.textbbox((0, 0), token, font=font)
    return {
        "text": token,
        "bbox": bbox,
        "width": max(1, bbox[2] - bbox[0]),
        "height": max(1, bbox[3] - bbox[1]),
        "offset_ratio": VERTICAL_PUNCTUATION_OFFSET_RATIOS.get(token, (0.0, 0.0)),
    }


def _finalize_vertical_column(
    chars: list[dict[str, Any]],
    char_gap: int,
) -> dict[str, Any]:
    column_width = max((int(item.get("width") or 0) for item in chars), default=0)
    column_height = 0
    for index, item in enumerate(chars):
        if index:
            column_height += char_gap
        column_height += int(item.get("height") or 0)
    return {
        "chars": chars,
        "width": column_width,
        "height": column_height,
    }


def _balance_vertical_characters(
    chars: list[dict[str, Any]],
    char_gap: int,
    column_count: int,
) -> list[dict[str, Any]]:
    if not chars:
        return []
    if column_count <= 1:
        return [_finalize_vertical_column(chars, char_gap)]

    total_height = 0
    for index, item in enumerate(chars):
        if index:
            total_height += char_gap
        total_height += int(item.get("height") or 0)
    target_height = total_height / max(column_count, 1)

    columns: list[dict[str, Any]] = []
    start = 0
    total_chars = len(chars)
    while start < total_chars:
        remaining_columns = column_count - len(columns)
        remaining_chars = total_chars - start
        if remaining_columns <= 1:
            end = total_chars
        else:
            max_take = remaining_chars - (remaining_columns - 1)
            current_height = 0
            end = start
            while end < start + max_take:
                char_height = int(chars[end].get("height") or 0)
                candidate_height = current_height + (char_gap if end > start else 0) + char_height
                remaining_after = total_chars - (end + 1)
                if end > start and candidate_height > target_height and remaining_after >= remaining_columns - 1:
                    break
                current_height = candidate_height
                end += 1
                if current_height >= target_height and remaining_after >= remaining_columns - 1:
                    break
            if end <= start:
                end = start + 1
        columns.append(_finalize_vertical_column(chars[start:end], char_gap))
        start = end
    return columns


def _wrap_text_for_box(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    paragraphs = _split_text_paragraphs(text)
    if not paragraphs:
        return []

    lines: list[str] = []
    for paragraph in paragraphs:
        current = ""
        for raw_char in paragraph:
            char = " " if raw_char.isspace() else raw_char
            if not current and char == " ":
                continue
            candidate = f"{current}{char}"
            bbox = draw.textbbox((0, 0), candidate.rstrip(), font=font)
            if current and bbox[2] - bbox[0] > max_width:
                lines.append(current.rstrip())
                current = "" if char == " " else char
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
    return lines or [str(text or "").strip()]


def _normalize_layout_direction(
    preferred_direction: Any,
    box_size: tuple[int, int],
    text: str,
) -> str:
    normalized = str(preferred_direction or "").strip().lower()
    alias_map = {
        "v": "vertical",
        "vert": "vertical",
        "vertical": "vertical",
        "竖排": "vertical",
        "h": "horizontal",
        "hor": "horizontal",
        "horizontal": "horizontal",
        "横排": "horizontal",
    }
    resolved = alias_map.get(normalized)
    if resolved:
        return resolved

    box_width, box_height = box_size
    aspect_ratio = box_height / max(box_width, 1)
    dense_length = len(re.sub(r"\s+", "", str(text or "")))
    if aspect_ratio >= 2.2:
        return "vertical"
    if aspect_ratio >= 1.45 and dense_length <= 24:
        return "vertical"
    return "horizontal"


def _build_horizontal_layout_candidate(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_size: tuple[int, int],
    font_size: int,
) -> dict[str, Any]:
    max_width, max_height = box_size
    font = _load_local_render_font(font_size)
    lines = _wrap_text_for_box(draw, text, font, max(8, max_width))
    rendered_text = "\n".join(lines)
    spacing = max(1, min(12, font_size // 5))
    bbox = draw.multiline_textbbox((0, 0), rendered_text, font=font, spacing=spacing, align="center")
    content_width = max(0, bbox[2] - bbox[0])
    content_height = max(0, bbox[3] - bbox[1])
    safe_width = max_width * 0.94
    safe_height = max_height * 0.92
    overflow = max(0.0, content_width - safe_width) + max(0.0, content_height - safe_height)
    return {
        "direction": "horizontal",
        "font": font,
        "font_size": font_size,
        "lines": lines,
        "spacing": spacing,
        "content_width": content_width,
        "content_height": content_height,
        "fits": content_width <= safe_width and content_height <= safe_height,
        "overflow": overflow,
    }


def _build_vertical_columns(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_height: int,
    char_gap: int,
) -> list[dict[str, Any]]:
    paragraphs = _split_text_paragraphs(_normalize_vertical_text(text))
    if not paragraphs:
        return []

    columns: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        paragraph_chars = [_measure_text_token(draw, raw_char, font) for raw_char in paragraph if raw_char]
        if not paragraph_chars:
            continue

        column_count = 1
        balanced_columns = [_finalize_vertical_column(paragraph_chars, char_gap)]
        while column_count < len(paragraph_chars):
            balanced_columns = _balance_vertical_characters(paragraph_chars, char_gap, column_count)
            if balanced_columns and max(int(column.get("height") or 0) for column in balanced_columns) <= max_height:
                break
            column_count += 1
        else:
            balanced_columns = _balance_vertical_characters(paragraph_chars, char_gap, len(paragraph_chars))
        columns.extend(balanced_columns)
    return columns


def _build_vertical_layout_candidate(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_size: tuple[int, int],
    font_size: int,
) -> dict[str, Any]:
    max_width, max_height = box_size
    font = _load_local_render_font(font_size)
    char_gap = max(1, min(6, font_size // 8))
    column_gap = max(2, min(12, font_size // 4))
    columns = _build_vertical_columns(draw, text, font, max(8, max_height), char_gap)
    content_width = sum(int(column.get("width") or 0) for column in columns)
    if len(columns) > 1:
        content_width += column_gap * (len(columns) - 1)
    content_height = max((int(column.get("height") or 0) for column in columns), default=0)
    safe_width = max_width * 0.92
    safe_height = max_height * 0.92
    overflow = max(0.0, content_width - safe_width) + max(0.0, content_height - safe_height)
    return {
        "direction": "vertical",
        "font": font,
        "font_size": font_size,
        "columns": columns,
        "char_gap": char_gap,
        "column_gap": column_gap,
        "content_width": content_width,
        "content_height": content_height,
        "fits": bool(columns) and content_width <= safe_width and content_height <= safe_height,
        "overflow": overflow,
    }


def _fit_text_layout_for_direction(
    text: str,
    box_size: tuple[int, int],
    direction: str,
) -> dict[str, Any]:
    max_width, max_height = box_size
    scratch_image = Image.new("RGB", (max(max_width, 8), max(max_height, 8)), (255, 255, 255))
    draw = ImageDraw.Draw(scratch_image)
    size_limit = max_width * (2 if direction == "vertical" else 1)
    initial_size = max(12, min(60, max_height, size_limit))

    best_layout: dict[str, Any] | None = None
    for font_size in range(initial_size, 9, -1):
        if direction == "vertical":
            candidate = _build_vertical_layout_candidate(draw, text, box_size, font_size)
        else:
            candidate = _build_horizontal_layout_candidate(draw, text, box_size, font_size)
        if candidate["fits"]:
            return candidate
        if best_layout is None:
            best_layout = candidate
            continue
        candidate_key = (int(candidate["overflow"]), -int(candidate["font_size"]))
        best_key = (int(best_layout["overflow"]), -int(best_layout["font_size"]))
        if candidate_key < best_key:
            best_layout = candidate

    if best_layout is not None:
        return best_layout
    return _build_horizontal_layout_candidate(draw, text, box_size, 10)


def _fit_text_layout_to_box(
    text: str,
    box_size: tuple[int, int],
    preferred_direction: Any = None,
) -> dict[str, Any]:
    preferred = _normalize_layout_direction(preferred_direction, box_size, text)
    aspect_ratio = box_size[1] / max(box_size[0], 1)
    primary_layout = _fit_text_layout_for_direction(text, box_size, preferred)
    alternate_direction = "horizontal" if preferred == "vertical" else "vertical"
    alternate_layout = _fit_text_layout_for_direction(text, box_size, alternate_direction)

    if primary_layout["fits"]:
        if preferred == "vertical" and aspect_ratio >= 1.7:
            return primary_layout
        if alternate_layout["fits"] and int(alternate_layout["font_size"]) >= int(primary_layout["font_size"]) + 6:
            return alternate_layout
        return primary_layout
    if alternate_layout["fits"]:
        return alternate_layout
    return min(
        (primary_layout, alternate_layout),
        key=lambda item: (int(item["overflow"]), -int(item["font_size"]), item["direction"] != preferred),
    )


def _resolve_region_insets(
    region: dict[str, Any],
    bbox: tuple[int, int, int, int],
    direction: str,
) -> tuple[int, int]:
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    aspect_ratio = height / max(width, 1)

    padding_ratio: float | None = None
    try:
        padding_ratio = float(region.get("padding_ratio"))
    except (TypeError, ValueError):
        padding_ratio = None
    if padding_ratio is not None:
        padding_ratio = max(0.55, min(0.92, padding_ratio))

    if direction == "vertical":
        inset_x_ratio = 0.18 if aspect_ratio >= 2.6 else 0.15 if aspect_ratio >= 1.8 else 0.12
        inset_y_ratio = 0.08 if aspect_ratio >= 2.2 else 0.10
    else:
        inset_x_ratio = 0.10 if width >= height else 0.12
        inset_y_ratio = 0.12 if width >= height else 0.10

    if padding_ratio is not None:
        requested_margin = max(0.04, min(0.22, (1.0 - padding_ratio) / 2))
        inset_x_ratio = max(inset_x_ratio, requested_margin)
        inset_y_ratio = max(inset_y_ratio, requested_margin * (0.85 if direction == "vertical" else 1.0))

    inset_x = max(3, min(width // 3, int(round(width * inset_x_ratio))))
    inset_y = max(3, min(height // 3, int(round(height * inset_y_ratio))))
    if width - inset_x * 2 < 16:
        inset_x = max(1, (width - 16) // 2)
    if height - inset_y * 2 < 16:
        inset_y = max(1, (height - 16) // 2)
    return inset_x, inset_y


def _resolve_region_fill_shape(
    region: dict[str, Any],
    bbox: tuple[int, int, int, int],
    direction: str,
) -> str:
    normalized = str(region.get("shape") or "").strip().lower()
    alias_map = {
        "oval": "ellipse",
        "ellipse": "ellipse",
        "circle": "ellipse",
        "round": "roundrect",
        "rounded": "roundrect",
        "roundrect": "roundrect",
        "rounded_rectangle": "roundrect",
        "box": "rect",
        "rect": "rect",
        "rectangle": "rect",
    }
    if normalized in alias_map:
        return alias_map[normalized]

    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    aspect_ratio = max(width, height) / max(1, min(width, height))
    if direction == "vertical":
        return "ellipse"
    if aspect_ratio <= 1.45:
        return "ellipse"
    if aspect_ratio <= 2.8:
        return "roundrect"
    return "rect"


def _fill_region_background(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    fill_color: tuple[int, int, int],
    fill_shape: str,
) -> None:
    x1, y1, x2, y2 = bbox
    if fill_shape == "ellipse":
        draw.ellipse((x1, y1, x2, y2), fill=fill_color)
        return
    if fill_shape == "roundrect":
        radius = max(6, min((x2 - x1) // 2, (y2 - y1) // 2, 24))
        try:
            draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill_color)
            return
        except AttributeError:
            pass
    draw.rectangle((x1, y1, x2, y2), fill=fill_color)


def _color_distance_manhattan(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum(abs(int(left[index]) - int(right[index])) for index in range(3))


def _color_luminance(color: tuple[int, int, int]) -> float:
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


def _color_saturation(color: tuple[int, int, int]) -> int:
    return max(color) - min(color)


def _build_region_shape_mask(size: tuple[int, int], fill_shape: str) -> Image.Image:
    width, height = size
    mask = Image.new("L", (max(1, width), max(1, height)), 0)
    draw = ImageDraw.Draw(mask)
    left, top, right, bottom = 0, 0, max(0, width - 1), max(0, height - 1)
    if fill_shape == "ellipse":
        draw.ellipse((left, top, right, bottom), fill=255)
        return mask
    if fill_shape == "roundrect":
        radius = max(6, min((right - left) // 2, (bottom - top) // 2, 24))
        try:
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=255)
            return mask
        except AttributeError:
            pass
    draw.rectangle((left, top, right, bottom), fill=255)
    return mask


def _seed_positions_for_region(size: tuple[int, int]) -> list[tuple[int, int]]:
    width, height = size
    seed_offsets = (
        (0.50, 0.50),
        (0.50, 0.34),
        (0.50, 0.66),
        (0.34, 0.50),
        (0.66, 0.50),
        (0.38, 0.38),
        (0.62, 0.38),
        (0.38, 0.62),
        (0.62, 0.62),
        (0.50, 0.22),
        (0.50, 0.78),
    )
    points: list[tuple[int, int]] = []
    for ratio_x, ratio_y in seed_offsets:
        x = min(width - 1, max(0, int(round((width - 1) * ratio_x))))
        y = min(height - 1, max(0, int(round((height - 1) * ratio_y))))
        point = (x, y)
        if point not in points:
            points.append(point)
    return points


def _score_bubble_seed(
    pixel: tuple[int, int, int],
    fill_color: tuple[int, int, int],
) -> float:
    luminance = _color_luminance(pixel)
    fill_luminance = _color_luminance(fill_color)
    distance = _color_distance_manhattan(pixel, fill_color)
    if fill_luminance >= 170:
        return luminance * 1.4 - distance * 1.15 - _color_saturation(pixel) * 0.12
    return -distance * 1.1 - abs(luminance - fill_luminance) * 0.45 - _color_saturation(pixel) * 0.08


def _pixel_matches_bubble_fill(
    pixel: tuple[int, int, int],
    seed_color: tuple[int, int, int],
    fill_color: tuple[int, int, int],
) -> bool:
    fill_luminance = _color_luminance(fill_color)
    seed_luminance = _color_luminance(seed_color)
    pixel_luminance = _color_luminance(pixel)
    distance_from_fill = _color_distance_manhattan(pixel, fill_color)
    distance_from_seed = _color_distance_manhattan(pixel, seed_color)
    luminance_delta = abs(pixel_luminance - seed_luminance)
    saturation = _color_saturation(pixel)

    if fill_luminance >= 185:
        return (
            distance_from_seed <= 72
            or (
                distance_from_fill <= 112
                and pixel_luminance >= max(148.0, seed_luminance - 44.0)
                and saturation <= 100
            )
        )
    if fill_luminance >= 135:
        return distance_from_seed <= 62 or (distance_from_fill <= 90 and luminance_delta <= 48.0 and saturation <= 112)
    return distance_from_seed <= 56 or (distance_from_fill <= 78 and luminance_delta <= 36.0)


def _extract_precise_bubble_mask(
    image: Image.Image,
    bbox: tuple[int, int, int, int],
    fill_color: tuple[int, int, int],
    fill_shape: str,
) -> Image.Image:
    x1, y1, x2, y2 = bbox
    crop = image.crop((x1, y1, x2, y2)).convert("RGB")
    width, height = crop.size
    if width < 4 or height < 4:
        return _build_region_shape_mask((width, height), fill_shape)

    blur_radius = max(1.2, min(4.0, min(width, height) / 34.0))
    blurred = crop.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    blurred_pixels = blurred.load()
    shape_mask = _build_region_shape_mask((width, height), fill_shape)
    shape_pixels = shape_mask.load()

    seeds: list[tuple[float, int, int, tuple[int, int, int]]] = []
    for seed_x, seed_y in _seed_positions_for_region((width, height)):
        if shape_pixels[seed_x, seed_y] <= 0:
            continue
        seed_color = tuple(int(channel) for channel in blurred_pixels[seed_x, seed_y])
        seeds.append((_score_bubble_seed(seed_color, fill_color), seed_x, seed_y, seed_color))
    if not seeds:
        return shape_mask
    seeds.sort(key=lambda item: item[0], reverse=True)

    best_mask: Image.Image | None = None
    best_area = 0
    neighbor_offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for _, seed_x, seed_y, seed_color in seeds[:6]:
        if shape_pixels[seed_x, seed_y] <= 0:
            continue

        visited: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque([(seed_x, seed_y)])
        component_mask = Image.new("L", (width, height), 0)
        component_pixels = component_mask.load()
        area = 0

        while queue:
            current_x, current_y = queue.popleft()
            if (current_x, current_y) in visited:
                continue
            visited.add((current_x, current_y))

            if current_x < 0 or current_x >= width or current_y < 0 or current_y >= height:
                continue
            if shape_pixels[current_x, current_y] <= 0:
                continue

            current_color = tuple(int(channel) for channel in blurred_pixels[current_x, current_y])
            if not _pixel_matches_bubble_fill(current_color, seed_color, fill_color):
                continue

            if component_pixels[current_x, current_y] == 0:
                component_pixels[current_x, current_y] = 255
                area += 1
            for offset_x, offset_y in neighbor_offsets:
                queue.append((current_x + offset_x, current_y + offset_y))

        if area > best_area:
            best_mask = component_mask
            best_area = area

    min_area_ratio = 0.14 if fill_shape == "ellipse" else 0.10 if fill_shape == "roundrect" else 0.08
    min_area = max(24, int(width * height * min_area_ratio))
    if best_mask is None or best_area < min_area:
        return shape_mask

    expanded_mask = best_mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(3))
    inner_shape_kernel = 7 if fill_shape == "ellipse" else 5
    inner_shape_mask = shape_mask.filter(ImageFilter.MinFilter(inner_shape_kernel))
    refined_mask = ImageChops.multiply(ImageChops.lighter(expanded_mask, inner_shape_mask), shape_mask)
    if refined_mask.getbbox() is None:
        return shape_mask
    return refined_mask


def _resolve_mask_content_box(
    mask: Image.Image,
    fill_shape: str,
    direction: str,
) -> tuple[int, int, int, int] | None:
    mask_bbox = mask.getbbox()
    if mask_bbox is None:
        return None

    left, top, right, bottom = mask_bbox
    width = right - left
    height = bottom - top
    if width < 16 or height < 16:
        return None

    pixels = mask.load()
    row_ratio = 0.60 if fill_shape == "ellipse" else 0.42 if fill_shape == "roundrect" else 0.20
    col_ratio = 0.54 if fill_shape == "ellipse" else 0.42 if fill_shape == "roundrect" else 0.20
    if direction == "vertical" and fill_shape == "ellipse":
        row_ratio = 0.56
        col_ratio = 0.48

    row_widths: list[tuple[int, int]] = []
    max_row_width = 0
    for current_y in range(top, bottom):
        row_left: int | None = None
        row_right: int | None = None
        for current_x in range(left, right):
            if pixels[current_x, current_y] <= 0:
                continue
            if row_left is None:
                row_left = current_x
            row_right = current_x
        if row_left is None or row_right is None:
            continue
        row_width = row_right - row_left + 1
        row_widths.append((current_y, row_width))
        max_row_width = max(max_row_width, row_width)

    col_heights: list[tuple[int, int]] = []
    max_col_height = 0
    for current_x in range(left, right):
        column_top: int | None = None
        column_bottom: int | None = None
        for current_y in range(top, bottom):
            if pixels[current_x, current_y] <= 0:
                continue
            if column_top is None:
                column_top = current_y
            column_bottom = current_y
        if column_top is None or column_bottom is None:
            continue
        column_height = column_bottom - column_top + 1
        col_heights.append((current_x, column_height))
        max_col_height = max(max_col_height, column_height)

    if max_row_width <= 0 or max_col_height <= 0:
        return None

    qualified_rows = [
        current_y
        for current_y, row_width in row_widths
        if row_width >= max(8, int(round(max_row_width * row_ratio)))
    ]
    qualified_cols = [
        current_x
        for current_x, column_height in col_heights
        if column_height >= max(8, int(round(max_col_height * col_ratio)))
    ]

    if not qualified_rows or not qualified_cols:
        return mask_bbox

    content_left = qualified_cols[0]
    content_top = qualified_rows[0]
    content_right = qualified_cols[-1] + 1
    content_bottom = qualified_rows[-1] + 1

    content_width = content_right - content_left
    content_height = content_bottom - content_top
    pad_x = max(2, min(10, content_width // (9 if direction == "vertical" else 12)))
    pad_y = max(2, min(10, content_height // (12 if direction == "vertical" else 10)))

    content_left = min(content_right - 8, content_left + pad_x)
    content_top = min(content_bottom - 8, content_top + pad_y)
    content_right = max(content_left + 8, content_right - pad_x)
    content_bottom = max(content_top + 8, content_bottom - pad_y)

    if content_right - content_left < 16 or content_bottom - content_top < 16:
        return mask_bbox
    return content_left, content_top, content_right, content_bottom


def _apply_region_mask_fill(
    canvas: Image.Image,
    bbox: tuple[int, int, int, int],
    fill_color: tuple[int, int, int],
    mask: Image.Image,
) -> None:
    if mask.getbbox() is None:
        return
    x1, y1, x2, y2 = bbox
    fill_layer = Image.new("RGBA", (max(1, x2 - x1), max(1, y2 - y1)), fill_color + (255,))
    softened_mask = mask.filter(ImageFilter.GaussianBlur(radius=0.6))
    canvas.paste(fill_layer, (x1, y1), softened_mask)


def _render_text_layout(
    draw: ImageDraw.ImageDraw,
    region_left: int,
    region_top: int,
    box_size: tuple[int, int],
    layout: dict[str, Any],
    text_color: tuple[int, int, int],
) -> None:
    box_width, box_height = box_size
    font = layout["font"]
    direction = str(layout.get("direction") or "horizontal")

    if direction == "vertical":
        columns = [column for column in layout.get("columns", []) if column.get("chars")]
        if not columns:
            return
        total_width = int(layout.get("content_width") or 0)
        current_right = region_left + max(0, (box_width - total_width) / 2) + total_width
        column_gap = int(layout.get("column_gap") or 0)
        char_gap = int(layout.get("char_gap") or 0)
        for column in columns:
            column_width = int(column.get("width") or 0)
            column_height = int(column.get("height") or 0)
            column_left = current_right - column_width
            cursor_y = region_top + max(0, (box_height - column_height) / 2)
            for char_info in column.get("chars", []):
                char = str(char_info.get("text") or "")
                char_width = int(char_info.get("width") or 0)
                char_height = int(char_info.get("height") or 0)
                glyph_bbox = char_info.get("bbox") or draw.textbbox((0, 0), char, font=font)
                offset_x_ratio, offset_y_ratio = char_info.get("offset_ratio") or (0.0, 0.0)
                font_size = int(layout.get("font_size") or 0)
                char_x = column_left + max(0, (column_width - char_width) / 2) - glyph_bbox[0] + font_size * offset_x_ratio
                char_y = cursor_y - glyph_bbox[1] + font_size * offset_y_ratio
                draw.text((char_x, char_y), char, font=font, fill=text_color)
                cursor_y += char_height + char_gap
            current_right = column_left - column_gap
        return

    lines = [str(item) for item in layout.get("lines", []) if str(item).strip()]
    rendered_text = "\n".join(lines).strip()
    if not rendered_text:
        return
    spacing = int(layout.get("spacing") or 0)
    text_bbox = draw.multiline_textbbox(
        (0, 0),
        rendered_text,
        font=font,
        spacing=spacing,
        align="center",
    )
    text_width = max(0, text_bbox[2] - text_bbox[0])
    text_height = max(0, text_bbox[3] - text_bbox[1])
    text_x = region_left + max(0, (box_width - text_width) / 2) - text_bbox[0]
    text_y = region_top + max(0, (box_height - text_height) / 2) - text_bbox[1]
    draw.multiline_text(
        (text_x, text_y),
        rendered_text,
        font=font,
        fill=text_color,
        spacing=spacing,
        align="center",
    )


def _build_manga_chat_layout_prompt(
    *,
    target_language: str,
    image_size: tuple[int, int],
) -> str:
    width, height = image_size
    return (
        "You are a manga page translation layout analyzer. "
        f"Detect every readable text region and translate it into {target_language}. "
        "Return JSON only. Do not output markdown or explanations. "
        'JSON schema: {"regions":[{"bbox":[x1,y1,x2,y2],"source_text":"...","translation":"...","background":"#RRGGBB","text_color":"#RRGGBB","direction":"vertical|horizontal","align":"center","padding_ratio":0.72,"shape":"ellipse|roundrect|rect"}]}. '
        f"Coordinates must use the original image pixels. Original image size: {width}x{height}. "
        "Auto-detect the original language from the image. "
        "Prefer one region per speech bubble, caption box, or sound effect block. "
        "For tall speech bubbles, prefer direction=vertical. For wide speech bubbles or narration boxes, prefer direction=horizontal. "
        "padding_ratio must be a number between 0.55 and 0.90 describing the safe inner area for redrawing text. "
        "shape should describe the original bubble body when possible. "
        "translation must be ready to render directly inside the original bubble."
    )


async def _request_manga_chat_layout_payload(
    *,
    settings: TranslationSettings,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    target_language: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    with Image.open(image_path) as image:
        image_size = image.size
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = _build_manga_chat_layout_prompt(
        target_language=target_language,
        image_size=image_size,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 2400,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise manga OCR and translation layout assistant. Output valid JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mimetypes.guess_type(image_path.name)[0] or 'image/png'};base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    }
    async with _create_async_http_client(timeout=float(timeout_seconds), follow_redirects=True) as client:
        response_payload = await _post_translation_json(
            client,
            f"{base_url}/chat/completions",
            headers=headers,
            payload=payload,
        )

    choices = response_payload.get("choices", [])
    if not choices:
        raise ValueError("视觉翻译模型未返回任何候选结果")
    message = choices[0].get("message", {})
    content = _normalize_translation_result(message.get("content", ""))
    return _extract_json_object_from_text(content)


def _render_manga_chat_layout_to_image(
    image_path: Path,
    layout_payload: dict[str, Any],
) -> tuple[bytes, str]:
    regions = layout_payload.get("regions")
    if not isinstance(regions, list):
        raise ValueError("视觉翻译模型返回缺少 regions 数组")

    with Image.open(image_path) as source_image:
        canvas = source_image.convert("RGBA")

    draw = ImageDraw.Draw(canvas)
    rendered_translations: list[str] = []

    for region in regions:
        if not isinstance(region, dict):
            continue
        bbox = _normalize_region_bbox(region.get("bbox"), canvas.size)
        translation = str(region.get("translation") or "").strip()
        if bbox is None or not translation:
            continue

        fill_color = _sample_region_fill_color(canvas, bbox, region.get("background"))
        text_color = _resolve_text_color(fill_color, region.get("text_color"))
        x1, y1, x2, y2 = bbox
        preferred_direction = region.get("direction")
        initial_layout = _fit_text_layout_to_box(translation, (max(8, x2 - x1), max(8, y2 - y1)), preferred_direction)
        resolved_direction = str(initial_layout.get("direction") or "horizontal")
        fill_shape = _resolve_region_fill_shape(region, bbox, resolved_direction)
        bubble_mask = _extract_precise_bubble_mask(canvas, bbox, fill_color, fill_shape)
        _apply_region_mask_fill(canvas, bbox, fill_color, bubble_mask)
        draw = ImageDraw.Draw(canvas)

        content_box = _resolve_mask_content_box(bubble_mask, fill_shape, resolved_direction)
        if content_box is None:
            inset_x, inset_y = _resolve_region_insets(region, bbox, resolved_direction)
            text_left = x1 + inset_x
            text_top = y1 + inset_y
            box_width = max(8, x2 - x1 - inset_x * 2)
            box_height = max(8, y2 - y1 - inset_y * 2)
        else:
            text_left = x1 + content_box[0]
            text_top = y1 + content_box[1]
            box_width = max(8, content_box[2] - content_box[0])
            box_height = max(8, content_box[3] - content_box[1])

        layout = _fit_text_layout_to_box(translation, (box_width, box_height), preferred_direction or resolved_direction)
        _render_text_layout(
            draw,
            text_left,
            text_top,
            (box_width, box_height),
            layout,
            text_color,
        )
        rendered_translations.append(translation)

    output = BytesIO()
    canvas.save(output, format="PNG")
    page_translation = "\n".join(rendered_translations).strip() or "【本页未识别到可翻译文字】"
    return output.getvalue(), page_translation


async def _translate_manga_page_with_chat_completions(
    *,
    settings: TranslationSettings,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    target_language: str,
    timeout_seconds: int,
) -> tuple[bytes, str]:
    layout_payload = await _request_manga_chat_layout_payload(
        settings=settings,
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        image_path=image_path,
        target_language=target_language,
        timeout_seconds=timeout_seconds,
    )
    return await asyncio.to_thread(_render_manga_chat_layout_to_image, image_path, layout_payload)


def _ensure_png_image_bytes(image_bytes: bytes) -> bytes:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return image_bytes

    with Image.open(BytesIO(image_bytes)) as image:
        output = BytesIO()
        if image.mode in {"RGBA", "LA", "P"}:
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        image.save(output, format="PNG")
        return output.getvalue()


async def _request_manga_image_edit_bytes(
    *,
    base_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    prompt: str,
    timeout_seconds: int,
) -> bytes:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    image_bytes = image_path.read_bytes()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json, image/png, image/*;q=0.9, */*;q=0.8",
    }
    data = {
        "model": model,
        "prompt": prompt,
        "size": "auto",
        "quality": "medium",
        "output_format": "png",
        "response_format": "b64_json",
        "n": "1",
    }
    retryable_status_codes = {408, 409, 425, 429, 500, 502, 503, 504}
    retryable_exceptions: tuple[type[Exception], ...] = (
        httpx.TransportError,
        ssl.SSLError,
    )
    last_error: Exception | None = None

    async with _create_async_http_client(timeout=float(timeout_seconds), follow_redirects=True) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(
                    f"{base_url}/images/edits",
                    headers=headers,
                    data=data,
                    files={"image": (image_path.name, image_bytes, mime_type)},
                )
                if response.status_code in retryable_status_codes and attempt < 3:
                    await asyncio.sleep(min(1.5 * attempt, 4.0))
                    continue
                if response.is_error:
                    detail = _summarize_image_api_error(response)
                    raise RuntimeError(f"漫画译图接口请求失败：HTTP {response.status_code}，{detail}")

                content_type = str(response.headers.get("Content-Type") or "").lower()
                if content_type.startswith("image/"):
                    if not response.content:
                        raise ValueError(f"漫画译图接口返回了空图片响应：{content_type}")
                    return response.content

                if response.content:
                    try:
                        with Image.open(BytesIO(response.content)):
                            return response.content
                    except UnidentifiedImageError:
                        pass

                text_body = response.text.strip()
                resolved_text_payload = _extract_image_bytes_from_text_body(text_body)
                if isinstance(resolved_text_payload, bytes):
                    return resolved_text_payload
                if isinstance(resolved_text_payload, str):
                    download_response = await client.get(resolved_text_payload)
                    download_response.raise_for_status()
                    return download_response.content

                if not text_body:
                    raise ValueError(
                        f"漫画译图接口返回为空响应，Content-Type={content_type or 'unknown'}"
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    preview = text_body[:240]
                    raise ValueError(
                        f"漫画译图接口返回了无法解析的响应，Content-Type={content_type or 'unknown'}，响应片段：{preview}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError("漫画译图接口返回不是有效 JSON")

                resolved_image = _extract_image_bytes_from_payload(payload)
                if isinstance(resolved_image, bytes):
                    return resolved_image

                download_response = await client.get(resolved_image)
                download_response.raise_for_status()
                return download_response.content
            except retryable_exceptions as exc:
                last_error = exc
                if attempt >= 3:
                    break
                await asyncio.sleep(min(1.5 * attempt, 4.0))
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if attempt >= 3:
                    break
                await asyncio.sleep(min(1.5 * attempt, 4.0))
            except RuntimeError as exc:
                last_error = exc
                if attempt >= 3:
                    break
                if (
                    "HTTP 408" not in str(exc)
                    and "HTTP 409" not in str(exc)
                    and "HTTP 425" not in str(exc)
                    and "HTTP 429" not in str(exc)
                    and "HTTP 500" not in str(exc)
                    and "HTTP 502" not in str(exc)
                    and "HTTP 503" not in str(exc)
                    and "HTTP 504" not in str(exc)
                ):
                    raise
                await asyncio.sleep(min(1.5 * attempt, 4.0))

    raise last_error or ValueError("漫画译图请求失败")


async def _translate_manga_pages_with_command(
    *,
    settings: TranslationSettings,
    target_language: str,
    chapter_index: int,
    title: str,
    image_files: list[str],
    book_dir: Path,
    log_callback: Callable[[str, str], Awaitable[None] | None] | None = None,
) -> tuple[list[str], list[str]]:
    if not image_files:
        raise ValueError("漫画章节没有可翻译的页面图片")

    provider, base_url, api_key, image_model = _resolve_manga_image_provider_config(settings)
    resolved_target_language = _resolve_translation_target_language(target_language)
    page_translations: list[str] = []
    translated_image_files: list[str] = []
    total_pages = len(image_files)

    for page_number, asset_path in enumerate(image_files, start=1):
        image_path = (book_dir / asset_path).resolve()
        if not image_path.exists():
            raise ValueError(f"漫画页面文件不存在：{asset_path}")

        translated_asset_path = build_translated_image_asset_path(asset_path)
        translated_image_path = (book_dir / translated_asset_path).resolve()
        translated_image_path.parent.mkdir(parents=True, exist_ok=True)
        translated_image_path.unlink(missing_ok=True)

        log_prefix = f"[漫画译图][第 {page_number}/{total_pages} 页] "
        await _notify_task_log(
            log_callback,
            "info",
            f"{log_prefix}开始调用模型 {image_model} 处理图片：{asset_path}",
        )

        prompt = _build_manga_image_edit_prompt(
            target_language=resolved_target_language,
            chapter_title=title,
            chapter_index=chapter_index,
            page_number=page_number,
            total_pages=total_pages,
        )
        page_translation = f"【本页已通过模型 {image_model} 完成图片翻译】"
        if _should_use_chat_completions_image_fallback(image_model):
            await _notify_task_log(
                log_callback,
                "info",
                f"{log_prefix}当前模型更适合走 /chat/completions 兼容方案，开始执行视觉识别与本地重绘",
            )
            translated_bytes, page_translation = await _translate_manga_page_with_chat_completions(
                settings=settings,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                model=image_model,
                image_path=image_path,
                target_language=resolved_target_language,
                timeout_seconds=BUILTIN_MANGA_IMAGE_TIMEOUT_SECONDS,
            )
        else:
            try:
                translated_bytes = await _request_manga_image_edit_bytes(
                    base_url=base_url,
                    api_key=api_key,
                    model=image_model,
                    image_path=image_path,
                    prompt=prompt,
                    timeout_seconds=BUILTIN_MANGA_IMAGE_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                if not _should_fallback_from_image_edit_error(exc):
                    raise
                await _notify_task_log(
                    log_callback,
                    "warning",
                    f"{log_prefix}图片编辑接口不可用，切换到 /chat/completions 兼容方案：{exc}",
                )
                translated_bytes, page_translation = await _translate_manga_page_with_chat_completions(
                    settings=settings,
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=image_model,
                    image_path=image_path,
                    target_language=resolved_target_language,
                    timeout_seconds=BUILTIN_MANGA_IMAGE_TIMEOUT_SECONDS,
                )
        normalized_bytes = _ensure_png_image_bytes(translated_bytes)
        translated_image_path.write_bytes(normalized_bytes)
        if translated_image_path.stat().st_size <= 0:
            raise RuntimeError(f"{log_prefix}未生成有效输出图片：{translated_image_path}")

        page_translations.append(page_translation)
        translated_image_files.append(translated_asset_path)
        await _notify_task_log(
            log_callback,
            "info",
            f"{log_prefix}处理完成，输出文件：{translated_asset_path}",
        )

    return page_translations, translated_image_files


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


def _18comic_session_headers(referer: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if referer:
        headers["Referer"] = referer
    return headers


def _sync_fetch_18comic_html(url: str, referer: str | None = None) -> SyncFetchResult:
    if curl_requests is None:
        raise RuntimeError("curl_cffi 不可用，无法抓取 18Comic")
    parsed = urlparse(url)
    is_photo_page = "/photo/" in parsed.path
    warmup_url = _18comic_album_url(url if is_photo_page else referer) if (is_photo_page or referer) else None
    request_referer = url if is_photo_page else referer
    last_error: Exception | None = None
    for attempt in range(1, 4):
        session = curl_requests.Session(impersonate="chrome124")
        try:
            if warmup_url:
                session.get(warmup_url, timeout=40)
            response = session.get(url, headers=_18comic_session_headers(request_referer), timeout=40)
            response.raise_for_status()
            return SyncFetchResult(text=response.text, resolved_url=str(response.url), status_code=response.status_code)
        except Exception as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(1.0 * attempt)
    raise last_error or RuntimeError(f"18Comic HTML fetch failed: {url}")


def _sync_fetch_18comic_binary(url: str, referer: str) -> bytes:
    if curl_requests is None:
        raise RuntimeError("curl_cffi unavailable, cannot fetch 18Comic images")
    last_error: Exception | None = None
    scramble_id = _18comic_cached_scramble_id(referer)
    for attempt in range(1, 5):
        session = curl_requests.Session(impersonate="chrome124")
        try:
            album_url = _18comic_album_url(referer)
            session.get(album_url, timeout=40)
            response = session.get(url, headers=_18comic_session_headers(referer), timeout=40)
            response.raise_for_status()
            image_bytes = bytes(response.content)
            return _18comic_descramble_bytes(image_bytes, url, referer, scramble_id)
        except Exception as exc:
            last_error = exc
            if attempt >= 4:
                break
            time.sleep(0.8 * attempt)
    raise last_error or RuntimeError(f"18Comic image download failed: {url}")

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
            raise ValueError(f"娴忚鍣ㄤ細璇濇姄鍙栬秴鏃讹細{url}")
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
        raise ValueError("Alphapolis 鐩綍鏁版嵁瑙ｆ瀽澶辫触") from exc
    if not isinstance(payload, dict):
        raise ValueError("Alphapolis 鐩綍鏁版嵁鏍煎紡寮傚父")
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


def _extract_18comic_cover(soup: BeautifulSoup, resolved_url: str) -> str | None:
    for selector in (".thumb-overlay img", ".img-responsive", "img[data-original]"):
        for image in soup.select(selector):
            for key in ("data-original", "data-src", "src"):
                value = str(image.get(key) or "").strip()
                if value and "blank.jpg" not in value and "new_logo" not in value:
                    return urljoin(resolved_url, value)
    return None


def _extract_18comic_synopsis(soup: BeautifulSoup) -> str:
    meta = soup.select_one("meta[name='description'], meta[property='og:description']")
    meta_text = meta.get("content") if meta is not None else ""
    if isinstance(meta_text, str) and meta_text.strip() and meta_text.strip() not in {"免費成人H漫線上看", "免费成人H漫在线看"}:
        return meta_text.strip()

    for panel in soup.select(".panel-body"):
        text = re.sub(r"\s+", " ", panel.get_text(" ", strip=True)).strip()
        if any(keyword in text for keyword in ("简介", "簡介", "描述", "敘述")):
            return text[:800]
    return ""


def _parse_18comic_page_images(html: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    image_urls: list[str] = []
    images = []
    for selector in (
        ".row.thumb-overlay-albums .scramble-page img",
        ".panel-body .scramble-page img",
        ".scramble-page img",
    ):
        images = soup.select(selector)
        if images:
            break
    if not images:
        images = soup.select("img[data-original]")

    for image in images:
        for key in ("data-original", "data-src", "src"):
            value = str(image.get(key) or "").strip()
            if not value or value.endswith("blank.jpg"):
                continue
            absolute = urljoin(current_url, value)
            if "/media/photos/" not in urlparse(absolute).path:
                continue
            if absolute not in image_urls:
                image_urls.append(absolute)
            break
    return image_urls


def _bika_image_url(media: Any) -> str:
    if not isinstance(media, dict):
        return ""
    file_server = str(media.get("fileServer") or "").strip()
    path = str(media.get("path") or "").strip().lstrip("/")
    if not file_server or not path:
        return ""
    return f"{file_server.rstrip('/')}/static/{quote(path, safe='/')}"


def _load_runtime_settings() -> TranslationSettings:
    try:
        from .db import load_settings
    except ImportError:
        from app.db import load_settings
    return load_settings()


def _save_runtime_settings(settings: TranslationSettings) -> TranslationSettings:
    try:
        from .db import save_settings
    except ImportError:
        from app.db import save_settings
    return save_settings(settings)


def _require_bika_credentials(settings: TranslationSettings | None = None) -> tuple[str, str]:
    runtime_settings = settings or _load_runtime_settings()
    credential = runtime_settings.bika.email.strip()
    password = runtime_settings.bika.password.strip()
    if not credential and not password:
        return "", ""
    if not credential or not password:
        raise ValueError("Bika 账号和密码需同时填写，或留空后由系统自动创建。")
    return credential, password


def _bika_auth_payloads(credential: str, password: str) -> list[dict[str, str]]:
    preferred_fields = ["email", "username", "account"]
    return [{field: credential, "password": password} for field in preferred_fields]


def _bika_random_token(length: int = 10) -> str:
    return "".join(secrets.choice(BIKA_RANDOM_ALPHABET) for _ in range(max(1, length)))


def _bika_register_payload() -> tuple[str, str, dict[str, str]]:
    stamp = time.strftime("%y%m%d")
    suffix = _bika_random_token(8)
    credential = f"bw{stamp}{suffix}"[:20]
    password = f"pw{stamp}{suffix}"[:20]
    payload = {
        "name": f"web{suffix}"[:20],
        "email": credential,
        "password": password,
        "question1": f"q1{_bika_random_token(6)}",
        "answer1": f"a1{_bika_random_token(8)}",
        "question2": f"q2{_bika_random_token(6)}",
        "answer2": f"a2{_bika_random_token(8)}",
        "question3": f"q3{_bika_random_token(6)}",
        "answer3": f"a3{_bika_random_token(8)}",
        "birthday": "2000-01-01",
        "gender": "m",
    }
    return credential, password, payload


def _persist_bika_credentials(settings: TranslationSettings, credential: str, password: str) -> None:
    previous_credential = settings.bika.email.strip()
    settings.bika.email = credential
    settings.bika.password = password
    if previous_credential and previous_credential != credential:
        _BIKA_TOKEN_CACHE.pop(previous_credential, None)
    _save_runtime_settings(settings)


async def _register_bika_account(client: httpx.AsyncClient, settings: TranslationSettings) -> tuple[str, str]:
    error_messages: list[str] = []
    for _ in range(5):
        credential, password, payload = _bika_register_payload()
        try:
            await _bika_request_with_retry(
                client,
                "auth/register",
                "POST",
                json_payload=payload,
            )
        except httpx.HTTPStatusError as exc:
            error_messages.append(_bika_response_error_message(exc.response, "Bika 自动注册失败"))
            if exc.response.status_code not in {400, 409, 422}:
                raise ValueError(f"Bika 自动注册失败：{error_messages[-1]}") from exc
            continue
        except ValueError as exc:
            error_messages.append(str(exc).strip() or "Bika 自动注册失败")
            continue
        _persist_bika_credentials(settings, credential, password)
        return credential, password
    unique_messages = [message for message in dict.fromkeys(error_messages) if message]
    detail = f" 接口返回：{'；'.join(unique_messages)}" if unique_messages else ""
    raise ValueError(f"Bika 自动注册失败，已重试 5 次。{detail}".strip())


async def _ensure_bika_credentials(
    client: httpx.AsyncClient,
    settings: TranslationSettings | None = None,
) -> tuple[str, str]:
    runtime_settings = settings or _load_runtime_settings()
    credential, password = _require_bika_credentials(runtime_settings)
    if credential and password:
        return credential, password
    return await _register_bika_account(client, runtime_settings)


def _bika_response_error_message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for key in ("message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                messages = [str(item).strip() for item in value if str(item).strip()]
                if messages:
                    return "；".join(messages)
            if isinstance(value, dict):
                messages = [str(item).strip() for item in value.values() if str(item).strip()]
                if messages:
                    return "；".join(messages)
    response_text = response.text.strip()
    return response_text or fallback


def _bika_signature(path: str, time_value: str, nonce: str, method: str) -> str:
    normalized_path = path.lstrip("/")
    message = f"{normalized_path}{time_value}{nonce}{method.upper()}{BIKA_SIGNATURE_SUFFIX}".lower()
    return hmac.new(BIKA_SIGNATURE_KEY.encode("utf-8"), message.encode("utf-8"), sha256).hexdigest()


def _bika_headers(path: str, method: str, token: str | None = None) -> dict[str, str]:
    time_value = str(int(time.time()))
    nonce = _bika_random_token(32)
    signature = _bika_signature(path, time_value, nonce, method)
    headers = {
        "app-channel": BIKA_APP_CHANNEL,
        "app-uuid": BIKA_APP_UUID,
        "app-version": BIKA_APP_VERSION,
        "accept": BIKA_API_ACCEPT,
        "app-platform": BIKA_APP_PLATFORM,
        "Content-Type": "application/json; charset=UTF-8",
        "time": time_value,
        "nonce": nonce,
        "image-quality": BIKA_IMAGE_QUALITY,
        "signature": signature,
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
        "Origin": BIKA_WEB_ORIGIN,
        "Referer": BIKA_WEB_REFERER,
    }
    if token:
        headers["authorization"] = token
    return headers


async def _bika_request(
    client: httpx.AsyncClient,
    path: str,
    method: str = "GET",
    *,
    token: str | None = None,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_path = path.lstrip("/")
    response = await client.request(
        method.upper(),
        f"{BIKA_API_BASE_URL}/{normalized_path}",
        headers=_bika_headers(normalized_path, method, token),
        json=json_payload,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") == 200:
        return payload
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("detail") or "Bika 鎺ュ彛杩斿洖寮傚父").strip()
        raise ValueError(message or "Bika 鎺ュ彛杩斿洖寮傚父")
    raise ValueError("Bika 鎺ュ彛杩斿洖浜嗕笉鍙瘑鍒殑鏁版嵁缁撴瀯")


async def _bika_request_with_retry(
    client: httpx.AsyncClient,
    path: str,
    method: str = "GET",
    *,
    token: str | None = None,
    json_payload: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await _bika_request(
                client,
                path,
                method,
                token=token,
                json_payload=json_payload,
            )
        except (httpx.TransportError, ssl.SSLError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            await asyncio.sleep(min(0.8 * attempt, 2.0))
    raise ValueError(f"Bika 请求失败：{last_error}") from last_error


async def _bika_auth_token(client: httpx.AsyncClient, settings: TranslationSettings | None = None, *, force: bool = False) -> str:
    credential, password = await _ensure_bika_credentials(client, settings)
    cache_key = credential
    if not force and cache_key in _BIKA_TOKEN_CACHE:
        return _BIKA_TOKEN_CACHE[cache_key]
    error_messages: list[str] = []
    for auth_payload in _bika_auth_payloads(credential, password):
        try:
            payload = await _bika_request_with_retry(
                client,
                "auth/sign-in",
                "POST",
                json_payload=auth_payload,
            )
        except httpx.HTTPStatusError as exc:
            error_messages.append(_bika_response_error_message(exc.response, "Bika 鐧诲綍澶辫触"))
            if exc.response.status_code not in {400, 401, 422}:
                raise ValueError(error_messages[-1]) from exc
            continue
        except ValueError as exc:
            error_messages.append(str(exc).strip() or "Bika 鐧诲綍澶辫触")
            continue

        data = payload.get("data") if isinstance(payload, dict) else None
        token = ""
        if isinstance(data, dict):
            token = str(data.get("token") or data.get("authorization") or "").strip()
        if not token:
            token = str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""
        if not token:
            raise ValueError("Bika 登录成功但没有返回 token")
        _BIKA_TOKEN_CACHE[cache_key] = token
        return token

    unique_messages = [message for message in dict.fromkeys(error_messages) if message]
    if unique_messages:
        raise ValueError(f"Bika 登录失败：已按邮箱和用户名两种方式尝试。接口返回：{"；".join(unique_messages)}")
    raise ValueError("Bika 登录失败：已按邮箱和用户名两种方式尝试，但接口没有返回可用结果")


async def _bika_authed_request(
    client: httpx.AsyncClient,
    path: str,
    method: str = "GET",
    *,
    settings: TranslationSettings | None = None,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = await _bika_auth_token(client, settings)
    try:
        return await _bika_request_with_retry(client, path, method, token=token, json_payload=json_payload)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        token = await _bika_auth_token(client, settings, force=True)
        return await _bika_request_with_retry(client, path, method, token=token, json_payload=json_payload)


async def _bika_fetch_comic(client: httpx.AsyncClient, comic_id: str, settings: TranslationSettings | None = None) -> dict[str, Any]:
    payload = await _bika_authed_request(client, f"comics/{comic_id}", settings=settings)
    data = payload.get("data") if isinstance(payload, dict) else None
    comic = data.get("comic") if isinstance(data, dict) else None
    if not isinstance(comic, dict):
        raise ValueError("Bika 婕敾璇︽儏鏁版嵁鏍煎紡寮傚父")
    return comic


async def _bika_fetch_episodes(
    client: httpx.AsyncClient,
    comic_id: str,
    settings: TranslationSettings | None = None,
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = await _bika_authed_request(client, f"comics/{comic_id}/eps?page={page}", settings=settings)
        data = payload.get("data") if isinstance(payload, dict) else None
        eps = data.get("eps") if isinstance(data, dict) else None
        if not isinstance(eps, dict):
            break
        docs = eps.get("docs")
        if isinstance(docs, list):
            episodes.extend(item for item in docs if isinstance(item, dict))
        current_page = int(eps.get("page") or page)
        total_pages = int(eps.get("pages") or current_page or 1)
        if current_page >= total_pages:
            break
        page = current_page + 1
    return episodes


async def _bika_fetch_pages(
    client: httpx.AsyncClient,
    comic_id: str,
    order: str,
    settings: TranslationSettings | None = None,
) -> tuple[list[str], str]:
    image_urls: list[str] = []
    chapter_title = ""
    page = 1
    while True:
        payload = await _bika_authed_request(
            client,
            f"comics/{comic_id}/order/{order}/pages?page={page}",
            settings=settings,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Bika 漫画页数据格式异常")
        pages = data.get("pages")
        if not isinstance(pages, dict):
            raise ValueError("Bika 漫画页列表缺失")
        docs = pages.get("docs")
        if isinstance(docs, list):
            for item in docs:
                media = item.get("media") if isinstance(item, dict) else None
                image_url = _bika_image_url(media)
                if image_url and image_url not in image_urls:
                    image_urls.append(image_url)
        episode = data.get("ep")
        if isinstance(episode, dict) and not chapter_title:
            chapter_title = str(episode.get("title") or "").strip()
        current_page = int(pages.get("page") or page)
        total_pages = int(pages.get("pages") or current_page or 1)
        if current_page >= total_pages:
            break
        page = current_page + 1
    return image_urls, chapter_title


async def _preview_18comic(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    album_url = _18comic_album_url(source_url)
    result = await asyncio.to_thread(_sync_fetch_18comic_html, album_url)
    soup = BeautifulSoup(result.text, "html.parser")
    fallback_title = payload.title or Path(urlparse(source_url).path).stem or "未命名漫画"
    title = str((soup.select_one("h1") or soup.select_one("title")).get_text(" ", strip=True) if (soup.select_one("h1") or soup.select_one("title")) else fallback_title).strip()
    title = _clean_title_suffix(title, (" Comics - ????", " - ????", " Comics", "|H?????? Comics - ????"))
    read_anchor = soup.select_one("a[href*='/photo/']")
    photo_url = urljoin(result.resolved_url, str(read_anchor.get("href") or "").strip()) if read_anchor is not None else _18comic_photo_url(album_url)
    photo_result = await asyncio.to_thread(_sync_fetch_18comic_html, photo_url, album_url)
    _18comic_cache_scramble_id(source_url, photo_result.text)
    page_count = len(_parse_18comic_page_images(photo_result.text, photo_result.resolved_url))
    chapter_title = title if page_count <= 1 else f"{title} / 第1话"
    return PreviewResponse(
        title=title,
        author=None,
        synopsis=_extract_18comic_synopsis(soup),
        cover=_extract_18comic_cover(soup, result.resolved_url),
        chapterCount=1,
        chapters=[ChapterPreview(title=chapter_title, url=photo_url, pageCount=page_count)],
    )


async def _preview_bika(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    comic_id = _bika_comic_id_from_url(source_url)
    if not comic_id:
        raise ValueError("鏃犳硶璇嗗埆 Bika 婕敾缂栧彿")
    runtime_settings = _load_runtime_settings()
    async with _create_async_http_client(timeout=40.0) as client:
        comic = await _bika_fetch_comic(client, comic_id, runtime_settings)
        episodes = await _bika_fetch_episodes(client, comic_id, runtime_settings)
    title = str(comic.get("title") or payload.title or "未命名漫画").strip()
    author = str(comic.get("author") or comic.get("chineseTeam") or "").strip() or None
    synopsis = str(comic.get("description") or "").strip()
    cover = _bika_image_url(comic.get("thumb"))
    base_origin = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
    chapters: list[ChapterPreview] = []
    for item in sorted(episodes, key=lambda episode: int(episode.get("order") or 0)):
        order = str(item.get("order") or "").strip()
        if not order:
            continue
        chapter_title = str(item.get("title") or "").strip() or f"第{order}话"
        chapters.append(
            ChapterPreview(
                title=chapter_title,
                url=f"{base_origin}/comic/reader/{comic_id}/{order}",
                pageCount=0,
            )
        )
    if not chapters:
        chapters = [ChapterPreview(title=title, url=f"{base_origin}/comic/reader/{comic_id}/1", pageCount=0)]
    return PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )


async def _preview_kakuyomu(source_url: str, payload: AddBookPayload) -> PreviewResponse:
    html, resolved_url = await _fetch_preview_html(source_url)
    state = _kakuyomu_state_from_html(html)
    work_id = _kakuyomu_work_id_from_url(source_url)
    if not work_id:
        raise ValueError("鏃犳硶璇嗗埆 Kakuyomu 浣滃搧缂栧彿")
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
                raise ValueError("Pixiv 绯诲垪鎺ュ彛杩斿洖寮傚父")
            chapters = [
                ChapterPreview(
                    title=str(item.get("title") or f"绔犺妭 {index}"),
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
            raise ValueError("鏃犳硶璇嗗埆 Pixiv 灏忚缂栧彿")
        novel_result = await _fetch_json(
            client,
            f"https://www.pixiv.net/ajax/novel/{novel_id}",
            _pixiv_api_headers(normalized),
        )
        body = novel_result["body"]
        if not isinstance(body, dict):
            raise ValueError("Pixiv 灏忚鎺ュ彛杩斿洖寮傚父")
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
    result: PreviewResponse
    if _is_18comic_url(source_url):
        result = await _preview_18comic(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_bikawebapp_url(source_url):
        result = await _preview_bika(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_kakuyomu_url(source_url):
        result = await _preview_kakuyomu(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_syosetu_url(source_url) or _is_novel18_url(source_url):
        result = await _preview_syosetu(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_pixiv_url(source_url):
        result = await _preview_pixiv(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_hameln_url(source_url):
        result = await _preview_hameln(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_novelup_url(source_url):
        result = await _preview_novelup(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})
    if _is_alphapolis_url(source_url):
        result = await _preview_alphapolis(source_url, payload)
        return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})

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

    result = PreviewResponse(
        title=title,
        author=author,
        synopsis=synopsis,
        cover=cover,
        chapterCount=len(chapters),
        chapters=chapters,
    )
    return result.model_copy(update={"bookKind": _resolved_preview_book_kind(source_url, payload)})


async def download_book(payload: AddBookPayload, preview: PreviewResponse, root_dir: Path) -> DownloadResult:
    safe_title = re.sub(r'[\/:*?"<>|]', "_", preview.title).strip() or "未命名小说"
    book_dir = root_dir / payload.language / safe_title
    book_dir.mkdir(parents=True, exist_ok=True)
    chapter_manifest: list[dict[str, str | int]] = []
    runtime_settings = _load_runtime_settings()
    image_download_semaphore = asyncio.Semaphore(
        _image_download_concurrency(str(payload.sourceUrl), runtime_settings.downloadConcurrency)
    )

    async with _build_http_client() as client:
        cover_file = await _download_cover_image(client, book_dir, preview.cover, str(payload.sourceUrl))
        if preview.chapters and _is_linovelib_url(preview.chapters[0].url):
            await _prime_linovelib_session(client, preview.chapters[0].url)
        for index, chapter in enumerate(preview.chapters, start=1):
            try:
                result = await _fetch_chapter_data(client, chapter.url, chapter.title)
                image_files = await _download_chapter_images(
                    client,
                    book_dir,
                    index,
                    result.image_urls,
                    chapter.url,
                    image_download_semaphore=image_download_semaphore,
                )
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
                    "translated_meta_file_name": None,
                    "illustration": result.illustration,
                    "image_urls": result.image_urls,
                    "image_files": image_files,
                    "translated_image_files": [],
                    "page_count": chapter.pageCount or len(image_files) or len(result.image_urls),
                    "images_repaired": _is_18comic_url(chapter.url),
                }
            )

    manifest = {
        "title": preview.title,
        "author": preview.author,
        "source_url": str(payload.sourceUrl),
        "book_kind": preview.bookKind,
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
        text = _format_illustration_text(chapter_title or "鎻掑浘", image_urls)
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
        raise ValueError("鏈兘浠庢垚涓哄皬璇村鍚ч〉闈㈡彁鍙栧嚭姝ｆ枃鍐呭")
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
        raise ValueError("鏃犳硶璇嗗埆 Pixiv 灏忚缂栧彿")
    payload = await _fetch_json(client, f"https://www.pixiv.net/ajax/novel/{novel_id}", _pixiv_api_headers(chapter_url))
    body = payload["body"]
    if not isinstance(body, dict):
        raise ValueError("Pixiv 灏忚鎺ュ彛杩斿洖寮傚父")
    text = _pixiv_content_to_text(str(body.get("content") or ""))
    image_urls = _extract_pixiv_image_urls(body)
    illustration = _is_illustration_chapter(chapter_title)
    if not text and image_urls:
        text = _format_illustration_text(chapter_title or str(body.get("title") or "鎻掑浘"), image_urls)
        illustration = True
    elif image_urls and illustration:
        text = _append_image_links(text, image_urls)
    if not text:
        raise ValueError("未能从 Pixiv 页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=image_urls, illustration=illustration)


def _sync_fetch_18comic_chapter_data(chapter_url: str, chapter_title: str = "") -> ChapterFetchResult:
    photo_url = chapter_url
    album_url = _18comic_album_url(chapter_url)
    result = _sync_fetch_18comic_html(photo_url, album_url)
    _18comic_cache_scramble_id(chapter_url, result.text)
    image_urls = _parse_18comic_page_images(result.text, result.resolved_url)
    if not image_urls:
        raise ValueError("未能从 18Comic 页面提取出漫画图片")
    title = chapter_title.strip() or "漫画章节"
    return ChapterFetchResult(text=_manga_placeholder_text(title, len(image_urls)), image_urls=image_urls, illustration=False)


async def _fetch_18comic_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    return await asyncio.to_thread(_sync_fetch_18comic_chapter_data, chapter_url, chapter_title)


async def _fetch_bika_chapter_data(
    client: httpx.AsyncClient,
    chapter_url: str,
    chapter_title: str = "",
) -> ChapterFetchResult:
    comic_id = _bika_comic_id_from_url(chapter_url)
    order = _bika_order_from_url(chapter_url)
    if not comic_id or not order:
        raise ValueError("鏃犳硶璇嗗埆 Bika 绔犺妭缂栧彿")
    runtime_settings = _load_runtime_settings()
    image_urls, resolved_title = await _bika_fetch_pages(client, comic_id, order, runtime_settings)
    if not image_urls:
        raise ValueError("未能从 Bika 接口提取出漫画页面")
    title = chapter_title.strip() or resolved_title or f"第{order}话"
    return ChapterFetchResult(text=_manga_placeholder_text(title, len(image_urls)), image_urls=image_urls, illustration=False)


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
        text = _format_illustration_text(chapter_title or "鎻掑浘", image_urls)
        illustration = True
    elif image_urls and illustration:
        text = _append_image_links(text, image_urls)
    if not text and not image_urls:
        raise ValueError("未能从 Alphapolis 页面提取出正文内容")
    return ChapterFetchResult(text=text, image_urls=image_urls, illustration=illustration)


async def _fetch_chapter_data(client: httpx.AsyncClient, chapter_url: str, chapter_title: str = "") -> ChapterFetchResult:
    try:
        if _is_18comic_url(chapter_url):
            return await _fetch_18comic_chapter_data(client, chapter_url, chapter_title)
        if _is_bikawebapp_url(chapter_url):
            return await _fetch_bika_chapter_data(client, chapter_url, chapter_title)
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


def _create_async_http_client(
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=follow_redirects,
        timeout=timeout,
        headers=headers,
        http2=False,
    )


def _build_http_client() -> httpx.AsyncClient:
    client = _create_async_http_client(timeout=20.0, headers=DEFAULT_HEADERS)
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
    raise ValueError(f"鏃犳硶璇诲彇鐩綍椤碉細{source_url}")


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
        merged = _format_illustration_text(chapter_title or "鎻掑浘", image_urls)
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
        if label in {"下一页", "下一頁", "下一话", "下一話"}:
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
    return any(keyword in normalized for keyword in ("鎻掑浘", "鎻掔暙", "illustration"))


def _format_illustration_text(chapter_title: str, image_urls: list[str]) -> str:
    lines = [f"{chapter_title}锛堟彃鍥剧珷鑺傦級", "", f"鍏辨敹闆嗗埌 {len(image_urls)} 寮犲浘鐗囬摼鎺ワ細", ""]
    lines.extend(image_urls)
    return "\n".join(lines).strip()


def _append_image_links(text: str, image_urls: list[str]) -> str:
    if not image_urls:
        return text
    if not text.strip():
        return "鎻掑浘閾炬帴锛歕n" + "\n".join(image_urls)
    return f"{text.rstrip()}\n\n鎻掑浘閾炬帴锛歕n" + "\n".join(image_urls)


async def _download_binary_bytes(
    client: httpx.AsyncClient,
    url: str,
    referer: str,
) -> bytes:
    if _is_18comic_url(url) or _is_18comic_url(referer):
        return await asyncio.to_thread(_sync_fetch_18comic_binary, url, referer)
    response = await _get_binary_response(client, url, referer=referer)
    return response.content


def _image_download_concurrency(source_url: str, concurrency: int) -> int:
    normalized = max(1, min(concurrency, 8))
    if _is_18comic_url(source_url) or _is_bikawebapp_url(source_url):
        return min(8, max(2, normalized * 2))
    return normalized


async def _download_chapter_images(
    client: httpx.AsyncClient,
    book_dir: Path,
    chapter_index: int,
    image_urls: list[str],
    referer: str,
    *,
    image_download_semaphore: asyncio.Semaphore | None = None,
) -> list[str]:
    if not image_urls:
        return []

    images_dir = book_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    async def download_single_image(image_number: int, image_url: str) -> str:
        extension = _image_extension_from_url(image_url)
        file_hash = md5(image_url.encode("utf-8")).hexdigest()[:10]
        filename = f"{chapter_index:04d}-{image_number:02d}-{file_hash}{extension}"
        target_path = images_dir / filename
        if target_path.exists():
            return f"images/{filename}"

        async def fetch_and_write() -> None:
            content = await _download_binary_bytes(client, image_url, referer)
            await asyncio.to_thread(target_path.write_bytes, content)

        if image_download_semaphore is None:
            await fetch_and_write()
        else:
            async with image_download_semaphore:
                if not target_path.exists():
                    await fetch_and_write()
        return f"images/{filename}"

    return await asyncio.gather(
        *(download_single_image(image_number, image_url) for image_number, image_url in enumerate(image_urls, start=1))
    )


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
    image_bytes = await _download_binary_bytes(client, cover_url, referer)
    extension = _image_extension_from_bytes(image_bytes, _image_extension_from_url(cover_url))
    filename = f"cover{extension}"
    target_path = covers_dir / filename
    if not target_path.exists():
        target_path.write_bytes(image_bytes)
    return f"covers/{filename}"


def _image_extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return suffix
    return ".jpg"


def _image_extension_from_bytes(image_bytes: bytes, fallback: str = ".jpg") -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if image_bytes.startswith(b"BM"):
        return ".bmp"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return ".webp"

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            format_name = (image.format or "").upper()
    except UnidentifiedImageError:
        return fallback

    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
        "BMP": ".bmp",
    }.get(format_name, fallback)


def _image_request_headers(url: str, referer: str) -> dict[str, str]:
    headers = _request_headers(url, referer=referer)
    headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    return headers


async def _translate_text(
    client: httpx.AsyncClient,
    settings: TranslationSettings,
    target_language: str,
    title: str,
    content: str,
) -> str:
    provider = settings.defaultProvider
    provider_config = settings.providers[provider]
    resolved_target_language = _resolve_translation_target_language(target_language)
    prompt = (
        f"章节标题：{title}\n"
        f"目标语言：{resolved_target_language}\n"
        f"请将以下章节内容翻译为{resolved_target_language}；如果原文已经是{resolved_target_language}，请保持原意并输出自然流畅的{resolved_target_language}版本。\n\n"
        f"{content}"
    )

    if provider == "anthropic":
        base_url = provider_config.baseUrl.rstrip("/")
        payload = await _post_translation_json(
            client,
            f"{base_url}/messages",
            headers={
                "x-api-key": provider_config.apiKey,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload={
                "model": provider_config.model,
                "max_tokens": 8192,
                "system": settings.systemPrompt,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        blocks = payload.get("content", [])
        parts = [block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
        text = "\n".join(part for part in parts if part).strip()
        if not text:
            raise ValueError("Anthropic 杩斿洖浜嗙┖缈昏瘧缁撴灉")
        return text

    base_url = provider_config.baseUrl.rstrip("/")
    payload = await _post_translation_json(
        client,
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {provider_config.apiKey}",
            "Content-Type": "application/json",
        },
        payload={
            "model": provider_config.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": settings.systemPrompt},
                {"role": "user", "content": prompt},
            ],
        },
    )
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("缈昏瘧鏈嶅姟杩斿洖浜嗙┖鍝嶅簲")

    message = choices[0].get("message", {})
    return _normalize_translation_result(message.get("content", ""))


def _media_type_for_path(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/jpeg")


def _normalize_translation_result(content_value: Any) -> str:
    if isinstance(content_value, list):
        parts = [item.get("text", "") for item in content_value if isinstance(item, dict)]
        content_value = "\n".join(part for part in parts if part)
    text = str(content_value).strip()
    if not text:
        raise ValueError("缈昏瘧鏈嶅姟杩斿洖浜嗙┖缈昏瘧缁撴灉")
    return text


async def _post_translation_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    max_retries: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None
    retryable_status_codes = {408, 409, 425, 429, 500, 502, 503, 504}
    retryable_exceptions: tuple[type[Exception], ...] = (
        httpx.TransportError,
        ssl.SSLError,
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code in retryable_status_codes and attempt < max_retries:
                await asyncio.sleep(min(1.2 * attempt, 4.0))
                continue
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("缈昏瘧鏈嶅姟杩斿洖浜嗕笉鍙瘑鍒殑鏁版嵁缁撴瀯")
            return data
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code not in retryable_status_codes or attempt >= max_retries:
                raise
            await asyncio.sleep(min(1.2 * attempt, 4.0))
        except retryable_exceptions as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            await asyncio.sleep(min(1.2 * attempt, 4.0))

    raise last_error or ValueError(f"翻译请求失败：{url}")


def _merge_page_translations(title: str, page_translations: list[str]) -> str:
    lines = [title, ""]
    for index, page_text in enumerate(page_translations, start=1):
        lines.append(f"【第 {index} 页】")
        lines.append(page_text.strip() or "【本页无对白】")
        lines.append("")
    return "\n".join(lines).strip()

