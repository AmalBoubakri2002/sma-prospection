import asyncio

import httpx

from app.core.config import settings


class SireneAPIError(Exception):
    pass


class SireneConfigError(SireneAPIError):
    """Erreur de configuration (clé manquante, URL invalide) — aucun retry utile."""
    pass


def _or_group(field: str, values: list[str], period: bool) -> str:
    if period:
        parts = [f"periode({field}:{v})" for v in values]
    else:
        parts = [f"{field}:{v}" for v in values]
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def build_query(
    codes_naf: list[str], codes_postaux: list[str], tranches_effectifs: list[str]
) -> str:
    """Construit le paramètre `q` de l'API Sirene. Vérifié empiriquement contre
    l'API réelle (juin 2026) : activitePrincipaleEtablissement et
    etatAdministratifEtablissement doivent être enveloppés dans periode(...),
    mais codePostalEtablissement et trancheEffectifsEtablissement non
    (sinon l'API renvoie une 400 "Erreur de syntaxe dans le paramètre q")."""
    groups = [
        _or_group("activitePrincipaleEtablissement", codes_naf, period=True),
        _or_group("codePostalEtablissement", codes_postaux, period=False),
        _or_group("trancheEffectifsEtablissement", tranches_effectifs, period=False),
        "periode(etatAdministratifEtablissement:A)",
    ]
    return " AND ".join(groups)


class SireneClient:
    """Client pour l'API Sirene (INSEE) — recherche multi-critères d'établissements.

    Auth par clé unique dans le header X-INSEE-Api-Key-Integration (portail-api.insee.fr).
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.INSEE_API_KEY
        self.base_url = (base_url or settings.INSEE_SIRENE_BASE_URL).rstrip("/")

    async def search_etablissements(
        self,
        codes_naf: list[str],
        codes_postaux: list[str],
        tranches_effectifs: list[str],
        quota: int,
    ) -> tuple[list[dict], int]:
        """Retourne (établissements, total_sirene).

        total_sirene est le nombre total d'établissements correspondant aux critères
        dans SIRENE, indépendamment du quota. Vaut 0 si l'API ne renvoie pas cette info."""
        if not self.api_key:
            raise SireneConfigError("INSEE_API_KEY non configurée (voir backend/.env)")

        query = build_query(codes_naf, codes_postaux, tranches_effectifs)
        page_size = min(settings.SIRENE_PAGE_SIZE, quota)
        results: list[dict] = []
        debut = 0
        total_sirene = 0

        headers = {"X-INSEE-Api-Key-Integration": self.api_key, "Accept": "application/json"}

        async with httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=15.0
        ) as client:
            while len(results) < quota:
                nombre = min(page_size, quota - len(results))
                response = await self._get_with_retry(
                    client, "/siret", {"q": query, "nombre": nombre, "debut": debut}
                )

                if response.status_code == 404:
                    break  # zéro résultat pour cette requête : pas une erreur
                if response.status_code != 200:
                    raise SireneAPIError(
                        f"Erreur API SIRENE ({response.status_code}) : {response.text[:300]}"
                    )

                data = response.json()
                etablissements = data.get("etablissements", [])
                if not etablissements:
                    break

                results.extend(etablissements)
                debut += len(etablissements)

                total = data.get("header", {}).get("total")
                if total is not None:
                    total_sirene = total
                    if debut >= total:
                        break

                if len(results) < quota:
                    await asyncio.sleep(settings.SIRENE_REQUEST_DELAY_SECONDS)

        return results[:quota], total_sirene

    async def _get_with_retry(
        self, client: httpx.AsyncClient, path: str, params: dict, max_retries: int = 3
    ) -> httpx.Response:
        response: httpx.Response
        for _ in range(max_retries):
            response = await client.get(path, params=params)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                continue
            return response
        return response
