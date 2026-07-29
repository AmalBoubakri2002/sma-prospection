"""Pipeline LangGraph : Veille → Enrichissement → Scoring → Rédaction → [HITL] → CRM.

Checkpoints persistés dans PostgreSQL (AsyncPostgresSaver, dossier §9.3) : l'état
du graphe — en particulier la suspension HITL avant le nœud CRM — survit aux
redémarrages du worker. Le graphe est compilé paresseusement via get_pipeline()
car l'initialisation du checkpointer (pool + setup des tables) est asynchrone.
"""

import logging
import uuid
from typing import NotRequired, TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agents.crm.agent import run_crm
from app.agents.enrichissement.agent import run_enrichissement
from app.agents.redaction.agent import run_redaction
from app.agents.scoring.agent import run_scoring
from app.agents.veille.agent import run_veille
from app.agents.veille.sirene import SireneConfigError
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.models.campaign import Campaign
from app.models.lead import LeadStatus
from app.services.campaign import update_campaign_status
from app.services.lead import count_leads_by_status_for_campaign, count_leads_for_campaign

logger = logging.getLogger("pipeline")

# Limite les relances Veille pour compenser des leads écartés à l'enrichissement,
# pour éviter une boucle sans fin si le vivier NAF/code postal est trop restreint.
MAX_VEILLE_RETRIES = 3


# ── État partagé ──────────────────────────────────────────────────────────────

class CampaignPipelineState(TypedDict):
    """Mémoire partagée traversant tous les nœuds ; seul campaign_id est requis au démarrage."""
    campaign_id: str              # UUID de la campagne (= thread_id LangGraph)
    error: str | None             # Premier message d'erreur — déclenche l'arrêt via les edges
    veille: NotRequired[dict]         # Rapport Agent Veille
    enrichissement: NotRequired[dict] # Rapport Agent Enrichissement
    scoring: NotRequired[dict]        # Rapport Agent Scoring
    redaction: NotRequired[dict]      # Rapport Agent Rédaction
    crm: NotRequired[dict]            # Rapport Agent CRM
    veille_retries: NotRequired[int]      # Nb de relances Veille pour compenser le quota
                                           # (voir node_check_quota)
    needs_more_leads: NotRequired[bool]   # Décision du nœud check_quota, lue par le routeur


# ── Nœud 1 : Veille ──────────────────────────────────────────────────────────

async def node_veille(state: CampaignPipelineState) -> dict:
    campaign_id = state["campaign_id"]
    logger.info("[Veille] Démarrage — campagne %s", campaign_id)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}
        try:
            result = await run_veille(db, campaign)
            await update_campaign_status(db, campaign, "enrichissement_pending")
            logger.info("[Veille] Terminé — %d leads collectés", result.get("leads_collected", 0))
            return {"veille": result}
        except SireneConfigError as exc:
            # Erreur de configuration : irrécupérable, pas de retry
            logger.error("[Veille] Erreur configuration SIRENE : %s", exc)
            await update_campaign_status(db, campaign, "failed")
            return {"error": str(exc)}
        except Exception as exc:
            logger.exception("[Veille] Échec inattendu")
            await update_campaign_status(db, campaign, "veille_failed")
            return {"error": str(exc)}


# ── Nœud 2 : Enrichissement ───────────────────────────────────────────────────

async def node_enrichissement(state: CampaignPipelineState) -> dict:
    campaign_id = state["campaign_id"]
    logger.info("[Enrichissement] Démarrage — campagne %s", campaign_id)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}
        try:
            result = await run_enrichissement(db, campaign)
            await update_campaign_status(db, campaign, "scoring_pending")
            logger.info(
                "[Enrichissement] Terminé — %d leads enrichis", result.get("leads_enrichis", 0)
            )
            return {"enrichissement": result}
        except Exception as exc:
            logger.exception("[Enrichissement] Échec")
            await update_campaign_status(db, campaign, "enrichissement_failed")
            return {"error": str(exc)}


# ── Nœud 2bis : vérification du quota (relance Veille si besoin) ────────────

async def node_check_quota(state: CampaignPipelineState) -> dict:
    """Relance Veille si le quota de leads ENRICHI n'est pas atteint, jusqu'à MAX_VEILLE_RETRIES."""
    campaign_id = state["campaign_id"]
    retries = state.get("veille_retries", 0)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}

        total_collected = await count_leads_for_campaign(db, campaign.id)
        counts = await count_leads_by_status_for_campaign(db, campaign.id)
        enrichis = counts.get(LeadStatus.ENRICHI, 0)

        quota_atteint = enrichis >= campaign.quota
        stock_epuise = (
            bool(campaign.estimated_prospects) and total_collected >= campaign.estimated_prospects
        )
        retries_epuises = retries >= MAX_VEILLE_RETRIES
        needs_more = not quota_atteint and not stock_epuise and not retries_epuises

        if needs_more:
            logger.info(
                "[Quota] Campagne %s — %d/%d leads enrichis, relance Veille (%d/%d)",
                campaign_id, enrichis, campaign.quota, retries + 1, MAX_VEILLE_RETRIES,
            )
        elif not quota_atteint:
            logger.warning(
                "[Quota] Campagne %s — quota non atteint (%d/%d leads enrichis), "
                "livraison avec le volume disponible : %s",
                campaign_id, enrichis, campaign.quota,
                "relances épuisées" if retries_epuises else "stock SIRENE épuisé",
            )

        return {
            "veille_retries": retries + 1 if needs_more else retries,
            "needs_more_leads": needs_more,
        }


def _route_after_quota_check(state: CampaignPipelineState) -> str:
    if state.get("error"):
        return END
    return "veille" if state.get("needs_more_leads") else "scoring"


# ── Nœud 3 : Scoring ─────────────────────────────────────────────────────────

async def node_scoring(state: CampaignPipelineState) -> dict:
    campaign_id = state["campaign_id"]
    logger.info("[Scoring] Démarrage — campagne %s", campaign_id)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}
        try:
            result = await run_scoring(db, campaign)
            await update_campaign_status(db, campaign, "redaction_pending")
            logger.info("[Scoring] Terminé — %d leads scorés", result.get("leads_scores", 0))
            return {"scoring": result}
        except Exception as exc:
            logger.exception("[Scoring] Échec")
            await update_campaign_status(db, campaign, "scoring_failed")
            return {"error": str(exc)}


# ── Nœud 4 : Rédaction ───────────────────────────────────────────────────────

async def node_redaction(state: CampaignPipelineState) -> dict:
    campaign_id = state["campaign_id"]
    logger.info("[Rédaction] Démarrage — campagne %s", campaign_id)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}
        try:
            result = await run_redaction(db, campaign)
            emails_generes = result.get("emails_generes", 0)
            leads_erreurs = result.get("leads_erreurs", 0)

            # Échec total (ex : modèle NVIDIA DEGRADED) — ne pas afficher une file de
            # validation vide comme si le run avait réussi. On repasse par "redaction_failed",
            # présent dans _RECOVERY_MAP, pour que l'orchestrateur retente automatiquement.
            if emails_generes == 0 and leads_erreurs > 0:
                logger.error(
                    "[Rédaction] Échec total — %d leads en erreur, aucun email généré",
                    leads_erreurs,
                )
                await update_campaign_status(db, campaign, "redaction_failed")
                return {"error": f"Rédaction : {leads_erreurs} leads en erreur, aucun email généré"}

            await update_campaign_status(db, campaign, "en_attente_validation")
            logger.info(
                "[Rédaction] Terminé — %d emails en attente de validation",
                emails_generes,
            )
            return {"redaction": result}
        except Exception as exc:
            logger.exception("[Rédaction] Échec")
            await update_campaign_status(db, campaign, "redaction_failed")
            return {"error": str(exc)}


# ── Nœud 5 : CRM (reprise après HITL) ────────────────────────────────────────

async def node_crm(state: CampaignPipelineState) -> dict:
    campaign_id = state["campaign_id"]
    logger.info("[CRM] Démarrage synchronisation — campagne %s", campaign_id)

    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign is None:
            return {"error": f"Campagne {campaign_id} introuvable"}
        try:
            result = await run_crm(db, campaign)
            await update_campaign_status(db, campaign, "completed")
            logger.info(
                "[CRM] Terminé — %d leads synchronisés vers Odoo",
                result.get("leads_synchronises", 0),
            )
            return {"crm": result}
        except Exception as exc:
            logger.exception("[CRM] Échec")
            await update_campaign_status(db, campaign, "crm_failed")
            return {"error": str(exc)}


# ── Routage conditionnel — court-circuit sur erreur ───────────────────────────

def _or_abort(next_node: str):
    """Fabrique un routeur : si erreur dans l'état → END, sinon → next_node."""
    def route(state: CampaignPipelineState) -> str:
        return END if state.get("error") else next_node
    return route


# ── Construction du graphe ────────────────────────────────────────────────────

_builder = StateGraph(CampaignPipelineState)

_builder.add_node("veille", node_veille)
_builder.add_node("enrichissement", node_enrichissement)
_builder.add_node("check_quota", node_check_quota)
_builder.add_node("scoring", node_scoring)
_builder.add_node("redaction", node_redaction)
_builder.add_node("crm", node_crm)

_builder.add_edge(START, "veille")
_builder.add_conditional_edges(
    "veille", _or_abort("enrichissement"), {END: END, "enrichissement": "enrichissement"}
)
_builder.add_conditional_edges(
    "enrichissement", _or_abort("check_quota"), {END: END, "check_quota": "check_quota"}
)
_builder.add_conditional_edges(
    "check_quota", _route_after_quota_check, {END: END, "veille": "veille", "scoring": "scoring"}
)
_builder.add_conditional_edges(
    "scoring", _or_abort("redaction"), {END: END, "redaction": "redaction"}
)
_builder.add_conditional_edges(
    "redaction", _or_abort("crm"), {END: END, "crm": "crm"}
)
_builder.add_edge("crm", END)

# ── Compilation paresseuse avec checkpoints PostgreSQL ───────────────────────

_pipeline = None
_pool: AsyncConnectionPool | None = None


async def get_pipeline():
    """Compile le graphe (une seule fois par process) avec des checkpoints
    PostgreSQL. Le graphe se suspend avant "crm" (HITL) ; une relance avec
    input=None reprend au checkpoint après validation — y compris après un
    redémarrage du worker, puisque l'état vit en base (tables checkpoints*)."""
    global _pipeline, _pool
    if _pipeline is not None:
        return _pipeline

    # psycopg attend un DSN "postgresql://", pas le dialecte SQLAlchemy+asyncpg.
    conninfo = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    # autocommit + dict_row : prérequis documentés d'AsyncPostgresSaver ;
    # prepare_threshold=0 évite les prepared statements (incompatibles pgbouncer).
    _pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open()

    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()  # crée/migre les tables checkpoints* (idempotent)

    _pipeline = _builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["crm"],
    )
    logger.info("Graphe LangGraph compilé — checkpoints PostgreSQL actifs")
    return _pipeline
