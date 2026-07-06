"""Webhook Odoo 17 — reçoit les événements de retour CRM (lead.won/lost, mail.received),
à consommer par l'Agent CRM (à implémenter) pour mettre à jour le statut des leads."""

import logging

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger("webhooks-odoo")

router = APIRouter()

_SUPPORTED_EVENTS = {"lead.won", "lead.lost", "mail.received"}


@router.post("/odoo", status_code=status.HTTP_200_OK)
async def odoo_webhook(request: Request) -> dict:
    """Reçoit les notifications Odoo 17 et les enregistre pour traitement."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corps JSON invalide",
        )

    event = payload.get("event", "")
    odoo_lead_id = payload.get("odoo_lead_id")

    logger.info("Webhook Odoo reçu — event=%s odoo_lead_id=%s", event, odoo_lead_id)

    if event not in _SUPPORTED_EVENTS:
        logger.warning("Événement Odoo non géré : %s", event)
        return {"status": "ignored", "event": event}

    # TODO (Agent CRM) : rechercher le lead local par x_sma_pc_id,
    # mettre à jour son statut (REPONDU / SANS_REPONSE) et notifier le commercial.

    return {"status": "received", "event": event, "odoo_lead_id": odoo_lead_id}
