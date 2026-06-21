import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.nominatim import geocode_address


def test_geocode_address_empty():
    result = asyncio.run(geocode_address(""))
    assert result is None


def test_geocode_address_none_like():
    result = asyncio.run(geocode_address("   "))
    assert result is None


# ── tests avec mock HTTP ──────────────────────────────────────────────────────

def _make_nominatim_mock(status_code: int, json_body: list) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_body
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.anyio
async def test_geocode_address_returns_coords():
    nominatim_response = [{"lat": "48.8566", "lon": "2.3522"}]
    mock_client = _make_nominatim_mock(200, nominatim_response)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await geocode_address("12 RUE DE LA PAIX, 75008 PARIS")
    assert result is not None
    lat, lon = result
    assert abs(lat - 48.8566) < 0.001
    assert abs(lon - 2.3522) < 0.001


@pytest.mark.anyio
async def test_geocode_address_empty_results_returns_none():
    mock_client = _make_nominatim_mock(200, [])
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await geocode_address("ADRESSE INCONNUE 99999 NULLE PART")
    assert result is None


@pytest.mark.anyio
async def test_geocode_address_non_200_returns_none():
    mock_client = _make_nominatim_mock(500, [])
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await geocode_address("12 RUE DE LA PAIX, 75008 PARIS")
    assert result is None


@pytest.mark.anyio
async def test_geocode_address_malformed_response_returns_none():
    # Réponse sans clés lat/lon
    nominatim_response = [{"display_name": "Paris, France"}]
    mock_client = _make_nominatim_mock(200, nominatim_response)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await geocode_address("12 RUE DE LA PAIX, 75008 PARIS")
    assert result is None


@pytest.mark.anyio
async def test_geocode_address_connection_error_returns_none():
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await geocode_address("12 RUE DE LA PAIX, 75008 PARIS")
    assert result is None
