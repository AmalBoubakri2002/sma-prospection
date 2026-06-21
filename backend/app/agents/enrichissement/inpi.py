"""Client pour l'API open data INPI — comptes annuels par SIREN.

Endpoint : https://data.inpi.fr/entreprises/{siren}/comptes
Gratuit, sans authentification, rate-limit généreux.
Retourne le CA, résultat net et effectif pour les entreprises qui déposent
leurs comptes (SA, SAS, SARL principalement).
"""

import asyncio

import httpx

BASE_URL = "https://data.inpi.fr"
REQUEST_DELAY_SECONDS = 0.3


class InpiError(Exception):
    pass


async def get_finances_from_siren(siren: str) -> dict:
    """Retourne {'ca': int|None, 'resultat_net': int|None} pour un SIREN."""
    url = f"{BASE_URL}/entreprises/{siren}/comptes"
    async with httpx.AsyncClient(
        headers={"Accept": "application/json"},
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        response = await _get_with_retry(client, url)

    await asyncio.sleep(REQUEST_DELAY_SECONDS)

    if response.status_code == 404:
        return {}
    if response.status_code != 200:
        raise InpiError(f"INPI ({response.status_code}) : {response.text[:200]}")

    data = response.json()
    return _extract_latest_finances(data)


def _extract_latest_finances(data: list | dict) -> dict:
    """Extrait le CA et résultat net du bilan le plus récent."""
    if not data:
        return {}

    # L'API renvoie une liste de bilans par exercice
    bilans: list[dict] = data if isinstance(data, list) else data.get("bilans", [])
    if not bilans:
        return {}

    # Tri par date de clôture décroissante — on prend le plus récent
    def sort_key(b: dict) -> str:
        return b.get("dateCloture") or b.get("date_cloture") or ""

    bilans_sorted = sorted(bilans, key=sort_key, reverse=True)
    latest = bilans_sorted[0]

    def _first(bilan: dict, *keys: str) -> object:
        for k in keys:
            v = bilan.get(k)
            if v is not None:
                return v
        return None

    ca = _to_int(_first(latest, "chiffreAffaires", "chiffre_affaires", "ca"))
    resultat = _to_int(_first(latest, "resultatNet", "resultat_net", "resultat"))

    # CA année N-1 pour calculer l'évolution dans l'Agent Scoring
    prev = bilans_sorted[1] if len(bilans_sorted) >= 2 else None
    ca_n1 = _to_int(_first(prev, "chiffreAffaires", "chiffre_affaires", "ca")) if prev else None

    return {"ca": ca, "resultat_net": resultat, "ca_n1": ca_n1}


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, max_retries: int = 3
) -> httpx.Response:
    response: httpx.Response
    for _ in range(max_retries):
        response = await client.get(url)
        if response.status_code == 429:
            await asyncio.sleep(float(response.headers.get("Retry-After", 2)))
            continue
        return response
    return response
