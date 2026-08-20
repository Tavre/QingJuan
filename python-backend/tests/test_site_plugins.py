from __future__ import annotations

import hashlib
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main, scraper
from app.admin_auth import (
    ADMIN_CSRF_HEADER,
    ADMIN_PASSWORD_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    hash_admin_password,
)
from app.api.admin import router as admin_router
from app.api.routers import plugins_router
from app.application import create_application
from app.models import AddBookPayload, BookSourceEnabledPayload, BookSourceRecord
from app.security import API_PREFIX
from app.site_plugins import list_site_plugins, resolve_site_plugin


def test_site_plugin_registry_has_unique_ids_and_generic_fallback_last() -> None:
    plugins = list_site_plugins()

    assert len(plugins) == len({plugin.id for plugin in plugins})
    assert plugins[-1].id == "generic-web"
    assert {plugin.preview_handler for plugin in plugins} <= {
        "18comic",
        "alphapolis",
        "bika",
        "ciweimao",
        "comicores",
        "copymanga",
        "ehentai",
        "fanqie",
        "generic",
        "hameln",
        "kakuyomu",
        "novelup",
        "pixiv",
        "pixiv_comic",
        "qidian",
        "quark",
        "sfacg",
        "shaoniandream",
        "syosetu",
        "yanmaga",
    }
    assert {plugin.chapter_handler for plugin in plugins if plugin.chapter_handler} <= {
        "18comic",
        "alphapolis",
        "bika",
        "ciweimao",
        "comicores",
        "copymanga",
        "ehentai",
        "fanqie",
        "generic",
        "generic_manga",
        "hameln",
        "kakuyomu",
        "linovelib",
        "novelup",
        "pixiv",
        "pixiv_comic",
        "qidian",
        "quark",
        "sfacg",
        "shaoniandream",
        "syosetu",
        "yanmaga",
    }
    assert resolve_site_plugin("https://fanqienovel.com/page/123").id == "fanqie"
    assert resolve_site_plugin("https://www.qidian.com/book/1004608738/").id == "qidian"
    assert resolve_site_plugin("https://www.shuqi.com/book/46543.html").id == "quark"
    assert resolve_site_plugin("https://comic.pixiv.net/works/123").id == "pixiv-comic"
    assert resolve_site_plugin("https://www.pixiv.net/artworks/123").id == "pixiv"
    assert resolve_site_plugin("https://yanmaga.jp/comics/10DANCE").id == "yanmaga"
    assert resolve_site_plugin("https://novel18.syosetu.com/n123/").id == "novel18"
    assert resolve_site_plugin("https://www.copymanga.site/comic/example").id == "copymanga"
    assert resolve_site_plugin("https://www.mangacopy.com/comic/example").id == "copymanga"
    assert resolve_site_plugin("https://www.comicores.cc/example/.html").id == "comicores"
    assert resolve_site_plugin("https://www.ciweimao.com/book/100495948").id == "ciweimao"
    assert resolve_site_plugin("https://e-hentai.org/g/123/0123456789/").id == "ehentai"
    assert resolve_site_plugin("https://book.sfacg.com/Novel/465469/").id == "sfacg"
    assert resolve_site_plugin("https://www.shaoniandream.com/book_detail/3490").id == "shaoniandream"
    assert "chapter" not in resolve_site_plugin("https://www.comicores.cc/example/.html").capabilities
    assert resolve_site_plugin("https://example.test/book").id == "generic-web"


def test_site_plugin_registry_rejects_non_http_urls() -> None:
    assert resolve_site_plugin("ftp://fanqienovel.com/page/123") is None
    assert resolve_site_plugin("//fanqienovel.com/page/123") is None
    assert resolve_site_plugin("file://fanqienovel.com/page/123") is None


def test_every_legacy_builtin_source_resolves_to_a_site_plugin() -> None:
    assert all(resolve_site_plugin(source.baseUrl) is not None for source in db.DEFAULT_BOOK_SOURCES)


def test_site_plugin_settings_are_seeded_and_preserve_user_choice(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)

    db.init_db()
    assert db.is_site_plugin_enabled("fanqie") is True
    assert db.get_book_source("source-builtin-quark").name == "夸克小说"
    assert db.get_book_source("source-builtin-qidian").name == "起点中文网"

    db.save_site_plugin_enabled("fanqie", False)
    db.init_db()

    assert db.is_site_plugin_enabled("fanqie") is False
    assert db.list_site_plugin_enabled_states()["fanqie"] is False


def test_site_plugin_state_uses_uncached_defaults_before_schema_exists(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_DATA_DIR_READY", True)
    monkeypatch.setattr(db, "_SITE_PLUGIN_STATE_CACHE", None)

    states = db.list_site_plugin_enabled_states()

    assert states == {plugin.id: plugin.default_enabled for plugin in list_site_plugins()}
    assert db._SITE_PLUGIN_STATE_CACHE is None


def test_site_plugin_state_database_errors_do_not_fail_open(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qingjuan.db")
    monkeypatch.setattr(db, "_SITE_PLUGIN_STATE_CACHE", None)

    def fail_to_connect():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "get_connection", fail_to_connect)

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        db.list_site_plugin_enabled_states()

    assert db._SITE_PLUGIN_STATE_CACHE is None


@pytest.mark.asyncio
async def test_disabled_site_plugin_blocks_preview_before_network(monkeypatch) -> None:
    called = False

    async def unexpected_preview(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled plugin must not invoke its preview handler")

    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: False)
    monkeypatch.setattr(scraper, "_preview_fanqie", unexpected_preview)

    with pytest.raises(ValueError, match="插件配置"):
        await scraper.preview_from_url(
            AddBookPayload(
                sourceUrl="https://fanqienovel.com/page/123",
                bookKind="长小说",
                language="中文",
            )
        )

    assert called is False


@pytest.mark.asyncio
async def test_disabled_site_plugin_blocks_chapter_before_network(monkeypatch) -> None:
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: False)

    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="番茄小说"):
            await scraper._fetch_chapter_data(
                client,
                "https://fanqienovel.com/reader/123",
                "第一章",
            )


@pytest.mark.asyncio
async def test_disabled_site_plugin_blocks_builtin_search_before_network(monkeypatch) -> None:
    called = False

    async def unexpected_search(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("disabled plugin must not invoke its search handler")

    source = BookSourceRecord(
        id="source-builtin-kakuyomu",
        name="Kakuyomu",
        baseUrl="https://kakuyomu.jp",
        origin="builtin",
    )
    monkeypatch.setattr(scraper, "is_site_plugin_enabled", lambda plugin_id: False)
    monkeypatch.setattr(scraper, "_search_kakuyomu_works", unexpected_search)

    with pytest.raises(ValueError, match="Kakuyomu"):
        await scraper.search_builtin_site_books(source, "测试")

    assert called is False


def test_plugin_api_lists_and_updates_backend_state(monkeypatch) -> None:
    saved: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        main,
        "list_site_plugin_enabled_states",
        lambda: {plugin.id: plugin.default_enabled for plugin in list_site_plugins()},
    )
    monkeypatch.setattr(
        main,
        "save_site_plugin_enabled",
        lambda plugin_id, enabled: saved.append((plugin_id, enabled)),
    )
    application = create_application(routers=[plugins_router])

    with TestClient(application) as client:
        listed = client.get("/plugins")
        updated = client.put("/plugins/fanqie", json={"enabled": False})

    assert listed.status_code == 200
    assert any(plugin["id"] == "fanqie" for plugin in listed.json())
    quark = next(plugin for plugin in listed.json() if plugin["id"] == "quark")
    assert {"search", "preview", "chapter", "on_demand"} <= set(quark["capabilities"])
    qidian = next(plugin for plugin in listed.json() if plugin["id"] == "qidian")
    assert {"account_login", "bookshelf_import", "on_demand"} <= set(qidian["capabilities"])
    assert qidian["accountLoggedIn"] is False
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert saved == [("fanqie", False)]


def test_admin_session_manages_plugins_with_csrf(monkeypatch) -> None:
    monkeypatch.setenv(
        ADMIN_PASSWORD_HASH_ENV,
        hash_admin_password(
            "correct-admin-password",
            salt=b"0123456789abcdef",
            iterations=100_000,
        ),
    )
    monkeypatch.setenv(ADMIN_SESSION_SECRET_ENV, "11" * 32)
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(b"client-bearer-token").hexdigest(),
    )
    monkeypatch.setattr(
        main,
        "list_site_plugin_enabled_states",
        lambda: {plugin.id: plugin.default_enabled for plugin in list_site_plugins()},
    )
    monkeypatch.setattr(main, "save_site_plugin_enabled", lambda *_: None)
    application = create_application(
        routers=[plugins_router],
        public_routers=[admin_router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )

    with TestClient(application) as client:
        login = client.post(
            "/admin/api/login",
            json={"password": "correct-admin-password"},
        )
        listed = client.get(f"{API_PREFIX}/plugins")
        missing_csrf = client.put(
            f"{API_PREFIX}/plugins/fanqie",
            json={"enabled": False},
        )
        updated = client.put(
            f"{API_PREFIX}/plugins/fanqie",
            json={"enabled": False},
            headers={ADMIN_CSRF_HEADER: login.json()["csrfToken"]},
        )

    assert login.status_code == 200
    assert listed.status_code == 200
    assert missing_csrf.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False


@pytest.mark.asyncio
async def test_source_enabled_update_preserves_imported_rule_payload(monkeypatch) -> None:
    source = BookSourceRecord(
        id="source-1",
        name="测试书源",
        baseUrl="https://source.example.test",
        enabled=True,
        origin="manual",
        rulePayload={"searchUrl": "/search", "ruleSearch": {"name": "h2"}},
    )
    saved = None

    def capture(updated):
        nonlocal saved
        saved = updated
        return updated

    monkeypatch.setattr(main, "_get_source_or_404", lambda source_id: source)
    monkeypatch.setattr(main, "save_book_source", capture)

    updated = await main.put_source_enabled(
        source.id,
        BookSourceEnabledPayload(enabled=False),
    )

    assert updated.enabled is False
    assert updated.rulePayload == source.rulePayload
    assert saved == updated
