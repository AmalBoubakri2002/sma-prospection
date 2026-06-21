"""Extraction du numéro de téléphone professionnel depuis la homepage d'un site.

Patterns supportés (numéros français) :
  - 01 23 45 67 89  /  01.23.45.67.89  /  0123456789
  - +33 1 23 45 67 89  /  +33123456789
  - 0033 1 23 45 67 89
Filtre les numéros probablement non-professionnels (portable 06/07 si pas de
fixe disponible, mais les garde en fallback).
"""

import re

import httpx

_USER_AGENT = "Mozilla/5.0 (compatible; SMA-ProspectAI/1.0)"
_TIMEOUT = 8.0

# Capture les numéros sous toutes les formes françaises courantes
_PHONE_RE = re.compile(
    r"""
    (?:
        (?:\+33|0033)[\s.\-]?       # Préfixe international
        (?:\(0\)[\s.\-]?)?          # (0) optionnel
        [1-9]                        # Indicatif (1-9)
    |
        0[1-9]                       # Format national : 0X
    )
    (?:[\s.\-]?\d{2}){4}            # 4 groupes de 2 chiffres
    """,
    re.VERBOSE,
)

# Indicatifs fixes métropolitains : 01-05 et 09
_FIXE_RE = re.compile(r"^(?:\+33|0033)?[\s.\-]?\(?0?\)?[\s.\-]?[1-5,9]")


def _normalize_phone(raw: str) -> str:
    """Normalise en format 0X XX XX XX XX."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    if digits.startswith("0033") and len(digits) == 13:
        digits = "0" + digits[4:]
    if len(digits) == 10:
        return " ".join(digits[i:i+2] for i in range(0, 10, 2))
    return raw.strip()


def _pick_best_phone(candidates: list[str]) -> str | None:
    """Préfère un fixe (01-05, 09) plutôt qu'un mobile (06-07)."""
    if not candidates:
        return None
    fixe = [p for p in candidates if _FIXE_RE.match(p)]
    chosen = fixe[0] if fixe else candidates[0]
    return _normalize_phone(chosen)


async def scrape_phone_from_homepage(site_web: str) -> str | None:
    """Retourne le premier numéro de téléphone professionnel trouvé, ou None."""
    url = site_web if site_web.startswith("http") else f"https://{site_web}"
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except (httpx.RequestError, httpx.HTTPStatusError):
        return None

    if response.status_code != 200:
        return None

    candidates = _PHONE_RE.findall(response.text)
    return _pick_best_phone(candidates)
