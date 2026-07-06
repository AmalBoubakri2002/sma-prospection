"""Agent Rédaction — génère un email de prospection par lead QUALIFIE via l'API NVIDIA,
puis passe le lead en EN_ATTENTE_VALIDATION."""

import asyncio
import json
import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.services.lead import list_leads_to_redact, update_lead_email_genere

logger = logging.getLogger("agent-redaction")

# ── Prompt système ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Tu es un expert en prospection commerciale B2B pour des entreprises françaises.
Ta mission : rédiger un email de prospection professionnel, chaleureux et personnalisé
au nom de SMA ProspectAI, un service de prospection commerciale assistée par IA.

Réponds UNIQUEMENT avec un objet JSON valide contenant exactement ces deux clés :
{
  "objet": "...",   // Sujet de l'email — accrocheur, personnalisé (50-100 caractères)
  "contenu": "..."  // Corps de l'email en texte brut (150-250 mots)
                    // Structure : formule d'appel → valeur proposée → CTA → politesse
}

Règles de rédaction :
- Langue : français professionnel
- Personnalisation RÉELLE et vérifiable : appuie-toi sur au moins un élément concret
  et précis fourni dans le contexte du prospect (secteur d'activité, taille, localisation,
  année de création, profil commercial...). Ne te contente jamais de formules vagues du
  type "entreprises comme la vôtre" ou "professionnels de votre secteur" sans préciser
  de quoi il s'agit réellement.
- Si le prénom ou le nom du dirigeant n'est PAS fourni dans le contexte, n'utilise
  JAMAIS de placeholder comme "[Prénom]" ou "[Nom]" — utilise une formule neutre
  ("Bonjour,", "Madame, Monsieur,").
- Le nom complet et exact de l'entreprise (tel qu'indiqué dans "Entreprise cible")
  doit apparaître au moins une fois, texto, dans le corps de l'email — tu peux
  ensuite le raccourcir pour la suite du texte si c'est plus naturel.
- N'invente aucun fait sur SMA ProspectAI ou sur le prospect (pas de chiffres,
  durées d'expérience, spécialisations ou références client non fournis dans le contexte).
- Ne jamais mentionner de chiffres financiers précis (données internes)
- Ton : direct, humain, pas de jargon commercial agressif. Bannis les formules creuses
  et interchangeables : "solutions sur-mesure", "leviers concrets"/"leviers d'efficacité",
  "outils innovants", "renforcer votre positionnement", "expertise terrain", "résultats
  concrets", "accompagnement personnalisé". Si tu ne peux pas remplacer une de ces
  expressions par un fait précis du contexte, supprime-la plutôt que de la garder.
- CTA : proposer un court appel de 15 minutes
- Signature : "L'équipe SMA ProspectAI"
"""


# ── Construction du contexte lead ──────────────────────────────────────────────

_TAILLE_LABELS = {
    "NN": "micro-entreprise", "01": "micro-entreprise", "02": "micro-entreprise",
    "03": "micro-entreprise",
    "11": "TPE (1-9 salariés)", "12": "TPE (1-9 salariés)",
    "21": "PME (10-49 salariés)", "22": "PME (10-49 salariés)",
    "31": "PME (50-199 salariés)",
    "32": "ETI (200-499 salariés)", "41": "ETI (500-999 salariés)",
    "42": "ETI (500-999 salariés)",
    "51": "grande entreprise", "52": "grande entreprise", "53": "grande entreprise",
}

_LABEL_FR = {
    "CHAUD": "fort potentiel de conversion",
    "TIEDE": "potentiel de conversion modéré",
    "FROID": "potentiel de conversion faible",
}


def _build_context(lead: Lead) -> str:
    """Transforme les champs Lead en texte de contexte pour le modèle."""
    lines = [f"Entreprise cible : {lead.company_name}"]

    if lead.prenom_dirigeant and lead.nom_dirigeant:
        dirigeant = f"{lead.prenom_dirigeant} {lead.nom_dirigeant}"
        if lead.titre_dirigeant:
            dirigeant += f" ({lead.titre_dirigeant})"
        lines.append(f"Dirigeant : {dirigeant}")

    if lead.secteur:
        lines.append(f"Secteur (code NAF) : {lead.secteur}")

    if lead.taille_entreprise:
        label = _TAILLE_LABELS.get(lead.taille_entreprise, lead.taille_entreprise)
        lines.append(f"Taille : {label}")

    if lead.adresse:
        lines.append(f"Localisation : {lead.adresse}")

    if lead.site_web:
        lines.append(f"Site web : {lead.site_web}")

    # Indicateurs financiers — on ne cite pas les montants exacts
    if lead.ca is not None:
        lines.append("Données financières : disponibles (CA et résultat net connus)")

    if lead.date_creation:
        lines.append(f"Année de création : {lead.date_creation.year}")

    # Signal scoring — donne une idée du potentiel sans trahir l'algorithme
    if lead.label_scoring:
        hint = _LABEL_FR.get(lead.label_scoring, "")
        if hint:
            lines.append(f"Profil commercial : {hint}")

    return "\n".join(lines)


# ── Garde-fous ─────────────────────────────────────────────────────────────────

_CTA_KEYWORDS = [
    "appel", "rendez-vous", "15 minutes", "15min", "échanger",
    "disponible", "créneau", "convient", "échange rapide",
    "quelques minutes", "call", "discuter",
]

_WORD_COUNT_MIN = 80    # marge basse par rapport aux 150 du prompt
_WORD_COUNT_MAX = 300   # marge haute par rapport aux 250 du prompt


def _validate_email(objet: str, contenu: str, lead: Lead) -> list[str]:
    """Vérifie que l'email respecte les règles métier ; retourne la liste des violations."""
    errors: list[str] = []

    # Règle 1 : longueur du corps (avec marges pour éviter les faux positifs)
    word_count = len(contenu.split())
    if word_count < _WORD_COUNT_MIN:
        errors.append(f"Corps trop court : {word_count} mots (min {_WORD_COUNT_MIN})")
    elif word_count > _WORD_COUNT_MAX:
        errors.append(f"Corps trop long : {word_count} mots (max {_WORD_COUNT_MAX})")

    # Règle 2 : nom de l'entreprise mentionné dans le corps
    if lead.company_name and lead.company_name.lower() not in contenu.lower():
        errors.append(f"Nom entreprise '{lead.company_name}' absent du corps")

    # Règle 3 : présence d'un CTA
    contenu_lower = contenu.lower()
    if not any(kw in contenu_lower for kw in _CTA_KEYWORDS):
        errors.append("CTA absent (aucun mot-clé de prise de contact détecté)")

    # Règle 4 : objet non vide et pas trop long
    if not objet.strip():
        errors.append("Objet vide")
    elif len(objet) > 100:
        errors.append(f"Objet trop long : {len(objet)} caractères (max 100)")

    return errors


# ── Appel API NVIDIA / Mistral Nemotron ────────────────────────────────────────

async def _generate_email(client: AsyncOpenAI, lead: Lead, model: str) -> tuple[str, str]:
    """Appelle le modèle de rédaction et retourne (objet, contenu)."""
    context = _build_context(lead)
    user_message = (
        f"Génère un email de prospection pour ce prospect :\n\n{context}\n\n"
        "Réponds uniquement en JSON avec les clés 'objet' et 'contenu'."
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.6,
        top_p=0.7,
        max_tokens=600,
        stream=False,
    )

    raw = response.choices[0].message.content or ""

    # Le modèle peut enrober le JSON dans des backticks markdown : on nettoie
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Réponse non-JSON reçue du modèle : {raw[:200]}") from exc

    objet = str(data.get("objet", "")).strip()
    contenu = str(data.get("contenu", "")).strip()

    if not objet or not contenu:
        raise ValueError(f"Champs 'objet' ou 'contenu' manquants dans : {data}")

    # Tronquer si le modèle dépasse la limite du champ DB (String(500))
    return objet[:500], contenu


# ── Orchestration principale ───────────────────────────────────────────────────

async def run_redaction(db: AsyncSession, campaign: Campaign) -> dict:
    """Génère les emails pour tous les leads QUALIFIE de la campagne, par pages de 50."""
    if not settings.NVIDIA_API_KEY:
        raise RuntimeError(
            "NVIDIA_API_KEY non configurée — impossible de lancer l'Agent Rédaction."
        )

    # max_retries=1 : évite de multiplier l'attente si le modèle est en panne (5xx).
    client = AsyncOpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY,
        timeout=settings.NVIDIA_API_TIMEOUT_SECONDS,
        max_retries=1,
    )

    total_generes = 0
    total_erreurs = 0
    _MAX_ATTEMPTS = 3

    # Exclu du run courant pour ne pas boucler indéfiniment ; reste QUALIFIE pour le prochain run.
    failed_this_run: set = set()

    while True:
        leads = [
            lead for lead in await list_leads_to_redact(db, campaign.id)
            if lead.id not in failed_this_run
        ]
        if not leads:
            break

        for lead in leads:
            success = False
            last_exc: Exception | None = None

            for attempt in range(1, _MAX_ATTEMPTS + 1):
                # Bascule sur le modèle de secours dès la 2e tentative si configuré.
                model = settings.REDACTION_MODEL
                if attempt > 1 and settings.REDACTION_FALLBACK_MODEL:
                    model = settings.REDACTION_FALLBACK_MODEL

                try:
                    objet, contenu = await _generate_email(client, lead, model)

                    # Garde-fous : on vérifie l'email avant de le stocker
                    violations = _validate_email(objet, contenu, lead)
                    if violations:
                        raise ValueError(
                            f"Garde-fous échoués (tentative {attempt}/{_MAX_ATTEMPTS}) : "
                            + " | ".join(violations)
                        )

                    await update_lead_email_genere(db, lead, objet, contenu)
                    total_generes += 1
                    success = True
                    logger.debug(
                        "Email généré pour %s (tentative %d, modèle %s) — objet : %s",
                        lead.siret, attempt, model, objet[:60],
                    )
                    break  # succès → on passe au lead suivant

                except Exception as exc:
                    last_exc = exc
                    if attempt < _MAX_ATTEMPTS:
                        logger.debug(
                            "Tentative %d/%d échouée pour %s (modèle %s) : %s — nouvelle tentative",
                            attempt, _MAX_ATTEMPTS, lead.siret, model, exc,
                        )
                    # Backoff linéaire entre tentatives.
                    if settings.REDACTION_REQUEST_DELAY_SECONDS > 0:
                        await asyncio.sleep(attempt * settings.REDACTION_REQUEST_DELAY_SECONDS)

            if not success:
                logger.warning(
                    "Rédaction abandonnée pour %s après %d tentatives : %s",
                    lead.siret, _MAX_ATTEMPTS, last_exc,
                )
                total_erreurs += 1
                failed_this_run.add(lead.id)

            # Pause entre leads (indépendante du succès/échec)
            if success and settings.REDACTION_REQUEST_DELAY_SECONDS > 0:
                await asyncio.sleep(settings.REDACTION_REQUEST_DELAY_SECONDS)

    logger.info(
        "Campagne %s — rédaction : %d emails générés, %d erreurs",
        campaign.id,
        total_generes,
        total_erreurs,
    )
    return {
        "emails_generes": total_generes,
        "leads_erreurs": total_erreurs,
    }
