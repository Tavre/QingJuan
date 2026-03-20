from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from hashlib import md5
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import AddBookPayload, ChapterPreview, PreviewResponse, TranslationSettings

CHAPTER_PATTERN = re.compile(r"(chapter|episode|第.{0,6}[章节话卷篇])", re.IGNORECASE)
LINOVELIB_HOST_KEYWORDS = ("linovelib.com", "bilinovel.com")
LINOVELIB_PREFERRED_HOSTS = ("tw.linovelib.com", "www.bilinovel.com", "www.linovelib.com")
LINOVELIB_BOOK_PATH_PATTERN = re.compile(r"/novel/(?P<book_id>\d+)(?:\.html|/catalog|/\d+(?:_\d+)?\.html)?/?$")
LINOVELIB_CHAPTER_PATH_PATTERN = re.compile(r"/novel/(?P<book_id>\d+)/(?P<chapter_id>\d+)(?:_(?P<page>\d+))?\.html$")
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


def _is_linovelib_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(keyword in host for keyword in LINOVELIB_HOST_KEYWORDS)


def _normalize_source_url(url: str) -> str:
    if not _is_linovelib_url(url):
        return url

    parsed = urlparse(url)
    match = LINOVELIB_BOOK_PATH_PATTERN.match(parsed.path)
    if not match:
        return url

    book_id = match.group("book_id")
    return f"{parsed.scheme}://{parsed.netloc}/novel/{book_id}/catalog"


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


async def preview_from_url(payload: AddBookPayload) -> PreviewResponse:
    source_url = _normalize_source_url(str(payload.sourceUrl))
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


async def _fetch_chapter_data(client: httpx.AsyncClient, chapter_url: str, chapter_title: str = "") -> ChapterFetchResult:
    try:
        if _is_linovelib_url(chapter_url):
            return await _fetch_linovelib_chapter_data(client, chapter_url, chapter_title)

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
    return headers


def _build_http_client() -> httpx.AsyncClient:
    try:
        return httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=DEFAULT_HEADERS, http2=True)
    except ImportError:
        return httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=DEFAULT_HEADERS)


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


