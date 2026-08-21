from __future__ import annotations

import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_VERIFICATION_URI = "https://github.com/login/device"
_GITHUB_ACCEPT = "application/json"
_GITHUB_API_ACCEPT = "application/vnd.github+json"
_GITHUB_API_VERSION = "2022-11-28"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

DevicePollStatus = Literal[
    "authorized",
    "pending",
    "slow_down",
    "expired",
    "denied",
    "disabled",
]
DeviceFlowPurpose = Literal["login", "bind"]


class GitHubDeviceFlowError(RuntimeError):
    pass


class GitHubFlowNotFound(KeyError):
    pass


class GitHubFlowExpired(TimeoutError):
    pass


class GitHubFlowCapacityExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitHubDeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class GitHubDeviceTokenResult:
    status: DevicePollStatus
    access_token: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubIdentity:
    user_id: str
    login: str


@dataclass(slots=True)
class GitHubDeviceFlow:
    flow_id: str
    purpose: DeviceFlowPurpose
    user_id: str | None
    device_code: str
    client_id: str
    config_revision: int
    auth_epoch: int | None
    expires_at: float
    interval: int
    next_poll_at: float
    owner_key: str
    created_at: float
    in_flight: bool = False


class GitHubDeviceFlowStore:
    MAX_ACTIVE_FLOWS = 1_000
    MAX_ACTIVE_FLOWS_PER_OWNER = 10

    def __init__(self) -> None:
        self._flows: dict[str, GitHubDeviceFlow] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        purpose: DeviceFlowPurpose,
        user_id: str | None,
        device_code: str,
        client_id: str,
        config_revision: int,
        auth_epoch: int | None,
        expires_in: int,
        interval: int,
        owner_key: str = "anonymous",
        now: float | None = None,
    ) -> GitHubDeviceFlow:
        timestamp = time.monotonic() if now is None else now
        flow = GitHubDeviceFlow(
            flow_id=secrets.token_urlsafe(32),
            purpose=purpose,
            user_id=user_id,
            device_code=device_code,
            client_id=client_id,
            config_revision=config_revision,
            auth_epoch=auth_epoch,
            expires_at=timestamp + expires_in,
            interval=interval,
            next_poll_at=timestamp + interval,
            owner_key=owner_key,
            created_at=timestamp,
        )
        with self._lock:
            self._cleanup(timestamp)
            if len(self._flows) >= self.MAX_ACTIVE_FLOWS:
                raise GitHubFlowCapacityExceeded("GitHub 验证流程容量已满")
            owner_count = sum(existing.owner_key == owner_key for existing in self._flows.values())
            if owner_count >= self.MAX_ACTIVE_FLOWS_PER_OWNER:
                raise GitHubFlowCapacityExceeded("GitHub 验证流程创建过于频繁")
            self._flows[flow.flow_id] = flow
        return flow

    def reserve_poll(
        self,
        flow_id: str,
        *,
        now: float | None = None,
    ) -> tuple[GitHubDeviceFlow, int | None]:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            flow = self._flows.get(flow_id)
            if flow is None:
                self._cleanup(timestamp)
                raise GitHubFlowNotFound(flow_id)
            if flow.expires_at <= timestamp:
                self._flows.pop(flow_id, None)
                self._cleanup(timestamp)
                raise GitHubFlowExpired(flow_id)
            if flow.in_flight:
                return flow, 1
            if flow.next_poll_at > timestamp:
                return flow, max(1, math.ceil(flow.next_poll_at - timestamp))
            flow.next_poll_at = timestamp + flow.interval
            flow.in_flight = True
            self._cleanup(timestamp)
            return flow, None

    def release_poll(self, flow_id: str, *, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            flow = self._flows.get(flow_id)
            if flow is not None:
                flow.in_flight = False
                flow.next_poll_at = max(flow.next_poll_at, timestamp + flow.interval)

    def slow_down(self, flow_id: str, *, now: float | None = None) -> int:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            flow = self._flows.get(flow_id)
            if flow is None:
                raise GitHubFlowNotFound(flow_id)
            flow.interval = min(60, flow.interval + 5)
            flow.next_poll_at = timestamp + flow.interval
            flow.in_flight = False
            return flow.interval

    def consume(self, flow_id: str) -> GitHubDeviceFlow:
        with self._lock:
            flow = self._flows.pop(flow_id, None)
        if flow is None:
            raise GitHubFlowNotFound(flow_id)
        return flow

    def discard(self, flow_id: str) -> None:
        with self._lock:
            self._flows.pop(flow_id, None)

    def _cleanup(self, now: float) -> None:
        expired = [flow_id for flow_id, flow in self._flows.items() if flow.expires_at <= now]
        for flow_id in expired:
            self._flows.pop(flow_id, None)


async def start_github_device_authorization(
    client_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> GitHubDeviceAuthorization:
    payload = await _post_json(
        GITHUB_DEVICE_CODE_URL,
        data={"client_id": client_id},
        client=client,
    )
    device_code = _required_string(payload, "device_code", maximum=512)
    user_code = _required_string(payload, "user_code", maximum=64)
    verification_uri = _required_string(payload, "verification_uri", maximum=512)
    parsed_uri = urlsplit(verification_uri)
    if (
        parsed_uri.scheme != "https"
        or parsed_uri.hostname != "github.com"
        or parsed_uri.username is not None
        or parsed_uri.password is not None
        or parsed_uri.port not in {None, 443}
    ):
        raise GitHubDeviceFlowError("GitHub 返回了不可信的验证地址")
    expires_in = _bounded_integer(payload, "expires_in", minimum=60, maximum=1800)
    interval = _bounded_integer(payload, "interval", minimum=1, maximum=60)
    return GitHubDeviceAuthorization(
        device_code=device_code,
        user_code=user_code,
        verification_uri=GITHUB_VERIFICATION_URI,
        expires_in=expires_in,
        interval=interval,
    )


async def poll_github_device_token(
    client_id: str,
    device_code: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> GitHubDeviceTokenResult:
    payload = await _post_json(
        GITHUB_ACCESS_TOKEN_URL,
        data={
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        client=client,
    )
    error = payload.get("error")
    if isinstance(error, str):
        status_by_error: dict[str, DevicePollStatus] = {
            "authorization_pending": "pending",
            "slow_down": "slow_down",
            "expired_token": "expired",
            "access_denied": "denied",
            "device_flow_disabled": "disabled",
        }
        mapped = status_by_error.get(error)
        if mapped is not None:
            return GitHubDeviceTokenResult(status=mapped)
        raise GitHubDeviceFlowError("GitHub Device Flow 请求被拒绝")
    access_token = _required_string(payload, "access_token", maximum=2048)
    token_type = str(payload.get("token_type") or "").casefold()
    if token_type != "bearer":
        raise GitHubDeviceFlowError("GitHub 返回了不兼容的 Token 类型")
    return GitHubDeviceTokenResult(status="authorized", access_token=access_token)


async def fetch_github_identity(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> GitHubIdentity:
    headers = {
        "Accept": _GITHUB_API_ACCEPT,
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        "User-Agent": "QingJuan-Backend",
    }
    if client is not None:
        response = await client.get(GITHUB_USER_URL, headers=headers)
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as owned_client:
            response = await owned_client.get(GITHUB_USER_URL, headers=headers)
    try:
        response.raise_for_status()
        payload = response.json()
    except (ValueError, httpx.HTTPError):
        raise GitHubDeviceFlowError("无法读取 GitHub 用户身份") from None
    if not isinstance(payload, dict):
        raise GitHubDeviceFlowError("GitHub 用户身份响应无效")
    raw_id = payload.get("id")
    login = payload.get("login")
    if not isinstance(raw_id, int) or raw_id <= 0:
        raise GitHubDeviceFlowError("GitHub 用户 ID 无效")
    if (
        not isinstance(login, str)
        or not 1 <= len(login) <= 39
        or login.startswith("-")
        or login.endswith("-")
        or any(not (character.isascii() and (character.isalnum() or character == "-")) for character in login)
    ):
        raise GitHubDeviceFlowError("GitHub 用户名无效")
    return GitHubIdentity(user_id=str(raw_id), login=login)


async def _post_json(
    url: str,
    *,
    data: dict[str, str],
    client: httpx.AsyncClient | None,
) -> dict[str, object]:
    headers = {"Accept": _GITHUB_ACCEPT, "User-Agent": "QingJuan-Backend"}
    if client is not None:
        response = await client.post(url, data=data, headers=headers)
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as owned_client:
            response = await owned_client.post(url, data=data, headers=headers)
    try:
        response.raise_for_status()
        payload = response.json()
    except (ValueError, httpx.HTTPError):
        raise GitHubDeviceFlowError("GitHub Device Flow 服务暂不可用") from None
    if not isinstance(payload, dict):
        raise GitHubDeviceFlowError("GitHub Device Flow 响应无效")
    return payload


def _required_string(payload: dict[str, object], key: str, *, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise GitHubDeviceFlowError("GitHub Device Flow 响应缺少必需字段")
    return value


def _bounded_integer(
    payload: dict[str, object],
    key: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise GitHubDeviceFlowError("GitHub Device Flow 响应时间字段无效")
    return value
