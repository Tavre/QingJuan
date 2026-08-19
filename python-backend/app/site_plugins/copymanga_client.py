from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

MANGACOPY_ORIGIN = "https://www.mangacopy.com"
MANGACOPY_API_HOSTS = (
    "https://api.2024manga.com",
    "https://mapi.hotmangasg.com",
    "https://mapi.hotmangasd.com",
    "https://mapi.hotmangasf.com",
)
MANGACOPY_IMAGE_DOMAIN = "mangafunb.fun"
MANGACOPY_PLATFORM = "2"
MANGACOPY_BOOK_PATH = re.compile(
    r"^/comic/(?P<path_word>[A-Za-z0-9_-]+)(?:/.*)?$",
    re.IGNORECASE,
)
MANGACOPY_CHAPTER_PATH = re.compile(
    r"^/comic/(?P<path_word>[A-Za-z0-9_-]+)/chapter/(?P<chapter_id>[A-Za-z0-9-]+)/*$",
    re.IGNORECASE,
)


class CopyMangaError(ValueError):
    pass


def mangacopy_path_word_from_url(url: str) -> str | None:
    match = MANGACOPY_BOOK_PATH.match(urlparse(url).path)
    return match.group("path_word") if match else None


def mangacopy_chapter_ids_from_url(url: str) -> tuple[str, str] | None:
    match = MANGACOPY_CHAPTER_PATH.match(urlparse(url).path)
    if not match:
        return None
    return match.group("path_word"), match.group("chapter_id")


def canonical_mangacopy_book_url(path_word: str) -> str:
    return f"{MANGACOPY_ORIGIN}/comic/{quote(path_word, safe='-_')}"


def canonical_mangacopy_chapter_url(path_word: str, chapter_id: str) -> str:
    return (
        f"{MANGACOPY_ORIGIN}/comic/{quote(path_word, safe='-_')}"
        f"/chapter/{quote(chapter_id, safe='-')}"
    )


def is_allowed_mangacopy_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (
        host == MANGACOPY_IMAGE_DOMAIN or host.endswith(f".{MANGACOPY_IMAGE_DOMAIN}")
    )


def _api_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "platform": MANGACOPY_PLATFORM,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
        ),
    }


def _parse_api_response(response: httpx.Response, stage: str) -> Any:
    if response.status_code >= 400:
        raise CopyMangaError(f"拷贝漫画{stage}请求失败（HTTP {response.status_code}）")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CopyMangaError(f"拷贝漫画{stage}返回了无效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("code") != 200:
        message = str(payload.get("message") or "上游返回业务错误") if isinstance(payload, dict) else "上游返回格式异常"
        raise CopyMangaError(f"拷贝漫画{stage}失败：{message}")
    return payload.get("results")


async def request_mangacopy_api(
    client: httpx.AsyncClient,
    path: str,
    *,
    stage: str,
    params: dict[str, Any] | None = None,
) -> Any:
    query = dict(params or {})
    query.setdefault("platform", MANGACOPY_PLATFORM)
    last_error: Exception | None = None
    for host in MANGACOPY_API_HOSTS:
        response: httpx.Response | None = None
        try:
            response = await client.get(
                f"{host}{path}",
                params=query,
                headers=_api_headers(),
            )
            return _parse_api_response(response, stage)
        except (httpx.HTTPError, CopyMangaError) as exc:
            last_error = exc
            if (
                isinstance(exc, CopyMangaError)
                and response is not None
                and response.status_code < 500
            ):
                raise
    raise CopyMangaError(f"拷贝漫画{stage}请求失败：所有公开 API 节点均不可用") from last_error


async def get_mangacopy_detail(client: httpx.AsyncClient, path_word: str) -> dict[str, Any]:
    result = await request_mangacopy_api(
        client,
        f"/api/v3/comic2/{quote(path_word, safe='-_')}",
        stage="作品详情",
    )
    if not isinstance(result, dict):
        raise CopyMangaError("拷贝漫画作品详情返回格式异常")
    return result


async def get_mangacopy_chapters(
    client: httpx.AsyncClient,
    path_word: str,
    groups: object,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    if not isinstance(groups, dict):
        return []
    chapters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group_id, raw_group in groups.items():
        group = raw_group if isinstance(raw_group, dict) else {}
        group_path = str(group.get("path_word") or group_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", group_path):
            continue
        group_name = str(group.get("name") or "").strip()
        offset = 0
        for _ in range(100):
            result = await request_mangacopy_api(
                client,
                (
                    f"/api/v3/comic/{quote(path_word, safe='-_')}"
                    f"/group/{quote(group_path, safe='-_')}/chapters"
                ),
                stage="章节目录",
                params={"limit": page_size, "offset": offset},
            )
            if not isinstance(result, dict):
                raise CopyMangaError("拷贝漫画章节目录返回格式异常")
            items = result.get("list")
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                chapter_id = str(item.get("uuid") or "").strip()
                if not chapter_id or chapter_id in seen:
                    continue
                seen.add(chapter_id)
                chapters.append({**item, "_group_name": group_name})
            offset += len(items)
            total = int(result.get("total") or 0)
            if len(items) < page_size or (total and offset >= total):
                break
    return chapters


async def get_mangacopy_chapter(
    client: httpx.AsyncClient,
    path_word: str,
    chapter_id: str,
) -> dict[str, Any]:
    result = await request_mangacopy_api(
        client,
        (
            f"/api/v3/comic/{quote(path_word, safe='-_')}"
            f"/chapter/{quote(chapter_id, safe='-')}"
        ),
        stage="章节内容",
    )
    if not isinstance(result, dict):
        raise CopyMangaError("拷贝漫画章节内容返回格式异常")
    return result


async def search_mangacopy(
    client: httpx.AsyncClient,
    keyword: str,
    limit: int,
) -> list[dict[str, Any]]:
    result = await request_mangacopy_api(
        client,
        "/api/v3/search/comic",
        stage="作品搜索",
        params={"q": keyword, "q_type": "", "limit": limit, "offset": 0},
    )
    if not isinstance(result, dict):
        raise CopyMangaError("拷贝漫画搜索返回格式异常")
    items = result.get("list")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
