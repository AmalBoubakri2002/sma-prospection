from fastapi import APIRouter

from app.api.v1.endpoints import auth, campaigns, leads, metrics, notifications, users, webhooks

api_router = APIRouter()

api_router.include_router(auth.router,          prefix="/auth",          tags=["auth"])
api_router.include_router(users.router,         prefix="/users",         tags=["users"])
api_router.include_router(campaigns.router,      prefix="/campaigns",     tags=["campaigns"])
api_router.include_router(notifications.router,  prefix="/notifications", tags=["notifications"])
api_router.include_router(leads.router,          prefix="/leads",         tags=["leads"])
api_router.include_router(webhooks.router,       prefix="/webhooks",      tags=["webhooks"])
api_router.include_router(metrics.router,        prefix="/metrics",       tags=["metrics"])
