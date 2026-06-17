import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.agent_task import AgentName
from app.models.user import User
from app.schemas.campaign import (
    AgentTaskSummary,
    CampaignCreate,
    CampaignResponse,
    CampaignStatusResponse,
    CampaignStatusUpdate,
)
from app.services.agent_task import create_task, get_latest_task_for_campaign
from app.services.campaign import (
    create_campaign,
    delete_campaign,
    get_campaign,
    list_campaigns,
    update_campaign_status,
)
from app.services.lead import count_leads_by_campaign, count_leads_for_campaign

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
    campaigns = await list_campaigns(db, current_user.id)
    counts = await count_leads_by_campaign(db, current_user.id)
    for campaign in campaigns:
        campaign.leads_count = counts.get(campaign.id, 0)
    return campaigns


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


@router.post("/{campaign_id}/start", response_model=CampaignResponse, status_code=202)
async def start(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    if campaign.status == "running":
        raise HTTPException(status_code=409, detail="La campagne est déjà en cours")

    await create_task(
        db,
        campaign_id=campaign.id,
        agent_name=AgentName.VEILLE,
        payload={
            "codes_naf": campaign.codes_naf,
            "codes_postaux": campaign.codes_postaux,
            "tranches_effectifs": campaign.tranches_effectifs,
            "quota": campaign.quota,
        },
    )
    return await update_campaign_status(db, campaign, "running")


@router.get("/{campaign_id}/status", response_model=CampaignStatusResponse)
async def get_status(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    campaign = await get_campaign(db, campaign_id, current_user.id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campagne introuvable")

    leads_collected = await count_leads_for_campaign(db, campaign.id)
    task = await get_latest_task_for_campaign(db, campaign.id, agent_name=AgentName.VEILLE)
    task_summary = None
    if task:
        task_summary = AgentTaskSummary(
            agent_name=task.agent_name,
            status=task.status,
            attempts=task.attempts,
            error=(task.result or {}).get("error") if task.result else None,
        )

    return CampaignStatusResponse(
        id=campaign.id,
        status=campaign.status,
        leads_collected=leads_collected,
        task=task_summary,
    )


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
