from datetime import date

from app.agents.veille.normalizer import (
    build_address,
    normalize_company_name,
    normalize_etablissement,
    normalize_phone,
)


def test_normalize_phone_french_local_format():
    assert normalize_phone("01 23 45 67 89") == "+33123456789"


def test_normalize_phone_already_international():
    assert normalize_phone("+33123456789") == "+33123456789"


def test_normalize_phone_none():
    assert normalize_phone(None) is None


def test_normalize_company_name_strips_legal_form_suffix():
    assert normalize_company_name("ACME SARL") == "Acme"
    assert normalize_company_name("Dupont Conseil SAS") == "Dupont Conseil"


def test_build_address_assembles_fields():
    etablissement = {
        "adresseEtablissement": {
            "numeroVoieEtablissement": "12",
            "typeVoieEtablissement": "RUE",
            "libelleVoieEtablissement": "DE LA PAIX",
            "codePostalEtablissement": "75008",
            "libelleCommuneEtablissement": "PARIS",
        }
    }
    assert build_address(etablissement) == "12 RUE DE LA PAIX, 75008 PARIS"


def test_build_address_missing_fields_returns_none():
    assert build_address({}) is None


def test_normalize_etablissement_maps_core_fields():
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "ACME SARL"},
        "trancheEffectifsEtablissement": "12",
        "adresseEtablissement": {
            "codePostalEtablissement": "75008",
            "libelleCommuneEtablissement": "PARIS",
        },
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "62.01Z"}
        ],
    }
    result = normalize_etablissement(raw)
    assert result["siret"] == "12345678900012"
    assert result["company_name"] == "Acme"
    assert result["secteur"] == "62.01Z"
    assert result["taille_entreprise"] == "12"
    assert result["telephone"] is None
    assert result["site_web"] is None


# ── cas limites supplémentaires ───────────────────────────────────────────────

def test_normalize_company_name_mixed_case_unchanged():
    # Une dénomination déjà en mixed case (non tout-maj) ne passe pas en title()
    assert normalize_company_name("Dupont Conseil") == "Dupont Conseil"


def test_normalize_company_name_multiple_spaces_collapsed():
    # Les espaces multiples sont normalisés par " ".join(raw.split())
    assert normalize_company_name("ACME   SOLUTIONS  SARL") == "Acme Solutions"


def test_normalize_company_name_empty_returns_empty():
    assert normalize_company_name("") == ""
    assert normalize_company_name(None) == ""


def test_normalize_company_name_parentheses_in_slug():
    # Le nom avec parenthèses est géré dans email_guesser mais pas ici — vérifier qu'il ne plante pas
    result = normalize_company_name("CANDELA (CANDELA) SARL")
    assert isinstance(result, str)
    assert len(result) > 0


def test_current_periode_fallback_when_all_closed():
    """Quand toutes les périodes ont une dateFin, on retourne la première."""
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "CLOSED CO"},
        "periodesEtablissement": [
            {"dateFin": "2020-01-01", "activitePrincipaleEtablissement": "62.01Z"},
            {"dateFin": "2019-01-01", "activitePrincipaleEtablissement": "73.11Z"},
        ],
    }
    result = normalize_etablissement(raw)
    # La première période est retournée en fallback
    assert result["secteur"] == "62.01Z"


def test_company_name_from_enseigne_when_no_denomination():
    """L'enseigne est utilisée quand il n'y a pas de dénomination uniteLegale."""
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {},  # pas de denominationUniteLegale
        "periodesEtablissement": [
            {
                "dateFin": None,
                "enseigne1Etablissement": "MON ENSEIGNE",
                "activitePrincipaleEtablissement": "47.11B",
            }
        ],
    }
    result = normalize_etablissement(raw)
    assert result["company_name"] == "Mon Enseigne"


def test_company_name_from_nom_prenom_person():
    """Pour une personne physique sans dénomination, prénom + nom sont utilisés."""
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {
            "prenom1UniteLegale": "JEAN",
            "nomUniteLegale": "DUPONT",
        },
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "86.21Z"}
        ],
    }
    result = normalize_etablissement(raw)
    assert "DUPONT" in result["company_name"] or "Dupont" in result["company_name"]


def test_taille_entreprise_from_periode_when_absent_at_root():
    """La tranche d'effectif est lue dans la période si absente à la racine."""
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "TEST CO"},
        "periodesEtablissement": [
            {
                "dateFin": None,
                "activitePrincipaleEtablissement": "62.01Z",
                "trancheEffectifsEtablissement": "22",
            }
        ],
    }
    result = normalize_etablissement(raw)
    assert result["taille_entreprise"] == "22"


def test_date_creation_from_unite_legale():
    """dateCreationUniteLegale (date fondation société) prime sur dateCreationEtablissement."""
    raw = {
        "siret": "41826770400066",
        "uniteLegale": {
            "denominationUniteLegale": "ARTEFACT SAS",
            "dateCreationUniteLegale": "1998-03-06",   # fondation société
        },
        "dateCreationEtablissement": "2017-11-20",     # siège actuel — doit être ignoré
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "62.02A"}
        ],
    }
    result = normalize_etablissement(raw)
    assert result["date_creation"] == date(1998, 3, 6)


def test_date_creation_fallback_to_etablissement_when_no_unite_legale_date():
    """Si uniteLegale n'a pas de dateCreationUniteLegale, on utilise dateCreationEtablissement."""
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "DATETEST SAS"},  # pas de dateCreation
        "dateCreationEtablissement": "2010-03-15",
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "62.01Z"}
        ],
    }
    result = normalize_etablissement(raw)
    assert result["date_creation"] == date(2010, 3, 15)


def test_date_creation_none_when_absent():
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "NODATE SAS"},
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "62.01Z"}
        ],
    }
    result = normalize_etablissement(raw)
    assert result["date_creation"] is None


def test_date_creation_none_on_invalid_format():
    raw = {
        "siret": "12345678900012",
        "uniteLegale": {"denominationUniteLegale": "BADDATE SAS"},
        "dateCreationEtablissement": "not-a-date",
        "periodesEtablissement": [
            {"dateFin": None, "activitePrincipaleEtablissement": "62.01Z"}
        ],
    }
    result = normalize_etablissement(raw)
    assert result["date_creation"] is None


def test_build_address_with_indice_repetition():
    """L'indice de répétition ('BIS', 'TER') est inclus dans l'adresse."""
    etablissement = {
        "adresseEtablissement": {
            "numeroVoieEtablissement": "5",
            "indiceRepetitionEtablissement": "BIS",
            "typeVoieEtablissement": "RUE",
            "libelleVoieEtablissement": "DES FLEURS",
            "codePostalEtablissement": "69001",
            "libelleCommuneEtablissement": "LYON",
        }
    }
    adresse = build_address(etablissement)
    assert "5 BIS RUE DES FLEURS" in adresse
    assert "69001 LYON" in adresse
