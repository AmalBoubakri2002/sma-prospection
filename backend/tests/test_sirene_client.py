"""Tests unitaires pour SireneClient.search_etablissements — vérifie le retour du total SIRENE."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.veille.sirene import SireneClient, SireneAPIError


def _make_response(status_code: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = ""
    return resp


@pytest.mark.anyio
async def test_returns_etablissements_and_total():
    """Le tuple (résultats, total_sirene) est correctement retourné."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    page = _make_response(200, {
        "header": {"total": 42},
        "etablissements": [{"siret": f"1234567890{i:04d}"} for i in range(3)],
    })

    with patch.object(client, "_get_with_retry", new_callable=AsyncMock, return_value=page):
        results, total = await client.search_etablissements(["62.01Z"], ["75008"], ["12"], quota=3)

    assert len(results) == 3
    assert total == 42


@pytest.mark.anyio
async def test_total_zero_when_404():
    """Quand SIRENE renvoie 404 (zéro résultat), total_sirene vaut 0."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    page = _make_response(404, {})

    with patch.object(client, "_get_with_retry", new_callable=AsyncMock, return_value=page):
        results, total = await client.search_etablissements(["99.99Z"], ["00000"], ["12"], quota=10)

    assert results == []
    assert total == 0


@pytest.mark.anyio
async def test_stops_at_sirene_total_not_quota():
    """Quand SIRENE a moins de résultats que le quota, on s'arrête au total SIRENE."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    # SIRENE dit total=2 mais quota=10
    page = _make_response(200, {
        "header": {"total": 2},
        "etablissements": [{"siret": "12345678900001"}, {"siret": "12345678900002"}],
    })

    call_count = 0

    async def fake_retry(client_, path, params):
        nonlocal call_count
        call_count += 1
        return page

    with patch.object(client, "_get_with_retry", side_effect=fake_retry):
        results, total = await client.search_etablissements(["62.01Z"], ["75008"], ["12"], quota=10)

    assert len(results) == 2
    assert total == 2
    assert call_count == 1  # une seule page, pas de tentative de pagination inutile


@pytest.mark.anyio
async def test_raises_on_api_error():
    """Une erreur 500 de l'API lève SireneAPIError."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    page = _make_response(500, {})
    page.text = "Internal Server Error"

    with patch.object(client, "_get_with_retry", new_callable=AsyncMock, return_value=page):
        with pytest.raises(SireneAPIError):
            await client.search_etablissements(["62.01Z"], ["75008"], ["12"], quota=5)


@pytest.mark.anyio
async def test_pagination_continues_past_excluded_sirets():
    """Les SIRET exclus (déjà en prospection) ne bloquent plus la collecte :
    la pagination avance jusqu'à trouver des entreprises nouvelles, au lieu de
    s'arrêter sur une première page saturée de SIRET connus."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    page1 = _make_response(200, {
        "header": {"total": 40},
        "etablissements": [{"siret": f"EXCLU{i:04d}"} for i in range(20)],
    })
    page2 = _make_response(200, {
        "header": {"total": 40},
        "etablissements": [{"siret": f"NOUVEAU{i:04d}"} for i in range(20)],
    })

    with (
        patch.object(client, "_get_with_retry", new_callable=AsyncMock, side_effect=[page1, page2]),
        patch("app.agents.veille.sirene.asyncio.sleep", new_callable=AsyncMock),
    ):
        results, total = await client.search_etablissements(
            ["62.01Z"], ["75008"], ["12"], quota=5,
            exclude_sirets={f"EXCLU{i:04d}" for i in range(20)},
        )

    assert len(results) == 5
    assert all(r["siret"].startswith("NOUVEAU") for r in results)
    assert total == 40


@pytest.mark.anyio
async def test_intra_pagination_duplicate_sirets_kept_once():
    """Un même SIRET revu sur deux pages (réordonnancement SIRENE) n'est gardé qu'une fois."""
    client = SireneClient(api_key="fake-key", base_url="https://fake.sirene")

    page1 = _make_response(200, {
        "header": {"total": 25},
        "etablissements": [{"siret": f"S{i:04d}"} for i in range(20)],
    })
    page2 = _make_response(200, {
        "header": {"total": 25},
        "etablissements": [{"siret": "S0000"}, {"siret": "S9999"}],
    })

    with (
        patch.object(client, "_get_with_retry", new_callable=AsyncMock, side_effect=[page1, page2]),
        patch("app.agents.veille.sirene.asyncio.sleep", new_callable=AsyncMock),
    ):
        results, _ = await client.search_etablissements(
            ["62.01Z"], ["75008"], ["12"], quota=21,
        )

    sirets = [r["siret"] for r in results]
    assert sirets.count("S0000") == 1
    assert "S9999" in sirets
