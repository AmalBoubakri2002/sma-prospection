import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignResponse, CampaignStatusUpdate
from app.services.campaign import (
    create_campaign,
    delete_campaign,
    get_campaign,
    list_campaigns,
    update_campaign_status,
)

router = APIRouter()


@router.post("/", response_model=CampaignResponse, status_code=201)
async def create(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    return await create_campaign(db, data, current_user.id)


@router.get("/", response_model=list[CampaignResponse])
async def list_(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    return await list_campaigns(db, current_user.id)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return campaign


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
async def update_status(
    campaign_id: uuid.UUID,
    data: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return await update_campaign_status(db, campaign, data.status)


@router.delete("/{campaign_id}", status_code=204)
async def delete(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    await delete_campaign(db, campaign)
