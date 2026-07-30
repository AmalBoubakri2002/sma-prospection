"""Worker Pipeline — point d'entrée unique pour les tâches PIPELINE, PIPELINE_RESUME, SCORING,
REDACTION et CRM.

L'état du graphe (dont la suspension HITL) est persisté dans PostgreSQL
(AsyncPostgresSaver, voir pipeline_graph.get_pipeline) : un redémarrage du
worker pendant la pause de validation ne perd plus la position dans le graphe.
resume_pipeline consulte l'état persistant ; si aucun checkpoint suspendu
n'existe (checkpoints purgés, campagne antérieure à la migration), il bascule
sur une tâche CRM manuelle (run_crm_task) — filet conservé, les leads VALIDE
sont déjà en base.
"""

import asyncio
import logging
import uuid

from app.agents.crm.agent import run_crm
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
from app.workers.pipeline_graph import CampaignPipelineState, get_pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s"
)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logger = logging.getLogger("worker-pipeline")


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
        pipeline = await get_pipeline()
        result = await pipeline.ainvoke(initial, config=config)

        snapshot = await pipeline.aget_state(config)
        if snapshot.next:
            # Graphe suspendu avant le nœud CRM — en attente de validation HITL.
            # La position est persistée en base (checkpoint PostgreSQL).
            logger.info(
                "Pipeline campagne %s suspendu — HITL (prochain nœud : %s)",
                campaign_id, list(snapshot.next),
            )
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
    pipeline = await get_pipeline()

    # L'état HITL vit dans les checkpoints PostgreSQL : on vérifie qu'un graphe
    # suspendu existe bien pour cette campagne (snapshot.next non vide).
    snapshot = await pipeline.aget_state(config)
    if not snapshot.next:
        # Aucun checkpoint suspendu (checkpoints purgés, ou campagne lancée avant
        # la migration AsyncPostgresSaver) — mais les leads validés par le
        # commercial sont déjà VALIDE en base, donc on bascule sur une tâche CRM
        # manuelle plutôt que d'échouer et de laisser la campagne bloquée.
        logger.warning(
            "Pipeline campagne %s — aucun état HITL suspendu en base, "
            "bascule sur une tâche CRM manuelle",
            campaign_id,
        )
        async with AsyncSessionLocal() as db:
            task = await db.get(AgentTask, task_id)
            campaign = await get_campaign_by_id(db, uuid.UUID(campaign_id))
            if task:
                await mark_done(db, task, {"status": "hitl_state_lost", "fallback": "crm_manual"})
            if campaign:
                await create_task(db, campaign.id, AgentName.CRM, {"recovery": True})
                await update_campaign_status(db, campaign, "crm_pending")
        return

    logger.info("Pipeline campagne %s — reprise après validation HITL", campaign_id)
    try:
        # Reprise d'un breakpoint STATIQUE (interrupt_before=["crm"]) : input=None
        # relance le graphe depuis le checkpoint suspendu. Command(resume=...) est
        # réservé aux interruptions dynamiques interrupt() et plante ici
        # (UnboundLocalError dans langgraph 1.2 — constaté le 2026-07-16, bug
        # historiquement masqué par la bascule CRM manuelle du MemorySaver).
        result = await pipeline.ainvoke(None, config=config)
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
            logger.info(
                "Tâche %s terminée — campagne %s : %s", task.agent_name, campaign_id, result
            )
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


async def _run_redaction_or_raise(db, campaign) -> dict:
    """Échec total (ex : modèle NVIDIA DEGRADED) → lève pour que _run_manual_agent_task
    bascule sur failure_status au lieu de marquer 'en_attente_validation' une file vide."""
    result = await run_redaction(db, campaign)
    if result.get("emails_generes", 0) == 0 and result.get("leads_erreurs", 0) > 0:
        raise RuntimeError(
            f"Rédaction : {result['leads_erreurs']} leads en erreur, aucun email généré"
        )
    return result


async def run_redaction_task(task_id: uuid.UUID) -> None:
    """Génère les emails des leads QUALIFIE d'une campagne (tâche REDACTION manuelle)."""
    async def _on_success(db, campaign, result):
        nb = result.get("emails_generes", 0)
        if nb > 0:
            await notify_emails_prets(db, campaign.commercial_id, nb)

    await _run_manual_agent_task(
        task_id,
        _run_redaction_or_raise,
        "en_attente_validation",
        "redaction_failed",
        on_success=_on_success,
    )


async def _run_crm_or_raise(db, campaign) -> dict:
    """Échec total (ex : Odoo injoignable) → lève pour que _run_manual_agent_task
    bascule sur 'crm_failed' au lieu de marquer 'completed' sans rien avoir synchronisé."""
    result = await run_crm(db, campaign)
    if result.get("leads_synchronises", 0) == 0 and result.get("leads_erreurs", 0) > 0:
        raise RuntimeError(
            f"CRM : {result['leads_erreurs']} leads en erreur, aucune synchronisation Odoo"
        )
    return result


async def run_crm_task(task_id: uuid.UUID) -> None:
    """Synchronise les leads VALIDE d'une campagne vers Odoo (tâche CRM manuelle —
    utilisée en secours quand l'état HITL du graphe LangGraph a été perdu, voir resume_pipeline)."""
    await _run_manual_agent_task(task_id, _run_crm_or_raise, "completed", "crm_failed")


# ── Boucle de polling ─────────────────────────────────────────────────────────

async def poll_once() -> int:
    processed = 0

    async with AsyncSessionLocal() as db:
        pipeline_tasks  = await get_pending_tasks(db, AgentName.PIPELINE)
        resume_tasks    = await get_pending_tasks(db, AgentName.PIPELINE_RESUME)
        scoring_tasks   = await get_pending_tasks(db, AgentName.SCORING)
        redaction_tasks = await get_pending_tasks(db, AgentName.REDACTION)
        crm_tasks       = await get_pending_tasks(db, AgentName.CRM)

    for task in pipeline_tasks:
        asyncio.create_task(run_new_pipeline(task.id))
    for task in resume_tasks:
        asyncio.create_task(resume_pipeline(task.id))
    for task in scoring_tasks:
        asyncio.create_task(run_scoring_task(task.id))
    for task in redaction_tasks:
        asyncio.create_task(run_redaction_task(task.id))
    for task in crm_tasks:
        asyncio.create_task(run_crm_task(task.id))

    processed = (
        len(pipeline_tasks) + len(resume_tasks) + len(scoring_tasks)
        + len(redaction_tasks) + len(crm_tasks)
    )
    return processed


async def main() -> None:
    logger.info(
        "Worker Pipeline démarré (poll toutes les %.0fs)",
        settings.WORKER_POLL_INTERVAL_SECONDS,
    )
    async with AsyncSessionLocal() as db:
        for agent in (
            AgentName.PIPELINE,
            AgentName.PIPELINE_RESUME,
            AgentName.SCORING,
            AgentName.REDACTION,
            AgentName.CRM,
        ):
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
