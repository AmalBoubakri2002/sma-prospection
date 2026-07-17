"""Tests du déclenchement automatique de la rédaction après requalification :
un lead qui devient QUALIFIE (changement de seuil ou override manuel) doit
recevoir une tâche REDACTION — sinon il reste qualifié sans email pour toujours
(bug constaté le 2026-07-17 en baissant le seuil d'une campagne)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_active_user
from app.api.v1.endpoints import campaigns as campaigns_ep
from app.api.v1.endpoints import leads as leads_ep
from app.db.base import get_db
from app.models.agent_task import AgentName
from app.models.lead import Lead, LeadStatus


def _make_lead(score: float, status: str) -> Lead:
    return Lead(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        company_name="Acme Corp",
        siret="12345678900011",
        score=score,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _make_campaign(score_minimum: float = 0.5, status: str = "completed") -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.score_minimum = score_minimum
    campaign.status = status
    return campaign


def _make_client(router_module, prefix: str, db: AsyncMock) -> AsyncClient:
    app = FastAPI()
    app.include_router(router_module.router, prefix=prefix)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_active_user] = lambda: MagicMock(id=uuid.uuid4())
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _db_returning_leads(leads: list[Lead]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = leads
    db.execute.return_value = result
    return db


# ── POST /campaigns/{id}/requalify ────────────────────────────────────────────

@pytest.mark.anyio
async def test_requalify_launches_redaction_for_newly_qualified():
    """Seuil abaissé : l'écarté repasse QUALIFIE → tâche REDACTION créée."""
    campaign = _make_campaign(score_minimum=0.5)
    lead = _make_lead(score=0.60, status=LeadStatus.ECARTE)  # sous l'ancien seuil, au-dessus du nouveau
    db = _db_returning_leads([lead])
    create_task = AsyncMock()

    async with _make_client(campaigns_ep, "/campaigns", db) as client:
        with (
            patch("app.api.v1.endpoints.campaigns.get_campaign", AsyncMock(return_value=campaign)),
            patch("app.api.v1.endpoints.campaigns.create_task", create_task),
            patch("app.api.v1.endpoints.campaigns.update_campaign_status", AsyncMock()),
        ):
            response = await client.post(f"/campaigns/{campaign.id}/requalify")

    assert response.status_code == 200
    body = response.json()
    assert body["qualifies"] == 1
    assert body["redaction_lancee"] is True
    assert lead.status == LeadStatus.QUALIFIE
    create_task.assert_awaited_once()
    assert create_task.call_args.kwargs["agent_name"] == AgentName.REDACTION


@pytest.mark.anyio
async def test_requalify_no_redaction_when_nothing_newly_qualified():
    """Seuil remonté : des qualifiés sont écartés, aucun nouveau qualifié → pas de tâche."""
    campaign = _make_campaign(score_minimum=0.8)
    lead = _make_lead(score=0.60, status=LeadStatus.QUALIFIE)  # va être écarté
    db = _db_returning_leads([lead])
    create_task = AsyncMock()

    async with _make_client(campaigns_ep, "/campaigns", db) as client:
        with (
            patch("app.api.v1.endpoints.campaigns.get_campaign", AsyncMock(return_value=campaign)),
            patch("app.api.v1.endpoints.campaigns.create_task", create_task),
            patch("app.api.v1.endpoints.campaigns.update_campaign_status", AsyncMock()),
        ):
            response = await client.post(f"/campaigns/{campaign.id}/requalify")

    body = response.json()
    assert body["rejetes"] == 1
    assert body["redaction_lancee"] is False
    create_task.assert_not_awaited()


@pytest.mark.anyio
async def test_requalify_skips_redaction_when_agent_already_running():
    """Pipeline en cours : pas de tâche doublonnée, le nœud Rédaction du graphe s'en chargera."""
    campaign = _make_campaign(score_minimum=0.5, status="running")
    lead = _make_lead(score=0.60, status=LeadStatus.ECARTE)
    db = _db_returning_leads([lead])
    create_task = AsyncMock()

    async with _make_client(campaigns_ep, "/campaigns", db) as client:
        with (
            patch("app.api.v1.endpoints.campaigns.get_campaign", AsyncMock(return_value=campaign)),
            patch("app.api.v1.endpoints.campaigns.create_task", create_task),
            patch("app.api.v1.endpoints.campaigns.update_campaign_status", AsyncMock()),
        ):
            response = await client.post(f"/campaigns/{campaign.id}/requalify")

    assert response.json()["redaction_lancee"] is False
    create_task.assert_not_awaited()


# ── PATCH /leads/{id}/status → QUALIFIE (override manuel) ────────────────────

@pytest.mark.anyio
async def test_manual_qualify_launches_redaction():
    lead = _make_lead(score=0.60, status=LeadStatus.ECARTE)
    campaign = _make_campaign(status="completed")
    db = AsyncMock()
    db.get.return_value = campaign
    create_task = AsyncMock()

    async with _make_client(leads_ep, "/leads", db) as client:
        with (
            patch("app.api.v1.endpoints.leads._get_owned_lead", AsyncMock(return_value=lead)),
            patch("app.api.v1.endpoints.leads.create_task", create_task),
            patch("app.api.v1.endpoints.leads.update_campaign_status", AsyncMock()),
        ):
            response = await client.patch(
                f"/leads/{lead.id}/status", json={"status": "QUALIFIE"}
            )

    assert response.status_code == 200
    create_task.assert_awaited_once()
    assert create_task.call_args.kwargs["agent_name"] == AgentName.REDACTION


@pytest.mark.anyio
async def test_manual_reject_does_not_launch_redaction():
    lead = _make_lead(score=0.60, status=LeadStatus.QUALIFIE)
    db = AsyncMock()
    create_task = AsyncMock()

    async with _make_client(leads_ep, "/leads", db) as client:
        with (
            patch("app.api.v1.endpoints.leads._get_owned_lead", AsyncMock(return_value=lead)),
            patch("app.api.v1.endpoints.leads.create_task", create_task),
            patch("app.api.v1.endpoints.leads.update_campaign_status", AsyncMock()),
        ):
            response = await client.patch(
                f"/leads/{lead.id}/status", json={"status": "REJETE"}
            )

    assert response.status_code == 200
    create_task.assert_not_awaited()
