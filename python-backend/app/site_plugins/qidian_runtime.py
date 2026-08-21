from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import requests

from .qidian_client import (
    QidianApiError,
    get_bookshelf_page,
    get_qrcode,
    poll_qrcode,
)

LOGIN_FLOW_TTL = timedelta(minutes=3)
ACCOUNT_SESSION_TTL = timedelta(hours=24)
MAX_BOOKSHELF_PAGES_PER_GROUP = 200


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class _LoginFlow:
    session: requests.Session
    upstream_session_key: str
    expires_at: datetime


class QidianRuntime:
    """起点插件的进程内登录态；任何公开方法都不返回 Cookie 或上游 sessionKey。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._login_flows: dict[str, _LoginFlow] = {}
        self._cookies: dict[str, str] = {}
        self._account_expires_at: datetime | None = None

    def account_status(self) -> dict[str, object]:
        with self._lock:
            self._purge_locked()
            logged_in = bool(self._cookies)
            return {
                "loggedIn": logged_in,
                "expiresAt": _iso(self._account_expires_at)
                if logged_in and self._account_expires_at
                else None,
            }

    def start_login(self) -> dict[str, object]:
        session = requests.Session()
        try:
            result = get_qrcode(session)
        except Exception:
            session.close()
            raise
        flow_id = f"qidian-login-{uuid4()}"
        expires_at = _now() + LOGIN_FLOW_TTL
        flow = _LoginFlow(
            session=session,
            upstream_session_key=str(result["sessionKey"]),
            expires_at=expires_at,
        )
        with self._lock:
            self._purge_locked()
            self._login_flows[flow_id] = flow
        return {
            "flowId": flow_id,
            "qrImageBase64": str(result["qrImageBase64"]),
            "expiresAt": _iso(expires_at),
        }

    def poll_login(self, flow_id: str) -> dict[str, object]:
        with self._lock:
            self._purge_locked()
            flow = self._login_flows.get(flow_id)
        if flow is None:
            raise QidianApiError("登录二维码不存在或已过期")

        result = poll_qrcode(flow.session, flow.upstream_session_key)
        status = str(result.get("status") or "error")
        message = str(result.get("message") or "登录状态未知")
        logged_in = False
        if status == "success":
            cookies = result.get("cookies")
            if not isinstance(cookies, dict):
                raise QidianApiError("起点登录会话无效")
            sanitized = {str(key): str(value) for key, value in cookies.items()}
            with self._lock:
                self._cookies = sanitized
                self._account_expires_at = _now() + ACCOUNT_SESSION_TTL
                self._close_all_flows_locked()
            logged_in = True
        elif status in {"cancelled", "expired", "error"}:
            with self._lock:
                removed = self._login_flows.pop(flow_id, None)
                if removed is not None:
                    removed.session.close()
        return {"status": status, "message": message, "loggedIn": logged_in}

    def logout(self) -> None:
        with self._lock:
            self._cookies = {}
            self._account_expires_at = None
            self._close_all_flows_locked()

    def cookies(self) -> dict[str, str]:
        with self._lock:
            self._purge_locked()
            return dict(self._cookies)

    def list_bookshelf_books(self) -> list[dict[str, object]]:
        cookies = self.cookies()
        if not cookies:
            raise QidianApiError("尚未登录起点账号")

        first_page = get_bookshelf_page(cookies, group_id=-100, page=1, page_size=100)
        results_by_id: dict[str, dict[str, object]] = {}
        self._merge_books(results_by_id, first_page.get("books"))
        self._fetch_group_pages(
            cookies,
            group_id=-100,
            first_page=first_page,
            target=results_by_id,
        )

        group_ids: list[int] = []
        for group in first_page.get("groups") or []:
            if not isinstance(group, dict):
                continue
            group_id = _as_int(group.get("groupId"), -100)
            if group_id != -100 and group_id not in group_ids:
                group_ids.append(group_id)
        for group_id in group_ids:
            group_first = get_bookshelf_page(cookies, group_id=group_id, page=1, page_size=100)
            self._merge_books(results_by_id, group_first.get("books"))
            self._fetch_group_pages(
                cookies,
                group_id=group_id,
                first_page=group_first,
                target=results_by_id,
            )
        return list(results_by_id.values())

    def _fetch_group_pages(
        self,
        cookies: dict[str, str],
        *,
        group_id: int,
        first_page: dict[str, object],
        target: dict[str, dict[str, object]],
    ) -> None:
        page_info = first_page.get("page")
        page_info = page_info if isinstance(page_info, dict) else {}
        total_pages = max(1, _as_int(page_info.get("totalPage"), 1))
        total_pages = min(total_pages, MAX_BOOKSHELF_PAGES_PER_GROUP)
        for page_number in range(2, total_pages + 1):
            page_payload = get_bookshelf_page(
                cookies,
                group_id=group_id,
                page=page_number,
                page_size=100,
            )
            self._merge_books(target, page_payload.get("books"))
            current_page = page_payload.get("page")
            if isinstance(current_page, dict) and bool(_as_int(current_page.get("isLast"), 0)):
                break

    @staticmethod
    def _merge_books(
        target: dict[str, dict[str, object]],
        books: object,
    ) -> None:
        if not isinstance(books, list):
            return
        for item in books:
            if not isinstance(item, dict):
                continue
            book_id = str(item.get("bid") or "")
            if book_id.isdigit():
                target.setdefault(book_id, dict(item))

    def _purge_locked(self) -> None:
        now = _now()
        expired_flow_ids = [flow_id for flow_id, flow in self._login_flows.items() if flow.expires_at <= now]
        for flow_id in expired_flow_ids:
            flow = self._login_flows.pop(flow_id)
            flow.session.close()
        if self._account_expires_at is not None and self._account_expires_at <= now:
            self._cookies = {}
            self._account_expires_at = None

    def _close_all_flows_locked(self) -> None:
        for flow in self._login_flows.values():
            flow.session.close()
        self._login_flows.clear()


QIDIAN_RUNTIME = QidianRuntime()
