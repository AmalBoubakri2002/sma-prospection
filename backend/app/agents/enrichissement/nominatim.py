"""Client Nominatim (OpenStreetMap) — géocodage d'adresse en coordonnées GPS.

Contraintes imposées par la politique d'usage Nominatim :
  - User-Agent obligatoire identifiant l'application
  - Maximum 1 requête/seconde
  - Pas de scraping en masse sans hébergement propre de l'instance

Référence : https://operations.osmfoundation.org/policies/nominatim/
"""

import asyncio

import httpx

BASE_URL = "https://nominatim.openstreetmap.org"
REQUEST_DELAY_SECONDS = 1.1  # légèrement au-dessus de 1s pour rester safe
USER_AGENT = "SMA-ProspectAI/1.0 (geocodage-leads-b2b)"


async def geocode_address(adresse: str) -> tuple[float, float] | None:
    """Retourne (latitude, longitude) pour une adresse, ou None si introuvable."""
    if not adresse or not adresse.strip():
        return None

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "fr"},
        timeout=10.0,
    ) as client:
        try:
            response = await client.get(
                "/search",
                params={"q": adresse, "format": "json", "limit": 1, "countrycodes": "fr"},
            )
        except httpx.RequestError:
            return None

    await asyncio.sleep(REQUEST_DELAY_SECONDS)

    if response.status_code != 200:
        return None

    results = response.json()
    if not results:
        return None

    try:
        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None

    return lat, lon
