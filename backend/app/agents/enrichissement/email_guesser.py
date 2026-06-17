"""Génération d'email professionnel à partir du nom du dirigeant et du domaine.

Logique : prénom.nom@domaine — pattern le plus courant en B2B français.
L'email généré est une estimation non vérifiée ; la validation réelle (MX, SMTP)
est hors scope pour cette version.
"""

import re
import unicodedata


def _remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _slugify_name_part(part: str) -> str:
    """Transforme 'Jean-Pierre' → 'jean-pierre', 'O'Brien' → 'obrien'."""
    clean = _remove_accents(part.lower())
    # garde lettres, chiffres et tirets, retire le reste
    clean = re.sub(r"[^a-z0-9-]", "", clean)
    return clean


def extract_domain(site_web: str | None) -> str | None:
    """Extrait le domaine depuis une URL ou un nom de domaine brut.

    Exemples :
    - 'https://www.example.fr' → 'example.fr'
    - 'www.example.com'        → 'example.com'
    - 'example.io'             → 'example.io'
    """
    if not site_web:
        return None
    url = site_web.strip().lower()
    # Retire le schéma
    url = re.sub(r"^https?://", "", url)
    # Retire le path/query
    url = url.split("/")[0].split("?")[0]
    # Retire www.
    url = re.sub(r"^www\.", "", url)
    # Rejette les domaines trop courts ou sans TLD
    if "." not in url or len(url) < 4:
        return None
    return url


def guess_email(
    prenom: str | None,
    nom: str | None,
    site_web: str | None,
) -> str | None:
    """Retourne l'email le plus probable, ou None si les données sont insuffisantes."""
    domain = extract_domain(site_web)
    if not domain:
        return None
    if not prenom or not nom:
        return None

    prenom_slug = _slugify_name_part(prenom)
    nom_slug = _slugify_name_part(nom)

    if not prenom_slug or not nom_slug:
        return None

    return f"{prenom_slug}.{nom_slug}@{domain}"
