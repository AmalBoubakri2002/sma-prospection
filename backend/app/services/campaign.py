import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.schemas.campaign import CampaignCreate


async def create_campaign(
    db: AsyncSession, data: CampaignCreate, commercial_id: uuid.UUID
) -> Campaign:
    campaign = Campaign(
        commercial_id=commercial_id,
        sector=data.sector,
        country=data.country,
        sizes=data.sizes,
        functions=data.functions,
        min_score=data.min_score,
        sources=data.sources,
        estimated_prospects=data.estimated_prospects,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def list_campaigns(
    db: AsyncSession, commercial_id: uuid.UUID
) -> list[Campaign]:
    result = await db.execute(
        select(Campaign)
        .where(Campaign.commercial_id == commercial_id)
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


async def get_campaign(
    db: AsyncSession, campaign_id: uuid.UUID, commercial_id: uuid.UUID
) -> Campaign | None:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.commercial_id == commercial_id,
        )
    )
    return result.scalar_one_or_none()


async def update_campaign_status(
    db: AsyncSession, campaign: Campaign, status: str
) -> Campaign:
    campaign.status = status
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def delete_campaign(db: AsyncSession, campaign: Campaign) -> None:
    await db.delete(campaign)
    await db.commit()
