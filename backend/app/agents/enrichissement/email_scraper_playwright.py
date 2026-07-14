# Fallback email scraper pour les sites à rendu JavaScript (SPA, React, Vue…). N'est appelé que lorsque le scraper httpx standard échoue.

import logging

from app.agents.enrichissement.email_scraper import extract_email_from_html

logger = logging.getLogger("agent-enrichissement")

_PLAYWRIGHT_TIMEOUT_MS = 15_000  # 15 s max pour le rendu JS


async def scrape_email_playwright(site_web: str) -> str | None:
    """Rend la page avec Playwright (Chromium headless) et cherche un email."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        return None

    url = site_web if site_web.startswith("http") else f"https://{site_web}"
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=_PLAYWRIGHT_TIMEOUT_MS)
                html = await page.content()
            finally:
                await browser.close()
    except Exception as exc:
        logger.debug("Playwright échoué pour %s : %s", site_web, exc)
        return None

    return extract_email_from_html(html, url)
