from __future__ import annotations

import base64
import json

import httpx
import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from app.fanqie_app import FanqieAppClient, FanqieAppConfig
from app.fanqie_crypto import SHARED_KEY, decrypt_chapter_payload, sm3


def _encrypted(value: bytes, key: bytes, iv: bytes) -> str:
    return base64.b64encode(iv + AES.new(key, AES.MODE_CBC, iv).encrypt(pad(value, 16))).decode("ascii")


def test_sm3_matches_standard_vector() -> None:
    assert sm3(b"abc").hex() == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"


def test_decrypt_chapter_payload_supports_html_and_json() -> None:
    key = bytes(range(16))
    iv = bytes(range(16, 32))
    html = "<p>完整正文</p>".encode()
    assert decrypt_chapter_payload(_encrypted(html, key, iv), key=key) == "<p>完整正文</p>"
    payload = json.dumps({"content": "<p>正文</p>"}, ensure_ascii=False).encode("utf-8")
    assert decrypt_chapter_payload(_encrypted(payload, key, iv), key=key) == {"content": "<p>正文</p>"}


@pytest.mark.asyncio
async def test_app_client_registers_key_and_fetches_full_chapter() -> None:
    chapter_key = bytes(range(16))
    register_iv = bytes(range(32, 48))
    register_ciphertext = _encrypted(chapter_key, SHARED_KEY, register_iv)
    chapter_iv = bytes(range(48, 64))
    chapter_ciphertext = _encrypted("<p>完整的受限正文</p>".encode(), chapter_key, chapter_iv)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/crypt/registerkey"):
            return httpx.Response(
                200, json={"code": 0, "data": {"key": register_ciphertext, "keyver": 7}}, request=request
            )
        assert request.url.path.endswith("/reader/full/v")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "item_id": "10001",
                    "book_id": "20001",
                    "title": "受限章",
                    "chapterWordNumber": 7,
                    "key_version": 7,
                    "content": chapter_ciphertext,
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FanqieAppClient(
            client,
            config=FanqieAppConfig(device_id="2187355326004404", install_id="2187355326270644"),
        ).fetch_chapter(
            "10001",
            book_id="20001",
            title="受限章",
            source_url="https://fanqienovel.com/reader/10001",
        )

    assert result.chapter.text == "完整的受限正文"
    assert result.chapter.content_source == "app_full_api"
    assert result.chapter.authorization_method == "app_full_api"
    assert len(requests) == 2
    assert requests[0].method == "POST"
    assert requests[1].method == "GET"
    assert "x-argus" in requests[1].headers
