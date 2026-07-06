"""Client BODACC open data (bodacc-datadila.opendatasoft.com) — 3e source financière,
sans authentification. `jugement` et `depot` sont des champs JSON string imbriqués."""

import asyncio
import json

import httpx

_BASE_URL = (
    "https://bodacc-datadila.opendatasoft.com"
    "/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
)
_REQUEST_DELAY = 0.3

_FAMILLE_PROCEDURE = "procédures collectives"
_FAMILLE_DEPOT = "dépôts des comptes"

_OUVERTURE_KEYWORDS = frozenset([
    "liquidation judiciaire", "redressement judiciaire",
    "procédure de sauvegarde", "sauvegarde accélérée",
    "ouverture de la procédure",
])
_CLOTURE_KEYWORDS = frozenset([
    "clôture", "fin de la liquidation", "arrêt du plan",
    "résolution du plan", "fin de la procédure",
])


class BodaccError(Exception):
    pass


async def get_procedure_from_bodacc(siren: str) -> dict:
    """Retourne {'en_procedure_collective': bool, 'annee_derniers_comptes': str | None}."""
    params = {
        "where": f'registre like "%{siren}%"',
        "order_by": "dateparution desc",
        "limit": 20,
        "select": "familleavis_lib,dateparution,jugement,depot",
    }

    async with httpx.AsyncClient(
        headers={"Accept": "application/json"},
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(_BASE_URL, params=params)
        except httpx.RequestError as exc:
            raise BodaccError(f"Requête BODACC échouée : {exc}") from exc

    await asyncio.sleep(_REQUEST_DELAY)

    if response.status_code == 404:
        return {"en_procedure_collective": False, "annee_derniers_comptes": None}
    if response.status_code != 200:
        raise BodaccError(f"BODACC ({response.status_code}) : {response.text[:200]}")

    results = response.json().get("results", [])
    return _analyse_records(results)


def _parse_json_field(raw: str | None) -> dict:
    """Décode un champ JSON string de l'API BODACC (ex: jugement, depot)."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _analyse_records(results: list[dict]) -> dict:
    annee_derniers_comptes: str | None = None
    last_procedure_is_open: bool | None = None

    for record in results:
        famille = (record.get("familleavis_lib") or "").lower()

        # ── Dépôt de comptes ──────────────────────────────────────────────────
        if _FAMILLE_DEPOT in famille:
            if annee_derniers_comptes is None:
                depot = _parse_json_field(record.get("depot"))
                date_cloture = depot.get("dateCloture") or ""
                annee = date_cloture[:4]
                if annee.isdigit():
                    annee_derniers_comptes = annee

        # ── Procédure collective ───────────────────────────────────────────────
        if _FAMILLE_PROCEDURE in famille:
            if last_procedure_is_open is None:
                jugement = _parse_json_field(record.get("jugement"))
                nature = (jugement.get("nature") or "").lower()

                is_cloture = any(kw in nature for kw in _CLOTURE_KEYWORDS)
                is_ouverture = any(kw in nature for kw in _OUVERTURE_KEYWORDS)

                if is_cloture:
                    last_procedure_is_open = False
                elif is_ouverture:
                    last_procedure_is_open = True

    return {
        "en_procedure_collective": bool(last_procedure_is_open),
        "annee_derniers_comptes": annee_derniers_comptes,
    }
