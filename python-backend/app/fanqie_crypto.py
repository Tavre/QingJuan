from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

SHARED_KEY = bytes.fromhex("ac25c67ddd8f38c1b37a2348828e222e")
SIGN_KEY = bytes.fromhex("ac1adaae95a7af94a5114ab3b3a97dd80050aa0a39314c40528caec95256c28c")
DEFAULT_APP_CONFIG = {
    "aid": "1967",
    "license_id": "1611921764",
    "sdk_version": "v04.04.05-ov-android",
    "sdk_version_int": 134744640,
    "call_type": 738,
}
LOW_RAND = bytes((0xF2, 0x81))
HIGH_RAND = b"ao"
XOR_PREFIX = bytes((0xF2, 0xF7, 0xFC, 0xFF, 0xF2, 0xF7, 0xFC, 0xFF))
APP_BASE_URL = "https://reading.snssdk.com/reading"
APP_USER_AGENT = "com.dragon.read"


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _rotl32(value: int, shift: int) -> int:
    shift &= 31
    return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF


def sm3(data: bytes) -> bytes:
    mask = 0xFFFFFFFF
    padded_length = ((len(data) + 9 + 63) // 64) * 64
    message = bytearray(padded_length)
    message[: len(data)] = data
    message[len(data)] = 0x80
    message[-8:] = (len(data) * 8).to_bytes(8, "big")
    state = [
        0x7380166F,
        0x4914B2B9,
        0x172442D7,
        0xDA8A0600,
        0xA96F30BC,
        0x163138AA,
        0xE38DEE4D,
        0xB0FB0E4E,
    ]

    def p0(x: int) -> int:
        return (x ^ _rotl32(x, 9) ^ _rotl32(x, 17)) & mask

    def p1(x: int) -> int:
        return (x ^ _rotl32(x, 15) ^ _rotl32(x, 23)) & mask

    for offset in range(0, len(message), 64):
        words = [int.from_bytes(message[offset + i : offset + i + 4], "big") for i in range(0, 64, 4)]
        for i in range(16, 68):
            words.append(
                p1(words[i - 16] ^ words[i - 9] ^ _rotl32(words[i - 3], 15))
                ^ _rotl32(words[i - 13], 7)
                ^ words[i - 6]
            )
            words[i] &= mask
        expanded = [words[i] ^ words[i + 4] for i in range(64)]
        a, b, c, d, e, f, g, h = state
        for i in range(64):
            t = 0x79CC4519 if i <= 15 else 0x7A879D8A
            ss1 = _rotl32((_rotl32(a, 12) + e + _rotl32(t, i)) & mask, 7)
            ss2 = ss1 ^ _rotl32(a, 12)
            if i <= 15:
                ff = a ^ b ^ c
                gg = e ^ f ^ g
            else:
                ff = (a & b) | (a & c) | (b & c)
                gg = (e & f) | ((~e) & g)
            tt1 = (ff + d + ss2 + expanded[i]) & mask
            tt2 = (gg + h + ss1 + words[i]) & mask
            d, c, b, a = c, _rotl32(b, 9), a, tt1
            h, g, f, e = g, _rotl32(f, 19), e, p0(tt2)
        state = [(left ^ right) & mask for left, right in zip(state, (a, b, c, d, e, f, g, h), strict=True)]
    return b"".join(value.to_bytes(4, "big") for value in state)


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    return pad(data, block_size)


def _protobuf_varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    output = bytearray()
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def _protobuf_field(field_number: int, wire_type: int, value: bytes) -> bytes:
    return _protobuf_varint((field_number << 3) | wire_type) + value


def _protobuf_varint_field(field_number: int, value: int) -> bytes:
    return _protobuf_field(field_number, 0, _protobuf_varint(value))


def _protobuf_bytes_field(field_number: int, value: bytes) -> bytes:
    return _protobuf_field(field_number, 2, _protobuf_varint(len(value)) + value)


def _protobuf_string_field(field_number: int, value: str) -> bytes:
    return _protobuf_bytes_field(field_number, value.encode("utf-8"))


def _build_argus_protobuf(
    query: str, xss_stub: str, timestamp: int, config: Mapping[str, Any], rand: int
) -> bytes:
    params = dict(parse_qsl(query, keep_blank_values=True))
    device_id = params.get("device_id", "")
    version_name = params.get("version_name", "")
    body_hash = sm3(bytes.fromhex(xss_stub) if len(xss_stub) >= 32 else bytes(16))[:6]
    query_hash = sm3(query.encode("utf-8") if query else bytes(16))[:6]
    nested_15 = b"".join(
        (
            _protobuf_varint_field(1, 1),
            _protobuf_varint_field(2, 1),
            _protobuf_varint_field(3, 1),
            _protobuf_varint_field(7, 3348294860),
        )
    )
    nested_23 = b"".join(
        (
            _protobuf_string_field(1, "NX551J"),
            _protobuf_varint_field(2, 8196),
            _protobuf_varint_field(4, 2162219008),
        )
    )
    fields = (
        _protobuf_varint_field(1, 0x20200929 * 2),
        _protobuf_varint_field(2, 2),
        _protobuf_varint_field(3, rand),
        _protobuf_string_field(4, str(config["aid"])),
        _protobuf_string_field(5, device_id),
        _protobuf_string_field(6, str(config["license_id"])),
        _protobuf_string_field(7, version_name),
        _protobuf_string_field(8, str(config["sdk_version"])),
        _protobuf_varint_field(9, int(config["sdk_version_int"])),
        _protobuf_bytes_field(10, bytes(8)),
        _protobuf_varint_field(11, 0),
        _protobuf_varint_field(12, timestamp * 2),
        _protobuf_bytes_field(13, body_hash),
        _protobuf_bytes_field(14, query_hash),
        _protobuf_bytes_field(15, nested_15),
        _protobuf_string_field(16, ""),
        _protobuf_string_field(20, "none"),
        _protobuf_varint_field(21, int(config["call_type"])),
        _protobuf_bytes_field(23, nested_23),
        _protobuf_varint_field(25, 2),
    )
    return b"".join(fields)


def _simon_encrypt(block: bytes, key: bytes) -> bytes:
    mask = 0xFFFFFFFFFFFFFFFF
    z4 = 0x3DC94C3A046D678B
    key_words = [int.from_bytes(key[index : index + 8], "little") for index in range(0, 32, 8)]
    round_keys = list(key_words)

    def ror(value: int, bits: int) -> int:
        return ((value >> bits) | (value << (64 - bits))) & mask

    def rol(value: int, bits: int) -> int:
        return ((value << bits) | (value >> (64 - bits))) & mask

    for index in range(4, 72):
        tmp = ror(round_keys[index - 1], 3) ^ round_keys[index - 3]
        tmp ^= ror(tmp, 1)
        round_keys.append((~round_keys[index - 4] ^ tmp ^ ((z4 >> ((index - 4) % 62)) & 1) ^ 3) & mask)
    x = int.from_bytes(block[:8], "little")
    y = int.from_bytes(block[8:], "little")
    for round_key in round_keys[:72]:
        x, y = y, (x ^ (rol(y, 1) & rol(y, 8)) ^ rol(y, 2) ^ round_key) & mask
    return x.to_bytes(8, "little") + y.to_bytes(8, "little")


def _argus(query: str, xss_stub: str, timestamp: int, config: Mapping[str, Any], rand: int) -> str:
    protobuf = _pkcs7_pad(_build_argus_protobuf(query, xss_stub, timestamp, config, rand))
    sm3_input = SIGN_KEY + LOW_RAND + HIGH_RAND + SIGN_KEY
    simon_key = sm3(sm3_input)
    encrypted = b"".join(
        _simon_encrypt(protobuf[offset : offset + 16], simon_key) for offset in range(0, len(protobuf), 16)
    )
    data = bytearray(XOR_PREFIX + encrypted)
    for index in range(len(XOR_PREFIX), len(data)):
        data[index] ^= data[index % 8]
    data.reverse()
    plaintext = bytes((0xA6, 0x6E, 0xAD, 0x9F, 0x77, 0x01, 0xD0, 0x0C, 0x18)) + bytes(data) + HIGH_RAND
    aes_key = hashlib.md5(SIGN_KEY[:16]).digest()
    iv = hashlib.md5(SIGN_KEY[16:]).digest()
    ciphertext = AES.new(aes_key, AES.MODE_CBC, iv).encrypt(_pkcs7_pad(plaintext))
    return _b64encode(LOW_RAND + ciphertext)


def _speck_encrypt(key: bytes, plaintext: bytes) -> bytes:
    mask = 0xFFFFFFFFFFFFFFFF
    round_keys = [int.from_bytes(key[:8], "little")]
    ls = [int.from_bytes(key[index : index + 8], "little") for index in range(8, 32, 8)]
    for index in range(33):
        rotated_x = ((ls[index] >> 8) | (ls[index] << 56)) & mask
        new_x = (index ^ ((rotated_x + round_keys[index]) & mask)) & mask
        ls.append(new_x)
        rotated_y = ((round_keys[index] << 3) | (round_keys[index] >> 61)) & mask
        round_keys.append(new_x ^ rotated_y)
    padded = _pkcs7_pad(plaintext)
    output = bytearray()
    for offset in range(0, len(padded), 16):
        y = int.from_bytes(padded[offset : offset + 8], "little")
        x = int.from_bytes(padded[offset + 8 : offset + 16], "little")
        for round_key in round_keys[:34]:
            x = (((x >> 8) | (x << 56)) + y) & mask
            x ^= round_key
            y = (((y << 3) | (y >> 61)) & mask) ^ x
        output.extend(y.to_bytes(8, "little") + x.to_bytes(8, "little"))
    return bytes(output)


def _ladon(timestamp: int, config: Mapping[str, Any], random_bytes: bytes) -> str:
    key = hashlib.md5(random_bytes + str(config["aid"]).encode("ascii")).hexdigest().encode("ascii")
    plaintext = f"{timestamp}-{config['license_id']}-{config['aid']}".encode()
    encrypted = _speck_encrypt(key, plaintext)
    return _b64encode(random_bytes + encrypted)


def build_app_query(
    item_id: str = "",
    *,
    device_id: str,
    install_id: str,
    book_id: str | None = None,
) -> str:
    values: dict[str, str] = {
        "iid": install_id,
        "device_id": device_id,
        "ac": "wifi",
        "channel": "43536163a",
        "aid": "1967",
        "app_name": "novelapp",
        "version_code": "70132",
        "version_name": "7.0.1.32",
        "device_platform": "android",
        "os": "android",
        "ssmix": "a",
        "os_version": "10",
        "device_type": "P30",
        "device_brand": "realme",
        "update_version_code": "70132",
        "manifest_version_code": "70132",
    }
    if item_id:
        values.update({"item_id": item_id, "req_type": "1"})
    if book_id:
        values.update({"book_id": book_id, "novel_text_type": "1"})
    return urlencode(values)


def sign_app_request(
    query: str,
    body: bytes | str = b"",
    *,
    timestamp: int | None = None,
    rand: int | None = None,
) -> dict[str, str]:
    resolved_timestamp = int(time.time()) if timestamp is None else int(timestamp)
    resolved_rand = (int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF) if rand is None else int(rand)
    body_bytes = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    stub = hashlib.md5(body_bytes).hexdigest() if body_bytes else ""
    headers = {
        "x-argus": _argus(query, stub, resolved_timestamp, DEFAULT_APP_CONFIG, resolved_rand),
        "x-ladon": _ladon(resolved_timestamp, DEFAULT_APP_CONFIG, os.urandom(4)),
        "x-khronos": str(resolved_timestamp),
        "x-ss-req-ticket": str(int(time.time() * 1000)),
    }
    if stub:
        headers["X-SS-STUB"] = stub
    return headers


def encrypt_register_body(device_id: str, *, random_text: str | None = None) -> str:
    device_hex = str(device_id).strip()
    if not device_hex.isdigit():
        raise ValueError("device_id 必须是数字")
    value = int(device_hex).to_bytes(16, "big", signed=False)[::-1][:8]
    iv = (
        (random_text or base64.b64encode(os.urandom(12)).decode("ascii"))[:16].encode("ascii").ljust(16, b"0")
    )
    encrypted = AES.new(SHARED_KEY, AES.MODE_CBC, iv).encrypt(_pkcs7_pad(value))
    return json.dumps({"content": _b64encode(iv + encrypted)}, ensure_ascii=False, separators=(",", ":"))


def decrypt_register_key(encoded: str) -> bytes:
    payload = _b64decode(encoded)
    if len(payload) <= 16:
        raise ValueError("注册接口返回的密钥数据为空")
    return unpad(AES.new(SHARED_KEY, AES.MODE_CBC, payload[:16]).decrypt(payload[16:]), 16)


def decrypt_chapter_payload(encoded: str, *, key: bytes, compressed: bool = False) -> Any:
    payload = _b64decode(encoded)
    if len(payload) <= 16:
        raise ValueError("章节密文为空")
    plain = unpad(AES.new(key, AES.MODE_CBC, payload[:16]).decrypt(payload[16:]), 16)
    if compressed:
        plain = gzip.decompress(plain)
    text = plain.decode("utf-8")
    if text.lstrip().startswith("<"):
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("章节明文不是有效 HTML 或 JSON") from exc


__all__ = [
    "APP_BASE_URL",
    "APP_USER_AGENT",
    "build_app_query",
    "decrypt_chapter_payload",
    "decrypt_register_key",
    "encrypt_register_body",
    "sign_app_request",
    "sm3",
]
