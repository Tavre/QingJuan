from fastapi import APIRouter

health_router = APIRouter(tags=["health"])
sources_router = APIRouter(tags=["sources"])
library_router = APIRouter(tags=["library"])
tasks_router = APIRouter(tags=["tasks"])
settings_router = APIRouter(tags=["settings"])

API_ROUTERS = (
    health_router,
    sources_router,
    library_router,
    tasks_router,
    settings_router,
)
