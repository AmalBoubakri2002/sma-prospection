import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTask, AgentTaskStatus


async def create_task(
    db: AsyncSession, campaign_id: uuid.UUID, agent_name: str, payload: dict
) -> AgentTask:
    task = AgentTask(campaign_id=campaign_id, agent_name=agent_name, payload=payload)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_pending_tasks(db: AsyncSession, agent_name: str, limit: int = 5) -> list[AgentTask]:
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.agent_name == agent_name, AgentTask.status == AgentTaskStatus.PENDING)
        .order_by(AgentTask.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_latest_task_for_campaign(
    db: AsyncSession, campaign_id: uuid.UUID, agent_name: str | None = None
) -> AgentTask | None:
    stmt = select(AgentTask).where(AgentTask.campaign_id == campaign_id)
    if agent_name:
        stmt = stmt.where(AgentTask.agent_name == agent_name)
    stmt = stmt.order_by(AgentTask.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_active_task(
    db: AsyncSession, campaign_id: uuid.UUID
) -> AgentTask | None:
    """Retourne la tâche PENDING ou RUNNING la plus récente, tous agents confondus.
    Utilisé par le endpoint /status pour afficher l'agent actuellement actif."""
    result = await db.execute(
        select(AgentTask)
        .where(
            AgentTask.campaign_id == campaign_id,
            AgentTask.status.in_([AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING]),
        )
        .order_by(AgentTask.created_at.desc())
        .limit(1)
    )
    active = result.scalar_one_or_none()
    if active:
        return active
    # Aucune tâche active → retourner la dernière tâche terminée (pour l'historique)
    result = await db.execute(
        select(AgentTask)
        .where(AgentTask.campaign_id == campaign_id)
        .order_by(AgentTask.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mark_running(db: AsyncSession, task: AgentTask) -> AgentTask:
    task.status = AgentTaskStatus.RUNNING
    task.attempts += 1
    await db.commit()
    await db.refresh(task)
    return task


async def mark_done(db: AsyncSession, task: AgentTask, result: dict) -> AgentTask:
    task.status = AgentTaskStatus.DONE
    task.result = result
    await db.commit()
    await db.refresh(task)
    return task


async def mark_failed_or_retry(db: AsyncSession, task: AgentTask, error: str) -> AgentTask:
    if task.attempts < task.max_attempts:
        task.status = AgentTaskStatus.PENDING
    else:
        task.status = AgentTaskStatus.FAILED
    task.result = {"error": error}
    await db.commit()
    await db.refresh(task)
    return task


async def recover_stuck_running_tasks(db: AsyncSession, agent_name: str) -> int:
    """Reset RUNNING tasks back to PENDING at worker startup.
    Guards against tasks left RUNNING when a worker process was killed mid-execution."""
    result = await db.execute(
        update(AgentTask)
        .where(AgentTask.agent_name == agent_name, AgentTask.status == AgentTaskStatus.RUNNING)
        .values(status=AgentTaskStatus.PENDING)
        .returning(AgentTask.id)
    )
    await db.commit()
    return len(result.fetchall())
