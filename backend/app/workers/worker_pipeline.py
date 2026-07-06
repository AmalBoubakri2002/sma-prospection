"""Worker Pipeline — point d'entrée unique pour les tâches PIPELINE, PIPELINE_RESUME, SCORING et REDACTION.

MemorySaver garde l'état HITL en mémoire du process : si le worker redémarre entre la
suspension et la validation commerciale, l'état est perdu et il faut relancer via POST /start.
"""

import asyncio
import logging
import uuid

from langgraph.types import Command

from app.agents.redaction.agent import run_redaction
from app.agents.scoring.agent import run_scoring
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.models.agent_task import AgentName, AgentTask
from app.services.agent_task import (
    create_task,
    get_pending_tasks,
    mark_done,
    mark_failed_or_retry,
    mark_running,
    recover_stuck_running_tasks,
)
from app.services.campaign import get_campaign_by_id, update_campaign_status
from app.services.notification import notify_emails_prets
from app.workers.pipeline_graph import CampaignPipelineState, pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [worker-pipeline] %(message)s"
)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logger = logging.getLogger("worker-pipeline")

# campaign_id en attente de validation HITL ; perdu si le worker redémarre.
_waiting_for_hitl: set[str] = set()


# ── Pipeline LangGraph complet ────────────────────────────────────────────────

async def run_new_pipeline(task_id: uuid.UUID) -> None:
    """Lance le graphe LangGraph pour une nouvelle campagne (tâche PIPELINE)."""
    async with AsyncSessionLocal() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return
        campaign_id = str(task.campaign_id)
        await mark_running(db, task)

    config = {"configurable": {"thread_id": campaign_id}}
    initial: CampaignPipelineState = {"campaign_id": campaign_id, "error": None}

    logger.info("Pipeline démarré — campagne %s", campaign_id)
    try:
        result = await pipeline.ainvoke(initial, config=config)

        snapshot = await pipeline.aget_state(config)
        if snapshot.next:
            # Graphe suspendu avant le nœud CRM — en attente de validation HITL
            logger.info(
                "Pipeline campagne %s suspendu — HITL (prochain nœud : %s)",
                campaign_id, list(snapshot.next),
            )
            _waiting_for_hitl.add(campaign_id)
            async with AsyncSessionLocal() as db:
                task = await db.get(AgentTask, task_id)
                if task:
                    await mark_done(db, task, {"status": "waiting_hitl", **result})
        else:
            error = result.get("error")
            async with AsyncSessionLocal() as db:
                task = await db.get(AgentTask, task_id)
                if task:
                    if error:
                        await mark_failed_or_retry(db, task, error)
                    else:
                        await mark_done(db, task, result)
            if error:
                logger.error("Pipeline campagne %s échoué : %s", campaign_id, error)
            else:
                logger.info("Pipeline campagne %s terminé", campaign_id)

    except Exception as exc:
        logger.exception("Pipeline campagne %s — erreur inattendue", campaign_id)
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            if task:
                await mark_failed_or_retry(db, task, str(exc))


async def resume_pipeline(task_id: uuid.UUID) -> None:
    """Reprend le graphe après validation commerciale (tâche PIPELINE_RESUME)."""
    async with AsyncSessionLocal() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return
        campaign_id = str(task.campaign_id)
        await mark_running(db, task)

    config = {"configurable": {"thread_id": campaign_id}}

    if campaign_id not in _waiting_for_hitl:
        logger.error(
            "Pipeline campagne %s — aucun état HITL en mémoire "
            "(redémarrage du worker ?). Utiliser POST /start pour relancer.",
            campaign_id,
        )
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            campaign = await get_campaign_by_id(db, uuid.UUID(campaign_id))
            if task:
                task.attempts = task.max_attempts
                await mark_failed_or_retry(
                    db, task,
                    "État HITL perdu (redémarrage du worker). Relancer via POST /start.",
                )
            if campaign:
                await update_campaign_status(db, campaign, "redaction_done")
        return

    _waiting_for_hitl.discard(campaign_id)
    logger.info("Pipeline campagne %s — reprise après validation HITL", campaign_id)
    try:
        result = await pipeline.ainvoke(Command(resume=None), config=config)
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            if task:
                await mark_done(db, task, result)
        logger.info("Pipeline campagne %s — entièrement terminé", campaign_id)
    except Exception as exc:
        logger.exception("Pipeline campagne %s — erreur lors de la reprise CRM", campaign_id)
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            if task:
                await mark_failed_or_retry(db, task, str(exc))


# ── Tâches manuelles (POST /score, POST /redact) ─────────────────────────────

async def _run_manual_agent_task(
    task_id: uuid.UUID,
    run_agent,
    success_status: str,
    failure_status: str,
    on_success=None,
) -> None:
    """Scaffolding commun aux tâches manuelles SCORING/REDACTION."""
    campaign_id: uuid.UUID | None = None

    async with AsyncSessionLocal() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return
        campaign = await get_campaign_by_id(db, task.campaign_id)
        if campaign is None:
            await mark_failed_or_retry(db, task, "Campagne introuvable")
            return
        campaign_id = campaign.id
        await mark_running(db, task)

    async with AsyncSessionLocal() as db:
        campaign = await get_campaign_by_id(db, campaign_id)
        task = await db.get(AgentTask, task_id)
        if campaign is None or task is None:
            return
        try:
            result = await run_agent(db, campaign)
            await update_campaign_status(db, campaign, success_status)
            if on_success:
                await on_success(db, campaign, result)
            await mark_done(db, task, result)
            logger.info("Tâche %s terminée — campagne %s : %s", task.agent_name, campaign_id, result)
        except Exception as exc:
            logger.exception("Tâche %s échouée — campagne %s", task.agent_name, campaign_id)
            await db.rollback()
            campaign = await get_campaign_by_id(db, campaign_id)
            task = await db.get(AgentTask, task_id)
            if task:
                await mark_failed_or_retry(db, task, str(exc))
            if campaign:
                await update_campaign_status(db, campaign, failure_status)


async def run_scoring_task(task_id: uuid.UUID) -> None:
    """Re-score les leads ENRICHI d'une campagne (tâche SCORING manuelle)."""
    async def _on_success(db, campaign, result):
        await create_task(db, campaign.id, AgentName.REDACTION, {})

    await _run_manual_agent_task(
        task_id, run_scoring, "redaction_pending", "scoring_failed", on_success=_on_success
    )


async def run_redaction_task(task_id: uuid.UUID) -> None:
    """Génère les emails des leads QUALIFIE d'une campagne (tâche REDACTION manuelle)."""
    async def _on_success(db, campaign, result):
        nb = result.get("emails_generes", 0)
        if nb > 0:
            await notify_emails_prets(db, campaign.commercial_id, nb)

    await _run_manual_agent_task(
        task_id, run_redaction, "en_attente_validation", "redaction_failed", on_success=_on_success
    )


# ── Boucle de polling ─────────────────────────────────────────────────────────

async def poll_once() -> int:
    processed = 0

    async with AsyncSessionLocal() as db:
        pipeline_tasks  = await get_pending_tasks(db, AgentName.PIPELINE)
        resume_tasks    = await get_pending_tasks(db, AgentName.PIPELINE_RESUME)
        scoring_tasks   = await get_pending_tasks(db, AgentName.SCORING)
        redaction_tasks = await get_pending_tasks(db, AgentName.REDACTION)

    for task in pipeline_tasks:
        asyncio.create_task(run_new_pipeline(task.id))
    for task in resume_tasks:
        asyncio.create_task(resume_pipeline(task.id))
    for task in scoring_tasks:
        asyncio.create_task(run_scoring_task(task.id))
    for task in redaction_tasks:
        asyncio.create_task(run_redaction_task(task.id))

    processed = len(pipeline_tasks) + len(resume_tasks) + len(scoring_tasks) + len(redaction_tasks)
    return processed


async def main() -> None:
    logger.info(
        "Worker Pipeline démarré (poll toutes les %.0fs)",
        settings.WORKER_POLL_INTERVAL_SECONDS,
    )
    async with AsyncSessionLocal() as db:
        for agent in (AgentName.PIPELINE, AgentName.PIPELINE_RESUME, AgentName.SCORING, AgentName.REDACTION):
            recovered = await recover_stuck_running_tasks(db, agent)
            if recovered:
                logger.warning(
                    "%d tâche(s) %s bloquée(s) RUNNING → PENDING (redémarrage)",
                    recovered, agent,
                )
    while True:
        try:
            processed = await poll_once()
            if processed:
                logger.info("Tâches traitées : %d", processed)
        except Exception:
            logger.exception("Erreur durant le cycle de polling")
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
