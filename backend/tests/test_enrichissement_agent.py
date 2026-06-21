"""Tests unitaires pour run_enrichissement — couvre les 3 corrections critiques :
  1. Boucle sur les lots de 50 (quota > 50)
  2. Fallback INPI quand recherche-entreprises ne retourne pas de CA
  3. Compteurs distincts (tous traités vs avec données réelles)
  4. Propagation de ca_n1 depuis INPI
  5. Calcul de score_intent (proxy complétude)
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.agent import _compute_score_intent, run_enrichissement
from app.models.lead import Lead, LeadStatus


def _make_lead(siret: str, adresse: str | None = None, site_web: str | None = None) -> Lead:
    lead = MagicMock(spec=Lead)
    lead.siret = siret
    lead.adresse = adresse
    lead.site_web = site_web
    lead.company_name = f"Entreprise {siret}"
    return lead


def _make_campaign() -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    return campaign


@pytest.mark.anyio
async def test_loop_processes_all_leads_beyond_page_size():
    """Fix 1 : run_enrichissement doit boucler tant qu'il reste des leads COLLECTE."""
    campaign = _make_campaign()
    db = AsyncMock()

    batch1 = [_make_lead(f"1234567890{i:04d}") for i in range(3)]
    batch2 = [_make_lead(f"9876543210{i:04d}") for i in range(2)]

    call_count = 0

    async def fake_list_leads(db_, campaign_id, page_size=50):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return batch1
        if call_count == 2:
            return batch2
        return []

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=fake_list_leads),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock, return_value={}),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock, return_value={}),
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock),
    ):
        result = await run_enrichissement(db, campaign)

    assert result["leads_enrichis"] == 5
    assert call_count == 3  # lot1, lot2, lot vide (terminaison)


@pytest.mark.anyio
async def test_inpi_fallback_used_when_no_ca_from_recherche_entreprises():
    """Fix 2 : INPI est appelé comme fallback si recherche-entreprises ne retourne pas de CA."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[
            [lead], []
        ]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock,
              return_value={"telephone": "0145678900"}),  # pas de CA
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock,
              return_value={"ca": 850000, "resultat_net": 42000}) as mock_inpi,
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        result = await run_enrichissement(db, campaign)

    mock_inpi.assert_awaited_once_with("123456789")  # SIREN = 9 premiers chiffres du SIRET

    updated_fields = mock_update.call_args[0][2]  # 3ème argument positionnel
    assert updated_fields.get("ca") == 850000
    assert updated_fields.get("resultat_net") == 42000


@pytest.mark.anyio
async def test_inpi_called_for_ca_n1_even_when_ca_from_source1():
    """INPI est toujours appelé (pour ca_n1), mais son ca ne remplace pas celui de source 1."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[
            [lead], []
        ]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock,
              return_value={"ca": 1500000, "resultat_net": 80000}),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock,
              return_value={"ca": 900000, "resultat_net": 30000, "ca_n1": 750000}) as mock_inpi,
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        await run_enrichissement(db, campaign)

    # INPI est toujours appelé (pour ca_n1)
    mock_inpi.assert_awaited_once()
    saved = mock_update.call_args[0][2]
    # ca de source 1 conservé (1 500 000), pas écrasé par INPI (900 000)
    assert saved.get("ca") == 1500000
    # ca_n1 vient d'INPI
    assert saved.get("ca_n1") == 750000


@pytest.mark.anyio
async def test_leads_avec_donnees_counter_accurate():
    """Fix 3 : leads_avec_donnees ne compte que les leads avec au moins un champ renseigné."""
    campaign = _make_campaign()
    db = AsyncMock()

    lead_with_data = _make_lead("11111111100001")
    lead_empty = _make_lead("22222222200002")

    call_count = 0

    async def fake_list(db_, campaign_id, page_size=50):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [lead_with_data, lead_empty]
        return []

    async def fake_enrich(siret):
        if siret == "11111111100001":
            return {"telephone": "0145000000"}
        return {}

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=fake_list),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", side_effect=fake_enrich),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock, return_value={}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock),
    ):
        result = await run_enrichissement(db, campaign)

    assert result["leads_enrichis"] == 2
    assert result["leads_avec_donnees"] == 1


@pytest.mark.anyio
async def test_empty_campaign_returns_zero():
    """Aucun lead COLLECTE → retourne immédiatement avec zéro."""
    campaign = _make_campaign()
    db = AsyncMock()

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", new_callable=AsyncMock, return_value=[]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
    ):
        result = await run_enrichissement(db, campaign)

    assert result["leads_enrichis"] == 0
    assert result["leads_avec_donnees"] == 0


# ── score_intent ──────────────────────────────────────────────────────────────

def _make_lead_for_intent(**kwargs) -> MagicMock:
    lead = MagicMock(spec=Lead)
    lead.email = kwargs.get("email")
    lead.telephone = kwargs.get("telephone")
    lead.site_web = kwargs.get("site_web")
    lead.prenom_dirigeant = kwargs.get("prenom_dirigeant")
    lead.ca = kwargs.get("ca")
    return lead


def test_score_intent_all_present():
    lead = _make_lead_for_intent(
        email="j.dupont@acme.fr",
        telephone="01 45 67 89 00",
        site_web="https://acme.fr",
        prenom_dirigeant="Jean",
        ca=500000,
    )
    # email×2 + phone + web + dirigeant + ca = 6/6 = 1.0
    assert _compute_score_intent({}, lead) == 1.0


def test_score_intent_nothing():
    lead = _make_lead_for_intent()
    # 0/6 = 0.0
    assert _compute_score_intent({}, lead) == 0.0


def test_score_intent_email_only():
    lead = _make_lead_for_intent()
    fields = {"email": "j.dupont@acme.fr"}
    # email×2 / 6 = 2/6 ≈ 0.3333
    result = _compute_score_intent(fields, lead)
    assert abs(result - 2 / 6) < 0.001


def test_score_intent_fields_override_lead():
    """Les données dans fields (enrichissement en cours) priment sur les attributs du lead."""
    lead = _make_lead_for_intent()
    fields = {"email": "found@acme.fr", "ca": 100000}
    # email×2 + ca = 3/6 = 0.5
    result = _compute_score_intent(fields, lead)
    assert abs(result - 3 / 6) < 0.001


@pytest.mark.anyio
async def test_inpi_ca_n1_propagated_to_fields():
    """ca_n1 retourné par INPI est stocké dans les champs du lead."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")
    lead.email = None
    lead.telephone = None
    lead.site_web = None
    lead.prenom_dirigeant = None
    lead.ca = None

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[[lead], []]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock,
              return_value={}),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock,
              return_value={"ca": 500000, "resultat_net": 20000, "ca_n1": 430000}),
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock,
              return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock,
              return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        await run_enrichissement(db, campaign)

    saved_fields = mock_update.call_args[0][2]
    assert saved_fields.get("ca_n1") == 430000


# ── cross-SIRET reuse ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_cross_siret_reuse_skips_all_apis():
    """Si le SIRET a déjà été enrichi dans une autre campagne, les API ne sont pas rappelées."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    cached_data = {
        "telephone": "01 45 67 89 00",
        "site_web": "https://acme.fr",
        "email": "j.dupont@acme.fr",
        "ca": 800000,
        "ca_n1": 700000,
    }

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[[lead], []]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock,
              return_value=cached_data),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock) as mock_enrich,
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock) as mock_inpi,
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        result = await run_enrichissement(db, campaign)

    # Aucune API rappelée
    mock_enrich.assert_not_awaited()
    mock_inpi.assert_not_awaited()
    # Lead quand même traité et sauvegardé
    assert result["leads_enrichis"] == 1
    assert result["leads_avec_donnees"] == 1
    saved = mock_update.call_args[0][2]
    assert saved["telephone"] == "01 45 67 89 00"
    assert saved["ca_n1"] == 700000
