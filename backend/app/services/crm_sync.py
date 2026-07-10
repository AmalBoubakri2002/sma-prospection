import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_sync import CRMSync, CRMSyncStatus


async def get_crm_sync_by_lead_id(db: AsyncSession, lead_id: uuid.UUID) -> CRMSync | None:
    result = await db.execute(select(CRMSync).where(CRMSync.lead_id == lead_id))
    return result.scalar_one_or_none()


async def mark_crm_sync_success(db: AsyncSession, lead_id: uuid.UUID, odoo_lead_id: int) -> CRMSync:
    """Upsert : un seul enregistrement de synchro par lead, mis à jour à chaque tentative."""
    sync = await get_crm_sync_by_lead_id(db, lead_id)
    if sync is None:
        sync = CRMSync(lead_id=lead_id)

    sync.odoo_lead_id = odoo_lead_id
    sync.sync_status = CRMSyncStatus.SUCCESS
    sync.synced_at = datetime.now(timezone.utc)
    sync.error_message = None
    db.add(sync)
    await db.commit()
    await db.refresh(sync)
    return sync


async def mark_crm_sync_error(db: AsyncSession, lead_id: uuid.UUID, error_message: str) -> CRMSync:
    sync = await get_crm_sync_by_lead_id(db, lead_id)
    if sync is None:
        sync = CRMSync(lead_id=lead_id)

    sync.sync_status = CRMSyncStatus.ERROR
    sync.error_message = error_message[:2000]
    db.add(sync)
    await db.commit()
    await db.refresh(sync)
    return sync
