# Agent Scoring — Lit les leads en statut ENRICHI, calcule le score XGBoost pour chacun,et écrit le résultat dans lead.score + lead.label_scoring.

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scoring import predictor
from app.models.campaign import Campaign
from app.models.lead import LeadStatus
from app.services.lead import list_leads_to_score, update_lead_scored

logger = logging.getLogger("agent-scoring")


async def run_scoring(db: AsyncSession, campaign: Campaign) -> dict:
    """
    Orchestre le scoring de tous les leads ENRICHI d'une campagne.

    Traite par pages de 50 (même mécanique que l'Agent Enrichissement)
    pour ne pas charger toute la table en mémoire.
    """
    total_scored = 0
    total_errors = 0
    # Exclu du run courant pour ne pas boucler indéfiniment ; reste ENRICHI pour le prochain run.
    failed_this_run: set = set()

    while True:
        leads = [
            lead for lead in await list_leads_to_score(db, campaign.id)
            if lead.id not in failed_this_run
        ]
        if not leads:
            break

        for lead in leads:
            try:
                score, label, shap_json = predictor.predict(lead)
                # ECARTE = rejet automatique (score < seuil) ; REJETE est réservé au rejet humain.
                status = (
                    LeadStatus.QUALIFIE if round(score, 2) >= round(campaign.score_minimum, 2) else LeadStatus.ECARTE
                )
                await update_lead_scored(db, lead, score, label, status, shap_json)
                total_scored += 1
                logger.debug(
                    "Lead %s scoré → %.4f (%s) [%s]", lead.siret, score, label, status
                )
            except Exception as exc:
                logger.warning(
                    "Scoring échoué pour %s : %s", lead.siret, exc
                )
                total_errors += 1
                failed_this_run.add(lead.id)

    logger.info(
        "Campagne %s — scoring : %d scorés, %d erreurs",
        campaign.id,
        total_scored,
        total_errors,
    )
    return {
        "leads_scores": total_scored,
        "leads_erreurs": total_errors,
    }
