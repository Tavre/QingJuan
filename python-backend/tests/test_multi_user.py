from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.main as main
import app.multi_user as multi_user
from app.two_factor import TWO_FACTOR_ENCRYPTION_KEY_ENV


@pytest.mark.parametrize("configured", ["1", "true", "TRUE", " yes ", "ON"])
def test_explicit_true_values_enable_multi_user(monkeypatch, configured: str) -> None:
    monkeypatch.setenv(multi_user.MULTI_USER_ENV, configured)

    assert multi_user.multi_user_enabled() is True


@pytest.mark.parametrize("configured", ["0", "false", "FALSE", " no ", "OFF"])
def test_explicit_false_values_disable_multi_user(monkeypatch, configured: str) -> None:
    monkeypatch.setenv(multi_user.MULTI_USER_ENV, configured)

    assert multi_user.multi_user_enabled() is False


def test_invalid_multi_user_value_raises_clear_configuration_error(monkeypatch) -> None:
    monkeypatch.setenv(multi_user.MULTI_USER_ENV, "enabled")

    with pytest.raises(RuntimeError, match=r"QINGJUAN_MULTI_USER.*配置无效.*布尔值"):
        multi_user.multi_user_enabled()


async def test_invalid_multi_user_value_stops_startup_before_database_or_workers(
    monkeypatch,
) -> None:
    monkeypatch.setenv(multi_user.MULTI_USER_ENV, "enabled")
    database_started = False

    def record_database_start() -> None:
        nonlocal database_started
        database_started = True

    monkeypatch.setattr(main, "init_db", record_database_start)
    application = FastAPI()

    with pytest.raises(RuntimeError, match=r"QINGJUAN_MULTI_USER.*配置无效"):
        await main._run_startup(application)

    assert database_started is False
    assert not hasattr(application.state, "queue_worker")
    assert not hasattr(application.state, "export_cleanup_worker")


@pytest.mark.parametrize("configured_key", [None, "short", "g" * 64])
async def test_multi_user_startup_requires_stable_two_factor_key(
    monkeypatch,
    configured_key: str | None,
) -> None:
    monkeypatch.setenv(multi_user.MULTI_USER_ENV, "1")
    if configured_key is None:
        monkeypatch.delenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, configured_key)
    database_started = False

    def record_database_start() -> None:
        nonlocal database_started
        database_started = True

    monkeypatch.setattr(main, "init_db", record_database_start)
    with pytest.raises(RuntimeError, match=TWO_FACTOR_ENCRYPTION_KEY_ENV):
        await main._run_startup(FastAPI())
    assert database_started is False


async def test_single_user_startup_does_not_require_two_factor_key(monkeypatch) -> None:
    class StartupReached(RuntimeError):
        pass

    monkeypatch.setenv(multi_user.MULTI_USER_ENV, "0")
    monkeypatch.delenv(TWO_FACTOR_ENCRYPTION_KEY_ENV, raising=False)
    monkeypatch.setattr(
        main,
        "validate_two_factor_encryption_key",
        lambda: pytest.fail("single-user startup must not validate the 2FA key"),
    )
    monkeypatch.setattr(
        main,
        "validate_admin_auth_configuration",
        lambda: (_ for _ in ()).throw(StartupReached()),
    )
    with pytest.raises(StartupReached):
        await main._run_startup(FastAPI())


@pytest.mark.parametrize(
    ("platform_name", "expected"),
    [("nt", False), ("posix", True)],
)
def test_unconfigured_multi_user_mode_uses_platform_default(
    monkeypatch,
    platform_name: str,
    expected: bool,
) -> None:
    monkeypatch.delenv(multi_user.MULTI_USER_ENV, raising=False)
    monkeypatch.setattr(
        multi_user,
        "os",
        SimpleNamespace(name=platform_name, getenv=os.getenv),
    )

    assert multi_user.multi_user_enabled() is expected
