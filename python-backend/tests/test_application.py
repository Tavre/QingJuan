import hashlib
import io

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import db, main
from app.api.routers import health_router
from app.application import APP_TITLE, APP_VERSION, create_application, read_app_version
from app.models import (
    BookRecord,
    OpenAICompatibleConfig,
    PublicBookRecord,
    TranslationSettings,
)
from app.security import API_PREFIX


def test_application_factory_registers_router() -> None:
    @health_router.get("/_factory-test", include_in_schema=False)
    async def factory_test() -> dict[str, str]:
        return {"status": "ok"}

    application = create_application(routers=[health_router])

    with TestClient(application) as client:
        response = client.get("/_factory-test")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_factory_sets_metadata() -> None:
    application = create_application(routers=[])

    assert application.title == APP_TITLE
    assert application.version == APP_VERSION


def test_api_prefix_and_bearer_authentication(monkeypatch) -> None:
    token = "test-token-with-enough-randomness"
    monkeypatch.setenv("QINGJUAN_AUTH_TOKEN_SHA256", hashlib.sha256(token.encode()).hexdigest())
    router = APIRouter()

    @router.get("/private")
    async def private_route() -> dict[str, str]:
        return {"status": "ok"}

    application = create_application(
        routers=[router],
        api_prefix=API_PREFIX,
        authenticate=True,
    )
    with TestClient(application) as client:
        missing = client.get(f"{API_PREFIX}/private")
        incorrect = client.get(
            f"{API_PREFIX}/private",
            headers={"Authorization": "Bearer incorrect"},
        )
        accepted = client.get(
            f"{API_PREFIX}/private",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert missing.status_code == 401
    assert incorrect.status_code == 401
    assert accepted.status_code == 200


def test_public_book_dto_does_not_expose_server_path() -> None:
    internal = BookRecord(
        id="book-1",
        title="测试",
        sourceUrl="",
        bookKind="长小说",
        language="中文",
        status="已下载",
        chapterCount=1,
        translated=False,
        localPath="/var/lib/qingjuan/private/book-1",
    )

    payload = PublicBookRecord.model_validate(internal).model_dump()

    assert "localPath" not in payload
    assert "/var/lib/qingjuan" not in str(payload)


def test_settings_view_does_not_return_api_key() -> None:
    settings = TranslationSettings(
        translationModel=OpenAICompatibleConfig(
            enabled=True,
            apiKey="upstream-secret",
            model="translation-model",
        )
    )

    payload = main._settings_view(settings).model_dump()

    assert payload["translationModel"]["apiKeyConfigured"] is True
    assert "upstream-secret" not in str(payload)
    assert "apiKey" not in payload["translationModel"]


def test_startup_console_outputs_connection_info_without_token(monkeypatch) -> None:
    raw_token = "server-connection-secret"
    monkeypatch.setenv("QINGJUAN_PUBLIC_URL", "http://10.0.0.20:19453/")
    monkeypatch.setenv(
        "QINGJUAN_AUTH_TOKEN_SHA256",
        hashlib.sha256(raw_token.encode()).hexdigest(),
    )

    output = "\n".join(main._startup_console_lines("0.0.0.0", 19453))

    assert "客户端地址：http://10.0.0.20:19453" in output
    assert "业务 API：http://10.0.0.20:19453/api/v1" in output
    assert "Bearer 认证：已启用" in output
    assert raw_token not in output


def test_console_stream_is_reconfigured_from_cp1252_to_utf8() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")

    main._configure_unicode_stream(stream)
    stream.write("青卷 FastAPI 后端已启动")
    stream.flush()

    assert buffer.getvalue().decode("utf-8") == "青卷 FastAPI 后端已启动"
    stream.detach()


def test_read_app_version_uses_pubspec_semantic_version(tmp_path) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: qingjuan\nversion: 1.0.1+6\n", encoding="utf-8")

    assert read_app_version(pubspec) == "1.0.1"


def test_legacy_selected_provider_migrates_to_single_openai_compatible_model() -> None:
    migrated = db._migrate_settings_payload(
        {
            "defaultProvider": "custom",
            "systemPrompt": "test",
            "providers": {
                "openai": {
                    "enabled": False,
                    "baseUrl": "https://api.openai.com/v1",
                    "apiKey": "",
                    "model": "",
                },
                "custom": {
                    "enabled": True,
                    "baseUrl": "https://gateway.example.test/v1",
                    "apiKey": "secret",
                    "model": "vision-model",
                },
            },
        }
    )

    assert migrated["translationModel"] == {
        "enabled": True,
        "baseUrl": "https://gateway.example.test/v1",
        "apiKey": "secret",
        "model": "vision-model",
    }
    assert "defaultProvider" not in migrated
    assert "providers" not in migrated
