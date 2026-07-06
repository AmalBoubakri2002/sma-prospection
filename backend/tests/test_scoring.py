"""Tests unitaires pour l'agent Scoring — jusqu'ici zéro couverture alors que
c'est le composant où plusieurs bugs silencieux ont déjà été trouvés en prod
(fuite de label, CA=0 mal nettoyé, seuils Chaud/Tiède/Froid incohérents avec
l'arrondi d'affichage). Couvre :
  1. Les seuils de _prob_to_label (bornes exactes ">=")
  2. build_feature_vector avec données financières manquantes (imputation médiane)
  3. build_feature_vector avec données financières connues
  4. Non-régression train/inférence : build_feature_vector (app/) et
     build_features (ml/) doivent produire le même vecteur pour la même
     entreprise — un vecteur désynchronisé casse le modèle silencieusement
     (voir feature_spec.py, docstring de module).
"""

import math
from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.agents.scoring.feature_builder import build_feature_vector
from app.agents.scoring.feature_spec import FEATURE_NAMES, TAILLE_MIDPOINT, TAILLE_TO_CODE
from app.agents.scoring.predictor import _prob_to_label
from app.models.lead import Lead
from ml.train_scoring_model import build_features

FEATURE_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}


def _make_lead(**overrides) -> MagicMock:
    lead = MagicMock(spec=Lead)
    lead.siret = "12345678900014"
    lead.ca = None
    lead.ca_n1 = None
    lead.resultat_net = None
    lead.date_creation = None
    lead.taille_entreprise = None
    lead.secteur = None
    lead.email = None
    lead.telephone = None
    lead.site_web = None
    lead.prenom_dirigeant = None
    for k, v in overrides.items():
        setattr(lead, k, v)
    return lead


def _make_config(**median_overrides) -> dict:
    medians = {
        "ca": 1_000_000.0,
        "ca_n1": 1_000_000.0,
        "marge_nette": 0.05,
        "age_entreprise": 10.0,
        "secteur_categories": ["62", "70"],
    }
    medians.update(median_overrides)
    return {"medians": medians}


# ── _prob_to_label : bornes exactes ────────────────────────────────────────────

@pytest.mark.parametrize("prob,expected", [
    (0.0,    "HORS_CIBLE"),
    (0.2999, "HORS_CIBLE"),
    (0.3,    "FROID"),
    (0.4999, "FROID"),
    (0.5,    "TIEDE"),
    (0.7499, "TIEDE"),
    (0.75,   "CHAUD"),
    (1.0,    "CHAUD"),
])
def test_prob_to_label_thresholds(prob, expected):
    """Seuils ">=" : un score de 0.7499 doit rester TIEDE, pas CHAUD.

    Le front affiche Math.round(score*100) pour le pourcentage (choix produit
    assumé, voir LeadScoreBadge.tsx) alors que ce label est tranché sur le
    score non arrondi — un score de 0.7499 peut donc s'afficher "75%" à côté
    d'un badge "Tiède". Ce test fige au moins les bornes exactes côté backend,
    pour que ce léger décalage d'affichage reste le seul écart, sans dérive
    supplémentaire côté seuils.
    """
    assert _prob_to_label(prob) == expected


# ── build_feature_vector : données manquantes → imputation médiane, flags à 0 ──

def test_build_feature_vector_missing_financials_use_medians():
    lead = _make_lead()
    config = _make_config()
    medians = config["medians"]

    vec = build_feature_vector(lead, config)

    assert vec.shape == (1, len(FEATURE_NAMES))
    assert vec[0, FEATURE_INDEX["a_ca"]] == 0.0
    assert vec[0, FEATURE_INDEX["a_ca_n1"]] == 0.0
    assert vec[0, FEATURE_INDEX["a_resultat_net"]] == 0.0
    assert vec[0, FEATURE_INDEX["ca_log1p"]] == pytest.approx(math.log1p(medians["ca"]), rel=1e-5)
    assert vec[0, FEATURE_INDEX["ca_n1_log1p"]] == pytest.approx(math.log1p(medians["ca_n1"]), rel=1e-5)
    assert vec[0, FEATURE_INDEX["marge_nette"]] == pytest.approx(medians["marge_nette"], rel=1e-5)
    assert vec[0, FEATURE_INDEX["age_entreprise"]] == pytest.approx(medians["age_entreprise"], rel=1e-5)
    assert vec[0, FEATURE_INDEX["croissance_ca"]] == 0.0
    assert vec[0, FEATURE_INDEX["has_email"]] == 0.0
    assert vec[0, FEATURE_INDEX["has_phone"]] == 0.0
    assert vec[0, FEATURE_INDEX["has_website"]] == 0.0
    assert vec[0, FEATURE_INDEX["has_dirigeant"]] == 0.0
    assert vec[0, FEATURE_INDEX["taille_code"]] == 0.0  # "NN" (défaut) → TPE
    assert vec[0, FEATURE_INDEX["secteur_code"]] == -1.0  # secteur inconnu, hors catégories


def test_build_feature_vector_ca_exactly_zero_treated_as_missing():
    """clean_financial_value : ca=0 est un artefact de bug d'enrichissement
    (voir feature_spec.py), pas une vraie valeur — doit être imputé comme
    ca manquant, PAS comme ca confirmé nul."""
    lead = _make_lead(ca=0)
    config = _make_config()

    vec = build_feature_vector(lead, config)

    assert vec[0, FEATURE_INDEX["a_ca"]] == 0.0
    assert vec[0, FEATURE_INDEX["ca_log1p"]] == pytest.approx(math.log1p(config["medians"]["ca"]), rel=1e-5)


def test_build_feature_vector_resultat_net_exactly_zero_is_known_value():
    """Contrairement à ca=0, resultat_net=0 est une vraie valeur API (bilan à
    résultat net nul) — ne doit PAS être traité comme manquant."""
    lead = _make_lead(resultat_net=0)
    config = _make_config()

    vec = build_feature_vector(lead, config)

    assert vec[0, FEATURE_INDEX["a_resultat_net"]] == 1.0
    assert vec[0, FEATURE_INDEX["rn_signed_log1p"]] == 0.0


# ── build_feature_vector : données connues → transforms corrects, flags à 1 ────

def test_build_feature_vector_known_financials():
    lead = _make_lead(
        ca=5_000_000,
        ca_n1=4_000_000,
        resultat_net=300_000,
        date_creation=date(2015, 1, 1),
        taille_entreprise="31",
        secteur="6201Z",
        email="a@b.fr",
        telephone="0100000000",
        site_web="https://b.fr",
        prenom_dirigeant="Jean",
    )
    config = _make_config(secteur_categories=["62", "70"])

    vec = build_feature_vector(lead, config)

    assert vec[0, FEATURE_INDEX["a_ca"]] == 1.0
    assert vec[0, FEATURE_INDEX["a_ca_n1"]] == 1.0
    assert vec[0, FEATURE_INDEX["a_resultat_net"]] == 1.0
    assert vec[0, FEATURE_INDEX["ca_log1p"]] == pytest.approx(math.log1p(5_000_000), rel=1e-5)
    assert vec[0, FEATURE_INDEX["rn_signed_log1p"]] == pytest.approx(math.log1p(300_000), rel=1e-5)
    assert vec[0, FEATURE_INDEX["marge_nette"]] == pytest.approx(300_000 / 5_000_000, rel=1e-5)
    assert vec[0, FEATURE_INDEX["croissance_ca"]] == pytest.approx((5_000_000 - 4_000_000) / 4_000_000, rel=1e-5)
    assert vec[0, FEATURE_INDEX["taille_code"]] == TAILLE_TO_CODE["31"]
    assert vec[0, FEATURE_INDEX["secteur_code"]] == 0.0  # "62" est à l'index 0
    assert vec[0, FEATURE_INDEX["has_email"]] == 1.0
    assert vec[0, FEATURE_INDEX["has_phone"]] == 1.0
    assert vec[0, FEATURE_INDEX["has_website"]] == 1.0
    assert vec[0, FEATURE_INDEX["has_dirigeant"]] == 1.0


# ── Non-régression train/inférence ──────────────────────────────────────────────

def test_feature_vector_matches_training_build_features():
    """build_feature_vector (inférence, app/) et build_features (entraînement,
    ml/) partagent FEATURE_NAMES mais sont deux implémentations séparées (une
    par Lead ORM, une vectorisée pandas) — rien ne garantit mécaniquement
    qu'elles restent équivalentes terme à terme. Ce test construit la même
    entreprise des deux côtés et vérifie que les deux vecteurs sont identiques,
    pour détecter une désynchronisation future avant qu'elle ne casse le
    modèle en silence (voir feature_spec.py, docstring de module)."""
    age_years = (date.today() - date(2015, 1, 1)).days / 365.25
    medians = _make_config(secteur_categories=["62", "70"])["medians"]

    lead = _make_lead(
        ca=5_000_000,
        ca_n1=4_000_000,
        resultat_net=300_000,
        date_creation=date(2015, 1, 1),
        taille_entreprise="31",
        secteur="6201Z",
        email="a@b.fr",
        telephone="0100000000",
        site_web="https://b.fr",
        prenom_dirigeant="Jean",
    )
    vec_inference = build_feature_vector(lead, {"medians": medians})

    df = pd.DataFrame([{
        "ca": 5_000_000,
        "ca_n1": 4_000_000,
        "resultat_net": 300_000,
        "marge_nette": 300_000 / 5_000_000,
        "croissance_ca": (5_000_000 - 4_000_000) / 4_000_000,
        "age_entreprise": age_years,
        "taille_entreprise": "31",
        "secteur": "6201Z",
        "has_email": 1,
        "has_phone": 1,
        "has_website": 1,
        "has_dirigeant": 1,
    }])
    vec_train, _ = build_features(df, medians=dict(medians))

    np.testing.assert_allclose(vec_inference[0], vec_train[0], rtol=1e-4, atol=1e-4)


def test_feature_vector_matches_training_build_features_missing_data():
    """Même vérification que ci-dessus, mais pour une entreprise sans aucune
    donnée financière — le chemin d'imputation médiane est celui qui a
    justement causé la fuite de label corrigée le 2026-07-04."""
    medians = _make_config(secteur_categories=["62", "70"])["medians"]

    lead = _make_lead(taille_entreprise="NN", secteur=None)
    vec_inference = build_feature_vector(lead, {"medians": medians})

    df = pd.DataFrame([{
        "ca": np.nan,
        "ca_n1": np.nan,
        "resultat_net": np.nan,
        "marge_nette": np.nan,
        "croissance_ca": np.nan,
        "age_entreprise": np.nan,
        "taille_entreprise": "NN",
        "secteur": None,
        "has_email": 0,
        "has_phone": 0,
        "has_website": 0,
        "has_dirigeant": 0,
    }])
    vec_train, _ = build_features(df, medians=dict(medians))

    np.testing.assert_allclose(vec_inference[0], vec_train[0], rtol=1e-4, atol=1e-4)


# ── SHAP top 5 : une seule feature par groupe sémantique ────────────────────────

def test_compute_shap_dedupes_correlated_financial_features():
    """Sans regroupement, le top 5 SHAP pur peut afficher 4-5 variantes du même
    signal financier (ex: Résultat net + Marge nette + CA disponible + CA par
    salarié + Chiffre d'affaires en même temps, cas réel observé sur A J C
    Ingenierie) au lieu de facteurs réellement distincts. Une seule feature —
    la plus contributive — doit représenter chaque groupe."""
    import json

    import app.agents.scoring.predictor as predictor
    from app.agents.scoring.feature_spec import FEATURE_NAMES

    # Contributions construites pour reproduire le cas réel : 3 features du
    # groupe "financier_ca" et 3 du groupe "financier_rn" dominent toutes les
    # autres, mais ne doivent compter que pour 1 slot chacune dans le top 5.
    contribs_by_feature = {
        "ca_log1p": 0.05,
        "a_ca": 0.09,                  # la plus forte du groupe financier_ca
        "ca_n1_log1p": 0.0,
        "a_ca_n1": 0.0,
        "rn_signed_log1p": 0.20,       # la plus forte du groupe financier_rn
        "a_resultat_net": 0.15,
        "marge_nette": 0.10,
        "croissance_ca": 0.0,
        "age_entreprise": 0.08,
        "has_email": 0.02,
        "has_phone": 0.01,
        "has_website": 0.01,
        "has_dirigeant": 0.01,
        "taille_code": 0.07,
        "secteur_code": 0.06,
        "ca_par_salarie_log1p": 0.04,
    }
    contribs_row = np.array([contribs_by_feature[f] for f in FEATURE_NAMES] + [0.0])  # +biais

    booster = MagicMock()
    booster.predict.return_value = np.array([contribs_row])
    original_model = predictor._model
    predictor._model = MagicMock()
    predictor._model.get_booster.return_value = booster
    try:
        shap_json = predictor._compute_shap(np.zeros((1, len(FEATURE_NAMES))), FEATURE_NAMES)
    finally:
        predictor._model = original_model

    result = json.loads(shap_json)

    assert len(result) == 5
    groups = [predictor._FEATURE_GROUPS.get(r["feature"], r["feature"]) for r in result]
    assert len(groups) == len(set(groups)), f"groupes en double dans le top 5 : {groups}"
    # La feature la plus contributive de chaque groupe financier gagne le
    # slot, pas la première rencontrée dans FEATURE_NAMES.
    features = {r["feature"] for r in result}
    assert "rn_signed_log1p" in features  # gagne financier_rn (0.20 > 0.15 > 0.10)
    assert "a_resultat_net" not in features
    assert "marge_nette" not in features
    assert "a_ca" in features            # gagne financier_ca (0.09 > 0.05 > 0.04)
    assert "ca_log1p" not in features
    assert "ca_par_salarie_log1p" not in features
