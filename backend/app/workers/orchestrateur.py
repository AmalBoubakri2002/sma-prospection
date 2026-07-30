"""Détecte les campagnes bloquées en état intermédiaire sans tâche active,
et recrée la tâche de reprise appropriée (cas d'un worker qui a planté)."""
import asyncio
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.models.agent_task import AgentName, AgentTask, AgentTaskStatus
from app.models.campaign import Campaign
from app.services.agent_task import create_task
from app.services.campaign import update_campaign_status

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s"
)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logger = logging.getLogger("orchestrateur")

# Statuts intermédiaires/d'échec → tâche de reprise. Le graphe relance depuis le
# début mais les agents sont idempotents, donc il avance directement à l'étape
# non terminée. "en_attente_validation" (HITL), "failed" et "completed" sont
# volontairement absents : ce sont des états terminaux/légitimes, pas de reprise.
_RECOVERY_MAP: dict[str, str] = {
    "running":                 AgentName.PIPELINE,
    "veille_failed":           AgentName.PIPELINE,
    "enrichissement_pending":  AgentName.PIPELINE,
    "enrichissement_failed":   AgentName.PIPELINE,
    "scoring_pending":         AgentName.PIPELINE,
    "scoring_failed":          AgentName.PIPELINE,
    "redaction_pending":       AgentName.PIPELINE,
    "redaction_failed":        AgentName.PIPELINE,
    # CRM : reprise via une tâche CRM directe (pas PIPELINE) — à ce stade les leads
    # à synchroniser sont déjà VALIDE en base, pas besoin de rejouer veille→rédaction.
    "crm_pending":             AgentName.CRM,
    "crm_failed":              AgentName.CRM,
}
_STUCK_STATUSES = list(_RECOVERY_MAP.keys())

# Intervalle de supervision (plus espacé que le poll des workers)
_SUPERVISION_INTERVAL = settings.WORKER_POLL_INTERVAL_SECONDS * 12  # ~60s par défaut

# Nombre maximum de reprises par l'orchestrateur avant abandon définitif
_MAX_RECOVERY_ATTEMPTS = 3


class SupervisorState(TypedDict):
    stuck_campaigns: list[dict]
    recovered: int


# ── Nœud 1 : détection ───────────────────────────────────────────────────────

async def _detect_stuck(state: SupervisorState) -> dict:
    """Trouve les campagnes en état intermédiaire sans tâche active."""
    stuck: list[dict] = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.status.in_(_STUCK_STATUSES))
        )
        campaigns = list(result.scalars().all())

        if campaigns:
            active_result = await db.execute(
                select(AgentTask.campaign_id).where(
                    AgentTask.campaign_id.in_([c.id for c in campaigns]),
                    AgentTask.status.in_(
                        [AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING]
                    ),
                ).distinct()
            )
            active_campaign_ids = set(active_result.scalars().all())
            stuck = [
                {"campaign_id": c.id, "status": c.status}
                for c in campaigns if c.id not in active_campaign_ids
            ]

    if stuck:
        for item in stuck:
            logger.warning(
                "Campagne bloquée — id=%s status='%s' → reprise avec agent '%s'",
                item["campaign_id"],
                item["status"],
                _RECOVERY_MAP.get(item["status"], "inconnu"),
            )
    return {"stuck_campaigns": stuck}


# ── Nœud 2 : reprise ─────────────────────────────────────────────────────────

async def _recover(state: SupervisorState) -> dict:
    """Crée des tâches de reprise pour les campagnes bloquées."""
    recovered = 0
    async with AsyncSessionLocal() as db:
        for item in state["stuck_campaigns"]:
            agent_name = _RECOVERY_MAP.get(item["status"])
            if agent_name is None:
                continue

            # Garde-fou : abandon si trop de tâches FAILED pour cette campagne
            failed_count = (
                await db.execute(
                    select(func.count()).select_from(AgentTask).where(
                        AgentTask.campaign_id == item["campaign_id"],
                        AgentTask.status == AgentTaskStatus.FAILED,
                    )
                )
            ).scalar_one()

            if failed_count >= _MAX_RECOVERY_ATTEMPTS:
                logger.error(
                    "Campagne %s — %d tâches échouées, abandon définitif (statut → 'failed')",
                    item["campaign_id"],
                    failed_count,
                )
                campaign_result = await db.execute(
                    select(Campaign).where(Campaign.id == item["campaign_id"])
                )
                campaign = campaign_result.scalar_one_or_none()
                if campaign:
                    await update_campaign_status(db, campaign, "failed")
                continue

            logger.info(
                "Reprise campagne %s (status=%s) → tâche %s [tentative %d/%d]",
                item["campaign_id"],
                item["status"],
                agent_name,
                failed_count + 1,
                _MAX_RECOVERY_ATTEMPTS,
            )
            await create_task(
                db, item["campaign_id"], agent_name, {"recovery": True}
            )
            recovered += 1
    return {"recovered": recovered}


def _needs_recovery(state: SupervisorState) -> str:
    return "recover" if state["stuck_campaigns"] else "end"


# ── Construction du graphe LangGraph ─────────────────────────────────────────

_builder = StateGraph(SupervisorState)
_builder.add_node("detect", _detect_stuck)
_builder.add_node("recover", _recover)
_builder.add_edge(START, "detect")
_builder.add_conditional_edges(
    "detect",
    _needs_recovery,
    {"recover": "recover", "end": END},
)
_builder.add_edge("recover", END)

supervisor = _builder.compile()


# ── Boucle principale ─────────────────────────────────────────────────────────

async def run_supervision_cycle() -> int:
    initial: SupervisorState = {"stuck_campaigns": [], "recovered": 0}
    final: SupervisorState = await supervisor.ainvoke(initial)
    return final.get("recovered", 0)


async def main() -> None:
    logger.info(
        "Orchestrateur LangGraph démarré (supervision toutes les %.0fs)",
        _SUPERVISION_INTERVAL,
    )
    while True:
        try:
            recovered = await run_supervision_cycle()
            if recovered:
                logger.info("Campagnes récupérées : %d", recovered)
        except Exception:
            logger.exception("Erreur lors du cycle de supervision")
        await asyncio.sleep(_SUPERVISION_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
