#!/usr/bin/env python3
"""
Pipeline de génération du dataset de scoring B2B — 3 étapes, une par sous-commande.

  generate  → échantillonnage stratifié du stock SIRENE + enrichissement API
              (recherche-entreprises, INPI). Produit le CSV de base.
  patch     → complète après-coup les champs encore manquants d'un CSV existant
              (nouveau re-appel API + scraping DuckDuckGo/homepage optionnel).
  impute    → impute has_email/has_phone/has_website par tirage de Bernoulli
              calibré par taille d'entreprise, puis supprime les colonnes
              brutes (email/telephone/site_web), vides à 100% à ce stade.

Ordre d'exécution habituel : generate → patch (optionnel) → impute → train_scoring_model.py

Usage (depuis la racine du repo) :
    python backend/ml/dataset_pipeline.py generate \
        --sirene backend/ml/data/StockEtablissement_utf8.csv --n 20000
    python backend/ml/dataset_pipeline.py patch --csv backend/ml/dataset_scoring_real.csv \
        --scrape-web
    python backend/ml/dataset_pipeline.py impute --csv backend/ml/dataset_scoring_real.csv

Les 3 étapes vivent dans un seul fichier (regroupées le 2026-07-04) car `patch`
et `impute` dépendaient déjà de fonctions de `generate` (`_add_derived_features`,
`_add_label`) via un import inter-scripts fragile (`sys.path.insert` + import
d'un module frère) — ce n'était en pratique jamais qu'un seul pipeline.
"""

import argparse
import asyncio
import json
import logging
import math
import random
import sys
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

# ── Path setup — allow running from repo root or from backend/ ─────────────────
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
sys.path.insert(0, str(_BACKEND))

from app.agents.enrichissement.email_scraper import scrape_email_from_homepage  # noqa: E402
from app.agents.enrichissement.inpi import InpiError, get_finances_from_siren  # noqa: E402
from app.agents.enrichissement.phone_scraper import scrape_phone_from_homepage  # noqa: E402
from app.agents.enrichissement.recherche_entreprises import (  # noqa: E402
    RechercheEntreprisesClient,
    RechercheEntreprisesError,
    extract_contact_info,
    extract_dirigeant_principal,
)
from app.agents.enrichissement.shared import (  # noqa: E402
    apply_inpi_fallback,
    compute_score_exploitabilite,
)
from app.agents.enrichissement.web_search import find_company_website  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dataset-pipeline")


# ═══════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 : GENERATE — échantillonnage SIRENE + enrichissement API
# ═══════════════════════════════════════════════════════════════════════════

TODAY = date(2026, 6, 21)

# ── Barème de score_continu (règle métier, 2026-07-07) ──────────────────────
# Remplace l'ancien barème /7 (rentabilité + marge + taille + âge + CA, avec
# rampes continues) par un barème /100 en 3 blocs fournis par l'équipe métier :
# santé financière (50) + maturité (30) + capacité économique (20).
# taille_entreprise ne fait plus partie du barème (contrairement à avant) —
# elle reste en revanche une feature du modèle XGBoost (feature_spec.py),
# donc le recouvrement label/features est réduit par rapport à l'ancien barème,
# pas aggravé.

# Résultat net — 30 pts. Corrigé le 2026-07-07 (suite) : la version précédente
# (rentable=30 / équilibre=15 / inconnu=15 / déficit=0, palier dur) traitait un
# déficit de -10k€ EXACTEMENT comme un déficit de -10M€ — perte d'information
# jugée trop brutale pour un modèle ML. Remplacé par un barème sur le ratio
# resultat_net/ca (ampleur du déficit relative à la taille de l'entreprise,
# pas la valeur absolue) : ratio>0→30, [-2%,0%]→15, [-5%,-2%[→10,
# [-10%,-5%[→5, <-10%→0.
RN_RATIO_POINTS_POSITIVE = 30.0
RN_RATIO_POINTS_FLOOR = 0.0     # ratio < -10%
RN_POINTS_UNKNOWN = 15.0        # ni ratio ni resultat_net disponibles (crédit neutre)

# Repéré le 2026-07-07 (suite) sur données réelles (Neo9/Reeliant/Expertease
# Partners, RN respectivement +550k€/+624k€/0€, tous scorés identiquement à
# 15 pts) : quand `ca` manque (17.2% des leads du dataset ont ce profil), le
# ratio RN/CA est incalculable et le RN connu était totalement ignoré — un
# lead confirmé à +624k€ de résultat net traité EXACTEMENT comme un lead dont
# on ne sait rien. Fallback : si le ratio est incalculable mais resultat_net
# est connu, petit ajustement autour du crédit neutre basé sur le seul signe
# (pas l'ampleur, non observable sans CA) — pour ne pas perdre un signal
# disponible sans sur-interpréter une magnitude qu'on ne peut pas mesurer.
RN_SIGN_FALLBACK_BONUS = 5.0

# Marge nette — 20 pts. Corrigé le 2026-07-07 (suite) : remplace les paliers
# durs par une rampe linéaire continue (barème fourni) — score_marge =
# clamp((marge_nette / MARGE_RAMP_CEILING) * 20, 0, 20). Marge inconnue :
# crédit neutre (non spécifié par le barème fourni, choix cohérent avec le
# traitement du résultat net ci-dessus).
MARGE_RAMP_CEILING = 0.20
MARGE_POINTS_MAX = 20.0
MARGE_POINTS_UNKNOWN = 10.0

# Maturité — 30 pts, basé uniquement sur age_entreprise (paliers durs fournis
# tels quels). Le barème fourni ne distingue pas "jeune (<2 ans)" de "âge
# inconnu" — les deux tombent dans le même palier bas (5 pts), à la différence
# du traitement RN/CA ci-dessus/dessous. Choix délibéré de suivre le barème
# littéralement plutôt que d'improviser un crédit neutre non spécifié : l'âge
# vient de la date de création SIRENE, quasi toujours disponible en pratique.
AGE_POINTS_CORE = 30.0        # 5 ≤ âge ≤ 20 ans
AGE_POINTS_YOUNG = 20.0       # 2 ≤ âge < 5 ans
AGE_POINTS_OLD = 15.0         # âge > 20 ans
AGE_POINTS_LOW = 5.0          # âge < 2 ans, OU âge inconnu (voir note ci-dessus)

# Capacité économique — 20 pts, échelle log entre ces deux bornes (barème
# fourni). CA inconnu : crédit neutre (milieu de barème), même logique que
# RN inconnu — absence de donnée ≠ mauvaise capacité (non spécifié par le
# barème fourni, choix cohérent avec le reste du fichier).
CA_LOG_LOW = 100_000.0        # en dessous : 0 pt
CA_LOG_HIGH = 10_000_000.0    # à partir de : 20 pts pleins
CA_POINTS_MAX = 20.0
CA_POINTS_UNKNOWN = 10.0

TAILLE_SAMPLE_WEIGHTS: dict[str, float] = {
    "NN": 0.04, "00": 0.02, "01": 0.08, "02": 0.08, "03": 0.08,
    "11": 0.10, "12": 0.12,
    "21": 0.14, "22": 0.12,
    "31": 0.06, "32": 0.06,
    "41": 0.04, "42": 0.02,
    "51": 0.02, "52": 0.01, "53": 0.01,
}

# NAF divisions (2-char prefix) used for stratification — only B2B-relevant
NAF_STRATA = {
    "10", "13", "14", "15", "16", "17", "18", "20", "21", "22", "23",
    "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
    "41", "42", "43",
    "45", "46", "47",
    "49", "50", "51", "52", "53",
    "58", "59", "60", "61", "62", "63",
    "64", "65", "66",
    "68", "69", "70", "71", "72", "73", "74", "75",
    "77", "78", "79", "80", "81", "82",
}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _normalize_naf(code: str | None) -> str | None:
    """'47.11B' → '4711B', handles both INSEE formats."""
    if not code:
        return None
    return code.replace(".", "").strip().upper()


def _build_address(row: pd.Series) -> str | None:
    parts = []
    num = str(row.get("numeroVoieEtablissement") or "").strip()
    typ = str(row.get("typeVoieEtablissement") or "").strip()
    lib = str(row.get("libelleVoieEtablissement") or "").strip()
    cp = str(row.get("codePostalEtablissement") or "").strip()
    city = str(row.get("libelleCommuneEtablissement") or "").strip().title()
    if num and num != "nan":
        parts.append(num)
    if typ and typ != "nan":
        parts.append(typ)
    if lib and lib != "nan":
        parts.append(lib)
    street = " ".join(parts) if parts else None
    if cp and city and cp != "nan" and city != "Nan":
        loc = f"{cp} {city}"
    else:
        loc = None
    if street and loc:
        return f"{street}, {loc}"
    return loc or street


def load_sirene_sample(
    sirene_csv: str | Path,
    n_target: int,
    seed: int = 42,
    chunk_size: int = 200_000,
) -> pd.DataFrame:

    sirene_csv = Path(sirene_csv)
    if not sirene_csv.exists():
        raise FileNotFoundError(
            f"Fichier SIRENE introuvable : {sirene_csv}\n"
            "Téléchargez StockEtablissement_utf8.zip depuis :\n"
            "https://www.data.gouv.fr/fr/datasets/"
            "base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/"
        )

    log.info("Lecture du stock SIRENE par chunks de %d lignes…", chunk_size)

    needed_cols = [
        "siret", "siren",
        "etatAdministratifEtablissement",
        "statutDiffusionEtablissement",
        "trancheEffectifsEtablissement",
        "activitePrincipaleEtablissement",
        "dateCreationEtablissement",
        "numeroVoieEtablissement",
        "typeVoieEtablissement",
        "libelleVoieEtablissement",
        "codePostalEtablissement",
        "libelleCommuneEtablissement",
        "denominationUsuelleEtablissement",
        "etablissementSiege",
    ]

    strata: dict[str, list[dict]] = {}
    total_read = 0

    reader = pd.read_csv(
        sirene_csv,
        usecols=lambda c: c in needed_cols,
        dtype=str,
        chunksize=chunk_size,
        low_memory=False,
    )

    for chunk in reader:
        total_read += len(chunk)
        if total_read % 1_000_000 == 0:
            log.info("  … %d M lignes lues", total_read // 1_000_000)

        # Filter: active, diffusable, metropolitan France (5-digit CP), siège
        mask = (
            (chunk.get("etatAdministratifEtablissement", pd.Series()) == "A") &
            (chunk.get("statutDiffusionEtablissement", pd.Series()) != "P") &
            (chunk.get("etablissementSiege", pd.Series()) == "true")
        )
        cp = chunk.get("codePostalEtablissement", pd.Series())
        mask &= cp.str.match(r"^\d{5}$", na=False)

        active = chunk[mask].copy()
        if active.empty:
            continue

        active["naf_norm"] = active["activitePrincipaleEtablissement"].apply(_normalize_naf)
        active["naf_div"] = active["naf_norm"].str[:2]
        active = active[active["naf_div"].isin(NAF_STRATA)]

        taille_col = active.get("trancheEffectifsEtablissement", pd.Series())
        active["taille"] = taille_col.fillna("NN").replace({"": "NN"})

        for _, row in active.iterrows():
            taille = str(row["taille"])
            naf_div = str(row.get("naf_div", ""))
            key = f"{taille}|{naf_div}"
            if key not in strata:
                strata[key] = []
            strata[key].append(row.to_dict())

    log.info("Lignes totales lues : %d M", total_read // 1_000_000)
    log.info("Strates construites : %d", len(strata))

    rng = random.Random(seed)
    sampled_rows: list[dict] = []

    total_weight = sum(
        TAILLE_SAMPLE_WEIGHTS.get(k.split("|")[0], 0.01)
        for k in strata.keys()
    )

    remaining: dict[str, list[dict]] = {}
    for key, rows in strata.items():
        taille = key.split("|")[0]
        w = TAILLE_SAMPLE_WEIGHTS.get(taille, 0.01)
        quota = max(1, round(n_target * w / total_weight))
        shuffled = rows[:]
        rng.shuffle(shuffled)
        sampled_rows.extend(shuffled[:quota])
        leftover = shuffled[quota:]
        if leftover:
            remaining[key] = leftover

    log.info("Après allocation initiale par strate : %d lignes (cible %d)",
              len(sampled_rows), n_target)

    # Réallocation itérative du déficit vers les strates encore disponibles
    deficit = n_target - len(sampled_rows)
    round_n = 0
    while deficit > 0 and remaining:
        round_n += 1
        total_remaining = sum(len(v) for v in remaining.values())
        if total_remaining == 0:
            break
        taken_this_round = 0
        for key in list(remaining.keys()):
            rows = remaining[key]
            share = max(1, round(deficit * len(rows) / total_remaining))
            take, leftover = rows[:share], rows[share:]
            sampled_rows.extend(take)
            taken_this_round += len(take)
            if leftover:
                remaining[key] = leftover
            else:
                del remaining[key]
        deficit = n_target - len(sampled_rows)
        if taken_this_round == 0:
            break
    log.info("Après réallocation (%d tour(s)) : %d SIRETs (cible %d, capacité "
              "totale disponible avant réallocation atteinte si < cible)",
              round_n, len(sampled_rows), n_target)

    if len(sampled_rows) > n_target:
        sampled_rows = rng.sample(sampled_rows, n_target)

    df = pd.DataFrame(sampled_rows)
    n_before_dedup = len(df)
    df = df.drop_duplicates(subset=["siret"]).reset_index(drop=True)
    if len(df) != n_before_dedup:
        log.warning("Doublons siret inattendus supprimés : %d", n_before_dedup - len(df))
    log.info("Échantillon final : %d SIRETs uniques", len(df))
    return df


# ── Local JSON cache ───────────────────────────────────────────────────────────

class SiretCache:
    """Persist enrichment results to disk so interrupted runs resume cheaply."""

    def __init__(self, cache_path: Path):
        self._path = cache_path
        self._data: dict[str, dict] = {}
        if cache_path.exists():
            try:
                self._data = json.loads(cache_path.read_text())
                log.info("Cache chargé : %d SIRETs", len(self._data))
            except json.JSONDecodeError:
                log.warning("Cache corrompu, ignoré")

    def get(self, siret: str) -> dict | None:
        return self._data.get(siret)

    def set(self, siret: str, value: dict) -> None:
        self._data[siret] = value

    def flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, default=str))


# ── Async enrichment ───────────────────────────────────────────────────────────

async def _enrich_one_siret(
    siret: str,
    semaphore: asyncio.Semaphore,
    cache: SiretCache,
) -> dict:
    """Enrichit un SIRET via recherche-entreprises puis INPI en fallback.

    Mirrors app/agents/enrichissement/agent.py:_enrich_one but without DB
    dependencies — partage sa logique de fallback INPI et de score d'intention
    via app.agents.enrichissement.shared (source unique, voir ce module).
    """
    cached = cache.get(siret)
    if cached is not None:
        return cached

    fields: dict = {}

    async with semaphore:
        # Source 1: recherche-entreprises.api.gouv.fr
        try:
            client = RechercheEntreprisesClient()
            result = await client.get_by_siret(siret)
            if result:
                fields.update(extract_dirigeant_principal(result))
                fields.update(extract_contact_info(result))
        except (RechercheEntreprisesError, httpx.HTTPError) as exc:
            log.debug("recherche-entreprises %s : %s", siret, exc)

        # Small courtesy delay regardless of result
        await asyncio.sleep(0.2)

        # Source 2: INPI — fallback for ca_n1 and missing CA/résultat_net
        siren = siret[:9]
        try:
            inpi = await get_finances_from_siren(siren)
            apply_inpi_fallback(fields, inpi)
        except (InpiError, httpx.HTTPError) as exc:
            log.debug("INPI %s : %s", siren, exc)

    fields["score_exploitabilite"] = compute_score_exploitabilite(fields)
    cache.set(siret, fields)
    return fields


async def enrich_all(
    sirets: list[str],
    cache: SiretCache,
    concurrency: int = 5,
    cache_flush_every: int = 200,
) -> list[dict]:
    """Enrich all SIRETs with bounded concurrency, flushing cache periodically."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict] = [{}] * len(sirets)
    done_count = 0

    async def worker(idx: int, siret: str) -> None:
        nonlocal done_count
        results[idx] = await _enrich_one_siret(siret, semaphore, cache)
        done_count += 1
        if done_count % cache_flush_every == 0:
            cache.flush()
            log.info("  %d / %d SIRETs enrichis", done_count, len(sirets))

    await asyncio.gather(*(worker(i, s) for i, s in enumerate(sirets)))
    cache.flush()
    return results


def _add_derived_features(df: pd.DataFrame) -> pd.DataFrame:

    df["ca"] = df["ca"].replace(0, np.nan)

    date_creation = pd.to_datetime(df["date_creation"], errors="coerce")
    age_days = (pd.Timestamp(TODAY) - date_creation).dt.days
    df["age_entreprise"] = (age_days / 365.25).round(2)

    ca_n1_valid = df["ca_n1"].notna() & (df["ca_n1"] > 0) & df["ca"].notna()
    df["croissance_ca"] = ((df["ca"] - df["ca_n1"]) / df["ca_n1"]).round(4).where(ca_n1_valid)

    marge_valid = df["resultat_net"].notna() & df["ca"].notna() & (df["ca"] > 0)
    df["marge_nette"] = (df["resultat_net"] / df["ca"]).round(4).where(marge_valid)

    df["has_email"] = df["email"].notna().astype(int)
    df["has_phone"] = df["telephone"].notna().astype(int)
    df["has_website"] = df["site_web"].notna().astype(int)
    df["has_dirigeant"] = df["prenom_dirigeant"].notna().astype(int)
    return df


# ── Label (documented heuristic, see module docstring) ────────────────────────

def _compute_raw_score(df: pd.DataFrame) -> np.ndarray:
    """Score /100 normalisé en [0, 1] — voir limite de fuite de label en tête
    de fichier : ces mêmes champs redeviennent des features d'entraînement.

    Remplace le 2026-07-07 l'ancien barème /7 (rampes continues, taille
    incluse) par un barème /100 fourni par l'équipe métier, en 3 blocs
    indépendants :
      1. Santé financière (50 pts) = résultat net (30) + marge nette (20)
      2. Maturité (30 pts)         = âge de l'entreprise seul
      3. Capacité économique (20 pts) = CA, échelle logarithmique

    N'inclut volontairement PAS has_email/has_phone/has_website/has_dirigeant
    ni score_exploitabilite (voir shared.compute_score_exploitabilite) : ce
    sont des signaux de "avons-nous réussi à enrichir/contacter ce lead", pas
    de "ce lead est-il une bonne cible commerciale". Ni taille_entreprise,
    contrairement à l'ancien barème — elle reste une feature du modèle
    XGBoost (feature_spec.py) sans plus faire partie du label, ce qui réduit
    le recouvrement label/features par rapport à l'ancien barème.

    Résultat net et marge nette (2026-07-07, suite) : notées sur des fonctions
    graduées de l'ampleur relative (ratio resultat_net/ca), pas des paliers
    durs sur le signe brut — un déficit de -10k€ et un déficit de -10M€
    n'obtiennent plus le même score, seule leur ampleur relative au CA compte.
    Maturité/capacité restent en paliers durs (barème fourni tel quel).

    Fallback signe seul (2026-07-07, suite) : quand `ca` manque, le ratio est
    incalculable et resultat_net connu était ignoré (crédit neutre, comme
    "totalement inconnu") — voir RN_SIGN_FALLBACK_BONUS en tête de fichier.
    Ne s'applique qu'à resultat_net : marge_nette est par définition
    resultat_net/ca, sans CA il n'y a rien à dégrader même par le signe.
    """
    # ratio = resultat_net / ca (= marge_nette, déjà calculé par
    # _add_derived_features — NaN si ca ou resultat_net manquant).
    ratio = df["marge_nette"]
    ratio_known = ratio.notna()
    # >0%->30, [-2%,0%]->15, [-5%,-2%[->10, [-10%,-5%[->5, <-10%->0.
    score_rn_ratio = np.select(
        [ratio > 0, ratio >= -0.02, ratio >= -0.05, ratio >= -0.10],
        [RN_RATIO_POINTS_POSITIVE, 15.0, 10.0, 5.0],
        default=RN_RATIO_POINTS_FLOOR,
    )
    # Ratio incalculable (ca manquant) : replie sur le signe de resultat_net
    # seul quand il est connu (+/-5 pts autour du neutre), sinon neutre pur.
    rn = df["resultat_net"]
    score_rn_sign_fallback = np.select(
        [rn > 0, rn < 0],
        [RN_POINTS_UNKNOWN + RN_SIGN_FALLBACK_BONUS, RN_POINTS_UNKNOWN - RN_SIGN_FALLBACK_BONUS],
        default=RN_POINTS_UNKNOWN,
    )
    score_rn = np.where(ratio_known, score_rn_ratio, score_rn_sign_fallback)

    # Rampe linéaire continue : clamp((marge/MARGE_RAMP_CEILING)*20, 0, 20).
    # Marge inconnue -> crédit neutre (pas de fallback signe, voir docstring).
    marge_scaled = (ratio / MARGE_RAMP_CEILING * MARGE_POINTS_MAX).clip(
        lower=0.0, upper=MARGE_POINTS_MAX
    )
    score_marge = np.where(ratio_known, marge_scaled.fillna(0.0), MARGE_POINTS_UNKNOWN)

    age = df["age_entreprise"]
    # 5-20 ans->30 (coeur de cible), 2-5 ans->20, >20 ans->15, <2 ans OU âge
    # inconnu->5 (voir note sur ce dernier point en tête de fichier).
    score_age = np.select(
        [(age >= 5) & (age <= 20), (age >= 2) & (age < 5), age > 20],
        [AGE_POINTS_CORE, AGE_POINTS_YOUNG, AGE_POINTS_OLD],
        default=AGE_POINTS_LOW,
    )

    ca = df["ca"]
    ca_valid = ca.notna() & (ca > 0)
    log_lo, log_hi = math.log(CA_LOG_LOW), math.log(CA_LOG_HIGH)
    ca_ratio = ((np.log(ca.clip(lower=1.0)) - log_lo) / (log_hi - log_lo)).clip(
        lower=0.0, upper=1.0
    )
    # Échelle log entre CA_LOG_LOW (0 pt) et CA_LOG_HIGH (20 pts pleins) —
    # barème fourni. CA inconnu -> crédit neutre (10 pts, non spécifié par le
    # barème fourni, choisi par cohérence avec le traitement RN/marge ci-dessus).
    score_ca = np.where(ca_valid, ca_ratio.fillna(0.0) * CA_POINTS_MAX, CA_POINTS_UNKNOWN)

    return (score_rn + score_marge + score_age + score_ca) / 100.0

LABEL_THRESHOLD = 0.60


def _add_label(df: pd.DataFrame, np_rng: np.random.Generator,
               threshold: float = LABEL_THRESHOLD) -> pd.DataFrame:

    # Un bruit gaussien (σ=0.08, barème fourni le 2026-07-07) est ajouté au
    # score pour empêcher le modèle de simplement "mémoriser" la règle
    # déterministe.
    raw_scores = _compute_raw_score(df)

    noise = np_rng.normal(0, 0.08, size=len(df))
    proba = np.clip(raw_scores + noise, 0, 1)
    df["score_continu"] = proba
    df["label_scoring"] = (proba >= threshold).astype(int)
    n_pos = int(df["label_scoring"].sum())
    log.info(
        "Seuil label FIXE : %.2f → %d/%d positifs (%.1f%%) — taux non forcé, à documenter tel quel",
        threshold, n_pos, len(df), n_pos / len(df) * 100 if len(df) else 0,
    )
    return df


# ── Coverage / quality report ──────────────────────────────────────────────────

def print_coverage_report(df: pd.DataFrame) -> None:
    n = len(df)
    n_pos = int(df["label_scoring"].sum())
    w = 55

    print(f"\n{'═'*w}")
    print(f"  RAPPORT DE COUVERTURE — {n:,} leads réels")
    print(f"{'═'*w}")
    print(f"  label=1 (haute valeur) : {n_pos:,}  ({n_pos/n*100:.1f}%)")
    print(f"  label=0 (faible prio)  : {n-n_pos:,}  ({(n-n_pos)/n*100:.1f}%)")
    print(f"{'─'*w}")
    print("  Taux de complétion des champs (données réelles) :")

    coverage_cols = [
        ("ca",              "CA récupéré"),
        ("ca_n1",           "CA N-1 récupéré"),
        ("resultat_net",    "Résultat net récupéré"),
        ("email",           "Email disponible"),
        ("telephone",       "Téléphone disponible"),
        ("site_web",        "Site web disponible"),
        ("prenom_dirigeant","Dirigeant nommé"),
        ("date_creation",   "Date de création connue"),
        ("croissance_ca",   "Croissance CA calculable"),
        ("marge_nette",     "Marge nette calculable"),
    ]
    for col, label in coverage_cols:
        rate = df[col].notna().mean() * 100
        bar = "█" * int(rate / 5) + "░" * (20 - int(rate / 5))
        print(f"    {label:<32} {rate:5.1f}%  {bar}")

    print(f"{'─'*w}")
    print("  Distribution taille_entreprise :")
    t_dist = df["taille_entreprise"].value_counts().sort_index()
    for code, count in t_dist.items():
        print(f"    {code:>3}  {count:>6,}  ({count/n*100:.1f}%)")

    print(f"{'─'*w}")
    print("  CA (€) — entreprises avec CA connu :")
    ca_known = df["ca"].dropna()
    if len(ca_known):
        for stat, val in ca_known.describe(percentiles=[0.25, 0.5, 0.75, 0.95]).items():
            if stat in ("min", "25%", "50%", "75%", "95%", "max"):
                print(f"    {stat:<5} {val:>18,.0f} €")
    print(f"{'═'*w}\n")


def _cmd_generate(args: argparse.Namespace) -> None:
    out_path = Path(args.out) if args.out else _HERE / "dataset_scoring_real.csv"
    cache_path = Path(args.cache) if args.cache else out_path.parent / "siret_cache.json"
    np_rng = np.random.default_rng(args.seed)

    # ── Step 1: Stratified SIRENE sampling ───────────────────────────────────
    sirene_df = load_sirene_sample(args.sirene, n_target=args.n, seed=args.seed)

    # Build base row dict from SIRENE columns
    rows: list[dict] = []
    for _, r in sirene_df.iterrows():
        naf = _normalize_naf(str(r.get("activitePrincipaleEtablissement") or ""))
        taille = str(r.get("trancheEffectifsEtablissement") or r.get("taille") or "NN")
        taille = taille if taille not in ("nan", "") else "NN"

        raw_date = str(r.get("dateCreationEtablissement") or "")
        try:
            date_creation = date.fromisoformat(raw_date) if raw_date and raw_date != "nan" else None
        except ValueError:
            date_creation = None

        rows.append({
            "siret": str(r["siret"]).strip(),
            "company_name": str(r.get("denominationUsuelleEtablissement") or "").strip() or None,
            "secteur": naf,
            "taille_entreprise": taille,
            "adresse": _build_address(r),
            "date_creation": date_creation,
            # enrichment fields — filled in Step 2
            "telephone": None, "site_web": None,
            "prenom_dirigeant": None, "nom_dirigeant": None, "titre_dirigeant": None,
            "email": None, "ca": None, "ca_n1": None, "resultat_net": None,
            "score_exploitabilite": 0.0,
            "latitude": None, "longitude": None,
        })

    df = pd.DataFrame(rows)

    # ── Step 2: API enrichment ────────────────────────────────────────────────
    if not args.no_enrich:
        log.info("Enrichissement de %d SIRETs (concurrency=%d)…", len(df), args.concurrency)
        cache = SiretCache(cache_path)
        sirets = df["siret"].tolist()
        enriched = asyncio.run(enrich_all(sirets, cache, concurrency=args.concurrency))

        for i, fields in enumerate(enriched):
            for col in (
                "telephone", "site_web", "prenom_dirigeant", "nom_dirigeant",
                "titre_dirigeant", "email", "ca", "ca_n1", "resultat_net",
                "score_exploitabilite", "latitude", "longitude",
            ):
                if col in fields:
                    df.at[i, col] = fields[col]
    else:
        log.warning("--no-enrich activé : features API absentes, dataset incomplet")

    # ── Step 3: Derived features ──────────────────────────────────────────────
    df = _add_derived_features(df)

    # ── Step 4: Label ─────────────────────────────────────────────────────────
    df = _add_label(df, np_rng)

    # ── Step 5: Column order matching train_scoring_model.py expectation ──────
    expected_cols = [
        "company_name", "siret", "secteur", "taille_entreprise", "adresse",
        "telephone", "site_web", "prenom_dirigeant", "nom_dirigeant",
        "titre_dirigeant", "email", "ca", "ca_n1", "resultat_net",
        "date_creation", "score_exploitabilite", "latitude", "longitude",
        "age_entreprise", "croissance_ca", "marge_nette",
        "has_email", "has_phone", "has_website", "has_dirigeant",
        "score_continu", "label_scoring",
    ]
    df = df.reindex(columns=expected_cols)

    # ── Step 6: Save ──────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    log.info("Dataset sauvegardé : %s", out_path.resolve())

    # ── Step 7: Coverage report ────────────────────────────────────────────────
    print_coverage_report(df)


# ═══════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 : PATCH — complète les champs manquants d'un CSV existant
# ═══════════════════════════════════════════════════════════════════════════

async def _patch_one(
    row: pd.Series,
    semaphore: asyncio.Semaphore,
    scrape_web: bool,
) -> dict:
    """Retourne un dict de champs à mettre à jour pour cette ligne."""
    updates: dict = {}

    company_fallback: str | None = None

    async with semaphore:
        # ── CA N-1 via recherche-entreprises (re-appel, nouveau fix) ──────────
        if pd.isna(row.get("ca_n1")):
            try:
                client = RechercheEntreprisesClient()
                result = await client.get_by_siret(str(row["siret"]))
                if result:
                    info = extract_contact_info(result)
                    if info.get("ca_n1") is not None:
                        updates["ca_n1"] = info["ca_n1"]
                    # Profite du re-appel pour récupérer téléphone/site/géoloc si manquants
                    if pd.isna(row.get("telephone")) and info.get("telephone"):
                        updates["telephone"] = info["telephone"]
                    if pd.isna(row.get("site_web")) and info.get("site_web"):
                        updates["site_web"] = info["site_web"]
                    if pd.isna(row.get("latitude")) and info.get("latitude") is not None:
                        updates["latitude"] = info["latitude"]
                    if pd.isna(row.get("longitude")) and info.get("longitude") is not None:
                        updates["longitude"] = info["longitude"]
                    # nom_complet sert de repli pour la recherche DDG quand
                    # denominationUsuelleEtablissement est absente (~83% des cas SIRENE)
                    nom_complet = (result.get("nom_complet") or "").strip()
                    if nom_complet:
                        company_fallback = nom_complet
                        company_name_missing = pd.isna(row.get("company_name")) or not str(
                            row.get("company_name") or ""
                        ).strip()
                        if company_name_missing:
                            updates["company_name"] = nom_complet
            except (RechercheEntreprisesError, httpx.HTTPError) as exc:
                log.debug("recherche-entreprises %s : %s", row["siret"], exc)
            await asyncio.sleep(0.2)

        # ── Site web via DuckDuckGo si toujours absent ──────────────────────
        site_web = updates.get("site_web") or row.get("site_web")
        if scrape_web and (pd.isna(site_web) or not site_web):
            company = (
                str(row.get("company_name") or "").strip()
                or updates.get("company_name")
                or company_fallback
                or ""
            )
            if company:
                try:
                    found = await find_company_website(company, "")
                    if found:
                        site_web = found
                        updates["site_web"] = found
                except Exception:
                    pass
            await asyncio.sleep(1.0)

        # ── Email + téléphone via scraping homepage ──────────────────────────
        if scrape_web and site_web and not pd.isna(site_web):
            if pd.isna(row.get("email")) and "email" not in updates:
                try:
                    email = await scrape_email_from_homepage(site_web)
                    if email:
                        updates["email"] = email
                except Exception:
                    pass
            if pd.isna(row.get("telephone")) and "telephone" not in updates:
                try:
                    phone = await scrape_phone_from_homepage(site_web)
                    if phone:
                        updates["telephone"] = phone
                except Exception:
                    pass

    return updates


async def patch_all(
    df: pd.DataFrame,
    concurrency: int = 5,
    scrape_web: bool = False,
    checkpoint_path: Path | None = None,
    checkpoint_every: int = 2000,
) -> pd.DataFrame:
    """
    checkpoint_path : si fourni, sauvegarde le CSV tous les `checkpoint_every`
    lignes traitées. Contrairement au cache SIRET (qui persiste les réponses
    API brutes), seul un checkpoint du DataFrame permet de reprendre un run
    interrompu sans perdre le travail déjà fait — un run de plusieurs dizaines
    de minutes ne sauvegardait auparavant qu'à la toute fin (un seul
    df.to_csv() en fin de main()), donc une interruption (arrêt de session,
    process tué) perdait 100% de la progression même à 90% terminé.
    """
    semaphore = asyncio.Semaphore(concurrency)
    done = 0

    async def worker(idx: int, row: pd.Series) -> None:
        nonlocal done
        updates = await _patch_one(row, semaphore, scrape_web)
        for col, val in updates.items():
            df.at[idx, col] = val
        done += 1
        if done % 500 == 0:
            log.info("  %d / %d lignes patchées", done, len(df))
        if checkpoint_path is not None and done % checkpoint_every == 0:
            df.to_csv(checkpoint_path, index=False)
            log.info("  Checkpoint sauvegardé (%d / %d)", done, len(df))

    await asyncio.gather(*(worker(i, row) for i, row in df.iterrows()))
    return df


def _cmd_patch(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv)
    log.info("Chargement : %s", csv_path)
    df = pd.read_csv(csv_path, dtype={"siret": str})
    df["date_creation"] = pd.to_datetime(df["date_creation"], errors="coerce").dt.date

    # Colonnes requises par _patch_one / _add_derived_features : peuvent être
    # absentes si le CSV a déjà été passé par l'étape impute (qui les supprime
    # après avoir dérivé has_email/has_phone/has_website).
    for col in ("email", "telephone", "site_web", "latitude", "longitude"):
        if col not in df.columns:
            df[col] = np.nan

    n_missing_ca_n1 = df["ca_n1"].isna().sum()
    log.info("CA N-1 manquant pour %d / %d lignes", n_missing_ca_n1, len(df))

    log.info("Patch en cours (concurrency=%d, scrape_web=%s)…",
             args.concurrency, args.scrape_web)
    df = asyncio.run(patch_all(
        df, args.concurrency, args.scrape_web,
        checkpoint_path=csv_path, checkpoint_every=2000,
    ))

    # Préserve les has_* préexistants (ex: imputation Bernoulli antérieure via
    # l'étape impute) : _add_derived_features les recalculerait sinon
    # uniquement depuis email/telephone/site_web, qui peuvent être vides ici
    # (run sans --scrape-web, ou colonnes brutes déjà supprimées) — ce qui
    # écraserait silencieusement has_* à 0 (régression déjà rencontrée).
    prior_has = {
        col: df[col].fillna(0).astype(int) if col in df.columns else None
        for col in ("has_email", "has_phone", "has_website")
    }

    # Recalcul des features dérivées et du label
    df = _add_derived_features(df)
    for col, prior in prior_has.items():
        if prior is not None:
            df[col] = np.maximum(df[col].astype(int), prior)
    df = _add_label(df, np.random.default_rng(args.seed))

    df.to_csv(csv_path, index=False)
    log.info("Dataset sauvegardé : %s", csv_path.resolve())

    # Rapport de couverture
    n = len(df)
    coverage = {
        "CA récupéré":         df["ca"].notna().mean(),
        "CA N-1 récupéré":     df["ca_n1"].notna().mean(),
        "Résultat net":        df["resultat_net"].notna().mean(),
        "Croissance CA":       df["croissance_ca"].notna().mean(),
        "Email":               df["email"].notna().mean(),
        "Téléphone":           df["telephone"].notna().mean(),
        "Site web":            df["site_web"].notna().mean(),
        "Dirigeant":           df["prenom_dirigeant"].notna().mean(),
    }
    print(f"\n{'═'*50}")
    print(f"  COUVERTURE APRÈS PATCH — {n:,} leads")
    print(f"{'═'*50}")
    for label, rate in coverage.items():
        bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
        print(f"  {label:<22} {rate*100:5.1f}%  {bar}")
    n_pos = int(df["label_scoring"].sum())
    print(f"\n  label=1 : {n_pos:,} ({n_pos/n*100:.1f}%)")
    print(f"{'═'*50}\n")


# ═══════════════════════════════════════════════════════════════════════════
# ÉTAPE 3 : IMPUTE — has_email/has_phone/has_website par tirage de Bernoulli
# ═══════════════════════════════════════════════════════════════════════════
#
# Approche : tirage de Bernoulli par taille d'entreprise, basé sur des études
# officielles françaises. On travaille directement sur les features binaires
# utilisées par le modèle ML, sans stocker de fausses valeurs textuelles.
#
# Les colonnes brutes (email, telephone, site_web) sont supprimées du CSV car
# elles sont vides à 100% — seules les features has_* sont conservées.
#
# Sources des taux :
#   - Bpifrance Observatoire PME 2023 : présence digitale des TPE/PME
#   - INSEE Enquête TIC-PME 2022 : usage des TIC dans les PME
#   - FEVAD 2023 : présence web des entreprises françaises par taille
#
# Taux retenus :
#   Catégorie  | Site web | Téléphone | Email
#   ───────────|──────────|───────────|──────
#   Micro      |   20%    |    35%    |  10%
#   PE         |   55%    |    65%    |  25%
#   ME         |   75%    |    78%    |  40%
#   ETI        |   88%    |    85%    |  55%
#   GE         |   95%    |    90%    |  65%

# ── Mapping taille INSEE → catégorie ──────────────────────────────────────────
_TAILLE_TO_CAT: dict[str, str] = {
    "NN": "micro", "00": "micro", "01": "micro",
    "02": "pe",    "03": "pe",    "11": "pe",    "12": "pe",
    "21": "me",    "22": "me",    "31": "me",
    "32": "eti",   "41": "eti",
    "42": "ge",    "51": "ge",    "52": "ge",    "53": "ge",
}

# (p_has_website, p_has_phone, p_has_email) — Bpifrance/INSEE/FEVAD 2023
_RATES: dict[str, tuple[float, float, float]] = {
    "micro": (0.20, 0.35, 0.10),
    "pe":    (0.55, 0.65, 0.25),
    "me":    (0.75, 0.78, 0.40),
    "eti":   (0.88, 0.85, 0.55),
    "ge":    (0.95, 0.90, 0.65),
}

# Colonnes brutes inutiles dans le dataset ML (remplacées par les has_*)
_RAW_CONTACT_COLS = ["email", "telephone", "site_web"]


def impute_has_features(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    Impute has_email, has_phone, has_website directement comme features binaires.
    Ne modifie que les lignes où la feature vaut 0 (contact absent).
    """
    df = df.copy()
    cat_series = df["taille_entreprise"].fillna("NN").astype(str).map(
        lambda t: _TAILLE_TO_CAT.get(t, "micro")
    )

    features = [
        ("has_website", 0),
        ("has_phone",   1),
        ("has_email",   2),
    ]

    n_imputed: dict[str, int] = {}

    for feat, rate_idx in features:
        n_imputed[feat] = 0
        for cat, idx in df.groupby(cat_series).groups.items():
            p = _RATES[cat][rate_idx]
            missing_mask = df.loc[idx, feat] == 0
            missing_idx = idx[missing_mask]
            if len(missing_idx) == 0:
                continue
            draws = rng.random(len(missing_idx)) < p
            df.loc[missing_idx[draws], feat] = 1
            n_imputed[feat] += int(draws.sum())

    print("\n  Imputation has_* (Bpifrance/INSEE/FEVAD 2023) :")
    for feat, n in n_imputed.items():
        cov = df[feat].mean() * 100
        print(f"    {feat:<15} +{n:,} → couverture finale {cov:.1f}%")

    return df


def recompute_score_exploitabilite(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcule score_exploitabilite depuis les features binaires (pas les champs bruts)."""
    df["score_exploitabilite"] = (
        40 * df["has_email"] +
        25 * df["has_phone"] +
        20 * df["has_website"] +
        15 * df["has_dirigeant"]
    )
    return df


def _cmd_impute(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv)
    print(f"Chargement : {csv_path}")
    df = pd.read_csv(csv_path, dtype={"siret": str})
    df["date_creation"] = pd.to_datetime(df["date_creation"], errors="coerce").dt.date

    # Assure que les colonnes has_* existent
    for col in ["has_email", "has_phone", "has_website"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    print(f"\n  Couverture AVANT imputation ({len(df):,} leads) :")
    for feat in ["has_email", "has_phone", "has_website"]:
        print(f"    {feat:<15} {df[feat].mean()*100:.1f}%")
    print(f"    score_exploitabilite moyen : {df['score_exploitabilite'].mean():.1f}")

    rng = np.random.default_rng(args.seed)

    # Imputation des features binaires
    df = impute_has_features(df, rng)

    # Recalcul score_exploitabilite depuis les has_* mis à jour
    df = recompute_score_exploitabilite(df)

    # Suppression des colonnes brutes (vides à 100%, inutiles pour le ML)
    cols_to_drop = [c for c in _RAW_CONTACT_COLS if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        print(f"\n  Colonnes supprimées : {cols_to_drop}")

    # Recalcul du label avec les nouvelles features
    df = _add_label(df, rng)

    df.to_csv(csv_path, index=False)
    print(f"\nDataset sauvegardé : {csv_path.resolve()}")

    n = len(df)
    n_pos = int(df["label_scoring"].sum())
    print(f"\n{'═'*52}")
    print(f"  RÉSULTAT FINAL — {n:,} leads")
    print(f"{'═'*52}")
    # Champs déjà binaires (0/1) : la moyenne EST le taux. Tous les autres
    # champs (y compris numériques comme "ca") : le taux de couverture est
    # notna().mean(), PAS mean() — confondre les deux fait planter le
    # rapport pour "ca" (moyenne ~150M€ interprétée comme un pourcentage,
    # donnant une barre de plusieurs milliards de caractères).
    _binary_rate_fields = {"has_email", "has_phone", "has_website"}

    for field, label in [
        ("ca",              "CA"),
        ("ca_n1",           "CA N-1"),
        ("resultat_net",    "Résultat net"),
        ("croissance_ca",   "Croissance CA"),
        ("has_email",       "has_email"),
        ("has_phone",       "has_phone"),
        ("has_website",     "has_website"),
        ("prenom_dirigeant","Dirigeant"),
    ]:
        if field not in df.columns:
            continue
        if field in _binary_rate_fields:
            rate = df[field].mean()
        else:
            rate = df[field].notna().mean()
        bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
        print(f"  {label:<22} {rate*100:5.1f}%  {bar}")
    print(f"\n  score_exploitabilite moyen : {df['score_exploitabilite'].mean():.1f}")
    print(f"  label=1 : {n_pos:,} ({n_pos/n*100:.1f}%)")
    print(f"{'═'*52}\n")


# ═══════════════════════════════════════════════════════════════════════════
# CLI — sous-commandes generate / patch / impute
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline de génération du dataset de scoring B2B (generate → patch → impute).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="Échantillonnage SIRENE + enrichissement API")
    p_gen.add_argument(
        "--sirene", required=True, help="Chemin vers StockEtablissement_utf8.csv (INSEE)"
    )
    p_gen.add_argument("--n", type=int, default=20_000, help="Nombre de leads cible")
    p_gen.add_argument("--seed", type=int, default=42)
    p_gen.add_argument(
        "--concurrency", type=int, default=5, help="Nombre de requêtes API parallèles (défaut: 5)"
    )
    p_gen.add_argument(
        "--cache",
        default=None,
        help="Fichier cache JSON (défaut: même dossier que --out, siret_cache.json)",
    )
    p_gen.add_argument(
        "--out", default=None, help="CSV de sortie (défaut: ml/dataset_scoring_real.csv)"
    )
    p_gen.add_argument(
        "--no-enrich",
        action="store_true",
        help="Ignore l'étape d'enrichissement API (utile pour tester le sampling seul)",
    )
    p_gen.set_defaults(func=_cmd_generate)

    p_patch = sub.add_parser(
        "patch", help="Complète les champs manquants d'un CSV existant (mis à jour sur place)"
    )
    p_patch.add_argument("--csv", default="backend/ml/dataset_scoring_real.csv")
    p_patch.add_argument("--concurrency", type=int, default=5)
    p_patch.add_argument(
        "--scrape-web",
        action="store_true",
        help="Active le scraping email/téléphone via les sites web (lent)",
    )
    p_patch.add_argument("--seed", type=int, default=42)
    p_patch.set_defaults(func=_cmd_patch)

    p_imp = sub.add_parser(
        "impute", help="Impute has_email/has_phone/has_website (mis à jour sur place)"
    )
    p_imp.add_argument("--csv", default="backend/ml/dataset_scoring_real.csv")
    p_imp.add_argument("--seed", type=int, default=42)
    p_imp.set_defaults(func=_cmd_impute)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
