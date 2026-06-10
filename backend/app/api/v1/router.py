from fastapi import APIRouter

from app.api.v1.endpoints import auth, campaigns, users

api_router = APIRouter()

api_router.include_router(auth.router,      prefix="/auth",      tags=["auth"])
api_router.include_router(users.router,     prefix="/users",     tags=["users"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
