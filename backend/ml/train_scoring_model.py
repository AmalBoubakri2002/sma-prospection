#!/usr/bin/env python3
"""Entraîne un XGBoost qui approxime une règle métier documentée (dataset_pipeline.py)
— PAS un prédicteur de conversion réelle : label_scoring est une fonction déterministe
des mêmes champs (ca, resultat_net, marge_nette, ...) utilisés ici comme features, donc
le modèle réapprend la formule qui a servi à fabriquer son propre label (fuite de label).
Aucun signal de conversion réel et indépendant n'existe aujourd'hui pour entraîner/valider
contre autre chose. Les métriques (RMSE, R², CV-5) mesurent la fidélité à la règle, pas
un pouvoir prédictif réel — à ne jamais citer comme preuve de "qualité prédictive" seule.

Régression sur score_continu, pas classification + calibration Platt : évite les scores
qui se figent en blocs quasi identiques quand les classes sont presque séparables.

Calibration isotonique post-hoc (2026-07-07) : la régularisation XGBoost (reg_alpha,
reg_lambda, max_depth=4) compresse systématiquement les deux queues de la distribution
vers le centre (constaté : le modèle ne prédit jamais au-delà de ~0.79 même quand
score_continu atteint 1.0 sur 7.8% des leads). Fittée sur des prédictions OUT-OF-FOLD
(CV 5-fold ci-dessous), jamais sur les prédictions du modèle final sur ses propres
données de train — sinon la calibration apprendrait aussi le bruit du train et perdrait
sa garantie de monotonie utile sur données neuves.

Usage: python train_scoring_model.py [--data dataset_scoring_real.csv] [--out-dir models/]
Outputs: models/xgboost_scoring.joblib, models/score_calibrator.joblib, models/feature_config.json
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    mean_squared_error,
    precision_recall_curve,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, train_test_split

# Constantes et encodages partagés avec l'inférence prod (source unique —
# voir app/agents/scoring/feature_spec.py pour le pourquoi).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.agents.scoring.feature_spec import (  # noqa: E402
    FEATURE_NAMES,
    MARGE_NETTE_CLIP,
    TAILLE_MIDPOINT,
    TAILLE_TO_CODE,
    naf_division,
)


# ── Feature engineering ────────────────────────────────────────────────────────

def _naf_division_series(secteur: pd.Series) -> pd.Series:
    """Version vectorisée de naf_division() — applique la même règle
    ('6201Z' → '62', défaut '00') à une colonne entière sans boucle Python."""
    s = secteur.fillna("").astype(str)
    two = s.str.slice(0, 2)
    valid = two.str.len().eq(2) & two.str.isdigit()
    return two.where(valid, "00")


def build_features(df: pd.DataFrame, medians: dict | None = None) -> tuple[np.ndarray, dict]:
    """Transforme le DataFrame brut en matrice de features pour XGBoost.

    Entièrement vectorisé (pandas/numpy colonne par colonne) — un .iterrows() devient
    le goulot d'étranglement dès que le dataset grossit.

    Returns:
        X        — matrice (n, len(FEATURE_NAMES))
        medians  — dict des médianes calculées sur df (à sauvegarder pour l'inférence)
    """
    # ca=0 traité comme manquant, pas resultat_net=0 qui est une vraie valeur
    # (défense en profondeur, voir feature_spec.clean_financial_value).
    df = df.copy()
    df["ca"] = df["ca"].replace(0, np.nan)

    if medians is None:
        ca_median = float(df["ca"].median())
        # ca_n1 est quasi-jamais disponible : retombe sur la médiane de `ca`
        # plutôt que de propager un NaN silencieux dans log1p à l'inférence.
        ca_n1_median = float(df["ca_n1"].dropna().median())
        if np.isnan(ca_n1_median):
            ca_n1_median = ca_median
        medians = {
            "ca":             ca_median,
            "ca_n1":          ca_n1_median,
            "marge_nette":    float(df["marge_nette"].dropna().median()),
            "age_entreprise": float(df["age_entreprise"].dropna().median()),
        }

    # Encodage secteur au niveau division NAF (2 chiffres) : liste triée →
    # index stable entre train et inférence, catégories bien représentées.
    if medians.get("secteur_categories") is None:
        cats = sorted({naf_division(s) for s in df["secteur"].dropna().unique()})
        medians["secteur_categories"] = cats
    secteur_index = {c: i for i, c in enumerate(medians["secteur_categories"])}

    # clip(lower=0) évite un log1p(NaN) sur des CA négatifs aberrants (erreurs de saisie source).
    a_ca = df["ca"].notna().astype(np.float32)
    ca = df["ca"].clip(lower=0).fillna(medians["ca"])
    ca_n1 = df["ca_n1"].clip(lower=0).fillna(medians["ca_n1"])
    a_ca_n1 = df["ca_n1"].notna().astype(np.float32)

    rn = df["resultat_net"]
    a_rn = rn.notna().astype(np.float32)
    rn_signed_log1p = (np.sign(rn) * np.log1p(rn.abs())).fillna(0.0)

    marge = df["marge_nette"].fillna(medians["marge_nette"]).clip(
        -MARGE_NETTE_CLIP, MARGE_NETTE_CLIP
    )
    croissance = df["croissance_ca"].fillna(0.0)
    age = df["age_entreprise"].fillna(medians["age_entreprise"])

    taille_str = df["taille_entreprise"].astype(str)
    taille_code = taille_str.map(TAILLE_TO_CODE).fillna(0)
    effectif = taille_str.map(TAILLE_MIDPOINT).fillna(TAILLE_MIDPOINT["NN"])
    ca_par_salarie = ca / effectif.clip(lower=1)

    secteur_div = _naf_division_series(df["secteur"])
    secteur_code = secteur_div.map(secteur_index).fillna(-1)

    X = np.column_stack([
        np.log1p(ca),
        a_ca,
        np.log1p(ca_n1),
        a_ca_n1,
        rn_signed_log1p,
        a_rn,
        marge,
        croissance,
        age,
        taille_code,
        secteur_code,
        np.log1p(ca_par_salarie),
    ]).astype(np.float32)

    return X, medians


# ── Évaluation ─────────────────────────────────────────────────────────────────

def _bar(value: float, width: int = 30, char: str = "█") -> str:
    filled = int(round(value * width))
    return char * filled + "░" * (width - filled)


def print_calibration_table(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> None:
    """
    Reliability diagram en mode texte, adapté régression.
    Principe : si le modèle approxime bien score_continu (règle heuristique,
    pas une vraie conversion — voir limite en tête de fichier), le score
    prédit moyen par décile doit être proche du score_continu réel moyen.
    """
    df_cal = pd.DataFrame({"pred": y_pred, "true": y_true})
    df_cal["decile"] = pd.qcut(df_cal["pred"], n_bins, labels=False, duplicates="drop")

    print(f"\n{'─'*72}")
    print(" Calibration (fidélité du score prédit à score_continu)")
    print(f"{'─'*72}")
    print(f" {'Décile':>6}  {'Score prédit':>13}  {'Score réel':>10}  {'Delta':>7}  {'Verdict':>7}  Barre")
    print(f"{'─'*72}")

    for dec in sorted(df_cal["decile"].unique()):
        grp = df_cal[df_cal["decile"] == dec]
        mean_pred = grp["pred"].mean()
        mean_true = grp["true"].mean()
        delta = mean_true - mean_pred
        ok = "✓" if abs(delta) < 0.08 else ("⚠" if abs(delta) < 0.15 else "✗")
        bar = _bar(mean_true)
        print(f"   {int(dec)+1:>4}   {mean_pred:>13.3f}  {mean_true:>10.3f}  {delta:>+7.3f}  {ok:>7}  {bar}")

    print(f"{'─'*72}")
    print("  ✓ delta < 8%  |  ⚠ 8–15%  |  ✗ > 15%\n")


def print_score_distribution(y_pred: np.ndarray, n_bins: int = 10) -> None:
    """
    Histogramme des scores prédits sur tout le jeu de test — montre que le
    score s'étale sur un continuum plutôt que de se figer en quelques blocs
    identiques (symptôme corrigé le 2026-07-03, voir docstring de module).
    """
    bins = np.linspace(0, 1, n_bins + 1)
    counts, _ = np.histogram(y_pred, bins)
    max_count = max(counts) if len(counts) else 1

    print(f"\n{'─'*72}")
    print(" Distribution des scores prédits (jeu de test)")
    print(f"{'─'*72}")
    print(f" {'Intervalle':>12}  {'Nb leads':>8}  Barre")
    print(f"{'─'*72}")

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        c = int(counts[i])
        bar = "█" * int(c / max_count * 40) if max_count else ""
        print(f"  [{lo:.1f}–{hi:.1f}]  {c:>8,}  {bar}")

    n_unique = len(np.unique(np.round(y_pred, 3)))
    print(f"{'─'*72}")
    print(f"  Valeurs distinctes (arrondi 3 déc.) : {n_unique} / {len(y_pred)}")
    print("  Idéal : répartition étalée sur plusieurs intervalles, pas 1-2 pics isolés\n")


def print_operating_points(y_true: np.ndarray, y_prob: np.ndarray) -> None:
    """
    Précision et rappel à différents seuils, calculés contre le label
    HEURISTIQUE (pas une vraie conversion — voir limite en tête de fichier).
    Utile pour calibrer le score_minimum d'une campagne à la sélectivité
    voulue vis-à-vis de la règle, pas pour estimer un taux de conversion réel.
    """
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)

    print(f"\n{'─'*60}")
    print(" Points d'opération (à quel seuil couper ?)")
    print(f"{'─'*60}")
    print(f" {'Seuil':>8}  {'% leads sélectionnés':>18}  {'Précision':>10}  {'Rappel':>8}")
    print(f"{'─'*60}")

    for target_thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        idx = np.searchsorted(thresholds, target_thresh)
        if idx >= len(prec):
            continue
        pct_contacted = float((y_prob >= target_thresh).mean())
        print(
            f"  ≥ {target_thresh:.1f}   {pct_contacted:>17.1%}  {prec[idx]:>9.1%}  {rec[idx]:>7.1%}"
        )
    print(f"{'─'*60}")
    print(
        "  Précision = parmi les leads sélectionnés, % conformes à la règle\n"
        "  Rappel    = parmi tous les leads conformes à la règle, % sélectionnés\n"
        "  (contre le label heuristique — pas une vraie conversion)\n"
    )


def print_feature_importance(model: xgb.XGBRegressor) -> None:
    scores = model.feature_importances_
    ranked = sorted(zip(FEATURE_NAMES, scores), key=lambda x: x[1], reverse=True)
    max_score = ranked[0][1]

    print(f"\n{'─'*60}")
    print(" Importance des features (gain normalisé)")
    print(f"{'─'*60}")
    for name, score in ranked:
        bar = _bar(score / max_score, width=25)
        flag = " ⚠ dominante" if score > 0.25 else ""
        print(f"  {name:<22} {score:>6.1%}  {bar}{flag}")
    print(f"{'─'*60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main(data_path: str | None = None, out_dir: str | None = None) -> None:
    if data_path is None:
        data_path = str(Path(__file__).parent / "dataset_scoring_real.csv")
    if out_dir is None:
        out_dir = str(Path(__file__).parent.parent / "models")
    out = Path(out_dir)
    out.mkdir(exist_ok=True)

    # ── Chargement ───────────────────────────────────────────────────────────
    print(f"\nChargement : {data_path}")
    df = pd.read_csv(data_path)
    if "score_continu" not in df.columns:
        raise SystemExit(
            "Colonne 'score_continu' absente du CSV — régénérez le dataset "
            "avec la version 2026-07-03+ de dataset_pipeline.py "
            "(ancien format : label_scoring binaire uniquement)."
        )
    print(f"  {len(df):,} leads — score_continu moyen : {df['score_continu'].mean():.3f}")

    # ── Feature matrix ────────────────────────────────────────────────────────
    print("Construction des features…")
    X, medians = build_features(df)
    y = df["score_continu"].values.astype(np.float32)
    y_label = df["label_scoring"].values.astype(int)  # indicatif seulement (reporting)

    # ── Split 80/20 (pas de stratification : cible continue) ─────────────────
    X_train, X_test, y_train, y_test, ylabel_train, ylabel_test = train_test_split(
        X, y, y_label, test_size=0.20, random_state=42
    )
    # 10% du train → early stopping interne à XGBoost
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train, y_train, test_size=0.10, random_state=42
    )
    print(f"  Train: {len(X_tr):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")

    # ── Entraînement ─────────────────────────────────────────────────────────
    print("\nEntraînement XGBoost (régression)…")
    model = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="reg:squarederror",
        eval_metric="rmse",
        early_stopping_rounds=30,
        random_state=42,
        tree_method="hist",
        # n_jobs=1 : élimine la non-déterminisme du multi-threading sur "hist" (coût négligeable ici).
        n_jobs=1,
        verbosity=0,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    best_n = model.best_iteration + 1
    print(f"  Meilleur n_estimators : {best_n} (early stopping)")

    # ── Cross-validation (stabilité) ─────────────────────────────────────────
    print("\nCross-validation 5 folds…")
    cv_model = xgb.XGBRegressor(
        n_estimators=best_n,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="reg:squarederror",
        random_state=42,
        tree_method="hist",
        n_jobs=1,  # déterminisme — voir commentaire sur le modèle principal ci-dessus
        verbosity=0,
    )
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_rmses = []
    oof_pred = np.zeros_like(y_train)
    for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train), 1):
        cv_model.fit(X_train[tr_idx], y_train[tr_idx], verbose=False)
        fold_pred = cv_model.predict(X_train[val_idx])
        oof_pred[val_idx] = fold_pred
        rmse = float(np.sqrt(mean_squared_error(y_train[val_idx], fold_pred)))
        cv_rmses.append(rmse)
        print(f"  Fold {fold} : RMSE = {rmse:.4f}")

    # ── Calibration isotonique ────────────────────────────────────────────────
    # oof_pred couvre tout X_train avec des prédictions jamais vues par le modèle
    # qui les a produites (chaque fold prédit sur les données exclues de son propre
    # entraînement) — condition nécessaire pour que la calibration corrige le vrai
    # biais de généralisation du modèle plutôt que du simple bruit mémorisé.
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(oof_pred, y_train)

    # ── Évaluation finale sur test ────────────────────────────────────────────
    y_pred_raw = np.clip(model.predict(X_test), 0.0, 1.0)
    y_pred = np.clip(calibrator.predict(y_pred_raw), 0.0, 1.0)
    rmse_test_raw = float(np.sqrt(mean_squared_error(y_test, y_pred_raw)))
    rmse_test = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2_test = float(r2_score(y_test, y_pred))
    # AUC/AP indicatifs : reprennent label_scoring (seuil binaire) juste pour
    # vérifier que le score prédit continue à bien ordonner les leads que la
    # règle aurait qualifiés — pas la cible d'entraînement.
    auc_test = roc_auc_score(ylabel_test, y_pred)
    ap_test = average_precision_score(ylabel_test, y_pred)

    print(f"\n{'═'*60}")
    print("  FIDÉLITÉ À LA RÈGLE — jeu de test (20% holdout)")
    print("  ⚠ Mesure la fidélité à la règle heuristique de")
    print("    dataset_pipeline.py, PAS un pouvoir prédictif sur une")
    print("    vraie conversion (label et features partagent les mêmes")
    print("    ingrédients — voir limite documentée en tête de ce fichier).")
    print(f"{'═'*60}")
    print(f"  RMSE (fidélité, brut)      : {rmse_test_raw:.4f}")
    print(f"  RMSE (fidélité, calibré)   : {rmse_test:.4f}")
    print(f"  R² (calibré)               : {r2_test:.4f}")
    print(f"  CV-5 RMSE (fidélité) : {np.mean(cv_rmses):.4f} ± {np.std(cv_rmses):.4f}  {'✓ stable' if np.std(cv_rmses) < 0.01 else '⚠ instable'}")
    print(f"  AUC-ROC (indicatif, vs label_scoring seuillé) : {auc_test:.4f}")
    print(f"  Average Precision (indicatif)                 : {ap_test:.4f}")
    print(f"  Arbres utilisés      : {best_n}")
    print(f"  Score prédit — min/max (brut)    : {y_pred_raw.min():.3f} / {y_pred_raw.max():.3f}")
    print(f"  Score prédit — min/max (calibré) : {y_pred.min():.3f} / {y_pred.max():.3f}")
    print(f"{'═'*60}")

    print_calibration_table(y_test, y_pred)
    print_score_distribution(y_pred)
    print_operating_points(ylabel_test, y_pred)
    print_feature_importance(model)

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    model_path = out / "xgboost_scoring.joblib"
    joblib.dump(model, model_path)

    calibrator_path = out / "score_calibrator.joblib"
    joblib.dump(calibrator, calibrator_path)

    config = {
        "feature_names": FEATURE_NAMES,
        "medians": medians,
        "best_n_estimators": best_n,
        "metrics": {
            "caveat": (
                "Ces métriques mesurent la fidélité du modèle à la règle "
                "heuristique de ml/dataset_pipeline.py::_compute_raw_score "
                "(cible = fonction déterministe + bruit des mêmes champs que "
                "les features d'entrée), PAS un pouvoir prédictif sur une "
                "vraie conversion commerciale. Voir limite méthodologique "
                "documentée en tête de ml/train_scoring_model.py."
            ),
            "rmse_test_raw": round(rmse_test_raw, 4),
            "rmse_test": round(rmse_test, 4),
            "r2_test": round(r2_test, 4),
            "cv5_rmse_mean": round(float(np.mean(cv_rmses)), 4),
            "cv5_rmse_std": round(float(np.std(cv_rmses)), 4),
            "auc_test_vs_label_scoring": round(float(auc_test), 4),
            "average_precision_test_vs_label_scoring": round(float(ap_test), 4),
            "score_pred_range_raw": [round(float(y_pred_raw.min()), 3), round(float(y_pred_raw.max()), 3)],
            "score_pred_range_calibrated": [round(float(y_pred.min()), 3), round(float(y_pred.max()), 3)],
        },
    }
    config_path = out / "feature_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

    print(f"Modèle sauvegardé      : {model_path.resolve()}")
    print(f"Calibrateur sauvegardé : {calibrator_path.resolve()}")
    print(f"Config sauvegardée     : {config_path.resolve()}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None, help="CSV d'entrée (défaut: ml/dataset_scoring_real.csv)")
    parser.add_argument("--out-dir", default=None, help="Dossier artefacts (défaut: models/)")
    args = parser.parse_args()
    main(data_path=args.data, out_dir=args.out_dir)
