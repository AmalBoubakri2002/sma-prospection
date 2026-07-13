"""Tests du webhook Odoo entrant (boucle retour CRM) :
- authentification par secret partagé (fail closed si non configuré) ;
- routage des événements (inconnu → ignoré, lead introuvable → journalisé) ;
- règles de transition de statut dans apply_event (idempotence, garde-fous).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints import webhooks
from app.core.config import settings
from app.db.base import get_db
from app.models.lead import Lead, LeadStatus
from app.models.webhook_event import WebhookEventResult
from app.services.odoo_webhook import apply_event, find_lead_for_event

_SECRET = "test-webhook-secret"


def _make_lead(**overrides) -> Lead:
    defaults = dict(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        company_name="Acme Corp",
        siret="12345678900011",
        status=LeadStatus.SYNCHRONISE_CRM,
    )
    return Lead(**{**defaults, **overrides})


def _make_client(mock_db) -> AsyncClient:
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/webhooks")

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Authentification ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_webhook_rejected_without_secret_header():
    async with _make_client(AsyncMock()) as client:
        with patch.object(settings, "ODOO_WEBHOOK_SECRET", _SECRET):
            response = await client.post("/webhooks/odoo", json={"event": "lead.won"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_webhook_rejected_with_wrong_secret():
    async with _make_client(AsyncMock()) as client:
        with patch.object(settings, "ODOO_WEBHOOK_SECRET", _SECRET):
            response = await client.post(
                "/webhooks/odoo",
                json={"event": "lead.won"},
                headers={"X-SMA-Webhook-Secret": "mauvais-secret"},
            )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_webhook_fails_closed_when_secret_not_configured():
    """Secret vide côté backend = endpoint fermé (503), jamais ouvert à tous."""
    async with _make_client(AsyncMock()) as client:
        with patch.object(settings, "ODOO_WEBHOOK_SECRET", ""):
            response = await client.post(
                "/webhooks/odoo",
                json={"event": "lead.won"},
                headers={"X-SMA-Webhook-Secret": ""},
            )
    assert response.status_code == 503


# ── Routage des événements ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_webhook_unknown_event_is_ignored_but_journalized():
    record_event = AsyncMock()
    async with _make_client(AsyncMock()) as client:
        with (
            patch.object(settings, "ODOO_WEBHOOK_SECRET", _SECRET),
            patch("app.api.v1.endpoints.webhooks.record_event", record_event),
        ):
            response = await client.post(
                "/webhooks/odoo",
                json={"event": "lead.deleted", "odoo_lead_id": 42},
                headers={"X-SMA-Webhook-Secret": _SECRET},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert record_event.call_args.kwargs["result"] == WebhookEventResult.IGNORED


@pytest.mark.anyio
async def test_webhook_lead_not_found_returns_200_and_journalizes():
    """200 même si le lead est introuvable : un retry Odoo ne réparerait rien,
    l'entrée webhook_events suffit au diagnostic."""
    record_event = AsyncMock()
    find_lead = AsyncMock(return_value=None)
    async with _make_client(AsyncMock()) as client:
        with (
            patch.object(settings, "ODOO_WEBHOOK_SECRET", _SECRET),
            patch("app.api.v1.endpoints.webhooks.record_event", record_event),
            patch("app.api.v1.endpoints.webhooks.find_lead_for_event", find_lead),
        ):
            response = await client.post(
                "/webhooks/odoo",
                json={"event": "lead.won", "odoo_lead_id": 42},
                headers={"X-SMA-Webhook-Secret": _SECRET},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "lead_not_found"
    assert record_event.call_args.kwargs["result"] == WebhookEventResult.LEAD_NOT_FOUND


@pytest.mark.anyio
async def test_webhook_processed_event_returns_lead_info():
    lead = _make_lead()
    record_event = AsyncMock()
    find_lead = AsyncMock(return_value=lead)

    async def _apply(db, lead_arg, event):
        lead_arg.status = LeadStatus.REPONDU
        return WebhookEventResult.PROCESSED

    async with _make_client(AsyncMock()) as client:
        with (
            patch.object(settings, "ODOO_WEBHOOK_SECRET", _SECRET),
            patch("app.api.v1.endpoints.webhooks.record_event", record_event),
            patch("app.api.v1.endpoints.webhooks.find_lead_for_event", find_lead),
            patch("app.api.v1.endpoints.webhooks.apply_event", side_effect=_apply),
        ):
            response = await client.post(
                "/webhooks/odoo",
                json={"event": "message.received", "odoo_lead_id": 42, "x_sma_pc_id": str(lead.id)},
                headers={"X-SMA-Webhook-Secret": _SECRET},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["lead_id"] == str(lead.id)
    assert body["lead_status"] == LeadStatus.REPONDU
    assert record_event.call_args.kwargs["lead_id"] == lead.id


# ── apply_event : transitions de statut ────────────────────────────────────────

def _db_with_campaign(commercial_id=None):
    """AsyncMock de session dont db.get renvoie une campagne factice."""
    db = AsyncMock()
    campaign = MagicMock()
    campaign.commercial_id = commercial_id or uuid.uuid4()
    db.get.return_value = campaign
    return db


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("event", "expected_status"),
    [
        ("lead.won", LeadStatus.REPONDU),
        ("message.received", LeadStatus.REPONDU),
        ("lead.lost", LeadStatus.SANS_REPONSE),
    ],
)
async def test_apply_event_updates_status_and_notifies(event, expected_status):
    lead = _make_lead(status=LeadStatus.SYNCHRONISE_CRM)
    db = _db_with_campaign()
    notify = AsyncMock()

    with patch("app.services.odoo_webhook.notify_retour_crm", notify):
        result = await apply_event(db, lead, event)

    assert result == WebhookEventResult.PROCESSED
    assert lead.status == expected_status
    db.commit.assert_awaited()
    notify.assert_awaited_once()
    assert notify.call_args.args[2] == "Acme Corp"  # company_name
    assert notify.call_args.args[3] == event


@pytest.mark.anyio
async def test_apply_event_skips_lead_not_yet_synced():
    """Un lead encore dans le pipeline amont (avant synchro CRM) n'est jamais modifié."""
    lead = _make_lead(status=LeadStatus.EN_ATTENTE_VALIDATION)
    db = AsyncMock()
    notify = AsyncMock()

    with patch("app.services.odoo_webhook.notify_retour_crm", notify):
        result = await apply_event(db, lead, "lead.won")

    assert result == WebhookEventResult.SKIPPED_STATUS
    assert lead.status == LeadStatus.EN_ATTENTE_VALIDATION
    db.commit.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.anyio
async def test_apply_event_is_idempotent_on_redelivery():
    """Rejouer le même événement (relivraison Odoo) : aucun changement, pas de renotification."""
    lead = _make_lead(status=LeadStatus.REPONDU)
    db = AsyncMock()
    notify = AsyncMock()

    with patch("app.services.odoo_webhook.notify_retour_crm", notify):
        result = await apply_event(db, lead, "message.received")

    assert result == WebhookEventResult.NOOP
    db.commit.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.anyio
async def test_apply_event_lost_does_not_downgrade_repondu():
    """REPONDU décrit un fait acquis (le prospect a répondu) : une perte
    d'opportunité ultérieure ne le rétrograde pas en SANS_REPONSE."""
    lead = _make_lead(status=LeadStatus.REPONDU)
    db = AsyncMock()

    result = await apply_event(db, lead, "lead.lost")

    assert result == WebhookEventResult.NOOP
    assert lead.status == LeadStatus.REPONDU
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_apply_event_won_after_sans_reponse_updates():
    """Un lead SANS_REPONSE peut encore devenir REPONDU (relance tardive gagnée)."""
    lead = _make_lead(status=LeadStatus.SANS_REPONSE)
    db = _db_with_campaign()

    with patch("app.services.odoo_webhook.notify_retour_crm", AsyncMock()):
        result = await apply_event(db, lead, "lead.won")

    assert result == WebhookEventResult.PROCESSED
    assert lead.status == LeadStatus.REPONDU


# ── find_lead_for_event : résolution du lead ───────────────────────────────────

@pytest.mark.anyio
async def test_find_lead_prefers_x_sma_pc_id():
    lead = _make_lead()
    db = AsyncMock()
    db.get.return_value = lead

    found = await find_lead_for_event(db, str(lead.id), odoo_lead_id=42)

    assert found is lead
    db.get.assert_awaited_once_with(Lead, lead.id)
    db.execute.assert_not_awaited()  # pas besoin du repli crm_syncs


@pytest.mark.anyio
async def test_find_lead_falls_back_to_crm_sync_on_invalid_uuid():
    """x_sma_pc_id corrompu côté Odoo → repli sur crm_syncs.odoo_lead_id."""
    lead = _make_lead()
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = lead
    db.execute.return_value = execute_result

    found = await find_lead_for_event(db, "pas-un-uuid", odoo_lead_id=42)

    assert found is lead
    db.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_find_lead_returns_none_when_nothing_matches():
    db = AsyncMock()
    db.get.return_value = None
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    found = await find_lead_for_event(db, str(uuid.uuid4()), odoo_lead_id=42)

    assert found is None
