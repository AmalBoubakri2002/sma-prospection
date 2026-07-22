import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.metrics import MetricsResponse
from app.services.campaign import get_campaign
from app.services.metrics import get_metrics_report

router = APIRouter()


@router.get("/", response_model=MetricsResponse)
async def get_metrics(
    campaign_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Rapport de performance : funnel de conversion, qualité du scoring,
    délais moyens entre étapes du pipeline, fiabilité des agents et de la
    synchronisation CRM. Sans campaign_id : agrégé sur toutes les campagnes
    du commercial connecté."""
    if campaign_id is not None:
        campaign = await get_campaign(db, campaign_id, current_user.id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campagne introuvable")

    return await get_metrics_report(db, current_user.id, campaign_id)
