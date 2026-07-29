#Push d'un lead vers Odoo — dédup par x_sma_pc_id (write si déjà connu, sinon create) puis
# historisation de l'e-mail envoyé dans le chatter de la fiche Odoo.

import html

from app.agents.crm.mapping import build_odoo_payload
from app.models.lead import Lead
from app.services import odoo_client

# on les pousse directement dans l'étape "Qualified" plutôt que de les laisser
_QUALIFIED_STAGE_NAME = "Qualified"

# Cache mémoire : le stage_id et les comptes Odoo par email changent rarement, pas la peine
# de refaire un search Odoo à chaque lead.
_cached_qualified_stage_id: int | None | bool = None
# {email: (user_id, partner_id)} — un seul aller-retour Odoo sert à la fois pour
# le champ user_id (Vendeur) et pour author_id (auteur du message dans le chatter).
_cached_odoo_user_by_email: dict[str, tuple[int, int]] = {}


async def _get_qualified_stage_id() -> int | None:
    global _cached_qualified_stage_id
    if _cached_qualified_stage_id is None:
        ids = await odoo_client.execute_kw(
            "crm.stage", "search", [[["name", "=", _QUALIFIED_STAGE_NAME]]]
        )
        _cached_qualified_stage_id = ids[0] if ids else False
    return _cached_qualified_stage_id or None


async def _get_odoo_user(email: str | None) -> tuple[int, int] | None:
    # Retrouve (user_id, partner_id) du compte Odoo correspondant au commercial SMA-PC par
    # e-mail. user_id sert au champ Vendeur ; partner_id sert d'auteur pour les messages
    # postés dans le chatter (sans ça, tout apparaît posté par le compte technique API, quel
    # que soit le vendeur assigné au lead).

    if not email:
        return None
    if email in _cached_odoo_user_by_email:
        return _cached_odoo_user_by_email[email]
    users = await odoo_client.execute_kw(
        "res.users", "search_read", [[["login", "=", email]]], {"fields": ["partner_id"]}
    )
    if not users or not users[0].get("partner_id"):
        return None
    result = (users[0]["id"], users[0]["partner_id"][0])
    _cached_odoo_user_by_email[email] = result
    return result


async def find_crm_duplicate(lead: Lead) -> int | None:
    """Fiche Odoo ACTIVE portant le même SIRET mais issue d'un autre lead SMA-PC
    (autre campagne) : la même entreprise est déjà suivie dans le CRM.

    Renvoie son id pour que l'Agent CRM s'y RATTACHE au lieu de créer un doublon
    — et surtout de renvoyer un email à un prospect déjà engagé (voire gagné).
    Renvoie None si c'est notre propre fiche (simple retry du même lead) ou s'il
    n'y a pas de doublon. Les fiches archivées (perdues) ne comptent pas : une
    entreprise perdue peut légitimement être re-prospectée plus tard."""
    if not lead.siret:
        return None
    own = await odoo_client.execute_kw(
        "crm.lead", "search", [[["x_sma_pc_id", "=", str(lead.id)]]]
    )
    if own:
        return None
    ids = await odoo_client.execute_kw(
        "crm.lead", "search", [[["x_siret", "=", lead.siret]]], {"limit": 1}
    )
    return ids[0] if ids else None


async def push_lead_to_odoo(lead: Lead, commercial_email: str | None = None) -> int:
    payload = build_odoo_payload(lead)
    sma_pc_id = payload["x_sma_pc_id"]

    stage_id = await _get_qualified_stage_id()
    if stage_id:
        payload["stage_id"] = stage_id

    odoo_user = await _get_odoo_user(commercial_email)
    if odoo_user:
        payload["user_id"] = odoo_user[0]

    existing_ids = await odoo_client.execute_kw(
        "crm.lead", "search", [[["x_sma_pc_id", "=", sma_pc_id]]]
    )
    if existing_ids:
        odoo_lead_id = existing_ids[0]
        await odoo_client.execute_kw("crm.lead", "write", [[odoo_lead_id], payload])
        return odoo_lead_id

    return await odoo_client.execute_kw("crm.lead", "create", [payload])


async def historize_email_in_chatter(
    odoo_lead_id: int, objet: str, contenu: str, commercial_email: str | None = None
) -> None:
    #Log l'e-mail de prospection envoyé dans le chatter (mail.message) de la fiche Odoo.
    body = f"Objet : {objet}\n\n{contenu or ''}"
    kwargs = {"body": body, "subject": objet}

    odoo_user = await _get_odoo_user(commercial_email)
    if odoo_user:
        kwargs["author_id"] = odoo_user[1]

    await odoo_client.execute_kw("crm.lead", "message_post", [[odoo_lead_id]], kwargs)


async def send_prospection_email(
    odoo_lead_id: int, objet: str, contenu: str, email_to: str, email_from: str
) -> int:
    """Envoie l'email de prospection au prospect via le module mail d'Odoo.

    mail.mail est créé directement (pas via message_post) : l'envoi ne passe
    donc pas par le chatter et ne déclenche pas notre détection message.received
    (réservée aux messages ENTRANTS). model/res_id relient quand même l'email à
    la fiche crm.lead côté Odoo.

    L'état est relu après send() : Odoo peut marquer le mail 'exception' sans
    lever d'erreur, on ne passe le lead en CONTACTE que sur un état 'sent'."""
    # Le corps généré est en texte brut : échappement HTML puis retours à la
    # ligne convertis, pour un rendu propre dans les clients mail.
    body_html = "<p>" + html.escape(contenu or "").replace("\n", "<br>") + "</p>"

    mail_id = await odoo_client.execute_kw(
        "mail.mail",
        "create",
        [{
            "subject": objet,
            "body_html": body_html,
            "email_to": email_to,
            "email_from": email_from,
            "model": "crm.lead",
            "res_id": odoo_lead_id,
        }],
    )
    await odoo_client.execute_kw("mail.mail", "send", [[mail_id]], {"raise_exception": True})

    records = await odoo_client.execute_kw("mail.mail", "read", [[mail_id], ["state"]])
    state = records[0]["state"] if records else "inconnu"
    if state != "sent":
        raise odoo_client.OdooError(f"Email mail.mail #{mail_id} non envoyé (état {state!r})")
    return mail_id
