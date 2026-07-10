# Adaptateur REST→JSON-RPC — traduit un Lead SMA-PC en payload crm.lead Odoo.

from app.models.lead import Lead

def build_odoo_payload(lead: Lead) -> dict:
    contact_name = " ".join(
        part for part in (lead.prenom_dirigeant, lead.nom_dirigeant) if part
    )

    payload = {
        "name": lead.company_name,
        "partner_name": contact_name or None,
        "email_from": lead.email,
        "phone": lead.telephone,
        "x_sector": lead.secteur,
        "x_score_ia": lead.score,
        "x_label_ia": lead.label_scoring,
        "description": lead.contenu_email,
        "x_sma_pc_id": str(lead.id),
    }
    # Odoo n'aime pas recevoir None sur des champs qu'on ne veut pas écraser ;
    # on n'envoie que ce qu'on a réellement (x_sma_pc_id est toujours présent).
    return {key: value for key, value in payload.items() if value is not None}
