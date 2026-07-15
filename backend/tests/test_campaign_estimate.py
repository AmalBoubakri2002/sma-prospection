"""Tests de GET /campaigns/estimate — estimation du vivier disponible avant
lancement : total SIRENE moins entreprises déjà en prospection ailleurs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agents.veille.sirene import SireneConfigError
from app.api.deps import require_active_user
from app.api.v1.endpoints import campaigns
from app.db.base import get_db


def _make_client() -> AsyncClient:
    app = FastAPI()
    app.include_router(campaigns.router, prefix="/campaigns")

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_active_user] = lambda: MagicMock()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _sirene_mock(total: int):
    client = MagicMock()
    client.count_etablissements = AsyncMock(return_value=total)
    return client


@pytest.mark.anyio
async def test_estimate_returns_pool_minus_prospected():
    sirene = _sirene_mock(total=12)
    async with _make_client() as client:
        with (
            patch("app.api.v1.endpoints.campaigns.SireneClient", return_value=sirene),
            patch("app.api.v1.endpoints.campaigns.count_sirets_in_prospection_matching",
                  AsyncMock(return_value=9)),
        ):
            response = await client.get(
                "/campaigns/estimate",
                params={
                    "codes_naf": "62.01Z,62.02A",
                    "codes_postaux": "75008,75009",
                    "tranches_effectifs": "12,21",
                },
            )

    assert response.status_code == 200
    assert response.json() == {
        "total_sirene": 12,
        "deja_en_prospection": 9,
        "disponible_estime": 3,
    }
    # Les listes CSV sont bien découpées avant l'appel SIRENE
    call = sirene.count_etablissements.call_args
    assert call.args == (["62.01Z", "62.02A"], ["75008", "75009"], ["12", "21"])


@pytest.mark.anyio
async def test_estimate_never_negative():
    """Plus d'entreprises en prospection que le total SIRENE du moment
    (critères modifiés entre-temps) : le disponible est plafonné à 0."""
    async with _make_client() as client:
        with (
            patch("app.api.v1.endpoints.campaigns.SireneClient", return_value=_sirene_mock(5)),
            patch("app.api.v1.endpoints.campaigns.count_sirets_in_prospection_matching",
                  AsyncMock(return_value=9)),
        ):
            response = await client.get(
                "/campaigns/estimate",
                params={"codes_naf": "62.01Z", "codes_postaux": "75008"},
            )

    assert response.status_code == 200
    assert response.json()["disponible_estime"] == 0


@pytest.mark.anyio
async def test_estimate_requires_naf_and_postal_codes():
    async with _make_client() as client:
        response = await client.get(
            "/campaigns/estimate",
            params={"codes_naf": "  ", "codes_postaux": ""},
        )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_estimate_returns_503_when_sirene_not_configured():
    sirene = MagicMock()
    sirene.count_etablissements = AsyncMock(side_effect=SireneConfigError("clé absente"))
    async with _make_client() as client:
        with patch("app.api.v1.endpoints.campaigns.SireneClient", return_value=sirene):
            response = await client.get(
                "/campaigns/estimate",
                params={"codes_naf": "62.01Z", "codes_postaux": "75008"},
            )
    assert response.status_code == 503
