from fastapi import APIRouter

from .admin import router as admin_router
from .devices import router as devices_router
from .translation_model import router as translation_model_router

health_router = APIRouter(tags=["health"])
system_router = APIRouter(tags=["system"])
sources_router = APIRouter(tags=["sources"])
plugins_router = APIRouter(tags=["plugins"])
library_router = APIRouter(tags=["library"])
tasks_router = APIRouter(tags=["tasks"])
settings_router = APIRouter(tags=["settings"])

API_ROUTERS = (
    system_router,
    devices_router,
    translation_model_router,
    plugins_router,
    sources_router,
    library_router,
    tasks_router,
    settings_router,
)

PUBLIC_ROUTERS = (health_router, admin_router)
