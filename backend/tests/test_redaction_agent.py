"""Tests unitaires pour l'Agent Rédaction.

Couvre :
  1. _build_context() — génération du contexte lead (fonction pure, pas d'API)
  2. run_redaction()  — pipeline complet avec API mockée
  3. Gestion d'erreur — un lead défaillant ne bloque pas les suivants
  4. JSON mal formé  — le modèle renvoie du texte au lieu de JSON
"""

import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.redaction.agent import _build_context, run_redaction
from app.models.lead import Lead, LeadStatus


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_lead(
    siret: str = "12345678901234",
    company_name: str = "TechCorp SAS",
    prenom: str | None = "Alice",
    nom: str | None = "Martin",
    titre: str | None = "CEO",
    secteur: str | None = "6201Z",
    taille: str | None = "21",
    adresse: str | None = "75008 Paris",
    email: str | None = "alice@techcorp.fr",
    telephone: str | None = "+33612345678",
    site_web: str | None = "https://techcorp.fr",
    ca: int | None = 500_000,
    ca_n1: int | None = 420_000,
    resultat_net: int | None = 50_000,
    date_creation: date | None = date(2015, 3, 1),
    score: float | None = 0.82,
    label_scoring: str | None = "CHAUD",
    status: str = LeadStatus.QUALIFIE,
) -> Lead:
    lead = MagicMock(spec=Lead)
    lead.siret = siret
    lead.company_name = company_name
    lead.prenom_dirigeant = prenom
    lead.nom_dirigeant = nom
    lead.titre_dirigeant = titre
    lead.secteur = secteur
    lead.taille_entreprise = taille
    lead.adresse = adresse
    lead.email = email
    lead.telephone = telephone
    lead.site_web = site_web
    lead.ca = ca
    lead.ca_n1 = ca_n1
    lead.resultat_net = resultat_net
    lead.date_creation = date_creation
    lead.score = score
    lead.label_scoring = label_scoring
    lead.status = status
    lead.scored_at = datetime.now(timezone.utc)
    return lead


def _make_campaign(score_minimum: float = 0.5) -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.score_minimum = score_minimum
    return campaign


def _mock_api_response(objet: str, contenu: str) -> MagicMock:
    """Simule la réponse de l'API NVIDIA / OpenAI."""
    msg = MagicMock()
    msg.content = json.dumps({"objet": objet, "contenu": contenu})
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def _valid_contenu(company_name: str) -> str:
    """Corps d'email respectant les garde-fous de _validate_email :
    >= 80 mots, nom de l'entreprise mentionné, CTA présent."""
    return (
        f"Bonjour,\n\n"
        f"Nous avons suivi le développement de {company_name} et nous pensons "
        f"pouvoir vous accompagner dans votre croissance grâce à notre expertise "
        f"en prospection commerciale. Notre équipe travaille avec des entreprises "
        f"similaires à la vôtre pour identifier de nouvelles opportunités "
        f"commerciales et optimiser leur démarche de prospection au quotidien. "
        f"Nous serions ravis d'échanger avec vous lors d'un court appel de 15 "
        f"minutes afin de mieux comprendre vos enjeux actuels et de voir "
        f"ensemble si une collaboration pourrait être pertinente pour "
        f"{company_name}. N'hésitez pas à nous indiquer un créneau qui vous "
        f"conviendrait.\n\nCordialement,\nL'équipe SMA ProspectAI"
    )


# ── Tests _build_context() ─────────────────────────────────────────────────────

def test_build_context_avec_toutes_les_donnees():
    """Le contexte doit inclure dirigeant, secteur, taille et signaux financiers."""
    lead = _make_lead()
    ctx = _build_context(lead)

    assert "TechCorp SAS" in ctx
    assert "Alice Martin" in ctx
    assert "CEO" in ctx
    assert "6201Z" in ctx
    assert "PME" in ctx           # taille "21" → PME 10-49 salariés
    assert "2015" in ctx          # année de création
    assert "fort potentiel" in ctx  # label CHAUD


def test_build_context_sans_dirigeant():
    """Sans dirigeant, le contexte ne doit pas contenir de ligne Dirigeant."""
    lead = _make_lead(prenom=None, nom=None, titre=None)
    ctx = _build_context(lead)

    assert "Dirigeant" not in ctx
    assert "TechCorp SAS" in ctx


def test_build_context_sans_donnees_financieres():
    """Sans CA, la ligne financière ne doit pas apparaître."""
    lead = _make_lead(ca=None, resultat_net=None)
    ctx = _build_context(lead)

    assert "financières" not in ctx


def test_build_context_label_froid():
    """Label FROID → message de potentiel faible dans le contexte."""
    lead = _make_lead(label_scoring="FROID")
    ctx = _build_context(lead)

    assert "faible" in ctx


# ── Tests run_redaction() ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_run_redaction_genere_email_pour_lead_qualifie():
    """Un lead QUALIFIE doit recevoir un email et passer en EMAIL_GENERE."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead()

    # L'API retourne un email valide
    api_response = _mock_api_response(
        objet="Optimisez votre croissance — TechCorp SAS",
        contenu=_valid_contenu("TechCorp SAS"),
    )

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.update_lead_email_genere", new_callable=AsyncMock) as mock_update,
        patch("app.agents.redaction.agent.AsyncOpenAI") as mock_client_cls,
        patch("app.agents.redaction.agent.settings") as mock_settings,
        patch("app.agents.redaction.agent.asyncio.sleep", new_callable=AsyncMock),
    ):
        # Simule : 1 lot de 1 lead, puis liste vide → fin de boucle
        mock_list.side_effect = [[lead], []]
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = ""
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        # Chaîne d'appel : client.chat.completions.create (async)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=api_response)
        mock_client_cls.return_value = mock_client

        result = await run_redaction(db, campaign)

    assert result["emails_generes"] == 1
    assert result["leads_erreurs"] == 0
    mock_update.assert_called_once()
    # Vérifie que l'objet transmis est correct
    call_args = mock_update.call_args
    assert "TechCorp SAS" in call_args.args[2]  # objet


@pytest.mark.anyio
async def test_run_redaction_continue_apres_erreur_unitaire():
    """Une erreur sur un lead ne doit pas interrompre le traitement des suivants."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead_ok = _make_lead(siret="11111111111111", company_name="Alpha SAS")
    lead_ko = _make_lead(siret="22222222222222", company_name="Beta SARL")

    api_response = _mock_api_response("Objet test", _valid_contenu("Alpha SAS"))

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.update_lead_email_genere", new_callable=AsyncMock),
        patch("app.agents.redaction.agent.AsyncOpenAI") as mock_client_cls,
        patch("app.agents.redaction.agent.settings") as mock_settings,
        patch("app.agents.redaction.agent.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_list.side_effect = [[lead_ko, lead_ok], []]
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = ""
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        mock_client = MagicMock()
        # lead_ko échoue sur ses 3 tentatives (timeout persistant) → erreur comptabilisée.
        # lead_ok réussit dès la 1ère tentative avec un email valide.
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                RuntimeError("Timeout API"),
                RuntimeError("Timeout API"),
                RuntimeError("Timeout API"),
                api_response,
            ]
        )
        mock_client_cls.return_value = mock_client

        result = await run_redaction(db, campaign)

    assert result["emails_generes"] == 1
    assert result["leads_erreurs"] == 1


@pytest.mark.anyio
async def test_run_redaction_json_mal_forme():
    """Si le modèle renvoie du texte non-JSON, l'erreur est comptabilisée."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead()

    msg = MagicMock()
    msg.content = "Désolé, je ne peux pas générer cet email."
    choice = MagicMock()
    choice.message = msg
    bad_response = MagicMock()
    bad_response.choices = [choice]

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.update_lead_email_genere", new_callable=AsyncMock) as mock_update,
        patch("app.agents.redaction.agent.AsyncOpenAI") as mock_client_cls,
        patch("app.agents.redaction.agent.settings") as mock_settings,
        patch("app.agents.redaction.agent.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_list.side_effect = [[lead], []]
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = ""
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=bad_response)
        mock_client_cls.return_value = mock_client

        result = await run_redaction(db, campaign)

    assert result["emails_generes"] == 0
    assert result["leads_erreurs"] == 1
    mock_update.assert_not_called()


@pytest.mark.anyio
async def test_run_redaction_sans_api_key():
    """Sans NVIDIA_API_KEY, run_redaction doit lever RuntimeError immédiatement."""
    campaign = _make_campaign()
    db = AsyncMock()

    with patch("app.agents.redaction.agent.settings") as mock_settings:
        mock_settings.NVIDIA_API_KEY = ""

        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
            await run_redaction(db, campaign)


@pytest.mark.anyio
async def test_run_redaction_aucun_lead():
    """Sans leads QUALIFIE, run_redaction termine proprement avec compteurs à zéro."""
    campaign = _make_campaign()
    db = AsyncMock()

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.AsyncOpenAI"),
        patch("app.agents.redaction.agent.settings") as mock_settings,
    ):
        mock_list.return_value = []
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = ""
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        result = await run_redaction(db, campaign)

    assert result == {"emails_generes": 0, "leads_erreurs": 0}


@pytest.mark.anyio
async def test_run_redaction_bascule_sur_modele_fallback():
    """Si REDACTION_FALLBACK_MODEL est configuré, les tentatives 2+ l'utilisent
    au lieu de REDACTION_MODEL — utile si le modèle principal est en panne."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead()

    api_response = _mock_api_response("Objet test", _valid_contenu("TechCorp SAS"))

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.update_lead_email_genere", new_callable=AsyncMock),
        patch("app.agents.redaction.agent.AsyncOpenAI") as mock_client_cls,
        patch("app.agents.redaction.agent.settings") as mock_settings,
        patch("app.agents.redaction.agent.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_list.side_effect = [[lead], []]
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = "meta/llama-3.1-70b-instruct"
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        mock_client = MagicMock()
        # 1ère tentative (modèle principal) échoue, 2e (modèle de secours) réussit.
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[RuntimeError("DEGRADED function cannot be invoked"), api_response]
        )
        mock_client_cls.return_value = mock_client

        result = await run_redaction(db, campaign)

    assert result["emails_generes"] == 1
    calls = mock_client.chat.completions.create.call_args_list
    assert calls[0].kwargs["model"] == "mistralai/mistral-nemotron"
    assert calls[1].kwargs["model"] == "meta/llama-3.1-70b-instruct"


@pytest.mark.anyio
async def test_run_redaction_ne_boucle_pas_indefiniment_si_lead_reste_qualifie():
    """Un lead qui échoue toutes ses tentatives reste QUALIFIE en base (retenté au
    prochain run), mais ne doit pas être repris indéfiniment DANS ce run — sinon
    list_leads_to_redact le renverrait à chaque itération de la boucle `while True`
    et run_redaction ne terminerait jamais."""
    campaign = _make_campaign()
    db = AsyncMock()
    lead = _make_lead()

    with (
        patch("app.agents.redaction.agent.list_leads_to_redact", new_callable=AsyncMock) as mock_list,
        patch("app.agents.redaction.agent.update_lead_email_genere", new_callable=AsyncMock),
        patch("app.agents.redaction.agent.AsyncOpenAI") as mock_client_cls,
        patch("app.agents.redaction.agent.settings") as mock_settings,
        patch("app.agents.redaction.agent.asyncio.sleep", new_callable=AsyncMock),
    ):
        # Simule la réalité : le lead reste QUALIFIE (pas d'update en cas d'échec),
        # donc chaque appel à list_leads_to_redact le renvoie à nouveau.
        mock_list.return_value = [lead]
        mock_settings.NVIDIA_API_KEY = "test-key"
        mock_settings.NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.REDACTION_MODEL = "mistralai/mistral-nemotron"
        mock_settings.REDACTION_FALLBACK_MODEL = ""
        mock_settings.REDACTION_REQUEST_DELAY_SECONDS = 0.0

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("DEGRADED function cannot be invoked")
        )
        mock_client_cls.return_value = mock_client

        result = await run_redaction(db, campaign)

    assert result == {"emails_generes": 0, "leads_erreurs": 1}
    # 1ère itération de `while True` traite le lead (3 tentatives), 2e itération le
    # revoit mais le filtre localement et sort de la boucle sans le retraiter.
    assert mock_list.call_count == 2
