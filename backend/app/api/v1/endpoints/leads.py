import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_active_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.lead import LeadListResponse, LeadResponse
from app.services.lead import list_leads

router = APIRouter()


@router.get("/", response_model=LeadListResponse)
async def get_leads(
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
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
        page=page,
        page_size=page_size,
    )
    return LeadListResponse(
        items=[LeadResponse.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )
