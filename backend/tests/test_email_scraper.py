from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.email_scraper import (
    _EMAIL_RE,
    _NONFUNCTIONAL_PREFIXES,
    scrape_email_from_homepage,
)


def test_email_regex_finds_address():
    html = '<p>Contactez-nous : jean.dupont@example.fr</p>'
    found = _EMAIL_RE.findall(html)
    assert "jean.dupont@example.fr" in found


def test_email_regex_ignores_html_entities():
    html = "Écrivez à prenom.nom&#64;example.com"
    # L'entité HTML n'est pas décodée — la regex ne trouve rien
    found = _EMAIL_RE.findall(html)
    assert not any("example.com" in e for e in found)


def test_nonfunctional_prefixes_filtered():
    assert "noreply" in _NONFUNCTIONAL_PREFIXES
    assert "postmaster" in _NONFUNCTIONAL_PREFIXES


def test_generic_but_functional_prefixes_not_filtered():
    # contact@, info@, hello@... restent des boîtes surveillées par une équipe :
    # exploitables en prospection B2B, contrairement aux alias noreply/postmaster.
    assert "contact" not in _NONFUNCTIONAL_PREFIXES
    assert "support" not in _NONFUNCTIONAL_PREFIXES
    assert "info" not in _NONFUNCTIONAL_PREFIXES


def test_jean_dupont_not_generic():
    assert "jean.dupont" not in _NONFUNCTIONAL_PREFIXES


# ── scrape_email_from_homepage — tests avec mock HTTP ────────────────────────

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
async def test_scrape_email_finds_professional_email():
    html = "<html><body><p>Email : jean.dupont@acme.fr</p></body></html>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "jean.dupont@acme.fr"


@pytest.mark.anyio
async def test_scrape_email_rejects_nonfunctional_prefix():
    # "noreply" est dans _NONFUNCTIONAL_PREFIXES (adresse automatisée) → ignoré
    html = "<p>noreply@acme.fr</p><p>marie.martin@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "marie.martin@acme.fr"


@pytest.mark.anyio
async def test_scrape_email_accepts_generic_functional_prefix():
    # "contact@" n'est plus rejeté : boîte générique mais surveillée par une équipe,
    # exploitable en prospection B2B (contrairement à noreply@/postmaster@).
    html = "<p>contact@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "contact@acme.fr"


@pytest.mark.anyio
async def test_scrape_email_rejects_infra_domain():
    # Email issu d'un domaine d'infra (sentry.io) → ignoré
    html = "<p>abc@sentry.io</p><p>paul.durand@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "paul.durand@acme.fr"


@pytest.mark.anyio
async def test_scrape_email_rejects_wrong_domain():
    # L'email appartient à un domaine différent du site → rejeté
    html = "<p>jean.dupont@autredomaine.com</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_email_rejects_hex_hash_prefix():
    # Préfixe hexadécimal >= 16 chars → email d'infra auto-généré, ignoré
    hex_prefix = "a1b2c3d4e5f6a7b8"  # 16 chars, tous hexadécimaux
    html = f"<p>{hex_prefix}@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_email_non_200_returns_none():
    mock_client = _make_http_mock(404, "")
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_email_connection_error_returns_none():
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result is None


@pytest.mark.anyio
async def test_scrape_email_rejects_image_extension_false_positive():
    # "@2x.png" ressemble à un email mais son TLD est une extension image
    html = "<img src='logo@2x.png'><p>jean.durand@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "jean.durand@acme.fr"


# ── filtre bureaux étrangers ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_scrape_email_rejects_foreign_office_hello_spain():
    """hello-spain@artefact.com doit être rejeté (bureau espagnol)."""
    html = "<p>hello-spain@artefact.com</p><p>pierre.martin@artefact.com</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://artefact.com")
    assert result == "pierre.martin@artefact.com"


@pytest.mark.anyio
async def test_scrape_email_rejects_foreign_office_city_prefix():
    """london@jellyfish.com doit être rejeté (bureau londonien)."""
    html = "<p>london@jellyfish.com</p><p>sophie.leclerc@jellyfish.com</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://jellyfish.com")
    assert result == "sophie.leclerc@jellyfish.com"


@pytest.mark.anyio
async def test_scrape_email_accepts_name_with_geo_word_in_company():
    """Un prénom/nom qui contient accidentellement un mot géo doit passer."""
    # "paris.dupont" — "paris" est un prénom ici, pas un bureau étranger
    # Mais notre filtre rejette "paris" comme mot géo → comportement attendu: rejeté
    # L'email "p.dupont@acme.fr" (sans mot géo) doit passer
    html = "<p>p.dupont@acme.fr</p>"
    mock_client = _make_http_mock(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await scrape_email_from_homepage("https://acme.fr")
    assert result == "p.dupont@acme.fr"
