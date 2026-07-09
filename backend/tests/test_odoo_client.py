from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import odoo_client
from app.services.odoo_client import OdooAuthError, OdooError, authenticate, execute_kw


@pytest.fixture(autouse=True)
def _reset_uid_cache():
    """Le uid est mis en cache au niveau module — évite qu'un test pollue le suivant."""
    odoo_client._cached_uid = None
    yield
    odoo_client._cached_uid = None


def _jsonrpc_response(result=None, error=None) -> MagicMock:
    response = MagicMock(status_code=200)
    body = {"jsonrpc": "2.0", "id": 1}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    response.json.return_value = body
    return response


def _make_client(*responses: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=list(responses))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ── authenticate ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_authenticate_missing_credentials_raises_auth_error():
    with patch.object(odoo_client.settings, "ODOO_USERNAME", ""), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", ""
    ):
        with pytest.raises(OdooAuthError, match="ODOO_USERNAME"):
            await authenticate(AsyncMock())


@pytest.mark.anyio
async def test_authenticate_success_caches_uid():
    client = _make_client(_jsonrpc_response(result=2))

    with patch.object(odoo_client.settings, "ODOO_USERNAME", "admin"), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", "admin"
    ):
        uid = await authenticate(client)

    assert uid == 2
    assert odoo_client._cached_uid == 2

    # Un second appel réutilise le cache, sans refaire de requête d'auth.
    uid2 = await authenticate(client)
    assert uid2 == 2
    client.post.assert_called_once()


@pytest.mark.anyio
async def test_authenticate_rejected_by_odoo_raises_auth_error():
    """Odoo renvoie result=False quand les identifiants sont invalides (pas d'erreur JSON-RPC)."""
    client = _make_client(_jsonrpc_response(result=False))

    with patch.object(odoo_client.settings, "ODOO_USERNAME", "admin"), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", "wrong"
    ):
        with pytest.raises(OdooAuthError, match="Authentification Odoo"):
            await authenticate(client)


@pytest.mark.anyio
async def test_authenticate_non_200_raises_odoo_error():
    response = MagicMock(status_code=500, text="internal error")
    client = _make_client(response)

    with patch.object(odoo_client.settings, "ODOO_USERNAME", "admin"), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", "admin"
    ):
        with pytest.raises(OdooError, match="500"):
            await authenticate(client)


@pytest.mark.anyio
async def test_authenticate_jsonrpc_error_field_raises_odoo_error():
    client = _make_client(_jsonrpc_response(error={"message": "Access Denied"}))

    with patch.object(odoo_client.settings, "ODOO_USERNAME", "admin"), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", "admin"
    ):
        with pytest.raises(OdooError, match="Access Denied"):
            await authenticate(client)


# ── execute_kw ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_execute_kw_authenticates_then_calls_object_execute_kw():
    mock_client = _make_client(
        _jsonrpc_response(result=2),  # common.authenticate
        _jsonrpc_response(result=[42]),  # object.execute_kw (ex: create → [id])
    )

    with patch("httpx.AsyncClient", return_value=mock_client), patch.object(
        odoo_client.settings, "ODOO_DB", "odoo"
    ), patch.object(odoo_client.settings, "ODOO_USERNAME", "admin"), patch.object(
        odoo_client.settings, "ODOO_PASSWORD", "admin"
    ):
        result = await execute_kw("crm.lead", "create", [{"name": "Acme Corp"}])

    assert result == [42]
    assert mock_client.post.call_count == 2

    second_call_payload = mock_client.post.call_args_list[1].kwargs["json"]
    assert second_call_payload["params"]["service"] == "object"
    assert second_call_payload["params"]["method"] == "execute_kw"
    assert second_call_payload["params"]["args"][3] == "crm.lead"
    assert second_call_payload["params"]["args"][4] == "create"


@pytest.mark.anyio
async def test_execute_kw_propagates_odoo_error():
    mock_client = _make_client(
        _jsonrpc_response(result=2),
        _jsonrpc_response(error={"message": "ValidationError"}),
    )

    with patch("httpx.AsyncClient", return_value=mock_client), patch.object(
        odoo_client.settings, "ODOO_USERNAME", "admin"
    ), patch.object(odoo_client.settings, "ODOO_PASSWORD", "admin"):
        with pytest.raises(OdooError, match="ValidationError"):
            await execute_kw("crm.lead", "create", [{}])
