import uuid

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
        email="jean.dupont@acme.fr",
        telephone="0102030405",
        secteur="6201Z",
        score=0.87,
        label_scoring="CHAUD",
        contenu_email="<p>Bonjour Jean...</p>",
    )
    payload = build_odoo_payload(lead)

    assert payload["name"] == "Acme Corp"
    assert payload["partner_name"] == "Jean Dupont"
    assert payload["email_from"] == "jean.dupont@acme.fr"
    assert payload["phone"] == "0102030405"
    assert payload["x_sector"] == "6201Z"
    assert payload["x_score_ia"] == 0.87
    assert payload["x_label_ia"] == "CHAUD"
    assert payload["description"] == "<p>Bonjour Jean...</p>"
    assert payload["x_sma_pc_id"] == str(lead.id)


def test_build_odoo_payload_omits_missing_optional_fields():
    lead = _make_lead()
    payload = build_odoo_payload(lead)

    assert payload == {"name": "Acme Corp", "x_sma_pc_id": str(lead.id)}


def test_build_odoo_payload_contact_name_with_only_first_name():
    lead = _make_lead(prenom_dirigeant="Jean")
    payload = build_odoo_payload(lead)

    assert payload["partner_name"] == "Jean"


def test_build_odoo_payload_sma_pc_id_is_string_uuid():
    lead = _make_lead()
    payload = build_odoo_payload(lead)

    assert isinstance(payload["x_sma_pc_id"], str)
    assert payload["x_sma_pc_id"] == str(lead.id)
