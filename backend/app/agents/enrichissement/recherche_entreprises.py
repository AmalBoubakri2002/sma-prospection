"""Client pour l'API recherche-entreprises.api.gouv.fr.

API officielle française (data.gouv.fr), sans clé, sans authentification.
Rate limit : ~7 req/s (généreux pour un usage séquentiel).
Documentation : https://recherche-entreprises.api.gouv.fr/docs/
"""

import asyncio

import httpx

BASE_URL = "https://recherche-entreprises.api.gouv.fr"
REQUEST_DELAY_SECONDS = 0.2  # 200ms entre appels, très en dessous des limites


class RechercheEntreprisesError(Exception):
    pass


class RechercheEntreprisesClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def get_by_siret(self, siret: str) -> dict | None:
        """Retourne les données enrichies pour un SIRET, ou None si non trouvé."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Accept": "application/json"},
            timeout=10.0,
        ) as client:
            response = await self._get_with_retry(
                client,
                "/search",
                {"q": siret, "page": 1, "per_page": 1},
            )

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RechercheEntreprisesError(
                f"Erreur API ({response.status_code}) : {response.text[:200]}"
            )

        data = response.json()
        results = data.get("results", [])
        if not results:
            return None

        return results[0]

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict,
        max_retries: int = 3,
    ) -> httpx.Response:
        """Retente sur 429 et sur les erreurs réseau transitoires (timeout, connexion
        réinitialisée) — un blip ponctuel de l'API ne doit pas vider un lead entièrement."""
        response: httpx.Response
        last_exc: httpx.RequestError | None = None
        for attempt in range(max_retries):
            try:
                response = await client.get(path, params=params)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_exc = exc
                await asyncio.sleep(min(2**attempt, 5))
                continue
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 2))
                await asyncio.sleep(retry_after)
                continue
            return response
        if last_exc is not None:
            raise RechercheEntreprisesError(
                f"Erreur réseau après {max_retries} tentatives : {last_exc}"
            ) from last_exc
        return response


_QUALITE_CODES: dict[str, str] = {
    "P": "Président",
    "D": "Directeur général",
    "C": "Gérant",
    "A": "Administrateur",
    "V": "Directeur général délégué",
    "X": "Président du conseil d'administration",
    "F": "Liquidateur",
}


_NON_EXEC_KEYWORDS = (
    "commissaire", "auditeur", "censeur",
    "conseil de surveillance", "observateur",
)


def _is_commissaire(qualite: str) -> bool:
    return any(kw in qualite.lower() for kw in _NON_EXEC_KEYWORDS)


def extract_dirigeant_principal(result: dict) -> dict:
    """Extrait le dirigeant principal depuis le résultat de l'API.

    Ignore les commissaires aux comptes et auditeurs — prend le premier
    vrai dirigeant (Président, Gérant, DG, etc.).
    """
    dirigeants = result.get("dirigeants", [])
    if not dirigeants:
        return {}

    dirigeant = None
    for d in dirigeants:
        qualite_raw = (d.get("qualite") or "").strip()
        if not _is_commissaire(qualite_raw):
            dirigeant = d
            break

    if dirigeant is None:
        return {}

    prenoms = dirigeant.get("prenoms") or ""
    nom = dirigeant.get("nom") or ""
    qualite_raw = (dirigeant.get("qualite") or "").strip()
    titre = qualite_raw if qualite_raw else None

    return {
        "prenom_dirigeant": prenoms.strip().title() if prenoms.strip() else None,
        "nom_dirigeant": nom.strip().upper() if nom.strip() else None,
        "titre_dirigeant": titre,
    }


def extract_contact_info(result: dict) -> dict:
    """Extrait téléphone, site web, géoloc, CA, CA N-1 et résultat net depuis le résultat de l'API."""
    siege = result.get("siege", {})

    telephone = siege.get("telephone") or None
    site_web = siege.get("site_internet") or None

    def _to_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    latitude = _to_float(siege.get("latitude"))
    longitude = _to_float(siege.get("longitude"))

    # finances: {"2024": {"ca": 1500000, "resultat_net": 80000}, "2023": {...}, ...}
    ca: int | None = None
    ca_n1: int | None = None
    resultat_net: int | None = None
    finances = result.get("finances") or {}
    if isinstance(finances, dict) and finances:
        years = sorted(finances.keys(), reverse=True)
        year_data = finances[years[0]] or {}
        raw_ca = year_data.get("ca")
        raw_rn = year_data.get("resultat_net")
        try:
            ca = int(float(raw_ca)) if raw_ca is not None else None
        except (ValueError, TypeError):
            ca = None
        try:
            resultat_net = int(float(raw_rn)) if raw_rn is not None else None
        except (ValueError, TypeError):
            resultat_net = None
        # CA N-1 depuis la deuxième année disponible
        if len(years) >= 2:
            prev_data = finances[years[1]] or {}
            raw_ca_n1 = prev_data.get("ca")
            try:
                ca_n1 = int(float(raw_ca_n1)) if raw_ca_n1 is not None else None
            except (ValueError, TypeError):
                ca_n1 = None

    return {
        "telephone": telephone,
        "site_web": site_web,
        "latitude": latitude,
        "longitude": longitude,
        "ca": ca,
        "ca_n1": ca_n1,
        "resultat_net": resultat_net,
    }


async def enrich_from_siret(siret: str) -> dict:
    """Point d'entrée principal : retourne un dict de champs enrichis pour un SIRET."""
    client = RechercheEntreprisesClient()
    result = await client.get_by_siret(siret)
    if result is None:
        return {}

    await asyncio.sleep(REQUEST_DELAY_SECONDS)

    enriched: dict = {}
    enriched.update(extract_dirigeant_principal(result))
    enriched.update(extract_contact_info(result))
    return enriched
