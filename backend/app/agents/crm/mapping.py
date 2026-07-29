# Adaptateur REST→JSON-RPC — traduit un Lead SMA-PC en payload crm.lead Odoo.

from app.models.lead import Lead

_LABEL_TO_PRIORITY = {
    "HORS_CIBLE": "0",
    "FROID": "1",
    "TIEDE": "2",
    "CHAUD": "3",
}


def build_odoo_payload(lead: Lead) -> dict:
    contact_name = " ".join(
        part for part in (lead.prenom_dirigeant, lead.nom_dirigeant) if part
    )

    payload = {
        "name": lead.company_name,
        # partner_name = "Company Name" (la société) ; contact_name = "Contact Name"
        # (la personne) — deux champs Odoo distincts, à ne pas confondre.
        "partner_name": lead.company_name,
        "contact_name": contact_name or None,
        "function": lead.titre_dirigeant,
        "email_from": lead.email,
        "phone": lead.telephone,
        "website": lead.site_web,
        "street": lead.adresse,
        "x_sector": lead.secteur,
        "x_score_ia": lead.score,
        "x_label_ia": lead.label_scoring,
        "priority": _LABEL_TO_PRIORITY.get(lead.label_scoring),
        "probability": round(lead.score * 100, 1) if lead.score is not None else None,
        "description": lead.contenu_email,
        "x_sma_pc_id": str(lead.id),
        "x_siret": lead.siret,
        "x_taille_entreprise": lead.taille_entreprise,
        "x_date_creation_entreprise": (
            lead.date_creation.isoformat() if lead.date_creation else None
        ),
        "x_ca": lead.ca,
        "x_resultat_net": lead.resultat_net,
    }
    return {key: value for key, value in payload.items() if value is not None}
