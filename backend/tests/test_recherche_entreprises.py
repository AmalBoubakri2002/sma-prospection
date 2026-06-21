from app.agents.enrichissement.recherche_entreprises import (
    extract_contact_info,
    extract_dirigeant_principal,
)

SAMPLE_RESULT = {
    "siren": "123456789",
    "nom_complet": "ACME TECHNOLOGIE SAS",
    "siege": {
        "siret": "12345678900014",
        "telephone": "0145678900",
        "site_internet": "https://www.acme-tech.fr",
    },
    "dirigeants": [
        {
            "prenoms": "Jean",
            "nom": "DUPONT",
            "qualite": "Directeur général",
        }
    ],
    "finances": {
        "2023": {"ca": 2500000, "resultat_net": 120000},
        "2022": {"ca": 2000000, "resultat_net": 90000},
    },
}


def test_extract_dirigeant_principal_nominal():
    result = extract_dirigeant_principal(SAMPLE_RESULT)
    assert result["prenom_dirigeant"] == "Jean"
    assert result["nom_dirigeant"] == "DUPONT"
    assert result["titre_dirigeant"] == "Directeur général"


def test_extract_dirigeant_principal_empty():
    result = extract_dirigeant_principal({"dirigeants": []})
    assert result == {}


def test_extract_contact_info_nominal():
    result = extract_contact_info(SAMPLE_RESULT)
    assert result["telephone"] == "0145678900"
    assert result["site_web"] == "https://www.acme-tech.fr"
    assert result["ca"] == 2500000
    assert result["resultat_net"] == 120000


def test_extract_contact_info_no_finances():
    result = extract_contact_info({"siege": {}})
    assert result["ca"] is None
    assert result["resultat_net"] is None
    assert result["telephone"] is None
    assert result["site_web"] is None


def test_extract_contact_info_takes_latest_year():
    result = extract_contact_info(SAMPLE_RESULT)
    assert result["ca"] == 2500000  # année 2023, pas 2022


# ── filtre commissaire aux comptes ────────────────────────────────────────────

def test_extract_dirigeant_skips_commissaire_takes_next():
    """Le commissaire aux comptes doit être ignoré ; le vrai dirigeant est pris."""
    result_with_commissaire = {
        "dirigeants": [
            {"prenoms": "Paul", "nom": "AUDIT", "qualite": "Commissaire aux comptes"},
            {"prenoms": "Marie", "nom": "MARTIN", "qualite": "Présidente"},
        ]
    }
    result = extract_dirigeant_principal(result_with_commissaire)
    assert result["prenom_dirigeant"] == "Marie"
    assert result["nom_dirigeant"] == "MARTIN"
    assert result["titre_dirigeant"] == "Présidente"


def test_extract_dirigeant_all_commissaires_returns_empty():
    """Quand tous les dirigeants sont commissaires, retourne un dict vide."""
    result = extract_dirigeant_principal({
        "dirigeants": [
            {"prenoms": "Paul", "nom": "AUDIT", "qualite": "Commissaire aux comptes"},
            {"prenoms": "Alice", "nom": "VERIFIE", "qualite": "Auditeur légal"},
        ]
    })
    assert result == {}


def test_extract_dirigeant_censeur_filtered():
    result = extract_dirigeant_principal({
        "dirigeants": [
            {"prenoms": "Bob", "nom": "CENS", "qualite": "Censeur"},
            {"prenoms": "Eve", "nom": "CEO", "qualite": "Directeur général"},
        ]
    })
    assert result["nom_dirigeant"] == "CEO"


def test_extract_contact_info_finances_float_string():
    """Les finances peuvent être des chaînes numériques — _to_int doit les gérer."""
    result_with_str_finances = {
        "siege": {},
        "finances": {
            "2023": {"ca": "3500000.0", "resultat_net": "-50000.5"}
        },
    }
    result = extract_contact_info(result_with_str_finances)
    assert result["ca"] == 3500000
    assert result["resultat_net"] == -50000
