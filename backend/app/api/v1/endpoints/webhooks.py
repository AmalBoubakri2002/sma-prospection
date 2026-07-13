# Webhook Odoo 17 — boucle retour de la synchronisation CRM 

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_db
from app.models.webhook_event import WebhookEventResult
from app.services.odoo_webhook import (
    EVENT_TO_STATUS,
    apply_event,
    find_lead_for_event,
    record_event,
)

logger = logging.getLogger("webhooks-odoo")

router = APIRouter()


class OdooWebhookPayload(BaseModel):
    event: str
    odoo_lead_id: int | None = None
    x_sma_pc_id: str | None = None


def verify_webhook_secret(
    x_sma_webhook_secret: str = Header(default=""),
) -> None:
    """Authentifie l'appelant par secret partagé (header X-SMA-Webhook-Secret).

    compare_digest : comparaison en temps constant, le secret ne doit pas être
    devinable octet par octet en mesurant le temps de réponse."""
    if not settings.ODOO_WEBHOOK_SECRET:
        # Fail closed : sans secret configuré on refuse tout, plutôt que
        # d'exposer un endpoint qui modifie des statuts sans authentification.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ODOO_WEBHOOK_SECRET non configuré côté backend",
        )
    if not hmac.compare_digest(x_sma_webhook_secret, settings.ODOO_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret webhook invalide",
        )


@router.post(
    "/odoo",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_webhook_secret)],
)
async def odoo_webhook(
    payload: OdooWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    logger.info(
        "Webhook Odoo reçu — event=%s odoo_lead_id=%s x_sma_pc_id=%s",
        payload.event, payload.odoo_lead_id, payload.x_sma_pc_id,
    )

    if payload.event not in EVENT_TO_STATUS:
        await record_event(
            db,
            event=payload.event,
            odoo_lead_id=payload.odoo_lead_id,
            lead_id=None,
            payload=payload.model_dump(),
            result=WebhookEventResult.IGNORED,
        )
        logger.warning("Événement Odoo non géré : %s", payload.event)
        return {"status": "ignored", "event": payload.event}

    lead = await find_lead_for_event(db, payload.x_sma_pc_id, payload.odoo_lead_id)
    if lead is None:
        await record_event(
            db,
            event=payload.event,
            odoo_lead_id=payload.odoo_lead_id,
            lead_id=None,
            payload=payload.model_dump(),
            result=WebhookEventResult.LEAD_NOT_FOUND,
        )
        logger.warning(
            "Webhook Odoo — aucun lead local pour odoo_lead_id=%s / x_sma_pc_id=%s",
            payload.odoo_lead_id, payload.x_sma_pc_id,
        )
        return {"status": "lead_not_found", "event": payload.event}

    result = await apply_event(db, lead, payload.event)
    await record_event(
        db,
        event=payload.event,
        odoo_lead_id=payload.odoo_lead_id,
        lead_id=lead.id,
        payload=payload.model_dump(),
        result=result,
    )

    return {
        "status": result.lower(),
        "event": payload.event,
        "lead_id": str(lead.id),
        "lead_status": lead.status,
    }
