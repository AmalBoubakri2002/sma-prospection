"""Worker indépendant pour l'Agent Enrichissement — boucle de polling sur agent_tasks.

Lancement en dev (process séparé du serveur FastAPI) :
    cd backend && source .venv/bin/activate && python -m app.workers.worker_enrichissement
"""

import asyncio
import logging
import uuid

from app.agents.enrichissement.agent import run_enrichissement
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.models.agent_task import AgentName, AgentTask, AgentTaskStatus
from app.services.agent_task import get_pending_tasks, mark_done, mark_failed_or_retry, mark_running
from app.services.campaign import get_campaign_by_id, update_campaign_status

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [worker-enrichissement] %(message)s"
)
logger = logging.getLogger("worker-enrichissement")


async def process_task(task_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(AgentTask, task_id)
        if task is None:
            return

        campaign = await get_campaign_by_id(db, task.campaign_id)
        if campaign is None:
            await mark_failed_or_retry(db, task, "Campagne introuvable")
            return

        task = await mark_running(db, task)
        try:
            result = await run_enrichissement(db, campaign)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Échec Agent Enrichissement pour la campagne %s", campaign.id
            )
            task = await mark_failed_or_retry(db, task, str(exc))
            if task.status == AgentTaskStatus.FAILED:
                await update_campaign_status(db, campaign, "enrichissement_failed")
            return

        await mark_done(db, task, result)
        await update_campaign_status(db, campaign, "enrichissement_done")
        logger.info("Campagne %s enrichissement terminé : %s", campaign.id, result)


async def poll_once() -> int:
    async with AsyncSessionLocal() as db:
        tasks = await get_pending_tasks(db, AgentName.ENRICHISSEMENT)
        task_ids = [t.id for t in tasks]
    for task_id in task_ids:
        await process_task(task_id)
    return len(task_ids)


async def main() -> None:
    logger.info(
        "Worker Agent Enrichissement démarré (poll toutes les %.0fs)",
        settings.WORKER_POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            processed = await poll_once()
            if processed:
                logger.info("Tâches traitées : %d", processed)
        except Exception:  # noqa: BLE001
            logger.exception("Erreur durant le cycle de polling")
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
