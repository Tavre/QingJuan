from __future__ import annotations

import os

MULTI_USER_ENV = "QINGJUAN_MULTI_USER"
DEFAULT_ADMIN_USER_ID = "user-admin"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def multi_user_enabled() -> bool:
    """Return whether per-user authentication and ownership isolation are enabled."""

    configured = os.getenv(MULTI_USER_ENV, "").strip().lower()
    if not configured:
        return os.name != "nt"
    if configured in _TRUE_VALUES:
        return True
    if configured in _FALSE_VALUES:
        return False
    accepted = ", ".join(sorted(_TRUE_VALUES | _FALSE_VALUES))
    raise RuntimeError(f"{MULTI_USER_ENV} 配置无效：必须是以下布尔值之一：{accepted}")
