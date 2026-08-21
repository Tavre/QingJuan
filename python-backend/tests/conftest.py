from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_to_legacy_single_user_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep pre-existing tests platform-independent; multi-user tests opt in explicitly."""

    monkeypatch.setenv("QINGJUAN_MULTI_USER", "0")
