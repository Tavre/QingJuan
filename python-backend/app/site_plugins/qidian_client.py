from __future__ import annotations

import html
import json
import re
import time
from contextlib import suppress
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

APP_ID = "10"
AREA_ID = "1"
RETURN_URL = "https://www.qidian.com/loginSuccess?surl=https%3A%2F%2Fwww.qidian.com%2F"

QRCODE_ENDPOINT = "https://ptlogin.yuewen.com/login/qrcode"
QR_LOGIN_ENDPOINT = "https://ptlogin.yuewen.com/login/qrcodelogin"
SUB_LOGIN_ENDPOINT = "https://ptlogin.qidian.com/login/sublogin"
BOOK_INFO_ENDPOINT = "https://wxapp.qidian.com/api/book/info"
CATALOG_ENDPOINT = "https://wxapp.qidian.com/api/book/categoryV2"
BOOKSHELF_ENDPOINT = "https://m.qidian.com/webcommon/bookshelf/mlist"
SEARCH_ENDPOINT = "https://m.qidian.com/so/"
SEARCH_ORDER_BY = {
    "default": 0,
    "popular": 1,
    "word": 3,
    "time": 4,
    "recommend": 9,
    "favorite": 11,
    "monthticket": 12,
}

REQUEST_TIMEOUT_SECONDS = 20
MAX_LOGIN_REDIRECTS = 8
_PAGE_CONTEXT_PATTERN = re.compile(
    r'<script\s+id="vite-plugin-ssr_pageContext"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_BOOK_PATH_PATTERNS = (
    re.compile(r"/(?:book|info)/(\d+)(?:/|$)"),
    re.compile(r"/chapter/(\d+)/(?:\d+)(?:/|$)"),
)
_CHAPTER_PATH_PATTERN = re.compile(r"/chapter/(\d+)/(\d+)(?:/|$)")


class QidianApiError(RuntimeError):
    pass


def qidian_book_id_from_url(value: str) -> str | None:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if host != "qidian.com" and not host.endswith(".qidian.com"):
        return None
    for pattern in _BOOK_PATH_PATTERNS:
        match = pattern.search(parsed.path)
        if match is not None:
            return match.group(1)
    return None


def qidian_chapter_ids_from_url(value: str) -> tuple[str, str] | None:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if host != "qidian.com" and not host.endswith(".qidian.com"):
        return None
    match = _CHAPTER_PATH_PATTERN.search(parsed.path)
    if match is None:
        return None
    return match.group(1), match.group(2)


def canonical_book_url(book_id: str) -> str:
    if not str(book_id).isdigit():
        raise QidianApiError("起点书籍 ID 无效")
    return f"https://www.qidian.com/book/{book_id}/"


def canonical_chapter_url(book_id: str, chapter_id: str) -> str:
    if not str(book_id).isdigit() or not str(chapter_id).isdigit():
        raise QidianApiError("起点章节 ID 无效")
    return f"https://m.qidian.com/chapter/{book_id}/{chapter_id}/"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid_value() -> str:
    return f"{int(time.time())}_{_now_ms() % 1_000_000}"


def _jsonp_payload(value: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", value, re.DOTALL)
    if match is None:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_payload(response: requests.Response, stage: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise QidianApiError(f"起点{stage}响应无法解析") from exc
    if not isinstance(payload, dict):
        raise QidianApiError(f"起点{stage}响应格式无效")
    return payload


def _request_get(
    session: requests.Session,
    url: str,
    *,
    stage: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    cookies: dict[str, str] | None = None,
) -> requests.Response:
    try:
        response = session.get(
            url,
            headers=headers,
            params=params,
            cookies=cookies,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise QidianApiError(f"起点{stage}请求失败") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise QidianApiError(f"起点{stage}请求失败（HTTP {response.status_code}）")
    return response


def _yuewen_headers() -> dict[str, str]:
    return {
        "User-Agent": DESKTOP_USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://passport.yuewen.com/",
    }


def _mobile_headers(referer: str = "https://m.qidian.com/") -> dict[str, str]:
    return {
        "User-Agent": MOBILE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer,
    }


def _wxapp_headers() -> dict[str, str]:
    return {
        "User-Agent": DESKTOP_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://wxapp.qidian.com/",
    }


def _login_params(method: str) -> dict[str, str]:
    return {
        "callback": f"jQuery{_now_ms()}",
        "appId": APP_ID,
        "areaId": AREA_ID,
        "source": "",
        "returnurl": RETURN_URL,
        "version": "",
        "imei": "",
        "qimei": "",
        "target": "iframe",
        "ticket": "1",
        "autotime": "30",
        "jumpdm": "yuewen",
        "ajaxdm": "yuewen",
        "auto": "1",
        "sdkversion": "",
        "method": method,
        "format": "jsonp",
        "_": str(_now_ms()),
    }


def get_qrcode(session: requests.Session) -> dict[str, Any]:
    session.headers.update(_yuewen_headers())
    params = _login_params("LoginV1.qrCodeCallback")
    params.update(
        {
            "uuid": _uuid_value(),
            "pageId": "qd_p_qidian",
            "bookId": "",
            "chapterId": "",
        }
    )
    response = _request_get(session, QRCODE_ENDPOINT, stage="登录二维码", params=params)
    payload = _jsonp_payload(response.text)
    data = payload.get("data")
    if payload.get("code") != 0 or not isinstance(data, dict):
        raise QidianApiError("获取起点登录二维码失败")
    session_key = str(data.get("sessionKey") or "")
    image = str(data.get("image") or "")
    if not session_key or not image:
        raise QidianApiError("起点登录二维码响应缺少必要字段")
    image_base64 = image.split(",", 1)[1] if image.startswith("data:") and "," in image else image
    return {
        "sessionKey": session_key,
        "qrImageBase64": image_base64,
        "expireSeconds": 180,
    }


def _allowed_login_return_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and any(
        host == domain or host.endswith(f".{domain}") for domain in ("qidian.com", "yuewen.com")
    )


def _follow_login_redirects(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    current_url = url
    current_params = params
    for _ in range(MAX_LOGIN_REDIRECTS + 1):
        if not _allowed_login_return_url(current_url):
            raise QidianApiError("起点登录返回地址不受信任")
        response = session.get(
            current_url,
            params=current_params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        current_params = None
        if response.status_code not in {301, 302, 303, 307, 308}:
            return
        location = str(response.headers.get("Location") or "").strip()
        if not location:
            return
        current_url = urljoin(current_url, location)
    raise QidianApiError("起点登录跳转次数过多")


def _complete_login(
    session: requests.Session,
    login_data: dict[str, Any],
) -> dict[str, str]:
    return_url = str(login_data.get("returnUrl") or login_data.get("302url") or "")
    with suppress(requests.RequestException, QidianApiError):
        if return_url and _allowed_login_return_url(return_url):
            _follow_login_redirects(session, return_url)
        else:
            _follow_login_redirects(
                session,
                SUB_LOGIN_ENDPOINT,
                params={
                    "appId": APP_ID,
                    "areaId": AREA_ID,
                    "returnurl": RETURN_URL,
                    "target": "iframe",
                    "ticket": login_data.get("ticket", ""),
                    "autotime": "30",
                    "jumpdm": "yuewen",
                    "ajaxdm": "yuewen",
                    "auto": "1",
                    "method": "LoginV1.qrCodeLoginCallback",
                    "format": "iframe",
                    "params": login_data.get("autoLoginSessionKey", ""),
                },
            )
    for landing_url in ("https://m.qidian.com/bookshelf/my/", "https://m.qidian.com/"):
        with suppress(requests.RequestException, QidianApiError):
            _follow_login_redirects(
                session,
                landing_url,
                headers=_mobile_headers(),
            )
    return {str(key): str(value) for key, value in session.cookies.get_dict().items()}


def poll_qrcode(
    session: requests.Session,
    session_key: str,
) -> dict[str, Any]:
    params = _login_params("LoginV1.qrCodeLoginCallback")
    params["qrcode"] = session_key
    response = _request_get(session, QR_LOGIN_ENDPOINT, stage="扫码状态", params=params)
    payload = _jsonp_payload(response.text)
    code = payload.get("code")
    scan_status = str(payload.get("scanStatus", "0"))
    message = str(payload.get("message") or "")

    login_data = payload.get("data")
    if code == 0 and scan_status == "5" and isinstance(login_data, dict):
        cookies = _complete_login(session, login_data)
        if not cookies.get("ywguid") or not cookies.get("ywkey"):
            raise QidianApiError("起点登录成功，但未取得可用登录会话")
        return {"status": "success", "message": "登录成功", "cookies": cookies}
    if scan_status == "1":
        return {"status": "scanned", "message": "已扫码，请在手机上确认"}
    if scan_status == "3":
        return {"status": "cancelled", "message": "手机端已取消，请重新获取二维码"}
    if scan_status == "4":
        return {"status": "expired", "message": "二维码已过期"}
    if code == -11033:
        return {"status": "error", "message": message or "登录被拒绝"}
    return {"status": "waiting", "message": "等待扫码"}


def get_book_info(book_id: str) -> dict[str, Any]:
    session = requests.Session()
    response = _request_get(
        session,
        BOOK_INFO_ENDPOINT,
        stage="作品信息",
        headers=_wxapp_headers(),
        params={"bookId": book_id},
    )
    payload = _json_payload(response, "作品信息")
    data = payload.get("data")
    book_info = data.get("bookInfo") if isinstance(data, dict) else None
    if payload.get("code") != 0 or not isinstance(book_info, dict):
        raise QidianApiError(str(payload.get("msg") or "获取起点作品信息失败"))
    return dict(book_info)


def get_catalog(book_id: str) -> dict[str, Any]:
    session = requests.Session()
    response = _request_get(
        session,
        CATALOG_ENDPOINT,
        stage="作品目录",
        headers=_wxapp_headers(),
        params={"bookId": book_id},
    )
    payload = _json_payload(response, "作品目录")
    data = payload.get("data")
    if payload.get("code") != 0 or not isinstance(data, dict):
        raise QidianApiError(str(payload.get("msg") or "获取起点作品目录失败"))

    volumes: list[dict[str, Any]] = []
    for volume_index, raw_volume in enumerate(data.get("vs") or []):
        if not isinstance(raw_volume, dict):
            continue
        chapters: list[dict[str, Any]] = []
        for raw_chapter in raw_volume.get("cs") or []:
            if not isinstance(raw_chapter, dict):
                continue
            chapter_id = str(raw_chapter.get("id") or "")
            if not chapter_id.isdigit():
                continue
            chapters.append(
                {
                    "chapterId": chapter_id,
                    "chapterName": str(raw_chapter.get("cN") or "未命名章节"),
                    "wordCount": raw_chapter.get("cnt"),
                    "postTime": raw_chapter.get("uT"),
                    "isVip": raw_chapter.get("sS") != 1,
                }
            )
        volumes.append(
            {
                "volumeIndex": volume_index,
                "chapterCount": len(chapters),
                "chapters": chapters,
            }
        )
    return {
        "bookId": str(data.get("bookId") or book_id),
        "bookName": str(data.get("bookName") or ""),
        "volumes": volumes,
        "chapterTotal": sum(len(volume["chapters"]) for volume in volumes),
    }


def _extract_page_context(value: str) -> dict[str, Any] | None:
    match = _PAGE_CONTEXT_PATTERN.search(value)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def search_books(
    keyword: str,
    *,
    page: int = 1,
    page_size: int = 20,
    order_by: str = "default",
    gender: str | None = None,
) -> dict[str, Any]:
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return {
            "data": {
                "keyword": "",
                "total": 0,
                "pageNum": 1,
                "pageSize": 0,
                "isLast": 1,
                "orderBy": 0,
                "books": [],
            }
        }
    resolved_page = max(1, int(page or 1))
    resolved_page_size = min(20, max(1, int(page_size or 20)))
    order_by_value = SEARCH_ORDER_BY.get(order_by, 0)
    params: dict[str, Any] = {
        "pageNum": resolved_page,
        "orderBy": order_by_value,
    }
    if gender in {"male", "female"}:
        params["gender"] = gender
    search_url = f"{SEARCH_ENDPOINT}{quote(normalized_keyword, safe='')}.html"
    session = requests.Session()
    try:
        response = _request_get(
            session,
            search_url,
            stage="作品搜索",
            headers=_mobile_headers(),
            params=params,
        )
    finally:
        session.close()

    page_context = _extract_page_context(response.text)
    try:
        page_data = page_context["pageContext"]["pageProps"]["pageData"]
        book_info = page_data["bookInfo"]
    except (KeyError, TypeError):
        raise QidianApiError("起点搜索页面缺少作品数据") from None
    if not isinstance(page_data, dict) or not isinstance(book_info, dict):
        raise QidianApiError("起点搜索作品数据格式无效")

    raw_records = book_info.get("records")
    records = raw_records if isinstance(raw_records, list) else []
    books: list[dict[str, Any]] = []
    for raw in records[:resolved_page_size]:
        if not isinstance(raw, dict):
            continue
        cover = str(raw.get("imgUrl") or "").strip()
        if cover.startswith("//"):
            cover = f"https:{cover}"
        books.append(
            {
                "bookId": raw.get("bid"),
                "bookName": raw.get("bName"),
                "cbid": raw.get("cbid"),
                "authorId": raw.get("cid"),
                "authorName": raw.get("bAuth"),
                "desc": raw.get("desc"),
                "category": raw.get("cat"),
                "subCategory": raw.get("subCateName"),
                "state": raw.get("state"),
                "signStatus": raw.get("signStatus"),
                "coverUrl": cover,
                "isVip": raw.get("isVip"),
                "wordCountText": raw.get("cnt"),
                "recommendCnt": raw.get("recomendCnt"),
                "favoriteCnt": raw.get("favoriteCnt"),
                "lastChapterName": raw.get("lastChapterName"),
                "lastUpdateTime": raw.get("lastUpdateTime"),
                "bookType": raw.get("bookType"),
                "isPub": raw.get("isPub"),
            }
        )
    return {
        "data": {
            "keyword": page_data.get("kw") or normalized_keyword,
            "total": book_info.get("total"),
            "pageNum": book_info.get("pageNum"),
            "pageSize": book_info.get("pageSize"),
            "isLast": book_info.get("isLast"),
            "orderBy": order_by_value,
            "books": books,
        }
    }


def _extract_paragraphs(value: str) -> list[str]:
    if not value:
        return []
    paragraphs: list[str] = []
    for part in re.split(r"<p[^>]*>|</p>|<br\s*/?>", value, flags=re.IGNORECASE):
        text = html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _truthy_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() not in {"", "0", "false", "none", "null"}


def get_chapter(
    book_id: str,
    chapter_id: str,
    *,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    session = requests.Session()
    response = _request_get(
        session,
        canonical_chapter_url(book_id, chapter_id),
        stage="章节正文",
        headers=_mobile_headers(),
        cookies=cookies or {},
    )
    page_context = _extract_page_context(response.text)
    try:
        page_data = page_context["pageContext"]["pageProps"]["pageData"]
        chapter_info = page_data["chapterInfo"]
    except (KeyError, TypeError):
        raise QidianApiError("起点章节页面缺少正文数据") from None
    if not isinstance(chapter_info, dict):
        raise QidianApiError("起点章节正文格式无效")
    if chapter_info.get("fkp"):
        raise QidianApiError("该章节为起点受保护正文，当前插件不处理受保护内容解密")
    if _truthy_flag(chapter_info.get("freeStatus")) and not _truthy_flag(chapter_info.get("isBuy")):
        raise QidianApiError("该章节仅返回试读内容，请在起点确认访问权限")

    paragraphs = _extract_paragraphs(str(chapter_info.get("content") or ""))
    if not paragraphs:
        raise QidianApiError("起点章节未返回可用正文")
    return {
        "chapterName": str(chapter_info.get("chapterName") or ""),
        "text": "\n".join(paragraphs),
        "paragraphs": paragraphs,
        "accessRestricted": _truthy_flag(chapter_info.get("vipStatus")),
        "authenticated": bool(cookies),
    }


def get_bookshelf_page(
    cookies: dict[str, str],
    *,
    group_id: int = -100,
    page: int = 1,
    page_size: int = 100,
    sort: int = 0,
) -> dict[str, Any]:
    if not cookies.get("ywguid") or not cookies.get("ywkey"):
        raise QidianApiError("尚未登录起点账号")
    session = requests.Session()
    response = _request_get(
        session,
        BOOKSHELF_ENDPOINT,
        stage="账号书架",
        headers=_mobile_headers("https://m.qidian.com/bookshelf/my/"),
        cookies=cookies,
        params={
            "gid": group_id,
            "sort": sort,
            "pageNum": page,
            "pageSize": page_size,
            "sortChange": 0,
            "_csrfToken": cookies.get("_csrfToken", ""),
        },
    )
    payload = _json_payload(response, "账号书架")
    data = payload.get("data")
    if payload.get("code") != 0 or not isinstance(data, dict):
        raise QidianApiError(str(payload.get("msg") or "获取起点账号书架失败"))

    groups = [dict(item) for item in data.get("groups") or [] if isinstance(item, dict)]
    group_names = {str(item.get("groupId")): str(item.get("groupName") or "") for item in groups}
    books: list[dict[str, Any]] = []
    for raw_book in data.get("list") or []:
        if not isinstance(raw_book, dict):
            continue
        book_id = str(raw_book.get("bid") or "")
        if not book_id.isdigit():
            continue
        raw_group_id = raw_book.get("groupId")
        books.append(
            {
                "bid": book_id,
                "bookName": str(raw_book.get("bName") or "未命名作品"),
                "authorName": str(raw_book.get("bAuth") or ""),
                "cateName": str(raw_book.get("cateName") or ""),
                "groupId": raw_group_id,
                "groupName": group_names.get(str(raw_group_id), ""),
            }
        )
    page_payload = data.get("page") if isinstance(data.get("page"), dict) else {}
    return {
        "count": int(data.get("count") or len(books)),
        "groups": groups,
        "page": dict(page_payload),
        "books": books,
    }
