"""Charge le modèle XGBoost (joblib) et expose predict() pour un Lead unique.

ATTENTION : score/label reflètent une règle de qualification, pas une probabilité de
conversion réelle — le modèle est entraîné sur un label dérivé des mêmes champs
financiers utilisés comme features, sans signal de conversion indépendant
(détails : ml/train_scoring_model.py, ml/dataset_pipeline.py).
"""

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb

from app.agents.scoring.feature_builder import build_feature_vector
from app.models.lead import Lead

logger = logging.getLogger("agent-scoring")

_MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"

_model: xgb.XGBRegressor | None = None
_config: dict | None = None

# Labels lisibles en français pour l'interface de validation
_FEATURE_LABELS_FR: dict[str, str] = {
    "ca_log1p":        "Chiffre d'affaires",
    "a_ca":            "CA disponible",
    "ca_n1_log1p":     "CA N-1",
    "a_ca_n1":         "CA N-1 disponible",
    "rn_signed_log1p": "Résultat net",
    "a_resultat_net":  "Résultat net disponible",
    "marge_nette":     "Marge nette",
    "croissance_ca":   "Croissance CA",
    "age_entreprise":  "Ancienneté entreprise",
    "has_email":       "Email disponible",
    "has_phone":       "Téléphone disponible",
    "has_website":     "Site web disponible",
    "has_dirigeant":   "Dirigeant identifié",
    "taille_code":     "Taille entreprise",
    "secteur_code":    "Secteur NAF",
    "ca_par_salarie_log1p": "CA par salarié",
}

# Regroupe les features corrélées (même signal, ex: CA) pour que le top 5 SHAP montre
# des facteurs distincts plutôt que plusieurs variantes du même facteur financier.
_FEATURE_GROUPS: dict[str, str] = {
    "ca_log1p":             "financier_ca",
    "a_ca":                 "financier_ca",
    "ca_par_salarie_log1p": "financier_ca",
    "rn_signed_log1p":      "financier_rn",
    "a_resultat_net":       "financier_rn",
    "marge_nette":          "financier_rn",
    "ca_n1_log1p":          "croissance",
    "a_ca_n1":              "croissance",
    "croissance_ca":        "croissance",
    "age_entreprise":       "anciennete",
    "taille_code":          "taille",
    "secteur_code":         "secteur",
    "has_email":            "contactabilite",
    "has_phone":            "contactabilite",
    "has_website":          "contactabilite",
    "has_dirigeant":        "contactabilite",
}


def _load() -> None:
    global _model, _config
    if _model is not None:
        return

    model_path = _MODELS_DIR / "xgboost_scoring.joblib"
    config_path = _MODELS_DIR / "feature_config.json"

    if not model_path.exists():
        raise FileNotFoundError(
            f"Modèle introuvable : {model_path}\n"
            "Lancez d'abord : python ml/train_scoring_model.py"
        )

    _model = joblib.load(model_path)
    _config = json.loads(config_path.read_text())
    logger.info("Modèle XGBoost (régression) chargé depuis %s", model_path)


def _prob_to_label(prob: float) -> str:
    if prob >= 0.75:
        return "CHAUD"
    if prob >= 0.50:
        return "TIEDE"
    if prob >= 0.30:
        return "FROID"
    return "HORS_CIBLE"


def _compute_shap(X: np.ndarray, feature_names: list[str]) -> str:
    """Calcule les contributions SHAP (pred_contribs) et retourne les 5 features les
    plus contributives, une seule par groupe sémantique (voir _FEATURE_GROUPS)."""
    booster = _model.get_booster()
    dmatrix = xgb.DMatrix(X, feature_names=feature_names)
    # contribs shape : (1, n_features + 1) — dernier élément = biais
    contribs = booster.predict(dmatrix, pred_contribs=True)
    feature_contribs = contribs[0, :-1]

    # Parcourt toutes les features par |contribution| décroissante, en ne
    # gardant que la première (donc la plus contributive) de chaque groupe.
    ranked_indices = np.argsort(np.abs(feature_contribs))[::-1]
    seen_groups: set[str] = set()
    top_indices: list[int] = []
    for i in ranked_indices:
        group = _FEATURE_GROUPS.get(feature_names[i], feature_names[i])
        if group in seen_groups:
            continue
        seen_groups.add(group)
        top_indices.append(int(i))
        if len(top_indices) == 5:
            break

    result = [
        {
            "feature":      feature_names[i],
            "label_fr":     _FEATURE_LABELS_FR.get(feature_names[i], feature_names[i]),
            "contribution": round(float(feature_contribs[i]), 4),
            "direction":    "positif" if feature_contribs[i] >= 0 else "négatif",
        }
        for i in top_indices
    ]
    return json.dumps(result, ensure_ascii=False)


def predict(lead: Lead) -> tuple[float, str, str | None]:
    """Retourne (score, label, shap_json) pour un lead."""
    _load()
    X = build_feature_vector(lead, _config)
    # clip : protège contre un léger dépassement de [0,1] sur des leads très extrêmes.
    prob = float(np.clip(_model.predict(X)[0], 0.0, 1.0))
    try:
        shap_json = _compute_shap(X, _config["feature_names"])
    except Exception as exc:
        logger.warning("SHAP non calculé pour %s : %s", lead.siret, exc)
        shap_json = None
    return round(prob, 4), _prob_to_label(prob), shap_json
