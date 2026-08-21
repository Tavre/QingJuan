from fastapi import APIRouter, Query, Request

from ..admin_auth import require_admin_write_access
from ..db import load_settings
from ..translation_model_health import (
    TranslationModelCheckResponse,
    check_translation_model,
    get_translation_model_check_snapshot,
)
from ..user_auth import require_user_access

router = APIRouter(tags=["translation-model"])


@router.post("/translation-model/check", response_model=TranslationModelCheckResponse)
async def post_translation_model_check(
    request: Request,
    force: bool = Query(default=False),
) -> TranslationModelCheckResponse:
    require_user_access(request)
    if force:
        require_admin_write_access(request)
        return await check_translation_model(load_settings(), force=True)
    return get_translation_model_check_snapshot(load_settings())
