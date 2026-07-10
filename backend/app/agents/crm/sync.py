#Push d'un lead vers Odoo — dédup par x_sma_pc_id (write si déjà connu, sinon create) puis historisation de l'e-mail envoyé dans le chatter de la fiche Odoo.

from app.agents.crm.mapping import build_odoo_payload
from app.models.lead import Lead
from app.services import odoo_client


async def push_lead_to_odoo(lead: Lead) -> int:
    payload = build_odoo_payload(lead)
    sma_pc_id = payload["x_sma_pc_id"]

    existing_ids = await odoo_client.execute_kw(
        "crm.lead", "search", [[["x_sma_pc_id", "=", sma_pc_id]]]
    )
    if existing_ids:
        odoo_lead_id = existing_ids[0]
        await odoo_client.execute_kw("crm.lead", "write", [[odoo_lead_id], payload])
        return odoo_lead_id

    return await odoo_client.execute_kw("crm.lead", "create", [payload])


async def historize_email_in_chatter(odoo_lead_id: int, objet: str, contenu: str) -> None:
    """Log l'e-mail de prospection envoyé dans le chatter (mail.message) de la fiche Odoo."""
    body = f"<p><strong>Objet :</strong> {objet}</p>{contenu or ''}"
    await odoo_client.execute_kw(
        "crm.lead",
        "message_post",
        [[odoo_lead_id]],
        {"body": body, "subject": objet},
    )
