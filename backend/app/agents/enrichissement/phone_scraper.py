"""Extraction du numéro de téléphone professionnel depuis la homepage d'un site.

Patterns supportés (numéros français) :
  - 01 23 45 67 89  /  01.23.45.67.89  /  0123456789
  - +33 1 23 45 67 89  /  +33123456789
  - 0033 1 23 45 67 89

Validation et normalisation via la librairie `phonenumbers` (Google libphonenumber,
Apache 2.0). Préfère les fixes (01-05, 09) aux mobiles (06-07).
"""

import re

import httpx
import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType

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


def _normalize_phone(raw: str) -> str | None:
    """Valide et normalise un numéro français ; retourne None si invalide ou non-français."""
    try:
        parsed = phonenumbers.parse(raw, "FR")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    if parsed.country_code != 33:
        return None
    return phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)


def _is_fixe(parsed: phonenumbers.PhoneNumber) -> bool:
    return phonenumbers.number_type(parsed) in (
        PhoneNumberType.FIXED_LINE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
        PhoneNumberType.VOIP,  # 09 (internet/box) — considérés fixes pour la prospection
    )


def _pick_best_phone(candidates: list[str]) -> str | None:
    """Valide chaque candidat via phonenumbers et préfère les fixes."""
    if not candidates:
        return None

    validated: list[tuple[str, bool]] = []  # (formatted, is_fixe)
    for raw in candidates:
        try:
            parsed = phonenumbers.parse(raw, "FR")
        except phonenumbers.NumberParseException:
            continue
        if not phonenumbers.is_valid_number(parsed):
            continue
        formatted = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
        validated.append((formatted, _is_fixe(parsed)))

    if not validated:
        return None

    fixe = [num for num, is_f in validated if is_f]
    return fixe[0] if fixe else validated[0][0]


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
