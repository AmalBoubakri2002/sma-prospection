"""Client pour l'API RNE INPI — comptes annuels par SIREN.

Utilise /api/companies/{siren}/attachments (registre-national-entreprises.inpi.fr),
qui renvoie directement les bilans saisis (bilansSaisis[].bilanSaisi.bilan.detail.pages),
et non /entreprises/{siren}/comptes sur data.inpi.fr : cet ancien endpoint est bloqué par
Cloudflare (403 "Just a moment...") quel que soit le token, alors que le domaine
registre-national-entreprises.inpi.fr (déjà utilisé pour le login SSO) répond normalement.

Seuls les types de bilan "C" (complet) et "S" (simplifié) sont interprétés — ils couvrent
l'écrasante majorité des PME/TPE ciblées en prospection. Les autres types (K=consolidé,
B=banque, assurance, agricole) ont une nomenclature de codes différente et ne sont pas
traités : get_finances_from_siren renvoie alors {} pour ce SIREN plutôt qu'une valeur
incorrecte, exactement comme lorsque le bilan n'est pas saisi ou est confidentiel.

Authentification : login (INPI_USERNAME / INPI_PASSWORD dans backend/.env) contre
le SSO du registre national, qui renvoie un token Bearer temporaire.
"""


import asyncio

import httpx

from app.core.config import settings

BASE_URL = "https://registre-national-entreprises.inpi.fr/api"
SSO_LOGIN_URL = f"{BASE_URL}/sso/login"
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
            raise InpiAuthError(
                f"Login INPI échoué ({response.status_code}) : {response.text[:200]}"
            )

        token = response.json().get("token")
        if not token:
            raise InpiAuthError("Login INPI réussi mais réponse sans champ 'token'")

        _cached_token = token
        return token


async def get_finances_from_siren(siren: str) -> dict:
    """Retourne {'ca': int|None, 'resultat_net': int|None, 'ca_n1': int|None} pour un SIREN."""
    url = f"{BASE_URL}/companies/{siren}/attachments"

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

    bilans_saisis = response.json().get("bilansSaisis", [])
    return _extract_latest_finances(bilans_saisis)


# Types de bilan interprétés — voir docstring du module.
_SUPPORTED_TYPES = frozenset({"C", "S"})

# CA "complet" (type C) : poste "Chiffres d'affaires nets", page 03, colonnes
# 3=Total année N / 4=Total année N-1.
_CA_COMPLET_CODE = "FJ"

# CA "simplifié" (type S) : pas de poste unique, on additionne ventes + production vendue
# (France + export), page 02, colonnes 1=année N / 2=année N-1 (export : colonne 1 seulement).
_CA_SIMPLIFIE_CODES = ("209", "210", "214", "215", "217", "218")

# Résultat de l'exercice : "DI" (passif, page 02) pour le complet, "310" (compte de
# résultat, page 02) pour le simplifié — les deux valent "bénéfice ou perte", vérifié
# par recoupement avec les postes HN (complet) / 136 (simplifié) sur des cas réels.
_RESULTAT_CODE = {"C": "DI", "S": "310"}


def _parse_amount(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _liasse_codes(bilan: dict) -> dict[str, dict]:
    """Aplatit les pages d'un bilan-saisi en {code_liasse: {"m1": ..., "m2": ...}}."""
    pages = bilan.get("detail", {}).get("pages", [])
    codes: dict[str, dict] = {}
    for page in pages:
        for liasse in page.get("liasses", []):
            code = liasse.get("code")
            if code:
                codes[code] = liasse
    return codes


def _extract_ca(codes: dict[str, dict], type_bilan: str) -> tuple[int | None, int | None]:
    if type_bilan == "C":
        fj = codes.get(_CA_COMPLET_CODE, {})
        return _parse_amount(fj.get("m3")), _parse_amount(fj.get("m4"))

    # type "S" : somme des postes de vente (France + export)
    found = False
    ca = ca_n1 = 0
    for code in _CA_SIMPLIFIE_CODES:
        liasse = codes.get(code)
        if liasse is None:
            continue
        found = True
        ca += _parse_amount(liasse.get("m1")) or 0
        ca_n1 += _parse_amount(liasse.get("m2")) or 0
    return (ca if found else None), (ca_n1 if found else None)


def _extract_resultat(codes: dict[str, dict], type_bilan: str) -> tuple[int | None, int | None]:
    liasse = codes.get(_RESULTAT_CODE[type_bilan], {})
    return _parse_amount(liasse.get("m1")), _parse_amount(liasse.get("m2"))


def _extract_latest_finances(bilans_saisis: list[dict]) -> dict:
    """Sélectionne le bilan-saisis le plus récent parmi les types supportés et en
    extrait CA / résultat net. Renvoie {} si aucun bilan exploitable (type non
    supporté, comptes confidentiels, ou pas encore saisis par l'INPI)."""
    candidats = [
        b for b in bilans_saisis
        if b.get("typeBilan") in _SUPPORTED_TYPES and b.get("bilanSaisi")
    ]
    if not candidats:
        return {}

    candidats.sort(key=lambda b: b.get("dateCloture") or "", reverse=True)
    latest = candidats[0]
    type_bilan = latest["typeBilan"]
    codes = _liasse_codes(latest["bilanSaisi"]["bilan"])

    ca, ca_n1 = _extract_ca(codes, type_bilan)
    resultat_net, _ = _extract_resultat(codes, type_bilan)

    return {"ca": ca, "resultat_net": resultat_net, "ca_n1": ca_n1}


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
