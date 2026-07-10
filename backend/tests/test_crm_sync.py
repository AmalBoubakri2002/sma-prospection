import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.crm.sync import historize_email_in_chatter, push_lead_to_odoo
from app.models.lead import Lead


def _make_lead(**overrides) -> Lead:
    defaults = dict(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        company_name="Acme Corp",
        siret="12345678900011",
    )
    return Lead(**{**defaults, **overrides})


@pytest.mark.anyio
async def test_push_lead_to_odoo_creates_when_not_found():
    lead = _make_lead()
    execute_kw = AsyncMock(side_effect=[[], 99])  # search → [] puis create → 99

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        odoo_lead_id = await push_lead_to_odoo(lead)

    assert odoo_lead_id == 99
    assert execute_kw.call_count == 2

    search_call, create_call = execute_kw.call_args_list
    assert search_call.args[:2] == ("crm.lead", "search")
    assert search_call.args[2] == [[["x_sma_pc_id", "=", str(lead.id)]]]
    assert create_call.args[:2] == ("crm.lead", "create")


@pytest.mark.anyio
async def test_push_lead_to_odoo_writes_when_already_synced():
    lead = _make_lead()
    execute_kw = AsyncMock(side_effect=[[42], None])  # search → [42] puis write → None

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        odoo_lead_id = await push_lead_to_odoo(lead)

    assert odoo_lead_id == 42
    assert execute_kw.call_count == 2

    search_call, write_call = execute_kw.call_args_list
    assert write_call.args[:2] == ("crm.lead", "write")
    assert write_call.args[2][0] == [42]  # ids passés à write


@pytest.mark.anyio
async def test_historize_email_in_chatter_calls_message_post():
    execute_kw = AsyncMock(return_value=None)

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await historize_email_in_chatter(42, "Objet test", "<p>Contenu</p>")

    execute_kw.assert_called_once()
    args = execute_kw.call_args.args
    assert args[:2] == ("crm.lead", "message_post")
    assert args[2] == [[42]]
    kwargs_payload = args[3]
    assert "Objet test" in kwargs_payload["body"]
    assert "<p>Contenu</p>" in kwargs_payload["body"]
    assert kwargs_payload["subject"] == "Objet test"
