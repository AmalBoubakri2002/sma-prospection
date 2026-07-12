import uuid
from datetime import date

from app.agents.crm.mapping import build_odoo_payload
from app.models.lead import Lead


def _make_lead(**overrides) -> Lead:
    defaults = dict(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        company_name="Acme Corp",
        siret="12345678900011",
    )
    return Lead(**{**defaults, **overrides})


def test_build_odoo_payload_maps_core_fields():
    lead = _make_lead(
        prenom_dirigeant="Jean",
        nom_dirigeant="Dupont",
        titre_dirigeant="Directeur Général",
        email="jean.dupont@acme.fr",
        telephone="0102030405",
        site_web="https://acme.fr",
        adresse="12 Rue de Rivoli, 75001 Paris",
        secteur="6201Z",
        score=0.87,
        label_scoring="CHAUD",
        contenu_email="<p>Bonjour Jean...</p>",
        taille_entreprise="21",
        date_creation=date(2012, 6, 15),
        ca=750_000,
        resultat_net=85_000,
    )
    payload = build_odoo_payload(lead)

    assert payload["name"] == "Acme Corp"
    # partner_name = société (distinct de contact_name = la personne) — ne pas confondre.
    assert payload["partner_name"] == "Acme Corp"
    assert payload["contact_name"] == "Jean Dupont"
    assert payload["function"] == "Directeur Général"
    assert payload["email_from"] == "jean.dupont@acme.fr"
    assert payload["phone"] == "0102030405"
    assert payload["website"] == "https://acme.fr"
    assert payload["street"] == "12 Rue de Rivoli, 75001 Paris"
    assert payload["x_sector"] == "6201Z"
    assert payload["x_score_ia"] == 0.87
    assert payload["x_label_ia"] == "CHAUD"
    assert payload["priority"] == "3"
    assert payload["description"] == "<p>Bonjour Jean...</p>"
    assert payload["x_sma_pc_id"] == str(lead.id)
    assert payload["x_siret"] == "12345678900011"
    assert payload["x_taille_entreprise"] == "21"
    assert payload["x_date_creation_entreprise"] == "2012-06-15"
    assert payload["x_ca"] == 750_000
    assert payload["x_resultat_net"] == 85_000


def test_build_odoo_payload_priority_covers_all_labels():
    expected = {"HORS_CIBLE": "0", "FROID": "1", "TIEDE": "2", "CHAUD": "3"}
    for label, priority in expected.items():
        lead = _make_lead(label_scoring=label)
        assert build_odoo_payload(lead)["priority"] == priority


def test_build_odoo_payload_omits_missing_optional_fields():
    lead = _make_lead()
    payload = build_odoo_payload(lead)

    assert payload == {
        "name": "Acme Corp",
        "partner_name": "Acme Corp",
        "x_sma_pc_id": str(lead.id),
        "x_siret": "12345678900011",
    }


def test_build_odoo_payload_contact_name_with_only_first_name():
    lead = _make_lead(prenom_dirigeant="Jean")
    payload = build_odoo_payload(lead)

    assert payload["contact_name"] == "Jean"


def test_build_odoo_payload_contact_name_absent_without_dirigeant():
    lead = _make_lead()
    payload = build_odoo_payload(lead)

    assert "contact_name" not in payload


def test_build_odoo_payload_sma_pc_id_is_string_uuid():
    lead = _make_lead()
    payload = build_odoo_payload(lead)

    assert isinstance(payload["x_sma_pc_id"], str)
    assert payload["x_sma_pc_id"] == str(lead.id)
