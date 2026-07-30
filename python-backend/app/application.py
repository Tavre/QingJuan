from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, FastAPI

APP_TITLE = "青卷后端"
APP_VERSION = "0.5.0"

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[AsyncIterator[None]]]


def create_application(
    *,
    routers: Iterable[APIRouter],
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """创建 FastAPI 应用；入口文件只负责组装，不再内联基础设施配置。"""

    application = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
    )
    for router in routers:
        application.include_router(router)

    return application
