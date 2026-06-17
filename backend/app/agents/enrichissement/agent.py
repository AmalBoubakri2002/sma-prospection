"""Agent Enrichissement — étape 2 du pipeline SMA-PC ProspectAI.

Sources utilisées (toutes gratuites, sans clé) :
  1. recherche-entreprises.api.gouv.fr → dirigeant, téléphone, site_web, CA, résultat net
  2. INPI (data.inpi.fr)               → CA / résultat net (fallback si absent de source 1)
  3. Scraping homepage                  → email (si site_web disponible)
  4. Nominatim (OpenStreetMap)          → latitude / longitude
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.enrichissement.email_guesser import guess_email
from app.agents.enrichissement.email_scraper import scrape_email_from_homepage
from app.agents.enrichissement.inpi import InpiError, get_finances_from_siren
from app.agents.enrichissement.nominatim import geocode_address
from app.agents.enrichissement.recherche_entreprises import (
    RechercheEntreprisesError,
    enrich_from_siret,
)
from app.models.campaign import Campaign
from app.services.lead import list_leads_to_enrich, update_lead_enriched

logger = logging.getLogger("agent-enrichissement")

_ENRICHMENT_FIELDS = frozenset({
    "telephone", "site_web", "ca", "resultat_net",
    "prenom_dirigeant", "nom_dirigeant", "titre_dirigeant",
    "email", "latitude", "longitude",
})


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

            # — Source 1 : recherche-entreprises (dirigeant, contact, finances) —
            try:
                data = await enrich_from_siret(lead.siret)
                fields.update(data)
            except RechercheEntreprisesError as exc:
                logger.warning("recherche-entreprises échoué pour %s : %s", lead.siret, exc)
                total_errors += 1

            # — Source 2 : INPI — fallback CA/résultat_net si absent de la source 1 —
            if not fields.get("ca"):
                siren = lead.siret[:9]
                try:
                    inpi_data = await get_finances_from_siren(siren)
                    if inpi_data.get("ca") is not None:
                        fields.setdefault("ca", inpi_data["ca"])
                    if inpi_data.get("resultat_net") is not None:
                        fields.setdefault("resultat_net", inpi_data["resultat_net"])
                except InpiError as exc:
                    logger.warning("INPI échoué pour %s : %s", lead.siret, exc)

            # — Source 3 : email (scraping ou génération par pattern) —
            site_web = fields.get("site_web") or lead.site_web
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

            # — Source 4 : Nominatim (GPS) —
            if lead.adresse:
                coords = await geocode_address(lead.adresse)
                if coords:
                    fields["latitude"], fields["longitude"] = coords

            has_data = any(fields.get(f) is not None for f in _ENRICHMENT_FIELDS)
            if has_data:
                total_with_data += 1

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
