import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CRMSyncStatus:
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class CRMSync(Base):
    """État technique de la synchronisation d'un Lead vers Odoo — séparé du cycle
    de vie métier du lead (Lead.status) pour permettre un retry indépendant en cas
    d'échec Odoo, sans perturber le statut du lead lui-même."""

    __tablename__ = "crm_syncs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # unique=True : un seul enregistrement de synchro par lead ; un retry met à
    # jour cette ligne plutôt que d'en créer une nouvelle.
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), unique=True, index=True
    )

    odoo_lead_id: Mapped[int | None] = mapped_column(Integer)
    sync_status: Mapped[str] = mapped_column(String(20), default=CRMSyncStatus.PENDING)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text())

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
