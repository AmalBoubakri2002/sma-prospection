import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import decode_access_token
from app.core.ws_manager import manager
from app.db.base import AsyncSessionLocal, get_db
from app.models.user import User, UserStatus
from app.schemas.notification import NotificationResponse
from app.services.notification import (
    get_notification_by_id,
    list_notifications,
    mark_notification_read,
)
from app.services.user import get_user_by_id

router = APIRouter()


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, token: str):
    await websocket.accept()

    user: User | None = None
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id:
            async with AsyncSessionLocal() as db:
                user = await get_user_by_id(db, user_id)
    except JWTError:
        user = None

    if not user or user.status == UserStatus.REJECTED:
        await websocket.close(code=4401)
        return

    manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.id, websocket)


@router.get("/", response_model=list[NotificationResponse])
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_notifications(db, current_user.id)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = await get_notification_by_id(db, notification_id)
    if not notification or notification.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return await mark_notification_read(db, notification)
