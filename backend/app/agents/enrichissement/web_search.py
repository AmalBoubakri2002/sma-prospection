"""Recherche du site web officiel d'une entreprise via DuckDuckGo HTML.

Utilise l'endpoint HTML de DuckDuckGo (pas de clé API requise).
Filtre les résultats génériques (Wikipedia, societe.com, pages jaunes, etc.)
pour ne garder que le site officiel de l'entreprise.
"""

import logging
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("agent-enrichissement")

_DDG_URL = "https://html.duckduckgo.com/html/"
_DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SMA-ProspectAI/1.0)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
_TIMEOUT = 10.0

# Domaines à exclure : annuaires, réseaux sociaux, presse
_EXCLUDED_DOMAINS = frozenset([
    "wikipedia.org", "fr.wikipedia.org",
    "societe.com", "pappers.fr", "infogreffe.fr",
    "pagesjaunes.fr", "kompass.com", "manageo.fr",
    "verif.com", "societe.ninja", "bfmtv.com",
    "lefigaro.fr", "lemonde.fr", "lesechos.fr",
    "linkedin.com", "facebook.com", "twitter.com",
    "youtube.com", "instagram.com",
    "bodacc.fr", "data.gouv.fr", "legifrance.gouv.fr",
    "infonet.fr", "societe-info.com", "sirene.fr",
    "annuaire-des-entreprises.commerce.gouv.fr",
    "cataloxy.org", "cataloxy.fr", "europages.fr", "europages.com",
    "cylex.fr", "hotfrog.fr", "yelp.com", "yelp.fr",
])

# DDG retourne des URLs directes dans les liens result__a
_RESULT_A_RE = re.compile(r'class="result__a"[^>]*href="(https?://[^"]+)"')


def _domain_keywords(company_name: str) -> list[str]:
    """Extrait les mots significatifs du nom d'entreprise pour valider le domaine."""
    # Retire les mots génériques (formes juridiques, prépositions)
    _STOP = {"consulting", "france", "groupe", "group", "solutions", "services",
              "sas", "sarl", "sa", "de", "du", "et", "le", "la", "les", "management",
              "technology", "technologies", "and", "ile", "idf"}
    words = re.findall(r"[a-z0-9]+", company_name.lower())
    return [w for w in words if w not in _STOP and len(w) >= 3]


def _root_domain(hostname: str) -> str:
    """Retourne le domaine racine (ex: sainoo.com depuis alsid.sainoo.com)."""
    parts = hostname.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else hostname


def _root_name(hostname: str) -> str:
    """Retourne le nom de domaine sans TLD (ex: 'xmco' depuis 'xmco.fr')."""
    parts = hostname.split(".")
    return parts[-2] if len(parts) >= 2 else hostname


def _is_valid_company_url(url: str, company_name: str = "") -> bool:
    """Rejette les annuaires et domaines non pertinents.

    Double validation :
    1. Blacklist annuaires/réseaux sociaux
    2. Un mot-clé du nom d'entreprise doit apparaître dans le DOMAINE RACINE
       (ex: alsid.sainoo.com → root = sainoo.com → 'alsid' absent → rejeté)
    """
    try:
        parsed = urlparse(url)
        hostname = re.sub(r"^www\.", "", parsed.hostname or "")
        root = _root_domain(hostname)

        # Blacklist annuaires
        if any(root == exc or root.endswith("." + exc) for exc in _EXCLUDED_DOMAINS):
            return False

        if company_name:
            keywords = _domain_keywords(company_name)
            if not keywords:
                return True
            root_name = _root_name(hostname)
            # Le mot-clé doit apparaître dans le nom racine du domaine,
            # ET le mot-clé doit être "significatif" (>= 5 chars OU constituer
            # au moins 50% du nom racine) pour éviter les faux positifs sur
            # des mots courts comme 'deep', 'log', 'neo'
            def _keyword_matches(kw: str) -> bool:
                if kw not in root_name:
                    return False
                return len(kw) >= 5 or (len(kw) / max(len(root_name), 1) >= 0.5)

            if not any(_keyword_matches(kw) for kw in keywords):
                return False

        return True
    except Exception:
        return False


async def find_company_website(company_name: str, ville: str = "") -> str | None:
    """Retourne l'URL du site officiel de l'entreprise, ou None si non trouvé.

    Requête : '<company_name> <ville> site officiel'
    """
    query = f"{company_name} {ville} site officiel".strip()
    try:
        async with httpx.AsyncClient(
            headers=_DDG_HEADERS,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.post(
                _DDG_URL,
                data={"q": query, "b": "", "kl": "fr-fr"},
            )
        # DDG retourne 202 ou la page d'accueil quand il throttle les requêtes
        if response.status_code != 200 or "result__a" not in response.text:
            logger.debug("DuckDuckGo a throttlé la requête pour '%s'", company_name)
            return None
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.debug("DuckDuckGo search failed for '%s': %s", company_name, exc)
        return None

    # DDG retourne des URLs directes dans les balises <a class="result__a">
    for match in _RESULT_A_RE.finditer(response.text):
        url = match.group(1)
        if _is_valid_company_url(url, company_name):
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"

    return None
