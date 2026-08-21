from __future__ import annotations

from datetime import datetime

from .db import (
    accept_user_totp_counter,
    consume_user_recovery_code,
    get_user_security_state,
)
from .two_factor import (
    decrypt_totp_secret,
    generate_recovery_codes,
    hash_recovery_code,
    hash_recovery_codes,
    verify_totp_code,
)


def two_factor_enabled(user_id: str) -> bool:
    state = get_user_security_state(user_id)
    return bool(state is not None and state.totp_secret_encrypted)


def verify_second_factor_code(
    user_id: str,
    code: str,
    *,
    now: int | float | datetime | None = None,
) -> bool:
    state = get_user_security_state(user_id)
    if state is None or not state.totp_secret_encrypted:
        return False
    if len(code) == 6 and code.isascii() and code.isdigit():
        try:
            secret = decrypt_totp_secret(state.totp_secret_encrypted)
            counter = verify_totp_code(
                secret,
                code,
                now=now,
                last_counter=state.totp_last_counter,
            )
        except (RuntimeError, ValueError):
            counter = None
        if counter is not None:
            return accept_user_totp_counter(user_id, counter)
        return False
    try:
        code_hash = hash_recovery_code(code)
    except (RuntimeError, TypeError, ValueError):
        return False
    return consume_user_recovery_code(user_id, code_hash)


def generate_recovery_code_material() -> tuple[list[str], list[str]]:
    codes = generate_recovery_codes()
    return codes, hash_recovery_codes(codes)
