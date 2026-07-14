"""Client pour l'API RNE INPI — comptes annuels par SIREN.

Non fonctionnel en pratique : l'endpoint JSON ciblé est bloqué par Cloudflare ;
le seul accès réel (API RNE) renvoie un PDF de bilan, dont le parsing n'est pas
implémenté. get_finances_from_siren lève donc toujours InpiError — géré par
l'appelant (agent.py), qui continue sans CA plutôt que d'échouer l'enrichissement.

Authentification : login (INPI_USERNAME / INPI_PASSWORD dans backend/.env) contre
le SSO du registre national, qui renvoie un token Bearer temporaire.
"""


import asyncio

import httpx

from app.core.config import settings

BASE_URL = "https://data.inpi.fr"
SSO_LOGIN_URL = "https://registre-national-entreprises.inpi.fr/api/sso/login"
REQUEST_DELAY_SECONDS = 0.3


class InpiError(Exception):
    pass


class InpiAuthError(InpiError):
    """Login échoué (identifiants invalides ou absents) — pas la peine de retenter."""


# Cache du token en mémoire (pas de TTL documenté par l'INPI) ; _login_lock évite
# des logins concurrents quand plusieurs leads sont traités en parallèle.
_cached_token: str | None = None
_login_lock = asyncio.Lock()


async def _login(client: httpx.AsyncClient) -> str:
    global _cached_token

    async with _login_lock:
        if _cached_token is not None:
            return _cached_token

        if not settings.INPI_USERNAME or not settings.INPI_PASSWORD:
            raise InpiAuthError(
                "INPI_USERNAME / INPI_PASSWORD non configurés dans backend/.env "
                "(voir 'Mes accès API' > 'Accès API RNE' sur data.inpi.fr)"
            )

        response = await client.post(
            SSO_LOGIN_URL,
            json={"username": settings.INPI_USERNAME, "password": settings.INPI_PASSWORD},
            timeout=10.0,
        )
        if response.status_code != 200:
            raise InpiAuthError(f"Login INPI échoué ({response.status_code}) : {response.text[:200]}")

        token = response.json().get("token")
        if not token:
            raise InpiAuthError("Login INPI réussi mais réponse sans champ 'token'")

        _cached_token = token
        return token


async def get_finances_from_siren(siren: str) -> dict:
    """Retourne {'ca': int|None, 'resultat_net': int|None, 'ca_n1': int|None} pour un SIREN."""
    url = f"{BASE_URL}/entreprises/{siren}/comptes"

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        token = await _login(client)
        response = await _get_with_retry(client, url, token)

        if response.status_code in (401, 403):
            # Token expiré/révoqué : on en redemande un et on retente une fois.
            global _cached_token
            _cached_token = None
            token = await _login(client)
            response = await _get_with_retry(client, url, token)

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
    client: httpx.AsyncClient, url: str, token: str, max_retries: int = 3
) -> httpx.Response:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    response: httpx.Response
    for _ in range(max_retries):
        response = await client.get(url, headers=headers)
        if response.status_code == 429:
            await asyncio.sleep(float(response.headers.get("Retry-After", 2)))
            continue
        return response
    return response
