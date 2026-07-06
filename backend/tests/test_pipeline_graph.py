"""Tests unitaires pour node_check_quota / _route_after_quota_check —
la boucle de compensation Veille↔Enrichissement qui relance la collecte
quand trop de leads sont écartés à l'enrichissement (données financières
insuffisantes, voir agent.py::_has_sufficient_financials) et que le quota de
la campagne n'est pas atteint.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.pipeline_graph import (
    MAX_VEILLE_RETRIES,
    _route_after_quota_check,
    node_check_quota,
)


def _make_campaign(quota: int = 10, estimated_prospects: int | None = 100) -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.quota = quota
    campaign.estimated_prospects = estimated_prospects
    return campaign


def _patch_db(campaign, total_collected: int, counts: dict[str, int]):
    """Patch AsyncSessionLocal pour que `async with AsyncSessionLocal() as db`
    renvoie un mock dont db.get(...) renvoie `campaign`."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=campaign)

    @asynccontextmanager
    async def _session_cm():
        yield db

    session_factory = MagicMock(side_effect=_session_cm)
    return (
        patch("app.workers.pipeline_graph.AsyncSessionLocal", session_factory),
        patch("app.workers.pipeline_graph.count_leads_for_campaign", new_callable=AsyncMock, return_value=total_collected),
        patch("app.workers.pipeline_graph.count_leads_by_status_for_campaign", new_callable=AsyncMock, return_value=counts),
    )


@pytest.mark.anyio
async def test_quota_atteint_ne_relance_pas():
    campaign = _make_campaign(quota=10)
    patches = _patch_db(campaign, total_collected=10, counts={"ENRICHI": 10})
    with patches[0], patches[1], patches[2]:
        result = await node_check_quota({"campaign_id": str(campaign.id)})

    assert result["needs_more_leads"] is False
    assert result["veille_retries"] == 0


@pytest.mark.anyio
async def test_quota_non_atteint_relance_veille():
    campaign = _make_campaign(quota=10, estimated_prospects=100)
    patches = _patch_db(campaign, total_collected=10, counts={"ENRICHI": 3, "ECARTE": 7})
    with patches[0], patches[1], patches[2]:
        result = await node_check_quota({"campaign_id": str(campaign.id)})

    assert result["needs_more_leads"] is True
    assert result["veille_retries"] == 1


@pytest.mark.anyio
async def test_relances_epuisees_arrete_malgre_quota_non_atteint():
    campaign = _make_campaign(quota=10, estimated_prospects=100)
    patches = _patch_db(campaign, total_collected=10, counts={"ENRICHI": 3})
    with patches[0], patches[1], patches[2]:
        result = await node_check_quota({
            "campaign_id": str(campaign.id), "veille_retries": MAX_VEILLE_RETRIES,
        })

    assert result["needs_more_leads"] is False
    assert result["veille_retries"] == MAX_VEILLE_RETRIES  # ne dépasse pas le plafond


@pytest.mark.anyio
async def test_stock_sirene_epuise_arrete_malgre_quota_non_atteint():
    campaign = _make_campaign(quota=10, estimated_prospects=5)
    # Tout le stock SIRENE disponible (5) a déjà été collecté, mais seuls 2
    # ont pu être enrichis avec des données financières suffisantes.
    patches = _patch_db(campaign, total_collected=5, counts={"ENRICHI": 2, "ECARTE": 3})
    with patches[0], patches[1], patches[2]:
        result = await node_check_quota({"campaign_id": str(campaign.id)})

    assert result["needs_more_leads"] is False
    assert result["veille_retries"] == 0


@pytest.mark.anyio
async def test_campaign_introuvable_renvoie_erreur():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _session_cm():
        yield db

    with patch("app.workers.pipeline_graph.AsyncSessionLocal", MagicMock(side_effect=_session_cm)):
        result = await node_check_quota({"campaign_id": str(uuid.uuid4())})

    assert "error" in result


def test_route_after_quota_check_error_goes_to_end():
    from langgraph.graph import END
    assert _route_after_quota_check({"error": "boom"}) == END


def test_route_after_quota_check_needs_more_goes_to_veille():
    assert _route_after_quota_check({"needs_more_leads": True}) == "veille"


def test_route_after_quota_check_satisfied_goes_to_scoring():
    assert _route_after_quota_check({"needs_more_leads": False}) == "scoring"
