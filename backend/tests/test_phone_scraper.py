"""Tests unitaires pour phone_scraper — normalisation, sélection fixe/mobile, scraping HTTP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.phone_scraper import (
    _normalize_phone,
    _pick_best_phone,
    scrape_phone_from_homepage,
)


# ── _normalize_phone ──────────────────────────────────────────────────────────

def test_normalize_phone_local_10_digits():
    assert _normalize_phone("0123456789") == "01 23 45 67 89"


def test_normalize_phone_with_spaces():
    assert _normalize_phone("01 23 45 67 89") == "01 23 45 67 89"


def test_normalize_phone_plus33():
    assert _normalize_phone("+33123456789") == "01 23 45 67 89"


def test_normalize_phone_0033_prefix():
    assert _normalize_phone("0033145678900") == "01 45 67 89 00"


def test_normalize_phone_dots_separator():
    assert _normalize_phone("01.23.45.67.89") == "01 23 45 67 89"


def test_normalize_phone_unrecognized_returns_stripped():
    # Un numéro qui n'est pas un format français standard est retourné tel quel (strippé)
    result = _normalize_phone("  +1-800-555-1234  ")
    assert result == "+1-800-555-1234"


# ── _pick_best_phone ──────────────────────────────────────────────────────────

def test_pick_best_phone_prefers_fixe_over_mobile():
    candidates = ["0645000000", "0145678900"]
    result = _pick_best_phone(candidates)
    # 0145678900 est un numéro fixe (01...)
    assert result == "01 45 67 89 00"


def test_pick_best_phone_mobile_fallback_when_no_fixe():
    candidates = ["0645000000"]
    result = _pick_best_phone(candidates)
    assert result == "06 45 00 00 00"


def test_pick_best_phone_empty_returns_none():
    assert _pick_best_phone([]) is None


def test_pick_best_phone_09_is_fixe():
    # 09 = numéro VOIP / Bbox, considéré fixe
    candidates = ["0612345678", "0912345678"]
    result = _pick_best_phone(candidates)
    assert result == "09 12 34 56 78"


def test_pick_best_phone_international_fixe_preferred():
    candidates = ["0612345678", "+33145678900"]
    result = _pick_best_phone(candidates)
    # +33145678900 → indicatif 1 = fixe
    assert result == "01 45 67 89 00"


# ── scrape_phone_from_homepage ────────────────────────────────────────────────

def _make_http_mock(status_code: int, text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = text
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.anyio
async def test_scrape_phone_finds_landline():
    html = "<html><body><p>Appelez-nous : 01 45 67 89 00</p></body></html>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_phone_from_homepage("https://acme.fr")
    assert result == "01 45 67 89 00"


@pytest.mark.anyio
async def test_scrape_phone_prefers_fixe_when_both_present():
    html = "<p>Mobile : 06 12 34 56 78 — Fixe : 01 45 67 89 00</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_phone_from_homepage("https://acme.fr")
    assert result == "01 45 67 89 00"


@pytest.mark.anyio
async def test_scrape_phone_non_200_returns_none():
    mock_client = _make_http_mock(403, "")
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_phone_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_phone_no_phone_in_html_returns_none():
    html = "<html><body><p>Aucun numéro ici</p></body></html>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_phone_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_phone_prefixes_https_when_missing():
    html = "<p>Tél : 01 23 45 67 89</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        # site sans schéma — la fonction doit ajouter https://
        result = await scrape_phone_from_homepage("acme.fr")
    assert result == "01 23 45 67 89"
    # Vérifie que get a été appelé avec https://
    call_url = mock_client.get.call_args[0][0]
    assert call_url.startswith("https://")


@pytest.mark.anyio
async def test_scrape_phone_connection_error_returns_none():
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_phone_from_homepage("https://acme.fr")
    assert result is None
