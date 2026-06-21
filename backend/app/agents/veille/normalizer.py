import re
from datetime import date

_LEGAL_FORM_SUFFIXES = re.compile(
    r"\s*\b(SARL|SAS|SASU|SA|EURL|SCI|SNC|EI|EIRL)\b\s*$", re.IGNORECASE
)


def normalize_phone(raw: str | None) -> str | None:
    """SIRENE ne fournit pas de téléphone — utilitaire prêt pour l'Agent
    Enrichissement, qui produira des numéros à normaliser au format +33XXXXXXXXX."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0") and len(digits) == 10:
        return "+33" + digits[1:]
    if digits.startswith("33") and len(digits) == 11:
        return "+" + digits
    return raw.strip()


def normalize_company_name(raw: str | None) -> str:
    if not raw:
        return ""
    name = " ".join(raw.split())
    name = _LEGAL_FORM_SUFFIXES.sub("", name).strip()
    return name.title() if name.isupper() else name


def _current_periode(etablissement: dict) -> dict:
    periodes = etablissement.get("periodesEtablissement") or []
    for periode in periodes:
        if periode.get("dateFin") is None:
            return periode
    return periodes[0] if periodes else {}


def build_address(etablissement: dict) -> str | None:
    adresse = etablissement.get("adresseEtablissement") or {}
    voie_parts = [
        adresse.get("numeroVoieEtablissement"),
        adresse.get("indiceRepetitionEtablissement"),
        adresse.get("typeVoieEtablissement"),
        adresse.get("libelleVoieEtablissement"),
    ]
    voie = " ".join(p for p in voie_parts if p)

    ville_parts = [
        adresse.get("codePostalEtablissement"),
        adresse.get("libelleCommuneEtablissement"),
    ]
    ville = " ".join(p for p in ville_parts if p)

    full = ", ".join(p for p in (voie, ville) if p)
    return full or None


def _company_name_from_raw(etablissement: dict) -> str:
    unite_legale = etablissement.get("uniteLegale") or {}
    periode = _current_periode(etablissement)

    denomination = (
        unite_legale.get("denominationUniteLegale")
        or periode.get("enseigne1Etablissement")
        or periode.get("denominationUsuelleEtablissement")
    )
    if denomination:
        return denomination

    prenom = unite_legale.get("prenom1UniteLegale")
    nom = unite_legale.get("nomUniteLegale")
    if nom:
        return " ".join(p for p in (prenom, nom) if p)

    return etablissement.get("siret", "")


def _parse_date(raw: str | None) -> date | None:
    """Parse une date SIRENE au format YYYY-MM-DD, retourne None si invalide."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def normalize_etablissement(etablissement: dict) -> dict:
    """Mappe un établissement brut SIRENE vers les colonnes du modèle Lead.
    telephone et site_web ne sont pas fournis par SIRENE : laissés à None
    pour être complétés plus tard par l'Agent Enrichissement."""
    periode = _current_periode(etablissement)

    secteur = periode.get("activitePrincipaleEtablissement") or etablissement.get(
        "activitePrincipaleRegistreMetiersEtablissement"
    )
    taille_entreprise = etablissement.get("trancheEffectifsEtablissement") or periode.get(
        "trancheEffectifsEtablissement"
    )
    unite_legale = etablissement.get("uniteLegale", {})
    date_creation = (
        _parse_date(unite_legale.get("dateCreationUniteLegale"))
        or _parse_date(etablissement.get("dateCreationEtablissement"))
    )

    return {
        "company_name": normalize_company_name(_company_name_from_raw(etablissement)),
        "siret": etablissement.get("siret", ""),
        "secteur": secteur,
        "taille_entreprise": taille_entreprise,
        "adresse": build_address(etablissement),
        "date_creation": date_creation,
        "telephone": None,
        "site_web": None,
    }
