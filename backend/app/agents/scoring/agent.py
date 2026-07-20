# Agent Scoring — Lit les leads en statut ENRICHI, calcule le score XGBoost pour chacun,et écrit le résultat dans lead.score + lead.label_scoring.

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scoring import predictor
from app.agents.scoring.decision import confidence_score, decide_status, label_for_score, score_ajuste
from app.models.campaign import Campaign
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
                score, shap_json = predictor.predict(lead)
                # Score pénalisé si CA manquant (imputé) — marge graduée selon le
                # résultat net réel disponible (voir decision.py).
                score = score_ajuste(score, lead.ca, lead.resultat_net)
                # Label calculé APRÈS ajustement : sinon un lead sans CA réel peut
                # afficher un badge CHAUD à côté d'un statut ECARTE.
                label = label_for_score(score)
                status = decide_status(score, campaign.score_minimum)
                # Part des données financières réelles (vs imputées) derrière ce
                # score — affiché à côté pour que le commercial pondère sa confiance.
                confidence = confidence_score(lead.ca, lead.ca_n1, lead.resultat_net)
                await update_lead_scored(db, lead, score, label, status, shap_json, confidence)
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
