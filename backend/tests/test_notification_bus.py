"""Tests du bus de notifications inter-processus (PostgreSQL LISTEN/NOTIFY) :
publication transactionnelle, routage vers les WebSockets, et intégration
dans create_notification (le push doit fonctionner depuis un worker)."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.notification_bus import CHANNEL, _handle_payload, publish
from app.services.campaign import update_campaign_status
from app.services.notification import create_notification


@pytest.mark.anyio
async def test_publish_emits_pg_notify_with_envelope():
    db = AsyncMock()
    recipient = uuid.uuid4()

    await publish(db, recipient, {"kind": "notification", "data": {"title": "Test"}})

    db.execute.assert_awaited_once()
    params = db.execute.call_args.args[1]
    assert params["channel"] == CHANNEL
    envelope = json.loads(params["payload"])
    assert envelope["recipient_id"] == str(recipient)
    assert envelope["payload"]["data"]["title"] == "Test"


@pytest.mark.anyio
async def test_handle_payload_routes_to_recipient_sockets():
    recipient = uuid.uuid4()
    payload = json.dumps(
        {
            "recipient_id": str(recipient),
            "payload": {"kind": "notification", "data": {"title": "Push"}},
        }
    )
    send = AsyncMock()

    with patch("app.core.notification_bus.manager.send_to_user", send):
        await _handle_payload(payload)

    send.assert_awaited_once_with(recipient, {"kind": "notification", "data": {"title": "Push"}})


@pytest.mark.anyio
async def test_handle_payload_ignores_invalid_json():
    """Un payload corrompu est logué et ignoré — jamais d'exception qui
    tuerait la boucle d'écoute."""
    send = AsyncMock()

    with patch("app.core.notification_bus.manager.send_to_user", send):
        await _handle_payload("pas du json {")
        await _handle_payload(json.dumps({"recipient_id": "pas-un-uuid"}))

    send.assert_not_awaited()


@pytest.mark.anyio
async def test_create_notification_publishes_before_commit():
    """La notification est publiée sur le bus DANS la transaction (avant le
    commit) : PostgreSQL la délivre au commit, y compris depuis un worker."""
    db = AsyncMock()

    async def _flush():
        # Simule les défauts appliqués par SQLAlchemy au flush
        notification = db.add.call_args.args[0]
        notification.id = uuid.uuid4()
        notification.is_read = False
        notification.created_at = datetime.now(timezone.utc)

    db.flush = AsyncMock(side_effect=_flush)
    recipient = uuid.uuid4()
    bus_publish = AsyncMock()

    with patch("app.services.notification.publish", bus_publish):
        await create_notification(
            db, recipient_id=recipient, type="EMAILS_PRETS",
            title="Emails prêts", message="2 emails générés",
        )

    bus_publish.assert_awaited_once()
    published_recipient = bus_publish.call_args.args[1]
    payload = bus_publish.call_args.args[2]
    assert published_recipient == recipient
    assert payload["kind"] == "notification"
    assert payload["data"]["title"] == "Emails prêts"
    assert payload["data"]["type"] == "EMAILS_PRETS"
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_update_campaign_status_publishes_campaign_update():
    """Chaque transition de statut de campagne émet un événement campaign_update
    vers le commercial — c'est ce qui permet aux pages de suivre la progression
    du pipeline en direct, sans polling ni rechargement."""
    db = AsyncMock()
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.commercial_id = uuid.uuid4()
    bus_publish = AsyncMock()

    with patch("app.services.campaign.publish", bus_publish):
        await update_campaign_status(db, campaign, "scoring_pending")

    assert campaign.status == "scoring_pending"
    bus_publish.assert_awaited_once()
    assert bus_publish.call_args.args[1] == campaign.commercial_id
    payload = bus_publish.call_args.args[2]
    assert payload["kind"] == "campaign_update"
    assert payload["data"] == {"campaign_id": str(campaign.id), "status": "scoring_pending"}
    db.commit.assert_awaited_once()
