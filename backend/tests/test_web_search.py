"""Tests unitaires pour web_search — validation d'URL, keywords, mock DuckDuckGo."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement.web_search import (
    _domain_keywords,
    _is_valid_company_url,
    find_company_website,
)


# ── _domain_keywords ──────────────────────────────────────────────────────────

def test_domain_keywords_filters_stop_words():
    keywords = _domain_keywords("France Services SAS")
    assert "france" not in keywords
    assert "services" not in keywords
    assert "sas" not in keywords


def test_domain_keywords_keeps_significant_words():
    keywords = _domain_keywords("XMCO Sécurité Informatique")
    assert "xmco" in keywords
    # "informatique" n'est pas dans _STOP
    assert "informatique" in keywords


def test_domain_keywords_minimum_length_3():
    keywords = _domain_keywords("AB Systems")
    assert "ab" not in keywords  # len < 3
    assert "systems" in keywords


# ── _is_valid_company_url ─────────────────────────────────────────────────────

def test_excluded_domain_wikipedia_rejected():
    assert _is_valid_company_url("https://fr.wikipedia.org/wiki/Acme", "Acme") is False


def test_excluded_domain_societe_com_rejected():
    assert _is_valid_company_url("https://www.societe.com/societe/acme.html", "Acme") is False


def test_excluded_domain_linkedin_rejected():
    assert _is_valid_company_url("https://www.linkedin.com/company/acme", "Acme") is False


def test_keyword_short_exact_match_accepted():
    # "XMCO" (4 chars) représente 100% de "xmco" → accepté
    assert _is_valid_company_url("https://xmco.fr", "XMCO") is True


def test_keyword_long_match_accepted():
    # "Lumapps" (7 chars >= 5) → accepté
    assert _is_valid_company_url("https://www.lumapps.com", "Lumapps") is True


def test_keyword_not_in_domain_rejected():
    # Aucun mot de "Dupont Conseil" ne figure dans "widget.fr"
    assert _is_valid_company_url("https://widget.fr", "Dupont Conseil") is False


def test_all_stop_words_skips_keyword_check():
    # Entreprise dont tous les mots sont des stop words → validation skippée → URL acceptée
    # "France Services" → keywords = [] après filtrage
    result = _is_valid_company_url("https://anysite.fr", "France Services")
    assert result is True


def test_invalid_url_returns_false():
    assert _is_valid_company_url("not-a-url", "Acme") is False


def test_no_company_name_accepts_non_excluded_domain():
    # Sans nom d'entreprise, seul le test de blacklist s'applique
    assert _is_valid_company_url("https://acme.fr", "") is True


# ── find_company_website ──────────────────────────────────────────────────────

def _make_ddg_response(status_code: int, html_body: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = html_body
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


_DDG_HTML_WITH_RESULT = """
<html><body>
  <a class="result__a" href="https://www.lumapps.com/fr/produit">LumApps</a>
  <a class="result__a" href="https://fr.wikipedia.org/wiki/LumApps">Wikipedia</a>
</body></html>
"""


@pytest.mark.anyio
async def test_find_company_website_returns_first_valid_url():
    mock_client = _make_ddg_response(200, _DDG_HTML_WITH_RESULT)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await find_company_website("LumApps", "Lyon")
    # lumapps.com est valide ; wikipedia est exclu
    assert result == "https://www.lumapps.com"


@pytest.mark.anyio
async def test_find_company_website_returns_none_when_no_valid_url():
    html = """
    <a class="result__a" href="https://fr.wikipedia.org/wiki/Truc">Wikipedia</a>
    <a class="result__a" href="https://www.societe.com/societe/truc.html">Societe</a>
    """
    mock_client = _make_ddg_response(200, html)
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await find_company_website("Truc", "Paris")
    assert result is None


@pytest.mark.anyio
async def test_find_company_website_ddg_throttle_returns_none():
    # DDG renvoie 202 quand il throttle → retour None
    mock_client = _make_ddg_response(202, "")
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await find_company_website("Acme", "Paris")
    assert result is None


@pytest.mark.anyio
async def test_find_company_website_connection_error_returns_none():
    import httpx

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await find_company_website("Acme", "Paris")
    assert result is None
