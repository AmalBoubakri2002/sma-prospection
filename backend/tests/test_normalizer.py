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
