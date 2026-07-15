# Traitement des webhooks Odoo entrants — boucle retour de la synchronisation CRM.

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.crm_sync import CRMSync
from app.models.lead import Lead, LeadStatus
from app.models.webhook_event import WebhookEvent, WebhookEventResult
from app.services.notification import notify_retour_crm

logger = logging.getLogger("webhooks-odoo")

EVENT_TO_STATUS = {
    "lead.won": LeadStatus.REPONDU,
    "lead.lost": LeadStatus.SANS_REPONSE,
    "message.received": LeadStatus.REPONDU,
}

# Un retour CRM ne s'applique qu'à un lead déjà passé par la synchronisation
# Odoo — jamais à un lead encore dans le pipeline amont, sinon on créerait un
# trou dans son cycle de vie (ex : EN_ATTENTE_VALIDATION → REPONDU sans
# validation commerciale ni synchronisation).
_UPDATABLE_STATUSES = {
    LeadStatus.SYNCHRONISE_CRM,
    LeadStatus.CONTACTE,
    LeadStatus.REPONDU,
    LeadStatus.SANS_REPONSE,
}


async def find_lead_for_event(
    db: AsyncSession, sma_pc_id: str | None, odoo_lead_id: int | None
) -> Lead | None:
    """Retrouve le lead local visé par un événement Odoo.

    D'abord par x_sma_pc_id (notre UUID, écrit dans Odoo par l'Agent CRM —
    source de vérité), sinon par odoo_lead_id via la table crm_syncs (repli
    utile si le champ custom a été vidé côté Odoo)."""
    if sma_pc_id:
        try:
            lead = await db.get(Lead, uuid.UUID(sma_pc_id))
        except ValueError:
            lead = None
        if lead is not None:
            return lead

    if odoo_lead_id is not None:
        # Plusieurs leads SMA-PC peuvent pointer vers la même fiche Odoo depuis
        # le rattachement anti-doublon (find_crm_duplicate) : on prend le plus
        # récent au lieu de laisser scalar_one_or_none échouer sur multiples.
        result = await db.execute(
            select(Lead)
            .join(CRMSync, CRMSync.lead_id == Lead.id)
            .where(CRMSync.odoo_lead_id == odoo_lead_id)
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    return None


async def apply_event(db: AsyncSession, lead: Lead, event: str) -> str:
    """Applique la transition de statut au lead et notifie le commercial.

    Renvoie un WebhookEventResult. Idempotent : rejouer le même événement
    (relivraison Odoo) ne change rien et ne renotifie pas."""
    new_status = EVENT_TO_STATUS[event]

    if lead.status not in _UPDATABLE_STATUSES:
        logger.warning(
            "Webhook Odoo %s ignoré — lead %s en statut %s (pas encore synchronisé CRM)",
            event, lead.id, lead.status,
        )
        return WebhookEventResult.SKIPPED_STATUS

    if lead.status == new_status:
        return WebhookEventResult.NOOP

    # Un prospect qui a répondu ne redevient pas SANS_REPONSE si l'opportunité
    # est perdue ensuite : REPONDU décrit un fait acquis (il y a eu une réponse),
    # pas l'issue commerciale — celle-ci reste visible dans Odoo (lead perdu).
    if lead.status == LeadStatus.REPONDU and new_status == LeadStatus.SANS_REPONSE:
        logger.info(
            "Webhook Odoo lead.lost — lead %s conservé en REPONDU (réponse déjà reçue)",
            lead.id,
        )
        return WebhookEventResult.NOOP

    lead.status = new_status
    await db.commit()
    logger.info("Webhook Odoo %s — lead %s passé en %s", event, lead.id, new_status)

    campaign = await db.get(Campaign, lead.campaign_id)
    if campaign is not None:
        await notify_retour_crm(db, campaign.commercial_id, lead.company_name, event)

    return WebhookEventResult.PROCESSED


async def record_event(
    db: AsyncSession,
    *,
    event: str,
    odoo_lead_id: int | None,
    lead_id: uuid.UUID | None,
    payload: dict,
    result: str,
) -> None:
    """Journalise l'événement reçu et son issue dans webhook_events (audit §13.5.5)."""
    db.add(
        WebhookEvent(
            event=event,
            odoo_lead_id=odoo_lead_id,
            lead_id=lead_id,
            payload=json.dumps(payload, ensure_ascii=False),
            result=result,
        )
    )
    await db.commit()
