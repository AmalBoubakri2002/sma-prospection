import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.notification_bus import listen_forever
from app.core.security import hash_password
from app.db.base import AsyncSessionLocal, Base, engine
from app.models import Notification, User  # noqa: F401 — registers all models on Base.metadata


async def _seed_admin() -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(User).where(User.email == settings.FIRST_ADMIN_EMAIL)
        )
        if existing.scalar_one_or_none() is not None:
            return
        admin = User(
            email=settings.FIRST_ADMIN_EMAIL,
            hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
            full_name=settings.FIRST_ADMIN_NAME,
            role="admin",
        )
        db.add(admin)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Les migrations sont gérées par Alembic (alembic upgrade head).
    # create_all est volontairement absent pour éviter les conflits avec les migrations.
    await _seed_admin()
    # Bus de notifications : le processus API écoute PostgreSQL (LISTEN/NOTIFY)
    # et pousse vers les WebSockets — les workers, eux, ne font que publier.
    listener = asyncio.create_task(listen_forever())
    yield
    listener.cancel()
    with suppress(asyncio.CancelledError):
        await listener
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health():
    return {"status": "ok", "project": settings.PROJECT_NAME}
