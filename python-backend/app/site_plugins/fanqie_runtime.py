from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import requests

from .fanqie_client import (
    FanqieApiError,
    create_session,
    get_bookshelf,
    get_qrcode,
    login_with_cookies,
    poll_qrcode,
)

LOGIN_FLOW_TTL = timedelta(minutes=3)
ACCOUNT_SESSION_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class _LoginFlow:
    session: requests.Session
    upstream_qrcode_token: str
    expires_at: datetime


class FanqieRuntime:
    """番茄插件进程内登录态；公开结果不包含 Cookie、账号 ID 或上游二维码令牌。"""

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
        session = create_session()
        try:
            result = get_qrcode(session)
        except Exception:
            session.close()
            raise
        flow_id = f"fanqie-login-{uuid4()}"
        expires_at = _now() + LOGIN_FLOW_TTL
        flow = _LoginFlow(
            session=session,
            upstream_qrcode_token=str(result["qrcodeToken"]),
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
            raise FanqieApiError("登录二维码不存在或已过期")

        result = poll_qrcode(flow.session, flow.upstream_qrcode_token)
        status = str(result.get("status") or "error")
        message = str(result.get("message") or "登录状态未知")
        logged_in = False
        if status == "success":
            cookies = result.get("cookies")
            if not isinstance(cookies, dict):
                raise FanqieApiError("番茄登录会话无效")
            sanitized = {str(key): str(value) for key, value in cookies.items()}
            with self._lock:
                self._cookies = sanitized
                self._account_expires_at = _now() + ACCOUNT_SESSION_TTL
                self._close_all_flows_locked(except_session=flow.session)
                flow.session.close()
            logged_in = True
        elif status in {"cancelled", "expired", "error"}:
            with self._lock:
                removed = self._login_flows.pop(flow_id, None)
                if removed is not None:
                    removed.session.close()
        return {"status": status, "message": message, "loggedIn": logged_in}

    def login_cookies(self, cookie_header: str) -> dict[str, object]:
        result = login_with_cookies(cookie_header)
        cookies = result.get("cookies")
        if not isinstance(cookies, dict):
            raise FanqieApiError("番茄登录会话无效")
        with self._lock:
            self._cookies = {str(key): str(value) for key, value in cookies.items()}
            self._account_expires_at = _now() + ACCOUNT_SESSION_TTL
            self._close_all_flows_locked()
        return self.account_status()

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
            raise FanqieApiError("尚未登录番茄账号")
        return list(get_bookshelf(cookies)["books"])

    def _purge_locked(self) -> None:
        now = _now()
        expired_flow_ids = [flow_id for flow_id, flow in self._login_flows.items() if flow.expires_at <= now]
        for flow_id in expired_flow_ids:
            flow = self._login_flows.pop(flow_id)
            flow.session.close()
        if self._account_expires_at is not None and self._account_expires_at <= now:
            self._cookies = {}
            self._account_expires_at = None

    def _close_all_flows_locked(self, *, except_session: requests.Session | None = None) -> None:
        for flow in self._login_flows.values():
            if flow.session is not except_session:
                flow.session.close()
        self._login_flows.clear()


FANQIE_RUNTIME = FanqieRuntime()
