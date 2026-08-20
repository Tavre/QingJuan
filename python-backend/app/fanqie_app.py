from __future__ import annotations

import json
import os
import secrets
import string
from dataclasses import dataclass
from typing import Any

import httpx

from .fanqie_crypto import (
    APP_BASE_URL,
    APP_USER_AGENT,
    build_app_query,
    decrypt_chapter_payload,
    decrypt_register_key,
    encrypt_register_body,
    sign_app_request,
)
from .fanqie_parser import FanqieReaderChapter, parse_fanqie_chapter_content

DEFAULT_DEVICE_ID = "2187355326004404"
DEFAULT_INSTALL_ID = "2187355326270644"
FANQIE_APP_MAX_RETRIES = 2
FANQIE_APP_TIMEOUT = 30.0


def _random_string(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _app_config_from_environment() -> FanqieAppConfig:
    return FanqieAppConfig(
        device_id=os.environ.get("QINGJUAN_FANQIE_DEVICE_ID", DEFAULT_DEVICE_ID).strip(),
        install_id=os.environ.get("QINGJUAN_FANQIE_INSTALL_ID", DEFAULT_INSTALL_ID).strip(),
    )


@dataclass(frozen=True)
class FanqieAppConfig:
    device_id: str
    install_id: str


@dataclass(frozen=True)
class FanqieAppChapter:
    chapter: FanqieReaderChapter
    key_version: int | None


class FanqieAppClient:
    """番茄阅读 APP 全文接口适配器。

    网页章节被限制时，APP 接口仍会返回加密正文。密钥只保存在当前请求
    生命周期的内存中，不写入项目数据目录或日志。
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        config: FanqieAppConfig | None = None,
        base_url: str = APP_BASE_URL,
    ) -> None:
        self._client = client
        self._config = config or _app_config_from_environment()
        self._base_url = base_url.rstrip("/")
        self._key: bytes | None = None
        self._key_version: int | None = None

    async def fetch_chapter(
        self,
        item_id: str,
        *,
        book_id: str = "",
        title: str = "",
        source_url: str | None = None,
        access_restricted: bool = True,
    ) -> FanqieAppChapter:
        normalized_item_id = str(item_id or "").strip()
        if not normalized_item_id.isdigit():
            raise ValueError("番茄章节编号无效")
        for attempt in range(FANQIE_APP_MAX_RETRIES + 1):
            await self._ensure_key()
            query = build_app_query(
                normalized_item_id,
                device_id=self._config.device_id,
                install_id=self._config.install_id,
            )
            payload = await self._get_json("/reader/full/v", query)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                raise ValueError("番茄 APP 接口未返回章节数据")
            key_version = _integer(data.get("key_version"))
            encrypted = str(data.get("content") or "").strip()
            if not encrypted or encrypted == "Invalid":
                if attempt < FANQIE_APP_MAX_RETRIES:
                    self._invalidate_key()
                    continue
                raise ValueError("番茄 APP 接口未返回可解密正文")
            if self._key is None:
                raise ValueError("番茄 APP 解密密钥未初始化")
            if key_version and self._key_version != key_version:
                if attempt < FANQIE_APP_MAX_RETRIES:
                    self._invalidate_key()
                    continue
                raise ValueError("番茄 APP 解密密钥版本不匹配")
            content = decrypt_chapter_payload(
                encrypted,
                key=self._key,
                compressed=_integer(data.get("compress_status")) == 1,
            )
            html = _content_html(content)
            if not html:
                raise ValueError("番茄 APP 解密结果不是章节正文")
            resolved_url = source_url or f"https://fanqienovel.com/reader/{normalized_item_id}"
            chapter = parse_fanqie_chapter_content(
                item_id=normalized_item_id,
                book_id=str(data.get("book_id") or data.get("bookId") or book_id),
                title=str(data.get("title") or data.get("chapter_title") or title),
                content=html,
                source_url=resolved_url,
                access_restricted=access_restricted,
                declared_word_count=_declared_word_count(data),
                content_source="app_full_api",
                authorization_method="app_full_api",
            )
            return FanqieAppChapter(chapter=chapter, key_version=self._key_version)
        raise ValueError("番茄 APP 章节请求超过重试上限")

    async def _ensure_key(self) -> None:
        if self._key is not None and self._key_version is not None:
            return
        body = encrypt_register_body(self._config.device_id, random_text=_random_string())
        query = build_app_query(device_id=self._config.device_id, install_id=self._config.install_id)
        payload = await self._post_json("/crypt/registerkey", query, body)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("key"):
            raise ValueError("番茄 APP 密钥注册失败")
        self._key = decrypt_register_key(str(data["key"]))
        version = _integer(data.get("keyver"), 0)
        self._key_version = version or None

    def _invalidate_key(self) -> None:
        self._key = None
        self._key_version = None

    async def _get_json(self, path: str, query: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}?{query}"
        headers = {
            **sign_app_request(query),
            "User-Agent": APP_USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://fanqienovel.com/",
        }
        response = await self._client.get(url, headers=headers)
        response.raise_for_status()
        return _decode_json_response(response)

    async def _post_json(self, path: str, query: str, body: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}?{query}"
        headers = {
            **sign_app_request(query, body),
            "User-Agent": APP_USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Referer": "https://fanqienovel.com/",
        }
        response = await self._client.post(url, headers=headers, content=body)
        response.raise_for_status()
        return _decode_json_response(response)


def _decode_json_response(response: httpx.Response) -> dict[str, Any]:
    if not response.content:
        raise ValueError("番茄 APP 接口返回空响应")
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("番茄 APP 接口返回无效 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("番茄 APP 接口返回结构异常")
    code = _integer(payload.get("code"), 0)
    if code not in {0, 200}:
        message = str(payload.get("message") or payload.get("status_msg") or f"code={code}")
        raise ValueError(f"番茄 APP 接口请求失败：{message}")
    return payload


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _declared_word_count(data: dict[str, Any]) -> int:
    for key in ("chapterWordNumber", "chapter_word_number", "word_count", "wordCount", "word_number"):
        value = _integer(data.get(key))
        if value > 0:
            return value
    return 0


def _content_html(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("content", "html", "body"):
            value = content.get(key)
            if isinstance(value, str):
                return value
    return ""


__all__ = ["FanqieAppChapter", "FanqieAppClient", "FanqieAppConfig"]
