"""Tests unitaires pour run_enrichissement — couvre les corrections critiques :
  1. Boucle sur les lots de 50 (quota > 50)
  2. Fallback INPI quand recherche-entreprises ne retourne pas de CA
  3. Compteurs distincts (tous traités vs avec données réelles)
  4. Propagation de ca_n1 depuis INPI
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.agent import _has_sufficient_financials, run_enrichissement
from app.models.lead import Lead, LeadStatus


def _make_lead(
    siret: str, adresse: str | None = None, site_web: str | None = None,
    ca: int | None = None, resultat_net: int | None = None,
) -> Lead:
    lead = MagicMock(spec=Lead)
    lead.siret = siret
    lead.adresse = adresse
    lead.site_web = site_web
    lead.company_name = f"Entreprise {siret}"
    # Explicitement None par défaut : un MagicMock(spec=...) renvoie un enfant
    # MagicMock (donc "truthy"/"is not None") pour tout attribut non fixé, ce
    # qui fausserait silencieusement _has_sufficient_financials (repli sur
    # lead.ca/lead.resultat_net quand `fields` ne les contient pas).
    lead.ca = ca
    lead.resultat_net = resultat_net
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
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
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
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
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
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
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
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
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
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
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


# ── filtre données financières insuffisantes ────────────────────────────────────

@pytest.mark.parametrize("fields,lead_ca,lead_rn,expected", [
    # ni CA ni résultat net → insuffisant
    ({}, None, None, False),
    # ca=0 traité comme absent (artefact de source, même convention que
    # feature_spec.clean_financial_value / formatCaOrUnknown)
    ({"ca": 0, "resultat_net": 50000}, None, None, False),
    # resultat_net manquant alors que ca est connu → insuffisant
    ({"ca": 100000}, None, None, False),
    # resultat_net=0 est une vraie valeur connue, pas un manque → suffisant
    ({"ca": 100000, "resultat_net": 0}, None, None, True),
    # les deux connus → suffisant
    ({"ca": 100000, "resultat_net": 5000}, None, None, True),
    # ca absent de `fields` mais déjà connu sur le lead (repli) → suffisant
    ({"resultat_net": 5000}, 100000, None, True),
])
def test_has_sufficient_financials(fields, lead_ca, lead_rn, expected):
    lead = _make_lead("12345678900014", ca=lead_ca, resultat_net=lead_rn)
    assert _has_sufficient_financials(fields, lead) is expected


@pytest.mark.anyio
async def test_run_enrichissement_scores_lead_without_financials():
    """Un lead sans CA ni résultat net reste ENRICHI (donc atteint l'Agent
    Scoring, voir list_leads_to_score) — seulement compté comme "données
    financières partielles" pour le reporting, plus écarté avant le scoring."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[[lead], []]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", new_callable=AsyncMock,
              return_value={"telephone": "0145678900"}),  # pas de CA ni resultat_net
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock, return_value={}),
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent.find_company_website", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.scrape_email_from_homepage", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.geocode_address", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        result = await run_enrichissement(db, campaign)

    assert result["leads_donnees_financieres_partielles"] == 1
    assert mock_update.call_args.kwargs["status"] == LeadStatus.ENRICHI


@pytest.mark.anyio
async def test_run_enrichissement_timeout_stays_enrichi_not_ecarte():
    """Un échec technique (timeout) reste ENRICHI sans données et n'est pas
    compté en "données financières partielles" — ce n'est pas un jugement sur
    la qualité du lead mais un échec technique, le distinguo doit rester
    lisible dans les stats de reporting."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead("12345678900014")

    async def _hang(*args, **kwargs):
        await asyncio.sleep(10)

    with (
        patch("app.agents.enrichissement.agent.list_leads_to_enrich", side_effect=[[lead], []]),
        patch("app.agents.enrichissement.agent.get_enriched_fields_by_siret", new_callable=AsyncMock, return_value=None),
        patch("app.agents.enrichissement.agent.enrich_from_siret", side_effect=_hang),
        patch("app.agents.enrichissement.agent.get_finances_from_siren", new_callable=AsyncMock, return_value={}),
        patch("app.agents.enrichissement.agent.get_procedure_from_bodacc", new_callable=AsyncMock,
              return_value={"en_procedure_collective": False}),
        patch("app.agents.enrichissement.agent._LEAD_TIMEOUT", 0.05),
        patch("app.agents.enrichissement.agent.update_lead_enriched", new_callable=AsyncMock) as mock_update,
    ):
        result = await run_enrichissement(db, campaign)

    assert result["leads_donnees_financieres_partielles"] == 0
    assert result["leads_erreurs"] == 1
    assert mock_update.call_args.kwargs["status"] == LeadStatus.ENRICHI
