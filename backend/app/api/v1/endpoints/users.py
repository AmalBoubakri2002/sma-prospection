import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.base import get_db
from app.models.user import User, UserStatus
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
from app.services.notification import notify_account_approved, notify_account_rejected
from app.services.user import (
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    update_user,
)

router = APIRouter()


@router.get("/", response_model=list[UserResponse])
async def get_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return await list_users(db, role="commercial")


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    commercials = await list_users(db, role="commercial")
    total = len(commercials)
    actifs = sum(1 for u in commercials if u.status == UserStatus.ACTIVE)
    en_attente = sum(1 for u in commercials if u.status == UserStatus.PENDING)
    inactifs = total - actifs
    return {"total": total, "actifs": actifs, "inactifs": inactifs, "en_attente": en_attente}


@router.post("/", response_model=UserResponse, status_code=201)
async def create_commercial(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if await get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    # Compte créé directement par un admin : pas besoin de validation.
    return await create_user(db, user_in, role="commercial", status=UserStatus.ACTIVE)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_commercial(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await get_user_by_id(db, str(user_id))
    if not user or user.role != "commercial":
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return await update_user(db, user, full_name=data.full_name)


async def _get_pending_or_managed_commercial(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await get_user_by_id(db, str(user_id))
    if not user or user.role != "commercial":
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user


@router.post("/{user_id}/approve", response_model=UserResponse)
async def approve_commercial(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await _get_pending_or_managed_commercial(db, user_id)
    user = await update_user(db, user, status=UserStatus.ACTIVE)
    await notify_account_approved(db, user)
    return user


@router.post("/{user_id}/reject", response_model=UserResponse)
async def reject_commercial(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await _get_pending_or_managed_commercial(db, user_id)
    user = await update_user(db, user, status=UserStatus.REJECTED)
    await notify_account_rejected(db, user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_commercial(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = await get_user_by_id(db, str(user_id))
    if not user or user.role != "commercial":
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await delete_user(db, user)
