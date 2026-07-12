import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.crm import sync
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


def _odoo_user(user_id: int, partner_id: int) -> list[dict]:
    """Forme renvoyée par res.users.search_read(fields=['partner_id'])."""
    return [{"id": user_id, "partner_id": [partner_id, "Nom"]}]


@pytest.fixture(autouse=True)
def _reset_caches():
    """Le stage_id et les comptes Odoo par email sont mis en cache au niveau module."""
    sync._cached_qualified_stage_id = None
    sync._cached_odoo_user_by_email = {}
    yield
    sync._cached_qualified_stage_id = None
    sync._cached_odoo_user_by_email = {}


@pytest.mark.anyio
async def test_push_lead_to_odoo_creates_when_not_found():
    lead = _make_lead()
    # stage search → [2] ; dedup search → [] ; create → 99
    execute_kw = AsyncMock(side_effect=[[2], [], 99])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        odoo_lead_id = await push_lead_to_odoo(lead)

    assert odoo_lead_id == 99
    assert execute_kw.call_count == 3

    stage_call, search_call, create_call = execute_kw.call_args_list
    assert stage_call.args[:2] == ("crm.stage", "search")
    assert search_call.args[:2] == ("crm.lead", "search")
    assert search_call.args[2] == [[["x_sma_pc_id", "=", str(lead.id)]]]
    assert create_call.args[:2] == ("crm.lead", "create")
    assert create_call.args[2][0]["stage_id"] == 2


@pytest.mark.anyio
async def test_push_lead_to_odoo_writes_when_already_synced():
    lead = _make_lead()
    # stage search → [2] ; dedup search → [42] ; write → None
    execute_kw = AsyncMock(side_effect=[[2], [42], None])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        odoo_lead_id = await push_lead_to_odoo(lead)

    assert odoo_lead_id == 42
    assert execute_kw.call_count == 3

    _, search_call, write_call = execute_kw.call_args_list
    assert write_call.args[:2] == ("crm.lead", "write")
    assert write_call.args[2][0] == [42]  # ids passés à write


@pytest.mark.anyio
async def test_push_lead_to_odoo_stage_lookup_is_cached_across_calls():
    lead1, lead2 = _make_lead(), _make_lead()
    execute_kw = AsyncMock(side_effect=[[2], [], 1, [], 2])  # stage cherché une seule fois

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await push_lead_to_odoo(lead1)
        await push_lead_to_odoo(lead2)

    stage_calls = [c for c in execute_kw.call_args_list if c.args[:2] == ("crm.stage", "search")]
    assert len(stage_calls) == 1


@pytest.mark.anyio
async def test_push_lead_to_odoo_sets_user_id_when_commercial_email_matches():
    lead = _make_lead()
    # stage search → [2] ; user search_read → [{id:7, partner_id:[70,...]}] ; dedup → [] ; create → 99
    execute_kw = AsyncMock(side_effect=[[2], _odoo_user(7, 70), [], 99])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await push_lead_to_odoo(lead, commercial_email="commercial@example.com")

    create_call = execute_kw.call_args_list[-1]
    assert create_call.args[2][0]["user_id"] == 7


@pytest.mark.anyio
async def test_push_lead_to_odoo_no_user_id_when_email_not_found_in_odoo():
    lead = _make_lead()
    # stage search → [2] ; user search_read → [] (aucun compte Odoo) ; dedup → [] ; create → 99
    execute_kw = AsyncMock(side_effect=[[2], [], [], 99])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await push_lead_to_odoo(lead, commercial_email="inconnu@example.com")

    create_call = execute_kw.call_args_list[-1]
    assert "user_id" not in create_call.args[2][0]


@pytest.mark.anyio
async def test_push_lead_to_odoo_retries_user_lookup_after_previous_miss():
    """Un compte Odoo créé après un premier échec de recherche doit être retrouvé
    sans attendre un redémarrage du worker (bug constaté : le "non trouvé" ne
    doit pas rester en cache indéfiniment, contrairement à un résultat trouvé)."""
    lead1, lead2 = _make_lead(), _make_lead()
    execute_kw = AsyncMock(
        side_effect=[
            [2], [], [], 1,                    # lead1 : stage, user search_read (vide), dedup, create
            _odoo_user(7, 70), [], 2,          # lead2 : user search_read (trouvé cette fois), dedup, create
        ]
    )

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await push_lead_to_odoo(lead1, commercial_email="commercial@example.com")
        await push_lead_to_odoo(lead2, commercial_email="commercial@example.com")

    user_search_calls = [c for c in execute_kw.call_args_list if c.args[:2] == ("res.users", "search_read")]
    assert len(user_search_calls) == 2  # re-cherché car le 1er essai n'avait rien trouvé

    last_create_call = execute_kw.call_args_list[-1]
    assert last_create_call.args[2][0]["user_id"] == 7


@pytest.mark.anyio
async def test_historize_email_in_chatter_calls_message_post():
    execute_kw = AsyncMock(return_value=None)

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        # Le body de message_post est échappé par Odoo avant affichage (constaté
        # en prod) : on envoie donc du texte brut, sans balises HTML à construire.
        await historize_email_in_chatter(42, "Objet test", "Ligne 1\nLigne 2")

    execute_kw.assert_called_once()
    args = execute_kw.call_args.args
    assert args[:2] == ("crm.lead", "message_post")
    assert args[2] == [[42]]
    kwargs_payload = args[3]
    assert kwargs_payload["body"] == "Objet : Objet test\n\nLigne 1\nLigne 2"
    assert kwargs_payload["subject"] == "Objet test"
    assert "author_id" not in kwargs_payload  # pas d'email commercial fourni


@pytest.mark.anyio
async def test_historize_email_in_chatter_sets_author_id_when_commercial_found():
    # user search_read → [{id:7, partner_id:[70,...]}] ; message_post → None
    execute_kw = AsyncMock(side_effect=[_odoo_user(7, 70), None])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        await historize_email_in_chatter(42, "Objet test", "Contenu", "commercial@example.com")

    message_post_call = execute_kw.call_args_list[-1]
    assert message_post_call.args[3]["author_id"] == 70


@pytest.mark.anyio
async def test_push_and_historize_share_the_odoo_user_cache():
    """push_lead_to_odoo et historize_email_in_chatter partagent le même cache :
    un seul aller-retour res.users pour les deux appels sur le même lead."""
    lead = _make_lead()
    execute_kw = AsyncMock(side_effect=[[2], _odoo_user(7, 70), [], 99, None])

    with patch("app.agents.crm.sync.odoo_client.execute_kw", execute_kw):
        odoo_lead_id = await push_lead_to_odoo(lead, commercial_email="commercial@example.com")
        await historize_email_in_chatter(odoo_lead_id, "Objet", "Contenu", "commercial@example.com")

    user_search_calls = [c for c in execute_kw.call_args_list if c.args[:2] == ("res.users", "search_read")]
    assert len(user_search_calls) == 1
