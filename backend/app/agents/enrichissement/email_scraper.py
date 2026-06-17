"""Scraping d'email professionnel sur la page d'accueil du site web.

Stratégie : GET {site_web}, chercher le premier email non-générique dans le HTML.
Emails filtrés : noreply, support, contact générique, webmaster, etc.
Ne fonctionne que si lead.site_web est renseigné.
"""

import re

import httpx

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

USER_AGENT = "SMA-ProspectAI/1.0 (recherche-entreprises B2B)"


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

    emails = _EMAIL_RE.findall(response.text)
    for email in emails:
        prefix = email.split("@")[0].lower()
        if prefix not in _GENERIC_PREFIXES:
            return email.lower()

    return None
