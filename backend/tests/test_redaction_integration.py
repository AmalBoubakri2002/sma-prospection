"""Test d'intégration — appel réel à l'API NVIDIA.

Lance uniquement si NVIDIA_API_KEY est définie dans l'environnement.
Utilisation :
    uv run pytest tests/test_redaction_integration.py -v -s
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.agents.redaction.agent import _build_context, _generate_email
from app.core.config import settings
from app.models.lead import Lead

# Sauter le test si pas de clé API
pytestmark = pytest.mark.skipif(
    not settings.NVIDIA_API_KEY,
    reason="NVIDIA_API_KEY non définie — test d'intégration ignoré",
)


def _make_lead_reel() -> Lead:
    """Lead fictif réaliste pour le test d'intégration."""
    lead = MagicMock(spec=Lead)
    lead.siret = "12345678901234"
    lead.company_name = "Dupont Consulting SAS"
    lead.prenom_dirigeant = "Jean"
    lead.nom_dirigeant = "Dupont"
    lead.titre_dirigeant = "Directeur Général"
    lead.secteur = "7022Z"           # Conseil pour les affaires et la gestion
    lead.taille_entreprise = "21"    # PME 10-49 salariés
    lead.adresse = "12 Rue de Rivoli, 75001 Paris"
    lead.email = "j.dupont@dupont-consulting.fr"
    lead.telephone = "+33144123456"
    lead.site_web = "https://dupont-consulting.fr"
    lead.ca = 750_000
    lead.ca_n1 = 620_000
    lead.resultat_net = 85_000
    lead.date_creation = date(2012, 6, 15)
    lead.score = 0.87
    lead.label_scoring = "CHAUD"
    lead.score_exploitabilite = 72.0
    return lead


@pytest.mark.anyio
async def test_integration_genere_email_reel():
    """Appel réel à mistral-nemotron via NVIDIA — vérifie que l'email est valide."""
    from openai import AsyncOpenAI

    lead = _make_lead_reel()

    # Afficher le contexte construit
    context = _build_context(lead)
    print("\n── Contexte envoyé au modèle ──────────────────────")
    print(context)
    print("───────────────────────────────────────────────────\n")

    client = AsyncOpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY,
    )

    objet, contenu = await _generate_email(client, lead, settings.REDACTION_MODEL)

    print("── Email généré ────────────────────────────────────")
    print(f"OBJET   : {objet}")
    print(f"\nCONTENU :\n{contenu}")
    print("───────────────────────────────────────────────────\n")

    # Assertions minimales
    assert objet, "L'objet ne doit pas être vide"
    assert contenu, "Le contenu ne doit pas être vide"
    assert len(objet) <= 500, "L'objet dépasse 500 caractères"
    assert len(contenu) >= 50, "Le contenu semble trop court"
    assert "Dupont" in objet or "Dupont" in contenu, \
        "Le nom du dirigeant devrait apparaître dans l'email"
