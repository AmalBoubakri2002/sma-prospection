import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.base import get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
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
    actifs = sum(1 for u in commercials if u.is_active)
    return {"total": total, "actifs": actifs, "inactifs": total - actifs}


@router.post("/", response_model=UserResponse, status_code=201)
async def create_commercial(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user_in.role = "commercial"
    if await get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    return await create_user(db, user_in)


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
    return await update_user(
        db,
        user,
        full_name=data.full_name,
        is_active=data.is_active,
    )


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
