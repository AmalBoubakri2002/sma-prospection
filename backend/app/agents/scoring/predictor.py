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
_calibrator = None

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
    "taille_code":     "Taille entreprise",
    "secteur_code":    "Secteur NAF",
    "ca_par_salarie_log1p": "CA par salarié",
}

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
}


def _load() -> None:
    global _model, _config, _calibrator
    if _model is not None:
        return

    model_path = _MODELS_DIR / "xgboost_scoring.joblib"
    config_path = _MODELS_DIR / "feature_config.json"
    calibrator_path = _MODELS_DIR / "score_calibrator.joblib"

    if not model_path.exists():
        raise FileNotFoundError(
            f"Modèle introuvable : {model_path}\n"
            "Lancez d'abord : python ml/train_scoring_model.py"
        )

    _model = joblib.load(model_path)
    _config = json.loads(config_path.read_text())

    try:
        if calibrator_path.exists():
            _calibrator = joblib.load(calibrator_path)
            logger.info("Calibrateur isotonique chargé depuis %s", calibrator_path)
        else:
            _calibrator = None
            logger.warning(
                "Calibrateur introuvable (%s) — scores non calibrés (modèle non "
                "réentraîné depuis l'introduction de la calibration isotonique)",
                calibrator_path,
            )
    except Exception:
        _calibrator = None
        logger.exception(
            "Échec du chargement du calibrateur (%s) — scores non calibrés", calibrator_path
        )
    logger.info("Modèle XGBoost (régression) chargé depuis %s", model_path)


_MIN_CONTRIB_SHARE = 0.05


def _compute_shap(X: np.ndarray, feature_names: list[str]) -> str:
   
    booster = _model.get_booster()
    dmatrix = xgb.DMatrix(X, feature_names=feature_names)
    
    contribs = booster.predict(dmatrix, pred_contribs=True)
    feature_contribs = contribs[0, :-1]
    total_abs = float(np.abs(feature_contribs).sum())


    ranked_indices = np.argsort(np.abs(feature_contribs))[::-1]
    seen_groups: set[str] = set()
    top_indices: list[int] = []
    for i in ranked_indices:
        if total_abs > 0 and abs(feature_contribs[i]) / total_abs < _MIN_CONTRIB_SHARE:
            continue
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


def predict(lead: Lead) -> tuple[float, str | None]:
   
    _load()
    X = build_feature_vector(lead, _config)
    raw = float(np.clip(_model.predict(X)[0], 0.0, 1.0))
    prob = float(np.clip(_calibrator.predict([raw])[0], 0.0, 1.0)) if _calibrator is not None else raw
    try:
        shap_json = _compute_shap(X, _config["feature_names"])
    except Exception as exc:
        logger.warning("SHAP non calculé pour %s : %s", lead.siret, exc)
        shap_json = None
    return round(prob, 4), shap_json
