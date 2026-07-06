"""Logique partagée entre l'Agent Enrichissement et les scripts `ml/` (dataset offline),
pour que les deux ne divergent pas silencieusement sur les poids/règles de fallback."""


def compute_score_intent(fields: dict) -> float:
    """Score d'intention (0-100) basé sur la complétude du profil enrichi."""
    return float(
        25 * int(bool(fields.get("email"))) +
        25 * int(bool(fields.get("telephone"))) +
        20 * int(bool(fields.get("site_web"))) +
        15 * int(bool(fields.get("prenom_dirigeant"))) +
        15 * int(bool(fields.get("ca")))
    )


def apply_inpi_fallback(fields: dict, inpi_data: dict) -> None:
    """Complète ca/ca_n1/resultat_net manquants dans `fields` avec les données INPI.

    Assignation directe, pas .setdefault() : `fields` contient déjà ces clés (à None),
    donc .setdefault() ne les remplacerait jamais.
    """
    if fields.get("ca_n1") is None and inpi_data.get("ca_n1") is not None:
        fields["ca_n1"] = inpi_data["ca_n1"]
    if not fields.get("ca") and inpi_data.get("ca") is not None:
        fields["ca"] = inpi_data["ca"]
    if not fields.get("resultat_net") and inpi_data.get("resultat_net") is not None:
        fields["resultat_net"] = inpi_data["resultat_net"]
