# Adaptateur REST→JSON-RPC — traduit un Lead SMA-PC en payload crm.lead Odoo.

from app.models.lead import Lead

# label_scoring (Agent Scoring) -> priority Odoo (0=Low ... 3=Very High).
# Mapping bijectif : 4 labels SMA-PC, 4 niveaux Odoo.
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
        # Champ natif Odoo (utilisé par le Kanban pondéré et les prévisions de
        # pipeline) — sans ça le score IA restait cantonné au champ custom x_score_ia,
        # invisible pour les rapports natifs Odoo.
        # NB : pas de expected_revenue ici — le CA du prospect (lead.ca) n'a aucun
        # rapport avec la valeur attendue du contrat SMA-PC ; on n'a pas de signal
        # réel pour ce champ, mieux vaut le laisser vide que de le remplir avec un
        # chiffre trompeur. À saisir manuellement par le commercial dans Odoo.
        "probability": round(lead.score * 100, 1) if lead.score is not None else None,
        "description": lead.contenu_email,
        "x_sma_pc_id": str(lead.id),
        "x_siret": lead.siret,
        "x_taille_entreprise": lead.taille_entreprise,
        "x_date_creation_entreprise": lead.date_creation.isoformat() if lead.date_creation else None,
        "x_ca": lead.ca,
        "x_resultat_net": lead.resultat_net,
    }
    # Odoo n'aime pas recevoir None sur des champs qu'on ne veut pas écraser ;
    # on n'envoie que ce qu'on a réellement (x_sma_pc_id est toujours présent).
    return {key: value for key, value in payload.items() if value is not None}
