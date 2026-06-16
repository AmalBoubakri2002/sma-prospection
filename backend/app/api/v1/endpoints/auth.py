from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.base import get_db
from app.models.user import User, UserStatus
from app.schemas.auth import CommercialRegister, Token, UserResponse, UserUpdate
from app.services.notification import notify_admins_new_registration
from app.services.user import authenticate_user, create_user, get_user_by_email, update_user

router = APIRouter()


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username.lower(), form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status == UserStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre demande d'inscription a été refusée",
        )
    return Token(access_token=create_access_token({"sub": str(user.id)}))


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_in: CommercialRegister,
    db: AsyncSession = Depends(get_db),
):
    if await get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    user = await create_user(db, user_in, role="commercial", status=UserStatus.PENDING)
    await notify_admins_new_registration(db, user)
    return user


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await update_user(db, current_user, full_name=data.full_name)
