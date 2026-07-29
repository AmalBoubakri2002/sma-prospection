#Agent Enrichissement : recherche-entreprises.api.gouv.fr + INPI/BODACC (fallback
# finances,procédures) + DuckDuckGo (site web) + scraping homepage/Playwright (email,
# téléphone) + Nominatim.

import asyncio
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.enrichissement.bodacc import BodaccError, get_procedure_from_bodacc
from app.agents.enrichissement.email_scraper import (
    _site_domain,
    is_valid_prospection_email,
    scrape_email_from_homepage,
)
from app.agents.enrichissement.email_scraper_playwright import scrape_email_playwright
from app.agents.enrichissement.inpi import InpiError, get_finances_from_siren
from app.agents.enrichissement.nominatim import geocode_address
from app.agents.enrichissement.phone_scraper import scrape_phone_from_homepage
from app.agents.enrichissement.recherche_entreprises import (
    RechercheEntreprisesError,
    enrich_from_siret,
)
from app.agents.enrichissement.shared import apply_inpi_fallback, compute_score_exploitabilite
from app.agents.enrichissement.web_search import find_company_website
from app.models.campaign import Campaign
from app.models.lead import LeadStatus
from app.services.lead import (
    get_enriched_fields_by_siret,
    list_leads_to_enrich,
    update_lead_enriched,
)

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


def _has_sufficient_financials(fields: dict, lead) -> bool:
    """Signale seulement (logs/stats) des données financières partielles ; ne décide plus
    du statut du lead. ca=0 est traité comme absent (comme ailleurs dans le pipeline),
    resultat_net=0 reste une vraie valeur connue."""
    ca = fields.get("ca") or lead.ca
    resultat_net = (
        fields.get("resultat_net") if fields.get("resultat_net") is not None else lead.resultat_net
    )
    return bool(ca) and resultat_net is not None


def _compute_score_exploitabilite(fields: dict, lead) -> float:
    """Comme shared.compute_score_exploitabilite, avec repli sur les champs déjà en
    base (lead réutilisé depuis un SIRET déjà enrichi)."""
    merged = {
        "email": fields.get("email") or lead.email,
        "telephone": fields.get("telephone") or lead.telephone,
        "site_web": fields.get("site_web") or lead.site_web,
        "prenom_dirigeant": fields.get("prenom_dirigeant") or lead.prenom_dirigeant,
    }
    return compute_score_exploitabilite(merged)


# TC = champs_renseignés / champs_totaux × 100
_CHAMPS_COMPLETUDE = [
    "email", "telephone", "site_web",
    "prenom_dirigeant", "nom_dirigeant",
    "ca", "secteur", "taille_entreprise",
    "adresse", "date_creation",
]


def _compute_completude(fields: dict, lead) -> float:
    """Retourne le pourcentage de champs clés renseignés (0.0 – 100.0)."""
    renseignes = sum(
        1 for champ in _CHAMPS_COMPLETUDE
        if fields.get(champ) is not None or getattr(lead, champ, None) is not None
    )
    return round(renseignes / len(_CHAMPS_COMPLETUDE) * 100, 1)


_LEAD_TIMEOUT = 45.0  # secondes max par lead (toutes sources confondues)


async def _enrich_one(db: AsyncSession, lead, db_lock: asyncio.Lock) -> tuple[dict, bool]:
    """Enrichit un lead depuis toutes les sources. Retourne (fields, has_data).

    db_lock sérialise les accès à `db`, partagée entre leads concurrents (une
    AsyncSession SQLAlchemy n'est pas sûre pour des appels concurrents)."""
    fields: dict = {}

    async with db_lock:
        cached = await get_enriched_fields_by_siret(db, lead.siret)
    if cached:
        fields.update(cached)
        fields["score_exploitabilite"] = _compute_score_exploitabilite(fields, lead)
        return fields, True

    # Sources 1-3 : indépendantes entre elles (aucune ne dépend du résultat
    # d'une autre), lancées concurremment pour diviser leur latence combinée
    # par ~3 au lieu de les attendre l'une après l'autre.
    siren = lead.siret[:9]
    data_result, inpi_result, bodacc_result = await asyncio.gather(
        enrich_from_siret(lead.siret),
        get_finances_from_siren(siren),
        get_procedure_from_bodacc(siren),
        return_exceptions=True,
    )

    if isinstance(data_result, RechercheEntreprisesError):
        logger.warning("recherche-entreprises échoué pour %s : %s", lead.siret, data_result)
    elif isinstance(data_result, BaseException):
        raise data_result
    else:
        data = data_result
        # Valide l'email de l'API avant d'injecter
        if "email" in data:
            api_domain = _site_domain(data.get("site_web") or "")
            if not is_valid_prospection_email(data["email"], api_domain):
                logger.debug(
                    "Email API rejeté pour %s : %s", lead.siret, data["email"]
                )
                del data["email"]
        fields.update(data)

    if isinstance(inpi_result, InpiError):
        logger.warning("INPI échoué pour %s : %s", lead.siret, inpi_result)
    elif isinstance(inpi_result, BaseException):
        raise inpi_result
    else:
        apply_inpi_fallback(fields, inpi_result)

    # ── Source 3 : BODACC — procédures collectives + confirmation dépôt comptes
    en_procedure = False
    if isinstance(bodacc_result, BodaccError):
        logger.warning("BODACC échoué pour %s : %s", lead.siret, bodacc_result)
    elif isinstance(bodacc_result, BaseException):
        raise bodacc_result
    else:
        en_procedure = bodacc_result.get("en_procedure_collective", False)
        if en_procedure:
            logger.info(
                "Lead %s (%s) — procédure collective détectée (BODACC)",
                lead.siret, lead.company_name,
            )

    site_web = fields.get("site_web") or lead.site_web
    if not site_web:
        ville = _extract_ville(lead.adresse)
        await asyncio.sleep(1.0)
        found = await find_company_website(lead.company_name, ville)
        if found:
            site_web = found
            fields["site_web"] = found

    if site_web:
        scraped = await scrape_email_from_homepage(site_web)
        if not scraped:
            scraped = await scrape_email_playwright(site_web)
        if scraped:
            fields["email"] = scraped

    if not fields.get("telephone") and site_web:
        phone = await scrape_phone_from_homepage(site_web)
        if phone:
            fields["telephone"] = phone

    if lead.adresse:
        coords = await geocode_address(lead.adresse)
        if coords:
            fields["latitude"], fields["longitude"] = coords

    has_data = any(fields.get(f) is not None for f in _ENRICHMENT_FIELDS)
    score_exploitabilite = 0.0 if en_procedure else _compute_score_exploitabilite(fields, lead)
    fields["score_exploitabilite"] = score_exploitabilite

    taux = _compute_completude(fields, lead)
    fields["taux_completude"] = taux
    if taux < 40.0:
        logger.warning(
            "Lead %s (%s) — taux de complétude faible : %.1f%% "
            "(données insuffisantes pour la personnalisation email)",
            lead.siret, lead.company_name, taux,
        )

    return fields, has_data


_ENRICH_CONCURRENCY = 5  # même ordre de grandeur que ml/dataset_pipeline.py::enrich_all


async def _enrich_and_save_one(
    db: AsyncSession, lead, semaphore: asyncio.Semaphore, db_lock: asyncio.Lock,
) -> tuple[bool, bool, bool]:
    """Enrichit un lead puis persiste le résultat. Retourne (has_data, errored,
    donnees_financieres_partielles). Borné par `semaphore` ; les accès à `db`
    passent par `db_lock` (voir _enrich_one)."""
    async with semaphore:
        errored = False
        try:
            fields, has_data = await asyncio.wait_for(
                _enrich_one(db, lead, db_lock), timeout=_LEAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Lead %s (%s) — timeout %gs, marqué ENRICHI sans données",
                lead.siret, lead.company_name, _LEAD_TIMEOUT,
            )
            fields = {"score_exploitabilite": 0.0}
            has_data = False
            errored = True
        except Exception as exc:
            logger.warning("Lead %s — erreur inattendue : %s", lead.siret, exc)
            fields = {"score_exploitabilite": 0.0}
            has_data = False
            errored = True

        donnees_financieres_partielles = not errored and not _has_sufficient_financials(
            fields, lead
        )

        async with db_lock:
            await update_lead_enriched(db, lead, fields, status=LeadStatus.ENRICHI)
        if donnees_financieres_partielles:
            logger.info(
                "Lead %s (%s) — CA/résultat net indisponibles à la source, "
                "scoré quand même sur données partielles",
                lead.siret, lead.company_name,
            )
        logger.debug(
            "Lead %s traité (données: %s) : %s", lead.siret, has_data, lead.company_name
        )
        return has_data, errored, donnees_financieres_partielles


async def run_enrichissement(db: AsyncSession, campaign: Campaign) -> dict:
    total_processed = 0
    total_with_data = 0
    total_errors = 0
    total_donnees_financieres_partielles = 0

    semaphore = asyncio.Semaphore(_ENRICH_CONCURRENCY)
    db_lock = asyncio.Lock()

    while True:
        leads = await list_leads_to_enrich(db, campaign.id)
        if not leads:
            break

        results = await asyncio.gather(
            *(_enrich_and_save_one(db, lead, semaphore, db_lock) for lead in leads),
            return_exceptions=True,
        )
        for lead, result in zip(leads, results):
            if isinstance(result, BaseException):
                logger.warning("Lead %s — échec inattendu du worker : %s", lead.siret, result)
                total_errors += 1
                continue
            has_data, errored, donnees_financieres_partielles = result
            total_processed += 1
            if has_data:
                total_with_data += 1
            if errored:
                total_errors += 1
            if donnees_financieres_partielles:
                total_donnees_financieres_partielles += 1

    logger.info(
        "Campagne %s — enrichissement : %d traités, %d avec données, %d erreurs API, "
        "%d scorés sur données financières partielles (CA/résultat net indisponibles)",
        campaign.id,
        total_processed,
        total_with_data,
        total_errors,
        total_donnees_financieres_partielles,
    )
    return {
        "leads_enrichis": total_processed,
        "leads_avec_donnees": total_with_data,
        "leads_donnees_financieres_partielles": total_donnees_financieres_partielles,
        "leads_erreurs": total_errors,
    }
