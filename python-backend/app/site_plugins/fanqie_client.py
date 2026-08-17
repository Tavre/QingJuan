from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlparse

import requests

WEB_ORIGIN = "https://fanqienovel.com"
PASSPORT_ORIGIN = "https://passport.fanqienovel.com"
WEB_AID = 1967
WEB_BIZ_TYPE = "web_novel_pc"
REQUEST_TIMEOUT_SECONDS = 25
MAX_COOKIE_HEADER_LENGTH = 64 * 1024
MAX_QR_IMAGE_BYTES = 2 * 1024 * 1024

GET_QRCODE_ENDPOINT = f"{PASSPORT_ORIGIN}/passport/web/get_qrcode/"
CHECK_QRCODE_ENDPOINT = f"{PASSPORT_ORIGIN}/passport/web/check_qrconnect/"
USER_INFO_ENDPOINTS = (
    f"{WEB_ORIGIN}/api/user/info/v2",
    f"{WEB_ORIGIN}/api/user/info",
)
BOOKSHELF_ENDPOINT = f"{WEB_ORIGIN}/reading/bookapi/bookshelf/info/v:version/"
SEARCH_ENDPOINT = f"{WEB_ORIGIN}/api/author/search/search_book/v1"

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class FanqieApiError(RuntimeError):
    pass


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DESKTOP_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"{WEB_ORIGIN}/",
        }
    )
    return session


def _request_get(
    session: requests.Session,
    url: str,
    *,
    stage: str,
    params: dict[str, Any] | None = None,
) -> requests.Response:
    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise FanqieApiError(f"番茄{stage}请求失败") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise FanqieApiError(f"番茄{stage}请求失败（HTTP {response.status_code}）")
    return response


def _json_payload(response: requests.Response, stage: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise FanqieApiError(f"番茄{stage}响应无法解析") from exc
    if not isinstance(payload, dict):
        raise FanqieApiError(f"番茄{stage}响应格式无效")
    return payload


def _successful_payload(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    if payload.get("code") != 0:
        message = str(payload.get("message") or "").strip()
        if "登录" in message or "login" in message.lower():
            raise FanqieApiError("番茄登录已过期，请重新登录")
        raise FanqieApiError(f"番茄{stage}失败")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise FanqieApiError(f"番茄{stage}响应缺少数据")
    return data


def _qr_image_base64(session: requests.Session, value: str) -> str:
    image = value.strip()
    if image.startswith("data:") and "," in image:
        return image.split(",", 1)[1]
    if not image.lower().startswith(("http://", "https://")):
        return image

    parsed = urlparse(image)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not (
        host == "fanqienovel.com" or host.endswith(".fanqienovel.com")
    ):
        raise FanqieApiError("番茄登录二维码地址不受信任")
    response = _request_get(session, image, stage="登录二维码图片")
    if len(response.content) > MAX_QR_IMAGE_BYTES:
        raise FanqieApiError("番茄登录二维码图片过大")
    return base64.b64encode(response.content).decode("ascii")


def get_qrcode(session: requests.Session) -> dict[str, Any]:
    response = _request_get(
        session,
        GET_QRCODE_ENDPOINT,
        stage="登录二维码",
        params={
            "aid": WEB_AID,
            "service": WEB_ORIGIN,
            "need_confirm": "1",
            "device_platform": "web",
            "biz_type": WEB_BIZ_TYPE,
            "from": WEB_BIZ_TYPE,
        },
    )
    data = _successful_payload(_json_payload(response, "登录二维码"), "获取登录二维码")
    token = str(data.get("qrcode_token") or "").strip()
    image = str(data.get("image") or "").strip()
    if not token or not image:
        raise FanqieApiError("番茄登录二维码响应缺少必要字段")
    return {
        "qrcodeToken": token,
        "qrImageBase64": _qr_image_base64(session, image),
        "expireSeconds": 180,
    }


def poll_qrcode(session: requests.Session, qrcode_token: str) -> dict[str, Any]:
    response = _request_get(
        session,
        CHECK_QRCODE_ENDPOINT,
        stage="扫码状态",
        params={"aid": WEB_AID, "qrcode_token": qrcode_token},
    )
    data = _successful_payload(_json_payload(response, "扫码状态"), "查询扫码状态")
    try:
        status = int(data.get("status", 1))
    except (TypeError, ValueError):
        status = 1
    if status == 1:
        return {"status": "waiting", "message": "等待扫码"}
    if status == 2:
        return {"status": "scanned", "message": "已扫码，请在手机上确认"}
    if status == 4:
        return {"status": "expired", "message": "二维码已过期"}
    if status != 3:
        return {"status": "error", "message": "番茄返回了未知扫码状态"}

    get_user_info(session)
    cookies = {str(key): str(value) for key, value in session.cookies.get_dict().items()}
    if not cookies:
        raise FanqieApiError("番茄扫码已确认，但未取得可用登录会话")
    return {"status": "success", "message": "登录成功", "cookies": cookies}


def parse_cookie_header(value: str) -> dict[str, str]:
    if not value or not value.strip():
        raise FanqieApiError("请输入番茄请求 Cookie")
    if len(value) > MAX_COOKIE_HEADER_LENGTH:
        raise FanqieApiError("番茄 Cookie 内容过长")
    if "\r" in value or "\n" in value:
        raise FanqieApiError("番茄 Cookie 格式无效")

    cookies: dict[str, str] = {}
    for segment in value.split(";"):
        part = segment.strip()
        if not part or "=" not in part:
            continue
        name, cookie_value = part.split("=", 1)
        name = name.strip()
        cookie_value = cookie_value.strip()
        if not name or not _COOKIE_NAME_PATTERN.fullmatch(name):
            raise FanqieApiError("番茄 Cookie 格式无效")
        cookies[name] = cookie_value
    if not cookies:
        raise FanqieApiError("番茄 Cookie 中没有可用字段")
    return cookies


def session_from_cookies(cookies: dict[str, str]) -> requests.Session:
    session = create_session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".fanqienovel.com", path="/")
    return session


def login_with_cookies(cookie_header: str) -> dict[str, Any]:
    session = session_from_cookies(parse_cookie_header(cookie_header))
    try:
        get_user_info(session)
        cookies = {str(key): str(value) for key, value in session.cookies.get_dict().items()}
        return {"cookies": cookies}
    finally:
        session.close()


def get_user_info(session: requests.Session) -> dict[str, Any]:
    for endpoint in USER_INFO_ENDPOINTS:
        response = _request_get(session, endpoint, stage="账号状态")
        payload = _json_payload(response, "账号状态")
        data = payload.get("data")
        if payload.get("code") != 0 or not isinstance(data, dict):
            continue
        user_id = str(data.get("id") or data.get("user_id") or "").strip()
        if user_id not in {"", "0", "1"}:
            return dict(data)
    raise FanqieApiError("未检测到有效番茄登录状态，请确认 Cookie 完整且未过期")


def get_bookshelf(cookies: dict[str, str]) -> dict[str, Any]:
    if not cookies:
        raise FanqieApiError("尚未登录番茄账号")
    session = session_from_cookies(cookies)
    try:
        get_user_info(session)
        response = _request_get(
            session,
            BOOKSHELF_ENDPOINT,
            stage="账号书架",
            params={
                "aid": WEB_AID,
                "iid": 0,
                "version_code": "57700",
                "update_version_code": "57700",
            },
        )
        data = _successful_payload(_json_payload(response, "账号书架"), "获取账号书架")
    finally:
        session.close()

    raw_books = data.get("book_shelf_info") or data.get("bookShelfInfo") or []
    raw_groups = data.get("group_data") or data.get("groupData") or []
    books_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(raw_books, list):
        for item in raw_books:
            if not isinstance(item, dict):
                continue
            book_id = str(item.get("book_id") or item.get("bookId") or "").strip()
            if not book_id.isdigit():
                continue
            books_by_id.setdefault(
                book_id,
                {
                    "bookId": book_id,
                    "bookType": item.get("book_type", item.get("bookType", 0)),
                    "groupId": str(item.get("group_id") or item.get("groupId") or ""),
                    "groupName": str(item.get("group_name") or item.get("groupName") or ""),
                },
            )
    groups = [dict(item) for item in raw_groups if isinstance(item, dict)] if isinstance(raw_groups, list) else []
    return {"books": list(books_by_id.values()), "groups": groups}


def search_books(query: str, limit: int = 20, *, cookies: dict[str, str] | None = None) -> list[dict[str, Any]]:
    keyword = query.strip()
    if not keyword:
        return []
    session = session_from_cookies(cookies or {})
    try:
        response = _request_get(
            session,
            SEARCH_ENDPOINT,
            stage="作品搜索",
            params={"query_word": keyword, "limit": max(1, min(limit, 60))},
        )
        payload = _json_payload(response, "作品搜索")
    finally:
        session.close()
    if payload.get("code") != 0:
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    values = data.get("search_book_data_list") or []
    return [dict(item) for item in values if isinstance(item, dict)] if isinstance(values, list) else []
