# Construit le vecteur de features XGBoost depuis un objet Lead ORM.

import math
from datetime import date

import numpy as np

from app.agents.scoring.feature_spec import (
    FEATURE_NAMES,
    MARGE_NETTE_CLIP,
    TAILLE_MIDPOINT,
    TAILLE_TO_CODE,
    ca_median_for_taille,
    clean_financial_value,
    naf_division as _naf_division,
    signed_log1p as _signed_log1p,
)
from app.models.lead import Lead

__all__ = ["FEATURE_NAMES", "build_feature_vector"]


def build_feature_vector(lead: Lead, config: dict) -> np.ndarray:
    """
    Transforme un Lead ORM en vecteur numpy (1, 15) prêt pour model.predict().

    Args:
        lead   : instance Lead SQLAlchemy (doit être en statut ENRICHI)
        config : contenu de models/feature_config.json

    Returns:
        X de forme (1, len(FEATURE_NAMES)), dtype float32
    """
    medians = config["medians"]
    secteur_index: dict[str, int] = {
        c: i for i, c in enumerate(medians["secteur_categories"])
    }

    today = date.today()

    # ── Financiers ────────────────────────────────────────────────────────────
    # ca=0 traité comme manquant (symptôme d'un CA jamais récupéré, cf. clean_financial_value).
    # resultat_net=0 est en revanche une vraie valeur (l'API ne renvoie jamais 0 pour "inconnu") ;
    # le traiter comme manquant double-pénaliserait les leads à RN nul mais par ailleurs solides.
    lead_ca = clean_financial_value(lead.ca)
    lead_rn = lead.resultat_net

    # max(0, ...) évite un log1p(NaN) si le CA source est aberrant (négatif).
    # CA manquant → médiane de la tranche de taille du lead, pas la médiane
    # globale (voir feature_spec.ca_median_for_taille).
    ca: float = (
        max(0.0, float(lead_ca))
        if lead_ca is not None
        else ca_median_for_taille(medians, lead.taille_entreprise)
    )
    ca_n1: int | None = lead.ca_n1
    rn: int | None = lead_rn

    marge_raw: float = (
        rn / lead_ca
        if rn is not None and lead_ca and lead_ca > 0
        else medians["marge_nette"]
    )
    marge: float = float(np.clip(marge_raw, -MARGE_NETTE_CLIP, MARGE_NETTE_CLIP))
    croissance: float = (
        (lead_ca - ca_n1) / ca_n1
        if lead_ca is not None and ca_n1 and ca_n1 > 0
        else 0.0
    )

    # ── Ancienneté ────────────────────────────────────────────────────────────
    age: float = (
        (today - lead.date_creation).days / 365.25
        if lead.date_creation is not None
        else medians["age_entreprise"]
    )

    # ── Encodages catégoriels ─────────────────────────────────────────────────
    taille_code = float(TAILLE_TO_CODE.get(str(lead.taille_entreprise or "NN"), 0))
    secteur_code = float(secteur_index.get(_naf_division(lead.secteur), -1))
    effectif = TAILLE_MIDPOINT.get(str(lead.taille_entreprise or "NN"), TAILLE_MIDPOINT["NN"])
    ca_par_salarie = ca / max(effectif, 1)

    vec = [
        math.log1p(ca),
        float(lead_ca is not None),
        math.log1p(max(0.0, float(ca_n1)) if ca_n1 is not None else medians["ca_n1"]),
        float(ca_n1 is not None),
        _signed_log1p(rn),
        float(rn is not None),
        marge,
        croissance,
        age,
        taille_code,
        secteur_code,
        math.log1p(ca_par_salarie),
    ]

    return np.array([vec], dtype=np.float32)
