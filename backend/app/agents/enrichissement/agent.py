"""Agent Enrichissement — étape 2 du pipeline SMA-PC ProspectAI.

Sources utilisées (toutes gratuites, sans clé) :
  1. recherche-entreprises.api.gouv.fr → dirigeant, téléphone, site_web, CA, résultat net
  2. INPI (data.inpi.fr)               → CA / résultat net (fallback si absent de source 1)
  3. DuckDuckGo HTML search            → site_web (fallback si absent de l'API officielle)
  4. Scraping homepage                  → email (scraping puis génération par pattern)
  5. Scraping homepage                  → téléphone (si absent de l'API officielle)
  6. Nominatim (OpenStreetMap)          → latitude / longitude
"""

import asyncio
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.enrichissement.email_guesser import guess_email
from app.agents.enrichissement.email_scraper import scrape_email_from_homepage
from app.agents.enrichissement.inpi import InpiError, get_finances_from_siren
from app.agents.enrichissement.nominatim import geocode_address
from app.agents.enrichissement.phone_scraper import scrape_phone_from_homepage
from app.agents.enrichissement.recherche_entreprises import (
    RechercheEntreprisesError,
    enrich_from_siret,
)
from app.agents.enrichissement.web_search import find_company_website
from app.models.campaign import Campaign
from app.services.lead import get_enriched_fields_by_siret, list_leads_to_enrich, update_lead_enriched

logger = logging.getLogger("agent-enrichissement")

_CITY_RE = re.compile(r"\b(\d{5})\s+(.+)$")


def _extract_ville(adresse: str | None) -> str:
    """Extrait la ville depuis une adresse du type '12 RUE TRUC, 75008 PARIS'."""
    if not adresse:
        return ""
    match = _CITY_RE.search(adresse)
    return match.group(2).title() if match else ""


_ENRICHMENT_FIELDS = frozenset({
    "telephone", "site_web", "ca", "resultat_net",
    "prenom_dirigeant", "nom_dirigeant", "titre_dirigeant",
    "email", "latitude", "longitude",
})


def _compute_score_intent(fields: dict, lead) -> float:
    """Proxy de joignabilité : score 0-1 basé sur la complétude du profil enrichi.

    Pondération : email ×2 (le contact le plus précieux), puis téléphone,
    site web, dirigeant identifié, CA connu — normalisé sur un max de 6 points.
    """
    a_email     = 1.0 if (fields.get("email")            or lead.email)            else 0.0
    a_phone     = 1.0 if (fields.get("telephone")        or lead.telephone)        else 0.0
    a_web       = 1.0 if (fields.get("site_web")         or lead.site_web)         else 0.0
    a_dirigeant = 1.0 if (fields.get("prenom_dirigeant") or lead.prenom_dirigeant) else 0.0
    a_ca        = 1.0 if (fields.get("ca")  is not None  or lead.ca  is not None)  else 0.0
    return round((a_email * 2 + a_phone + a_web + a_dirigeant + a_ca) / 6.0, 4)


async def run_enrichissement(db: AsyncSession, campaign: Campaign) -> dict:
    total_processed = 0
    total_with_data = 0
    total_errors = 0

    while True:
        leads = await list_leads_to_enrich(db, campaign.id)
        if not leads:
            break

        for lead in leads:
            fields: dict = {}

            # — Réutilisation cross-campagne : si ce SIRET a déjà été enrichi dans une
            # autre campagne, on réutilise directement ses données (même téléphone,
            # même email, même date_creation) sans rappeler les API. —
            cached = await get_enriched_fields_by_siret(db, lead.siret)
            if cached:
                fields.update(cached)
                fields["score_intent"] = _compute_score_intent(fields, lead)
                await update_lead_enriched(db, lead, fields)
                total_processed += 1
                total_with_data += 1
                logger.debug("Lead %s réutilisé depuis cache SIRET (cross-campagne)", lead.siret)
                continue

            # — Source 1 : recherche-entreprises (dirigeant, contact, finances) —
            try:
                data = await enrich_from_siret(lead.siret)
                fields.update(data)
            except RechercheEntreprisesError as exc:
                logger.warning("recherche-entreprises échoué pour %s : %s", lead.siret, exc)
                total_errors += 1

            # — Source 2 : INPI — toujours appelé pour ca_n1 (données multi-années).
            # ca et résultat_net utilisés uniquement en fallback si source 1 est vide. —
            siren = lead.siret[:9]
            try:
                inpi_data = await get_finances_from_siren(siren)
                # ca_n1 vient exclusivement d'INPI (multi-années indisponibles ailleurs)
                if inpi_data.get("ca_n1") is not None:
                    fields.setdefault("ca_n1", inpi_data["ca_n1"])
                # ca et résultat_net : seulement si source 1 n'a rien retourné
                if not fields.get("ca"):
                    if inpi_data.get("ca") is not None:
                        fields.setdefault("ca", inpi_data["ca"])
                    if inpi_data.get("resultat_net") is not None:
                        fields.setdefault("resultat_net", inpi_data["resultat_net"])
            except InpiError as exc:
                logger.warning("INPI échoué pour %s : %s", lead.siret, exc)

            # — Source 3 : site web (fallback DuckDuckGo si absent de l'API) —
            site_web = fields.get("site_web") or lead.site_web
            if not site_web:
                ville = _extract_ville(lead.adresse)
                await asyncio.sleep(1.0)  # évite le rate-limiting DDG
                found = await find_company_website(lead.company_name, ville)
                if found:
                    site_web = found
                    fields["site_web"] = found
                    logger.info("Site trouvé via DDG pour %s : %s", lead.company_name, found)

            # — Source 4 : email (scraping puis génération par pattern) —
            if site_web:
                scraped = await scrape_email_from_homepage(site_web)
                if scraped:
                    fields["email"] = scraped
                elif not fields.get("email"):
                    generated = guess_email(
                        prenom=fields.get("prenom_dirigeant"),
                        nom=fields.get("nom_dirigeant"),
                        site_web=site_web,
                    )
                    if generated:
                        fields["email"] = generated

            # — Source 5 : téléphone (scraping homepage si absent de l'API) —
            if not fields.get("telephone") and site_web:
                phone = await scrape_phone_from_homepage(site_web)
                if phone:
                    fields["telephone"] = phone

            # — Source 6 : Nominatim (GPS) —
            if lead.adresse:
                coords = await geocode_address(lead.adresse)
                if coords:
                    fields["latitude"], fields["longitude"] = coords

            has_data = any(fields.get(f) is not None for f in _ENRICHMENT_FIELDS)
            if has_data:
                total_with_data += 1

            # Score de joignabilité — toujours calculé, même si aucune source n'a répondu
            fields["score_intent"] = _compute_score_intent(fields, lead)

            # Le lead passe toujours en ENRICHI pour ne pas re-boucler indéfiniment.
            # has_data distingue un enrichissement réel d'un lead sans données disponibles.
            await update_lead_enriched(db, lead, fields)
            total_processed += 1
            logger.debug(
                "Lead %s traité (données: %s) : %s", lead.siret, has_data, lead.company_name
            )

    logger.info(
        "Campagne %s — enrichissement : %d traités, %d avec données, %d erreurs API",
        campaign.id,
        total_processed,
        total_with_data,
        total_errors,
    )
    return {
        "leads_enrichis": total_processed,
        "leads_avec_donnees": total_with_data,
        "leads_erreurs": total_errors,
    }
