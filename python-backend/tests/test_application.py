from fastapi.testclient import TestClient

from app.api.routers import health_router
from app.application import APP_TITLE, APP_VERSION, create_application


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
