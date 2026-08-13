from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import HTTPException, Request, status

from .db import touch_device
from .models import DeviceRecord

DEVICE_ID_HEADER = "X-QingJuan-Device-ID"
DEVICE_NAME_HEADER = "X-QingJuan-Device-Name"
DEVICE_PLATFORM_HEADER = "X-QingJuan-Device-Platform"

_DEVICE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_PLATFORMS = {"android", "windows", "linux", "macos", "ios", "other"}
_PLATFORM_LABELS = {
    "android": "Android 设备",
    "windows": "Windows 设备",
    "linux": "Linux 设备",
    "macos": "macOS 设备",
    "ios": "iOS 设备",
    "other": "未知设备",
}


@dataclass(frozen=True, slots=True)
class RequestDeviceIdentity:
    id: str
    name: str
    platform: str
    ip_address: str


def parse_request_device(request: Request) -> RequestDeviceIdentity | None:
    device_id = request.headers.get(DEVICE_ID_HEADER, "").strip().lower()
    encoded_name = request.headers.get(DEVICE_NAME_HEADER, "").strip()
    raw_platform = request.headers.get(DEVICE_PLATFORM_HEADER, "").strip().lower()
    if not device_id:
        if encoded_name or raw_platform:
            raise _invalid_device_headers()
        return None
    if not _DEVICE_ID_PATTERN.fullmatch(device_id):
        raise _invalid_device_headers()

    platform = raw_platform or "other"
    if platform not in _PLATFORMS:
        platform = "other"
    name = _decode_device_name(encoded_name)
    if not name:
        name = f"{_PLATFORM_LABELS[platform]} {device_id[:6]}"
    client_host = request.client.host if request.client is not None else "unknown"
    ip_address = client_host.strip()[:128] or "unknown"
    return RequestDeviceIdentity(
        id=device_id,
        name=name,
        platform=platform,
        ip_address=ip_address,
    )


async def register_request_device(request: Request) -> DeviceRecord | None:
    identity = parse_request_device(request)
    if identity is None:
        return None
    device = await asyncio.to_thread(
        touch_device,
        device_id=identity.id,
        name=identity.name,
        platform=identity.platform,
        ip_address=identity.ip_address,
    )
    if device.banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此设备已被管理员封禁",
        )
    return device


def _decode_device_name(value: str) -> str:
    if not value:
        return ""
    if len(value) > 300 or not value.isascii():
        raise _invalid_device_headers()
    try:
        decoded = unquote(value, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _invalid_device_headers() from error
    normalized = " ".join(decoded.split())
    if len(normalized) > 80 or any(not character.isprintable() for character in normalized):
        raise _invalid_device_headers()
    return normalized


def _invalid_device_headers() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="设备标识格式无效",
    )
