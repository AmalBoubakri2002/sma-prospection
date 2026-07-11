#Push d'un lead vers Odoo — dédup par x_sma_pc_id (write si déjà connu, sinon create) puis historisation de l'e-mail envoyé dans le chatter de la fiche Odoo.

from app.agents.crm.mapping import build_odoo_payload
from app.models.lead import Lead
from app.services import odoo_client

# Les leads arrivent ici toujours QUALIFIE + VALIDE (seule entrée de push_lead_to_odoo) :
# on les pousse directement dans l'étape "Qualified" plutôt que de les laisser
# atterrir en "New" et forcer un tri manuel côté commercial dans Odoo.
_QUALIFIED_STAGE_NAME = "Qualified"

# Cache mémoire (durée de vie du process) : le stage_id et les user_id par email
# changent rarement, pas la peine de refaire un search Odoo à chaque lead.
_cached_qualified_stage_id: int | None | bool = None
_cached_user_ids_by_email: dict[str, int | None] = {}


async def _get_qualified_stage_id() -> int | None:
    global _cached_qualified_stage_id
    if _cached_qualified_stage_id is None:
        ids = await odoo_client.execute_kw(
            "crm.stage", "search", [[["name", "=", _QUALIFIED_STAGE_NAME]]]
        )
        _cached_qualified_stage_id = ids[0] if ids else False
    return _cached_qualified_stage_id or None


async def _get_user_id_by_email(email: str | None) -> int | None:
    """Retrouve l'utilisateur Odoo (vendeur) correspondant au commercial SMA-PC par e-mail.

    Renvoie None si aucun compte Odoo ne correspond — le lead reste alors assigné
    au compte technique par défaut plutôt que d'échouer la synchronisation.
    """
    if not email:
        return None
    if email not in _cached_user_ids_by_email:
        ids = await odoo_client.execute_kw("res.users", "search", [[["login", "=", email]]])
        _cached_user_ids_by_email[email] = ids[0] if ids else None
    return _cached_user_ids_by_email[email]


async def push_lead_to_odoo(lead: Lead, commercial_email: str | None = None) -> int:
    payload = build_odoo_payload(lead)
    sma_pc_id = payload["x_sma_pc_id"]

    stage_id = await _get_qualified_stage_id()
    if stage_id:
        payload["stage_id"] = stage_id

    user_id = await _get_user_id_by_email(commercial_email)
    if user_id:
        payload["user_id"] = user_id

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
