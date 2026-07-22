"""Tests de l'endpoint /metrics : câblage de la route (vérification de
propriété de la campagne, délégation au service) et du calcul de taux pur."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_active_user
from app.api.v1.endpoints import metrics as metrics_ep
from app.db.base import get_db
from app.schemas.metrics import (
    CrmSyncMetrics,
    CycleTimeMetrics,
    FunnelMetrics,
    MetricsResponse,
    ScoringQualityMetrics,
)
from app.services.metrics import _safe_rate


def _make_client(db: AsyncMock) -> AsyncClient:
    app = FastAPI()
    app.include_router(metrics_ep.router, prefix="/metrics")

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_active_user] = lambda: MagicMock(id=uuid.uuid4())
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _empty_report(campaign_id: str | None = None) -> MetricsResponse:
    return MetricsResponse(
        generated_at=datetime.now(timezone.utc),
        campaign_id=campaign_id,
        nb_campagnes=0,
        nb_leads_total=0,
        funnel=FunnelMetrics(
            collecte=0, enrichi=0, ecarte=0, qualifie=0, email_genere=0,
            en_attente_validation=0, valide=0, rejete=0, synchronise_crm=0,
            contacte=0, repondu=0, sans_reponse=0,
        ),
        scoring=ScoringQualityMetrics(),
        cycle_time=CycleTimeMetrics(),
        agents=[],
        crm_sync=CrmSyncMetrics(total=0, success=0, error=0),
    )


# ── GET /metrics ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_metrics_global_delegates_to_service():
    """Sans campaign_id : pas de vérification de propriété, appel direct au
    service avec campaign_id=None (agrégé sur toutes les campagnes du commercial)."""
    report = AsyncMock(return_value=_empty_report())

    async with _make_client(AsyncMock()) as client:
        with (
            patch("app.api.v1.endpoints.metrics.get_metrics_report", report),
            patch("app.api.v1.endpoints.metrics.get_campaign", AsyncMock()) as get_campaign,
        ):
            response = await client.get("/metrics/")

    assert response.status_code == 200
    assert response.json()["nb_leads_total"] == 0
    get_campaign.assert_not_awaited()
    report.assert_awaited_once()
    assert report.call_args.args[2] is None


@pytest.mark.anyio
async def test_get_metrics_unknown_campaign_returns_404():
    campaign_id = uuid.uuid4()
    report = AsyncMock()

    async with _make_client(AsyncMock()) as client:
        with (
            patch("app.api.v1.endpoints.metrics.get_campaign", AsyncMock(return_value=None)),
            patch("app.api.v1.endpoints.metrics.get_metrics_report", report),
        ):
            response = await client.get(f"/metrics/?campaign_id={campaign_id}")

    assert response.status_code == 404
    report.assert_not_awaited()


@pytest.mark.anyio
async def test_get_metrics_scoped_to_owned_campaign():
    campaign_id = uuid.uuid4()
    campaign = MagicMock()
    campaign.id = campaign_id
    report = AsyncMock(return_value=_empty_report(str(campaign_id)))

    async with _make_client(AsyncMock()) as client:
        with (
            patch("app.api.v1.endpoints.metrics.get_campaign", AsyncMock(return_value=campaign)),
            patch("app.api.v1.endpoints.metrics.get_metrics_report", report),
        ):
            response = await client.get(f"/metrics/?campaign_id={campaign_id}")

    assert response.status_code == 200
    assert response.json()["campaign_id"] == str(campaign_id)
    assert report.call_args.args[2] == campaign_id


# ── _safe_rate ────────────────────────────────────────────────────────────

def test_safe_rate_returns_none_for_empty_denominator():
    assert _safe_rate(0, 0) is None


def test_safe_rate_computes_percentage_rounded():
    assert _safe_rate(1, 3) == 33.3


def test_safe_rate_full_success():
    assert _safe_rate(5, 5) == 100.0
