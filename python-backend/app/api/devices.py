from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..admin_auth import require_admin_session
from ..db import list_devices, set_device_banned
from ..models import DeviceBanPayload, DeviceView

router = APIRouter(tags=["devices"])


@router.post("/devices/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/devices", response_model=list[DeviceView])
async def get_devices(request: Request) -> list[DeviceView]:
    require_admin_session(request)
    return list_devices()


@router.put("/devices/{device_id}/ban", response_model=DeviceView)
async def update_device_ban(
    device_id: str,
    payload: DeviceBanPayload,
    request: Request,
) -> DeviceView:
    require_admin_session(request, require_csrf=True)
    device = set_device_banned(device_id, banned=payload.banned)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")
    return device
