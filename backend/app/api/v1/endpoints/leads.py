import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.campaign import Campaign
from app.models.lead import Lead, LeadStatus
from app.models.user import User
from app.schemas.lead import LeadListResponse, LeadResponse
from app.services.lead import get_leads_stats, list_leads, update_lead_email_content

router = APIRouter()

# Statuts modifiables manuellement par le commercial
_ALLOWED_MANUAL_STATUSES = {
    LeadStatus.QUALIFIE,
    LeadStatus.REJETE,
    LeadStatus.VALIDE,               # validation d'un email généré
    LeadStatus.EN_ATTENTE_VALIDATION,  # remise en file d'attente
}


class LeadStatusUpdate(BaseModel):
    status: str


class LeadEmailUpdate(BaseModel):
    objet_email: str
    contenu_email: str


class LeadStatsResponse(BaseModel):
    leads_a_valider: int
    emails_en_attente: int
    taux_validation: float | None
    taux_modification: float | None
    score_moyen: float | None


async def _get_owned_lead(db: AsyncSession, lead_id: uuid.UUID, commercial_id: uuid.UUID) -> Lead | None:
    """Renvoie le lead s'il appartient à une campagne de ce commercial, sinon None."""
    result = await db.execute(
        select(Lead)
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(Lead.id == lead_id, Campaign.commercial_id == commercial_id)
    )
    return result.scalar_one_or_none()


@router.get("/stats", response_model=LeadStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    stats = await get_leads_stats(db, commercial_id=current_user.id)
    return LeadStatsResponse(**stats)


@router.get("/", response_model=LeadListResponse)
async def get_leads(
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
    sort_by_score: bool = Query(False, description="Trier par score décroissant"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    leads, total = await list_leads(
        db,
        commercial_id=current_user.id,
        campaign_id=campaign_id,
        status=status,
        sort_by_score=sort_by_score,
        page=page,
        page_size=page_size,
    )
    return LeadListResponse(
        items=[LeadResponse.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{lead_id}/status", response_model=LeadResponse)
async def update_status(
    lead_id: uuid.UUID,
    data: LeadStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    if data.status not in _ALLOWED_MANUAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Statut invalide. Valeurs acceptées : {sorted(_ALLOWED_MANUAL_STATUSES)}",
        )

    lead = await _get_owned_lead(db, lead_id, current_user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead introuvable")
    if lead.score is None:
        raise HTTPException(status_code=409, detail="Ce lead n'a pas encore été scoré")

    lead.status = data.status
    await db.commit()
    await db.refresh(lead)
    return LeadResponse.model_validate(lead)


@router.patch("/{lead_id}/email", response_model=LeadResponse)
async def update_email(
    lead_id: uuid.UUID,
    data: LeadEmailUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_active_user),
):
    """Modifie l'email généré (objet + corps) sans changer le statut du lead."""
    lead = await _get_owned_lead(db, lead_id, current_user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead introuvable")
    if lead.objet_email is None:
        raise HTTPException(status_code=409, detail="Aucun email généré pour ce lead")

    updated = await update_lead_email_content(db, lead, data.objet_email, data.contenu_email)
    return LeadResponse.model_validate(updated)
