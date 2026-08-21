from __future__ import annotations

import math
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from app.two_factor import (
    RECOVERY_CODE_ALPHABET,
    RECOVERY_CODE_LENGTH,
    TWO_FACTOR_ENCRYPTION_KEY_ENV,
    build_totp_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_code,
    generate_totp_secret,
    hash_recovery_code,
    hash_recovery_codes,
    verify_recovery_code,
    verify_totp_code,
)

_RFC_6238_SHA1_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.fixture
def session_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    value = "42" * 32
    monkeypatch.setenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, value)
    return value


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    (
        (59, "287082"),
        (1_111_111_109, "081804"),
        (1_111_111_111, "050471"),
        (1_234_567_890, "005924"),
        (2_000_000_000, "279037"),
        (20_000_000_000, "353130"),
    ),
)
def test_totp_matches_last_six_digits_of_rfc_6238_sha1_vectors(
    timestamp: int,
    expected: str,
) -> None:
    assert generate_totp_code(_RFC_6238_SHA1_SECRET, now=timestamp) == expected


def test_totp_accepts_one_step_skew_and_rejects_replay() -> None:
    now = 1_700_000_010
    current_counter = now // 30
    previous_code = generate_totp_code(_RFC_6238_SHA1_SECRET, counter=current_counter - 1)
    current_code = generate_totp_code(_RFC_6238_SHA1_SECRET, counter=current_counter)
    next_code = generate_totp_code(_RFC_6238_SHA1_SECRET, counter=current_counter + 1)

    assert verify_totp_code(_RFC_6238_SHA1_SECRET, previous_code, now=now) == current_counter - 1
    assert verify_totp_code(_RFC_6238_SHA1_SECRET, current_code, now=now) == current_counter
    assert verify_totp_code(_RFC_6238_SHA1_SECRET, next_code, now=now) == current_counter + 1
    assert (
        verify_totp_code(
            _RFC_6238_SHA1_SECRET,
            previous_code,
            now=now,
            last_counter=current_counter - 1,
        )
        is None
    )
    assert (
        verify_totp_code(
            _RFC_6238_SHA1_SECRET,
            current_code,
            now=now,
            last_counter=current_counter,
        )
        is None
    )


def test_totp_validation_is_strict_and_datetime_is_supported() -> None:
    now = datetime.fromtimestamp(1_700_000_010, tz=UTC)
    code = generate_totp_code(_RFC_6238_SHA1_SECRET, now=now)

    assert verify_totp_code(_RFC_6238_SHA1_SECRET, code, now=now, window=0) == int(now.timestamp()) // 30
    assert verify_totp_code(_RFC_6238_SHA1_SECRET, f" {code}", now=now) is None
    assert verify_totp_code(_RFC_6238_SHA1_SECRET, "１２３４５６", now=now) is None
    assert verify_totp_code(_RFC_6238_SHA1_SECRET, "12345", now=now) is None
    with pytest.raises(ValueError, match="时区"):
        generate_totp_code(_RFC_6238_SHA1_SECRET, now=datetime(2026, 1, 1))


def test_generated_secret_and_otpauth_uri_are_authenticator_compatible() -> None:
    secret = generate_totp_secret()
    uri = build_totp_uri(secret, account_name="alice@example.com", issuer="青卷")
    parsed = urlsplit(uri)
    query = parse_qs(parsed.query)

    assert len(secret) == 32
    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert unquote(parsed.path) == "/青卷:alice@example.com"
    assert query == {
        "secret": [secret],
        "issuer": ["青卷"],
        "algorithm": ["SHA1"],
        "digits": ["6"],
        "period": ["30"],
    }


def test_totp_secret_encryption_round_trip_is_randomized(session_secret: str) -> None:
    secret = generate_totp_secret()
    first = encrypt_totp_secret(secret)
    second = encrypt_totp_secret(secret)

    assert first.startswith("qj2fa:v2:")
    assert first != second
    assert secret not in first
    assert decrypt_totp_secret(first) == secret
    assert decrypt_totp_secret(second, session_secret=session_secret) == secret


def test_totp_secret_encryption_rejects_tampering_and_wrong_key(session_secret: str) -> None:
    encrypted = encrypt_totp_secret(_RFC_6238_SHA1_SECRET)
    parts = encrypted.split(":")
    parts[-1] = ("A" if parts[-1][0] != "A" else "B") + parts[-1][1:]

    with pytest.raises(ValueError, match="篡改"):
        decrypt_totp_secret(":".join(parts))
    with pytest.raises(ValueError, match="篡改"):
        decrypt_totp_secret(encrypted, session_secret="24" * 32)
    with pytest.raises(ValueError, match="篡改"):
        decrypt_totp_secret(encrypted.replace(":v2:", ":v1:"))


def test_totp_secret_encryption_requires_configured_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match=TWO_FACTOR_ENCRYPTION_KEY_ENV):
        encrypt_totp_secret(_RFC_6238_SHA1_SECRET)


def test_recovery_codes_are_unique_readable_and_keyed(session_secret: str) -> None:
    codes = generate_recovery_codes()
    hashes = hash_recovery_codes(codes)

    assert len(codes) == len(set(codes)) == 10
    assert RECOVERY_CODE_LENGTH * math.log2(len(RECOVERY_CODE_ALPHABET)) >= 128
    assert all(len(code.replace("-", "")) == RECOVERY_CODE_LENGTH for code in codes)
    assert all(code.count("-") == 5 for code in codes)
    assert len(hashes) == len(set(hashes)) == 10
    for code, stored_hash in zip(codes, hashes, strict=True):
        assert code.replace("-", "") not in stored_hash
        assert verify_recovery_code(code, stored_hash)
        assert verify_recovery_code(code.lower().replace("-", " "), stored_hash)
        assert not verify_recovery_code("22222-22222-22222-22222-22222-22", stored_hash)
        replacement = "0" if stored_hash[-1] != "0" else "1"
        assert not verify_recovery_code(code, f"{stored_hash[:-1]}{replacement}")

    assert not verify_recovery_code(codes[0], hashes[0], session_secret="24" * 32)
    assert hash_recovery_code(codes[0], session_secret=session_secret) == hashes[0]


def test_totp_and_recovery_domains_are_independent(session_secret: str) -> None:
    secret = generate_totp_secret()
    encrypted = encrypt_totp_secret(secret, session_secret=session_secret)
    recovery_hash = hash_recovery_code(
        "23456-789AB-CDEFG-HJKMN-PQRST-VW",
        session_secret=session_secret,
    )

    assert encrypted.startswith("qj2fa:v2:")
    assert recovery_hash.startswith("qj2fa-recovery:v2:")
    assert encrypted != recovery_hash
