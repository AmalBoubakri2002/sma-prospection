"""Tests unitaires pour run_veille — couvre en particulier le calcul du quota
restant, qui doit se baser sur les leads encore "utiles" (pas sur le total
brut jamais collecté), sinon la boucle de compensation Veille↔Enrichissement
(pipeline_graph.py::node_check_quota) ne collecte jamais rien de plus quand
des leads ont été écartés faute de CA/résultat net (voir
agent.py::_has_sufficient_financials) — bug diagnostiqué le 2026-07-05 sur
une campagne réelle (quota=14, 2 leads écartés faute de données, Veille
refusait de recollecter car 14 SIRET avaient déjà été vus au total).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.veille.agent import run_veille


def _make_campaign(quota: int = 10) -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.quota = quota
    campaign.codes_naf = ["6201Z"]
    campaign.codes_postaux = ["75008"]
    campaign.tranches_effectifs = ["21"]
    campaign.estimated_prospects = 100
    return campaign


@pytest.mark.anyio
async def test_quota_deja_atteint_par_leads_utiles_ne_recollecte_pas():
    """14 SIRET collectés, tous utiles (aucun écarté faute de données) → quota
    déjà rempli, pas de nouvel appel SIRENE."""
    campaign = _make_campaign(quota=14)
    db = AsyncMock()

    with (
        patch("app.agents.veille.agent.get_existing_sirets", new_callable=AsyncMock,
              return_value={f"siret{i}" for i in range(14)}),
        patch("app.agents.veille.agent.count_usable_leads_for_campaign", new_callable=AsyncMock,
              return_value=14),
        patch("app.agents.veille.agent.SireneClient") as mock_client_cls,
    ):
        result = await run_veille(db, campaign)

    mock_client_cls.assert_not_called()
    assert result["leads_collected"] == 0
    assert result["raison"] == "quota déjà atteint"


@pytest.mark.anyio
async def test_quota_recalcule_sur_leads_utiles_relance_la_collecte():
    """14 SIRET collectés au total, mais 2 écartés faute de CA/résultat net →
    seuls 12 comptent pour le quota=14 : Veille doit redemander 2 SIRET de
    plus à SIRENE, pas 0."""
    campaign = _make_campaign(quota=14)
    db = AsyncMock()

    mock_client = AsyncMock()
    mock_client.search_etablissements = AsyncMock(return_value=([], 100))

    with (
        patch("app.agents.veille.agent.get_existing_sirets", new_callable=AsyncMock,
              return_value={f"siret{i}" for i in range(14)}),
        patch("app.agents.veille.agent.count_usable_leads_for_campaign", new_callable=AsyncMock,
              return_value=12),  # 2 écartés faute de données, exclus du compte utile
        patch("app.agents.veille.agent.SireneClient", return_value=mock_client),
        patch("app.agents.veille.agent.bulk_create_leads", new_callable=AsyncMock, return_value=[]),
    ):
        result = await run_veille(db, campaign)

    mock_client.search_etablissements.assert_awaited_once()
    called_quota = mock_client.search_etablissements.call_args.kwargs["quota"]
    assert called_quota == 2  # 14 (quota) - 12 (utiles), pas 14 - 14 = 0


@pytest.mark.anyio
async def test_dedup_utilise_bien_tous_les_sirets_pas_seulement_les_utiles():
    """La déduplication doit rester sur TOUS les SIRET déjà vus (y compris les
    écartés) pour ne jamais recollecter le même SIRET une deuxième fois."""
    campaign = _make_campaign(quota=14)
    db = AsyncMock()
    all_sirets = {f"siret{i}" for i in range(14)}

    mock_client = AsyncMock()
    mock_client.search_etablissements = AsyncMock(return_value=([], 100))

    with (
        patch("app.agents.veille.agent.get_existing_sirets", new_callable=AsyncMock,
              return_value=all_sirets),
        patch("app.agents.veille.agent.count_usable_leads_for_campaign", new_callable=AsyncMock,
              return_value=12),
        patch("app.agents.veille.agent.SireneClient", return_value=mock_client),
        patch("app.agents.veille.agent.dedupe") as mock_dedupe,
        patch("app.agents.veille.agent.bulk_create_leads", new_callable=AsyncMock, return_value=[]),
    ):
        mock_dedupe.return_value = []
        await run_veille(db, campaign)

    mock_dedupe.assert_called_once()
    assert mock_dedupe.call_args[0][1] == all_sirets
