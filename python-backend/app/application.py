from __future__ import annotations

import re
import sys
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI

from .security import API_PREFIX, authentication_enabled, require_api_token

APP_TITLE = "青卷后端"
_VERSION_PATTERN = re.compile(r"^version:\s*(\d+\.\d+\.\d+)(?:\+\d+)?\s*$")


def read_app_version(pubspec_path: Path) -> str:
    for line in pubspec_path.read_text(encoding="utf-8").splitlines():
        match = _VERSION_PATTERN.fullmatch(line)
        if match is not None:
            return match.group(1)
    raise RuntimeError(f"无法从 {pubspec_path} 读取应用版本")


def _pubspec_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "pubspec.yaml"
    return Path(__file__).resolve().parents[2] / "pubspec.yaml"


APP_VERSION = read_app_version(_pubspec_path())

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[AsyncIterator[None]]]


def create_application(
    *,
    routers: Iterable[APIRouter],
    public_routers: Iterable[APIRouter] = (),
    api_prefix: str = "",
    authenticate: bool = False,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """创建 FastAPI 应用；入口文件只负责组装，不再内联基础设施配置。"""

    application = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None if authentication_enabled() else "/docs",
        redoc_url=None if authentication_enabled() else "/redoc",
        openapi_url=None if authentication_enabled() else "/openapi.json",
    )
    for router in public_routers:
        application.include_router(router)
    dependencies = [Depends(require_api_token)] if authenticate else None
    router_prefix = api_prefix or (API_PREFIX if authenticate else "")
    for router in routers:
        application.include_router(
            router,
            prefix=router_prefix,
            dependencies=dependencies,
        )

    return application
