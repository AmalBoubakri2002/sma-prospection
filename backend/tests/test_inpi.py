from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.enrichissement import inpi
from app.agents.enrichissement.inpi import InpiAuthError, _extract_latest_finances, _login, _to_int


def test_extract_latest_finances_nominal():
    bilans = [
        {"dateCloture": "2022-12-31", "chiffreAffaires": 1000000, "resultatNet": 50000},
        {"dateCloture": "2023-12-31", "chiffreAffaires": 1500000, "resultatNet": 80000},
    ]
    result = _extract_latest_finances(bilans)
    assert result["ca"] == 1500000
    assert result["resultat_net"] == 80000
    # ca_n1 = CA de l'année N-1 (2022)
    assert result["ca_n1"] == 1000000


def test_extract_latest_finances_empty():
    assert _extract_latest_finances([]) == {}
    assert _extract_latest_finances({}) == {}


def test_extract_latest_finances_missing_ca():
    bilans = [{"dateCloture": "2023-12-31", "resultatNet": 10000}]
    result = _extract_latest_finances(bilans)
    assert result["ca"] is None
    assert result["resultat_net"] == 10000
    assert result["ca_n1"] is None  # pas de bilan N-1


def test_to_int_nominal():
    assert _to_int(1500000) == 1500000
    assert _to_int("2500000") == 2500000
    assert _to_int(1500000.0) == 1500000


def test_to_int_none():
    assert _to_int(None) is None
    assert _to_int("") is None


# ── cas supplémentaires ───────────────────────────────────────────────────────

def test_extract_latest_finances_snake_case_fields():
    """L'API INPI peut retourner des champs en snake_case."""
    bilans = [{"date_cloture": "2023-12-31", "chiffre_affaires": 900000, "resultat_net": 30000}]
    result = _extract_latest_finances(bilans)
    assert result["ca"] == 900000
    assert result["resultat_net"] == 30000
    assert result["ca_n1"] is None


def test_extract_latest_finances_dict_with_bilans_key():
    """L'API peut retourner un dict {'bilans': [...]} plutôt qu'une liste directe."""
    data = {
        "bilans": [
            {"dateCloture": "2023-06-30", "chiffreAffaires": 750000, "resultatNet": 12000}
        ]
    }
    result = _extract_latest_finances(data)
    assert result["ca"] == 750000
    assert result["resultat_net"] == 12000


def test_extract_latest_finances_zero_ca():
    """Un CA égal à zéro (entreprise sans chiffre d'affaires) ne doit pas être ignoré."""
    bilans = [{"dateCloture": "2023-12-31", "chiffreAffaires": 0, "resultatNet": -5000}]
    result = _extract_latest_finances(bilans)
    # Un CA de 0 est une valeur valide, pas une absence de données
    assert result["ca"] == 0
    assert result["resultat_net"] == -5000


def test_extract_latest_finances_picks_most_recent_by_date():
    bilans = [
        {"dateCloture": "2021-12-31", "chiffreAffaires": 500000, "resultatNet": 5000},
        {"dateCloture": "2023-12-31", "chiffreAffaires": 900000, "resultatNet": 25000},
        {"dateCloture": "2022-12-31", "chiffreAffaires": 700000, "resultatNet": 15000},
    ]
    result = _extract_latest_finances(bilans)
    assert result["ca"] == 900000     # 2023 est le plus récent
    assert result["ca_n1"] == 700000  # 2022 est N-1


def test_extract_latest_finances_single_bilan_no_ca_n1():
    """Un seul bilan disponible → ca_n1 est None."""
    bilans = [{"dateCloture": "2023-12-31", "chiffreAffaires": 500000, "resultatNet": 20000}]
    result = _extract_latest_finances(bilans)
    assert result["ca"] == 500000
    assert result["ca_n1"] is None


def test_to_int_zero():
    assert _to_int(0) == 0
    assert _to_int("0") == 0
    assert _to_int(0.0) == 0


def test_to_int_negative():
    assert _to_int(-50000) == -50000
    assert _to_int("-50000.5") == -50000


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
