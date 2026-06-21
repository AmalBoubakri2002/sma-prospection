"""Scraping d'email professionnel sur la page d'accueil du site web.

Stratégie : GET {site_web}, chercher le premier email non-générique dans le HTML.
Emails filtrés : noreply, support, contact générique, webmaster, etc.
Ne fonctionne que si lead.site_web est renseigné.
"""

import re
from urllib.parse import urlparse

import httpx

# Exclut les noms de fichiers d'images responsives (@2x.png, @2x.webp, etc.)
_IMAGE_EXTS = frozenset(["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp", "avif"])

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

_GENERIC_PREFIXES = frozenset(
    [
        "noreply", "no-reply", "donotreply", "support", "contact",
        "info", "hello", "webmaster", "admin", "postmaster",
        "abuse", "help", "service", "newsletter", "marketing",
    ]
)

# Mots géographiques indiquant un bureau étranger (hello-spain@, london@, etc.)
_GEO_WORDS = frozenset([
    "spain", "espagne", "london", "uk", "us", "usa", "france",
    "paris", "berlin", "amsterdam", "rome", "milan", "madrid",
    "barcelona", "germany", "deutschland", "italia", "netherlands",
    "singapore", "dubai", "india", "australia", "canada", "brazil",
    "mexico", "japan", "china", "korea", "russia", "turkey",
    "sweden", "norway", "denmark", "finland", "portugal", "poland",
    "brussels", "zurich", "vienna", "prague", "warsaw", "budapest",
])

# Domaines d'infrastructure à ignorer (monitoring, CMS, analytics)
_INFRA_DOMAINS = frozenset([
    "sentry.io", "sentry-next.wixpress.com", "wixpress.com",
    "googleapis.com", "googletagmanager.com", "doubleclick.net",
    "hotjar.com", "hubspot.com", "mailchimp.com", "sendgrid.net",
    "amazonaws.com", "cloudfront.net", "example.com", "example.org",
])

USER_AGENT = "SMA-ProspectAI/1.0 (recherche-entreprises B2B)"

# Préfixes de placeholder courants dans les templates de sites
_PLACEHOLDER_PREFIXES = frozenset(["exemple", "example", "test", "demo", "sample", "your"])
# Domaines de placeholder courants
_PLACEHOLDER_DOMAINS = frozenset(["monsite.com", "monadresse.com", "votresite.com",
                                    "yoursite.com", "domain.com", "yourdomain.com"])


def _site_domain(site_web: str) -> str | None:
    """Extrait le domaine racine du site web (ex: lumapps.com depuis www.lumapps.com)."""
    try:
        host = urlparse(site_web).hostname or ""
        parts = re.sub(r"^www\.", "", host).split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else None
    except Exception:
        return None


async def scrape_email_from_homepage(site_web: str) -> str | None:
    """Retourne le premier email professionnel trouvé sur la homepage, ou None."""
    url = site_web if site_web.startswith("http") else f"https://{site_web}"
    company_domain = _site_domain(url)

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=8.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except (httpx.RequestError, httpx.HTTPStatusError):
        return None

    if response.status_code != 200:
        return None

    emails = _EMAIL_RE.findall(response.text)
    for email in emails:
        parts = email.lower().split("@")
        if len(parts) != 2:
            continue
        prefix, domain = parts
        tld = domain.rsplit(".", 1)[-1].lower()
        if tld in _IMAGE_EXTS:
            continue
        if prefix in _GENERIC_PREFIXES or prefix in _PLACEHOLDER_PREFIXES:
            continue
        # Rejette les emails de bureaux étrangers : hello-spain@, london@, uk@...
        prefix_parts = re.split(r"[-_.]", prefix)
        if any(p in _GENERIC_PREFIXES or p in _GEO_WORDS for p in prefix_parts):
            continue
        if domain in _PLACEHOLDER_DOMAINS:
            continue
        if any(domain == d or domain.endswith("." + d) for d in _INFRA_DOMAINS):
            continue
        # Rejette les hashs hexadécimaux (emails d'infrastructure auto-générés)
        if len(prefix) >= 16 and all(c in "0123456789abcdef" for c in prefix):
            continue
        # Vérifie que le domaine de l'email est cohérent avec le site de l'entreprise
        if company_domain and not (domain == company_domain or domain.endswith("." + company_domain)):
            continue
        return email

    return None
