import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.lead import Lead, LeadStatus


async def get_existing_sirets(db: AsyncSession, campaign_id: uuid.UUID) -> set[str]:
    result = await db.execute(select(Lead.siret).where(Lead.campaign_id == campaign_id))
    return set(result.scalars().all())


async def bulk_create_leads(
    db: AsyncSession, campaign_id: uuid.UUID, leads: list[dict]
) -> list[Lead]:
    if not leads:
        return []
    objects = [Lead(campaign_id=campaign_id, **data) for data in leads]
    db.add_all(objects)
    await db.commit()
    for obj in objects:
        await db.refresh(obj)
    return objects


async def count_leads_for_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Lead).where(Lead.campaign_id == campaign_id)
    )
    return result.scalar_one()


async def count_leads_by_campaign(
    db: AsyncSession, commercial_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Compte les leads de chaque campagne d'un commercial, en une seule requête."""
    result = await db.execute(
        select(Lead.campaign_id, func.count())
        .join(Campaign, Campaign.id == Lead.campaign_id)
        .where(Campaign.commercial_id == commercial_id)
        .group_by(Lead.campaign_id)
    )
    return dict(result.all())


async def list_leads(
    db: AsyncSession,
    commercial_id: uuid.UUID,
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    base = select(Lead).join(Campaign, Campaign.id == Lead.campaign_id).where(
        Campaign.commercial_id == commercial_id
    )
    if campaign_id:
        base = base.where(Lead.campaign_id == campaign_id)
    if status:
        base = base.where(Lead.status == status)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    stmt = base.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_leads_to_enrich(
    db: AsyncSession, campaign_id: uuid.UUID, page_size: int = 50
) -> list[Lead]:
    """Leads en statut COLLECTE pour une campagne — entrée de l'Agent Enrichissement."""
    stmt = (
        select(Lead)
        .where(Lead.campaign_id == campaign_id, Lead.status == LeadStatus.COLLECTE)
        .order_by(Lead.created_at.asc())
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


_REUSABLE_FIELDS = (
    "telephone", "site_web", "email",
    "prenom_dirigeant", "nom_dirigeant", "titre_dirigeant",
    "ca", "resultat_net", "ca_n1",
    "latitude", "longitude", "date_creation",
)


async def get_enriched_fields_by_siret(db: AsyncSession, siret: str) -> dict | None:
    """Renvoie les champs enrichis du lead le plus récent avec ce SIRET (status=ENRICHI).

    Évite de re-scraper un SIRET déjà enrichi dans une autre campagne et garantit
    la cohérence (même téléphone, même email, même date_creation) entre campagnes."""
    stmt = (
        select(Lead)
        .where(Lead.siret == siret, Lead.status == LeadStatus.ENRICHI)
        .order_by(Lead.enriched_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        return None
    return {f: getattr(existing, f) for f in _REUSABLE_FIELDS if getattr(existing, f) is not None}


async def update_lead_enriched(db: AsyncSession, lead: Lead, fields: dict) -> Lead:
    """Met à jour les champs enrichis et passe le lead en ENRICHI."""
    for key, value in fields.items():
        if value is not None:
            setattr(lead, key, value)
    lead.status = LeadStatus.ENRICHI
    lead.enriched_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


