"""Tests unitaires pour run_enrichissement — couvre les 3 corrections critiques :
  1. Boucle sur les lots de 50 (quota > 50)
  2. Fallback INPI quand recherche-entreprises ne retourne pas de CA
  3. Compteurs distincts (tous traités vs avec données réelles)
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.agent import run_enrichissement
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

    _, kwargs = mock_update.call_args
    updated_fields = mock_update.call_args[0][2]  # 3ème argument positionnel
    assert updated_fields.get("ca") == 850000
    assert updated_fields.get("resultat_net") == 42000


@pytest.mark.anyio
async def test_inpi_not_called_when_ca_already_present():
    """Fix 2 : INPI ne doit pas être appelé si recherche-entreprises a déjà renvoyé un CA."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[
            [lead], []
        ]),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock,
              return_value={"ca": 1500000, "resultat_net": 80000}),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock) as mock_inpi,
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock),
    ):
        await run_enrichissement(db, campaign)

    mock_inpi.assert_not_awaited()


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
        patch("app.agents.enrichissement.agent.enrich_from_siret", side_effect=fake_enrich),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock, return_value={}),
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

    with patch("app.agents.enrichissement.agent.list_leads_to_enrich", new_callable=AsyncMock, return_value=[]):
        result = await run_enrichissement(db, campaign)

    assert result["leads_enrichis"] == 0
    assert result["leads_avec_donnees"] == 0
