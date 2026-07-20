import asyncio
import httpx
from app.agents.veille.normalizer import current_secteur
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
    groups = [
        _or_group("activitePrincipaleEtablissement", codes_naf, period=True),
        _or_group("codePostalEtablissement", codes_postaux, period=False),
        _or_group("trancheEffectifsEtablissement", tranches_effectifs, period=False),
        "periode(etatAdministratifEtablissement:A)",
    ]
    return " AND ".join(groups)


class SireneClient:

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.INSEE_API_KEY
        self.base_url = (base_url or settings.INSEE_SIRENE_BASE_URL).rstrip("/")

    async def search_etablissements(
        self,
        codes_naf: list[str],
        codes_postaux: list[str],
        tranches_effectifs: list[str],
        quota: int,
        exclude_sirets: set[str] | None = None,
    ) -> tuple[list[dict], int]:
    
        if not self.api_key:
            raise SireneConfigError("INSEE_API_KEY non configurée (voir backend/.env)")

        exclude = exclude_sirets or set()
        naf_cibles = set(codes_naf)
        query = build_query(codes_naf, codes_postaux, tranches_effectifs)
        page_size = settings.SIRENE_PAGE_SIZE
        results: list[dict] = []
        seen: set[str] = set()  # dédup intra-pagination
        debut = 0
        total_sirene = 0

        headers = {"X-INSEE-Api-Key-Integration": self.api_key, "Accept": "application/json"}

        async with httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=15.0
        ) as client:
            while len(results) < quota:
                response = await self._get_with_retry(
                    client, "/siret", {"q": query, "nombre": page_size, "debut": debut}
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

                debut += len(etablissements)

                for etab in etablissements:
                    siret = etab.get("siret", "")
                    if not siret or siret in exclude or siret in seen:
                        continue
                    if current_secteur(etab) not in naf_cibles:
                        continue
                    seen.add(siret)
                    results.append(etab)

                total = data.get("header", {}).get("total")
                if total is not None:
                    total_sirene = total
                    if debut >= total:
                        break

                if len(results) < quota:
                    await asyncio.sleep(settings.SIRENE_REQUEST_DELAY_SECONDS)

        return results[:quota], total_sirene

    async def count_etablissements(
        self,
        codes_naf: list[str],
        codes_postaux: list[str],
        tranches_effectifs: list[str],
    ) -> int:
        """Nombre total d'établissements SIRENE correspondant aux critères.

        Une seule requête (nombre=1) : on ne lit que header.total, sans
        télécharger les fiches. Sert à l'estimation du vivier disponible
        affichée avant le lancement d'une campagne."""
        if not self.api_key:
            raise SireneConfigError("INSEE_API_KEY non configurée (voir backend/.env)")

        query = build_query(codes_naf, codes_postaux, tranches_effectifs)
        headers = {"X-INSEE-Api-Key-Integration": self.api_key, "Accept": "application/json"}

        async with httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=15.0
        ) as client:
            response = await self._get_with_retry(
                client, "/siret", {"q": query, "nombre": 1, "debut": 0}
            )
            if response.status_code == 404:
                return 0  # zéro résultat pour cette requête : pas une erreur
            if response.status_code != 200:
                raise SireneAPIError(
                    f"Erreur API SIRENE ({response.status_code}) : {response.text[:300]}"
                )
            return response.json().get("header", {}).get("total", 0)

    async def _get_with_retry(
        self, client: httpx.AsyncClient, path: str, params: dict, max_retries: int = 3
    ) -> httpx.Response:
        response: httpx.Response
        for _ in range(max_retries):
            response = await client.get(path, params=params)
            if response.status_code == 429:
                # On plafonne à 30s pour ne pas bloquer le worker indéfiniment
                # même si l'API demande un délai plus long.
                retry_after = min(float(response.headers.get("Retry-After", 5)), 30.0)
                await asyncio.sleep(retry_after)
                continue
            return response
        return response
