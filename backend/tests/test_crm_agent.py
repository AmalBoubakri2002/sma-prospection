"""Tests de run_crm (Agent CRM) : enchaînement synchro → envoi email → CONTACTE,
et isolation des échecs (un échec d'envoi email n'annule pas la synchronisation).
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.crm.agent import run_crm
from app.core.config import settings
from app.models.lead import Lead, LeadStatus


def _make_lead(**overrides) -> Lead:
    defaults = dict(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        company_name="Acme Corp",
        siret="12345678900011",
        status=LeadStatus.VALIDE,
        email="prospect@example.com",
        objet_email="Objet test",
        contenu_email="Corps du message",
    )
    return Lead(**{**defaults, **overrides})


def _make_db(commercial_email="commercial@example.com"):
    db = AsyncMock()
    commercial = MagicMock()
    commercial.email = commercial_email
    db.get.return_value = commercial
    return db


def _campaign():
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.commercial_id = uuid.uuid4()
    return campaign


def _patches(lead, **overrides):
    """Patche toutes les dépendances de run_crm ; list_leads renvoie le lead une
    fois puis une liste vide (le vrai code sort les leads de VALIDE en les traitant)."""
    mocks = {
        "list_leads_to_sync_crm": AsyncMock(side_effect=[[lead], []]),
        "find_crm_duplicate": AsyncMock(return_value=None),
        "push_lead_to_odoo": AsyncMock(return_value=99),
        "historize_email_in_chatter": AsyncMock(),
        "send_prospection_email": AsyncMock(return_value=55),
        "mark_crm_sync_success": AsyncMock(),
        "mark_crm_sync_error": AsyncMock(),
        "update_lead_synced_crm": AsyncMock(),
        "update_lead_contacted": AsyncMock(),
    }
    mocks.update(overrides)
    return mocks


async def _run(db, campaign, mocks, send_emails=True):
    with ExitStack() as stack:
        stack.enter_context(patch.object(settings, "ODOO_SEND_EMAILS", send_emails))
        for name, mock in mocks.items():
            stack.enter_context(patch(f"app.agents.crm.agent.{name}", mock))
        return await run_crm(db, campaign)


@pytest.mark.anyio
async def test_run_crm_syncs_sends_email_and_marks_contacted():
    lead = _make_lead()
    mocks = _patches(lead)

    result = await _run(_make_db(), _campaign(), mocks)

    assert result == {
        "leads_synchronises": 1,
        "doublons_rattaches": 0,
        "leads_erreurs": 0,
        "emails_envoyes": 1,
        "emails_erreurs": 0,
    }
    send_call = mocks["send_prospection_email"].call_args
    assert send_call.args[0] == 99                        # odoo_lead_id du push
    assert send_call.args[3] == "prospect@example.com"    # destinataire = prospect
    assert send_call.args[4] == "commercial@example.com"  # expéditeur = commercial
    mocks["update_lead_contacted"].assert_awaited_once()


@pytest.mark.anyio
async def test_run_crm_email_failure_does_not_break_sync():
    """Échec SMTP : le lead reste synchronisé (fiche Odoo créée) mais pas CONTACTE."""
    lead = _make_lead()
    mocks = _patches(lead, send_prospection_email=AsyncMock(side_effect=RuntimeError("SMTP down")))

    result = await _run(_make_db(), _campaign(), mocks)

    assert result["leads_synchronises"] == 1
    assert result["emails_envoyes"] == 0
    assert result["emails_erreurs"] == 1
    mocks["update_lead_synced_crm"].assert_awaited_once()
    mocks["update_lead_contacted"].assert_not_awaited()


@pytest.mark.anyio
async def test_run_crm_skips_email_when_lead_has_no_address():
    lead = _make_lead(email=None)
    mocks = _patches(lead)

    result = await _run(_make_db(), _campaign(), mocks)

    assert result["leads_synchronises"] == 1
    assert result["emails_erreurs"] == 1
    mocks["send_prospection_email"].assert_not_awaited()
    mocks["update_lead_contacted"].assert_not_awaited()


@pytest.mark.anyio
async def test_run_crm_send_disabled_by_flag():
    """ODOO_SEND_EMAILS=false : synchro seule, aucun envoi ni erreur comptée."""
    lead = _make_lead()
    mocks = _patches(lead)

    result = await _run(_make_db(), _campaign(), mocks, send_emails=False)

    assert result["leads_synchronises"] == 1
    assert result["emails_envoyes"] == 0
    assert result["emails_erreurs"] == 0
    mocks["send_prospection_email"].assert_not_awaited()


@pytest.mark.anyio
async def test_run_crm_no_email_attempt_when_sync_fails():
    lead = _make_lead()
    mocks = _patches(lead, push_lead_to_odoo=AsyncMock(side_effect=RuntimeError("Odoo down")))

    result = await _run(_make_db(), _campaign(), mocks)

    assert result["leads_synchronises"] == 0
    assert result["leads_erreurs"] == 1
    mocks["mark_crm_sync_error"].assert_awaited_once()
    mocks["send_prospection_email"].assert_not_awaited()


@pytest.mark.anyio
async def test_run_crm_attaches_to_existing_odoo_lead_instead_of_duplicating():
    """Entreprise déjà suivie dans Odoo (autre campagne) : rattachement à la
    fiche existante — pas de création, pas d'historisation, pas d'email."""
    lead = _make_lead()
    mocks = _patches(lead, find_crm_duplicate=AsyncMock(return_value=77))

    result = await _run(_make_db(), _campaign(), mocks)

    assert result["doublons_rattaches"] == 1
    assert result["leads_synchronises"] == 0
    assert result["emails_envoyes"] == 0
    # Rattaché à la fiche existante #77, marqué synchronisé côté SMA-PC
    sync_call = mocks["mark_crm_sync_success"].call_args
    assert sync_call.args[2] == 77
    mocks["update_lead_synced_crm"].assert_awaited_once()
    # Aucune écriture Odoo ni email vers un prospect déjà engagé
    mocks["push_lead_to_odoo"].assert_not_awaited()
    mocks["historize_email_in_chatter"].assert_not_awaited()
    mocks["send_prospection_email"].assert_not_awaited()
    mocks["update_lead_contacted"].assert_not_awaited()


@pytest.mark.anyio
async def test_run_crm_uses_fallback_sender_when_no_commercial_email():
    lead = _make_lead()
    mocks = _patches(lead)

    await _run(_make_db(commercial_email=None), _campaign(), mocks)

    send_call = mocks["send_prospection_email"].call_args
    assert send_call.args[4] == settings.ODOO_EMAIL_FROM_DEFAULT
