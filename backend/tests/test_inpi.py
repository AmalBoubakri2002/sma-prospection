from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement import inpi
from app.agents.enrichissement.inpi import (
    InpiAuthError,
    _extract_ca,
    _extract_latest_finances,
    _extract_resultat,
    _liasse_codes,
    _login,
    _parse_amount,
)


def _bilan_saisi(type_bilan: str, date_cloture: str, pages: list[dict]) -> dict:
    """Construit un item `bilansSaisis[]` tel que renvoyé par
    /api/companies/{siren}/attachments."""
    return {
        "dateCloture": date_cloture,
        "typeBilan": type_bilan,
        "bilanSaisi": {"bilan": {"detail": {"pages": pages}}},
    }


def _liasse(code: str, **montants: str) -> dict:
    return {"code": code, **montants}


# ── _parse_amount ──────────────────────────────────────────────────────────────

def test_parse_amount_nominal():
    assert _parse_amount("000000000001220") == 1220


def test_parse_amount_negative():
    assert _parse_amount("-000000001127414") == -1127414


def test_parse_amount_none_or_empty():
    assert _parse_amount(None) is None
    assert _parse_amount("") is None


def test_parse_amount_zero():
    assert _parse_amount("000000000000000") == 0


# ── _liasse_codes ──────────────────────────────────────────────────────────────

def test_liasse_codes_flattens_pages():
    bilan = {
        "detail": {
            "pages": [
                {"numero": 2, "liasses": [_liasse("DI", m1="100", m2="80")]},
                {"numero": 3, "liasses": [_liasse("FJ", m3="500", m4="400")]},
            ]
        }
    }
    codes = _liasse_codes(bilan)
    assert codes["DI"]["m1"] == "100"
    assert codes["FJ"]["m3"] == "500"


# ── _extract_ca / _extract_resultat — type "C" (complet) ──────────────────────

def test_extract_ca_type_c():
    codes = {"FJ": _liasse("FJ", m3="000000000699000", m4="000000000890000")}
    ca, ca_n1 = _extract_ca(codes, "C")
    assert ca == 699000
    assert ca_n1 == 890000


def test_extract_resultat_type_c():
    codes = {"DI": _liasse("DI", m1="000000001353000", m2="000000002280000")}
    resultat, resultat_n1 = _extract_resultat(codes, "C")
    assert resultat == 1353000
    assert resultat_n1 == 2280000


def test_extract_ca_type_c_missing_code_returns_none():
    """Compte de résultat déclaré confidentiel (codeConfidentialite=2) : la page 03
    n'est pas rediffusée, FJ est absent."""
    assert _extract_ca({}, "C") == (None, None)


# ── _extract_ca / _extract_resultat — type "S" (simplifié) ────────────────────

def test_extract_ca_type_s_sums_codes():
    codes = {"210": _liasse("210", m1="000000001030000", m2="000000000890000")}
    ca, ca_n1 = _extract_ca(codes, "S")
    assert ca == 1030000
    assert ca_n1 == 890000


def test_extract_ca_type_s_sums_multiple_codes():
    codes = {
        "210": _liasse("210", m1="000000000500000", m2="000000000400000"),
        "214": _liasse("214", m1="000000000200000", m2="000000000100000"),
    }
    ca, ca_n1 = _extract_ca(codes, "S")
    assert ca == 700000
    assert ca_n1 == 500000


def test_extract_ca_type_s_no_codes_returns_none():
    assert _extract_ca({}, "S") == (None, None)


def test_extract_resultat_type_s():
    codes = {"310": _liasse("310", m1="000000000592000", m2="000000002280000")}
    resultat, resultat_n1 = _extract_resultat(codes, "S")
    assert resultat == 592000
    assert resultat_n1 == 2280000


# ── _extract_latest_finances ───────────────────────────────────────────────────

def test_extract_latest_finances_empty():
    assert _extract_latest_finances([]) == {}


def test_extract_latest_finances_type_c_nominal():
    bilans_saisis = [
        _bilan_saisi("C", "2023-12-31", [
            {"numero": 2, "liasses": [_liasse("DI", m1="000000001353000", m2="000000002280000")]},
            {"numero": 3, "liasses": [_liasse("FJ", m3="000000000699000", m4="000000000890000")]},
        ])
    ]
    result = _extract_latest_finances(bilans_saisis)
    assert result == {"ca": 699000, "resultat_net": 1353000, "ca_n1": 890000}


def test_extract_latest_finances_type_s_nominal():
    bilans_saisis = [
        _bilan_saisi("S", "2024-12-31", [
            {"numero": 2, "liasses": [
                _liasse("210", m1="000000001030000", m2="000000000890000"),
                _liasse("310", m1="000000000592000", m2="000000002280000"),
            ]},
        ])
    ]
    result = _extract_latest_finances(bilans_saisis)
    assert result == {"ca": 1030000, "resultat_net": 592000, "ca_n1": 890000}


def test_extract_latest_finances_picks_most_recent_by_date():
    older = _bilan_saisi("C", "2022-12-31", [
        {"numero": 2, "liasses": [_liasse("DI", m1="000000000100000")]},
        {"numero": 3, "liasses": [_liasse("FJ", m3="000000000500000")]},
    ])
    newer = _bilan_saisi("S", "2024-12-31", [
        {"numero": 2, "liasses": [
            _liasse("210", m1="000000000900000"),
            _liasse("310", m1="000000000250000"),
        ]},
    ])
    result = _extract_latest_finances([older, newer])
    assert result["ca"] == 900000
    assert result["resultat_net"] == 250000


def test_extract_latest_finances_ignores_unsupported_type():
    """Type 'K' (consolidé) a une nomenclature de codes différente — non interprété."""
    bilans_saisis = [
        _bilan_saisi("K", "2025-12-31", [
            {"numero": 3, "liasses": [_liasse("FJ", m3="000027376000000")]},
        ])
    ]
    assert _extract_latest_finances(bilans_saisis) == {}


def test_extract_latest_finances_ignores_entries_without_bilan_saisi():
    """Bilan confidentiel en intégralité (codeConfidentialite=1) : bilanSaisi absent."""
    bilans_saisis = [
        {"dateCloture": "2023-12-31", "typeBilan": "C", "bilanSaisi": None},
    ]
    assert _extract_latest_finances(bilans_saisis) == {}


def test_extract_latest_finances_partial_confidentiality_keeps_resultat():
    """codeConfidentialite=2 : compte de résultat (pages 03/04) masqué, mais le
    passif (page 02, DI) reste rediffusé — CA absent, résultat net disponible."""
    bilans_saisis = [
        _bilan_saisi("C", "2019-12-31", [
            {"numero": 2, "liasses": [_liasse("DI", m1="000000000549605", m2="000000000648817")]},
        ])
    ]
    result = _extract_latest_finances(bilans_saisis)
    assert result == {"ca": None, "resultat_net": 549605, "ca_n1": None}


def test_extract_latest_finances_zero_ca_is_not_ignored():
    bilans_saisis = [
        _bilan_saisi("C", "2023-12-31", [
            {"numero": 2, "liasses": [_liasse("DI", m1="-000000000005000")]},
            {"numero": 3, "liasses": [_liasse("FJ", m3="000000000000000")]},
        ])
    ]
    result = _extract_latest_finances(bilans_saisis)
    assert result["ca"] == 0
    assert result["resultat_net"] == -5000


# ── login (auth par identifiants, pas de clé API statique) ─────────────────────

@pytest.fixture(autouse=True)
def _reset_token_cache():
    """Le token est mis en cache au niveau module — évite qu'un test pollue le suivant."""
    inpi._cached_token = None
    yield
    inpi._cached_token = None


@pytest.mark.anyio
async def test_login_missing_credentials_raises_auth_error():
    with patch.object(inpi.settings, "INPI_USERNAME", ""), patch.object(inpi.settings, "INPI_PASSWORD", ""):
        with pytest.raises(InpiAuthError, match="INPI_USERNAME"):
            await _login(AsyncMock())


@pytest.mark.anyio
async def test_login_success_caches_token():
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"token": "abc123"}
    client = AsyncMock()
    client.post = AsyncMock(return_value=fake_response)

    with patch.object(inpi.settings, "INPI_USERNAME", "user"), patch.object(inpi.settings, "INPI_PASSWORD", "pass"):
        token = await _login(client)

    assert token == "abc123"
    assert inpi._cached_token == "abc123"

    # Un second appel réutilise le cache, sans refaire de requête de login.
    token2 = await _login(client)
    assert token2 == "abc123"
    client.post.assert_called_once()


@pytest.mark.anyio
async def test_login_non_200_raises_auth_error():
    fake_response = MagicMock(status_code=401, text="identifiants invalides")
    client = AsyncMock()
    client.post = AsyncMock(return_value=fake_response)

    with patch.object(inpi.settings, "INPI_USERNAME", "user"), patch.object(inpi.settings, "INPI_PASSWORD", "pass"):
        with pytest.raises(InpiAuthError, match="401"):
            await _login(client)


@pytest.mark.anyio
async def test_login_response_without_token_field_raises():
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"unexpected": "shape"}
    client = AsyncMock()
    client.post = AsyncMock(return_value=fake_response)

    with patch.object(inpi.settings, "INPI_USERNAME", "user"), patch.object(inpi.settings, "INPI_PASSWORD", "pass"):
        with pytest.raises(InpiAuthError, match="token"):
            await _login(client)
