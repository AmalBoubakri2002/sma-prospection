import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEventResult:
    """Issue du traitement d'un webhook Odoo — conservée pour la traçabilité."""

    PROCESSED = "PROCESSED"            # statut du lead mis à jour
    NOOP = "NOOP"                      # déjà dans le statut cible, ou transition refusée
    SKIPPED_STATUS = "SKIPPED_STATUS"  # lead pas encore passé par la synchronisation CRM
    LEAD_NOT_FOUND = "LEAD_NOT_FOUND"  # aucun lead local ne correspond — à investiguer
    IGNORED = "IGNORED"                # type d'événement non géré


class WebhookEvent(Base):
    """Journal des webhooks Odoo reçus (dossier de conception §13.5.5).

    Chaque événement est conservé avec son payload brut et le résultat de son
    traitement : c'est la piste d'audit de la boucle retour CRM, et le point de
    départ du diagnostic quand un statut Odoo ne se reflète pas côté SMA-PC."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event: Mapped[str] = mapped_column(String(50))
    odoo_lead_id: Mapped[int | None] = mapped_column(Integer)
    # SET NULL : l'entrée de journal survit à la purge RGPD du lead
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    payload: Mapped[str] = mapped_column(Text())      # JSON brut reçu d'Odoo
    result: Mapped[str] = mapped_column(String(20))   # WebhookEventResult

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
