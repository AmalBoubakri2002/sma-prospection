"""Scraping d'email professionnel sur la page d'accueil du site web.

Stratégie (dans l'ordre) :
  1. extruct — données structurées JSON-LD / Microdata (schema.org Organization, ContactPoint…)
  2. Regex  — balayage brut du HTML (fallback si extruct ne trouve rien)

Emails filtrés : noreply, support, contact générique, webmaster, etc.
Ne fonctionne que si lead.site_web est renseigné.
"""

import json
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

# Sous-domaines de staging/dev/versionnés (ex: site-neoxia-2022.neoxia.com)
_STAGING_RE = re.compile(
    r"\b(staging|dev|test|preprod|preview|beta|qa|demo|sandbox|local|uat)\b"
    r"|\b20\d{2}\b",  # années 2000–2099
    re.IGNORECASE,
)


def _site_domain(site_web: str) -> str | None:
    """Extrait le domaine racine du site web (ex: lumapps.com depuis www.lumapps.com)."""
    try:
        host = urlparse(site_web).hostname or ""
        parts = re.sub(r"^www\.", "", host).split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else None
    except Exception:
        return None


def is_valid_prospection_email(email: str, company_domain: str | None = None) -> bool:
    """Retourne True si l'email est exploitable pour une prospection B2B française.

    Appliqué à TOUTES les sources (API officielle, scraping, JSON-LD) pour éviter
    les emails de bureaux étrangers et de sous-domaines staging/versionnés.
    """
    parts = email.lower().split("@")
    if len(parts) != 2:
        return False
    prefix, domain = parts

    tld = domain.rsplit(".", 1)[-1].lower()
    if tld in _IMAGE_EXTS:
        return False

    if prefix in _GENERIC_PREFIXES or prefix in _PLACEHOLDER_PREFIXES:
        return False

    # Emails de bureaux géographiques : london@, spain@, hello-uk@…
    prefix_parts = re.split(r"[-_.]", prefix)
    if any(p in _GENERIC_PREFIXES or p in _GEO_WORDS for p in prefix_parts):
        return False

    if domain in _PLACEHOLDER_DOMAINS:
        return False

    if any(domain == d or domain.endswith("." + d) for d in _INFRA_DOMAINS):
        return False

    if len(prefix) >= 16 and all(c in "0123456789abcdef" for c in prefix):
        return False

    if company_domain:
        # Sous-domaine staging/versionné : site-neoxia-2022.neoxia.com
        if domain != company_domain and domain.endswith("." + company_domain):
            subdomain_part = domain[: -(len(company_domain) + 1)]
            if _STAGING_RE.search(subdomain_part):
                return False
        # Cohérence domaine avec le site de l'entreprise
        if not (domain == company_domain or domain.endswith("." + company_domain)):
            return False

    return True


# ── Extraction via données structurées (extruct) ─────────────────────────────

_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_EMAIL_KEYS = frozenset(["email", "contactEmail", "emailAddress"])


def _find_email_in_obj(obj: object, depth: int = 0) -> str | None:
    """Cherche récursivement un email dans un objet JSON-LD / Microdata."""
    if depth > 6:
        return None
    if isinstance(obj, list):
        for item in obj:
            result = _find_email_in_obj(item, depth + 1)
            if result:
                return result
    elif isinstance(obj, dict):
        for key in _EMAIL_KEYS:
            val = obj.get(key)
            if isinstance(val, str) and "@" in val:
                return val.strip()
        for val in obj.values():
            if isinstance(val, (dict, list)):
                result = _find_email_in_obj(val, depth + 1)
                if result:
                    return result
    return None


def _extract_email_from_structured_data(
    html: str, url: str, company_domain: str | None
) -> str | None:
    """Tente d'extraire un email depuis les blocs JSON-LD de la page.

    Utilise extruct si disponible (JSON-LD + Microdata), sinon parse les
    balises <script type="application/ld+json"> directement (fallback stdlib).
    Valide chaque email candidat via is_valid_prospection_email.
    """
    def _validated(raw: str | None) -> str | None:
        return raw if raw and is_valid_prospection_email(raw, company_domain) else None

    # ── Tentative extruct ─────────────────────────────────────────────────────
    try:
        import extruct  # type: ignore[import]
        data = extruct.extract(
            html, base_url=url, syntaxes=["json-ld", "microdata"], uniform=True
        )
        for item in data.get("json-ld", []) + data.get("microdata", []):
            email = _validated(_find_email_in_obj(item))
            if email:
                return email
        return None
    except Exception:
        pass  # extruct non installé ou erreur de parsing → fallback

    # ── Fallback stdlib : balises <script type="application/ld+json"> ─────────
    for match in _JSONLD_SCRIPT_RE.finditer(html):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        email = _validated(_find_email_in_obj(payload))
        if email:
            return email

    return None


# ── Extraction par regex brute ────────────────────────────────────────────────

def _extract_email_from_regex(html: str, company_domain: str | None) -> str | None:
    """Balayage regex du HTML brut — délègue la validation à is_valid_prospection_email."""
    for email in _EMAIL_RE.findall(html):
        if is_valid_prospection_email(email, company_domain):
            return email
    return None


# ── Point d'entrée public (réutilisé par le scraper Playwright) ──────────────

def extract_email_from_html(html: str, url: str) -> str | None:
    """Cherche un email dans le HTML rendu : extruct d'abord, regex en fallback."""
    company_domain = _site_domain(url)

    email = _extract_email_from_structured_data(html, url, company_domain)
    if email:
        return email

    return _extract_email_from_regex(html, company_domain)


async def scrape_email_from_homepage(site_web: str) -> str | None:
    """Retourne le premier email professionnel trouvé sur la homepage, ou None."""
    url = site_web if site_web.startswith("http") else f"https://{site_web}"

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

    return extract_email_from_html(response.text, url)
