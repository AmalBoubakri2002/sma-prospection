import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType:
    REGISTRATION_REQUEST = "REGISTRATION_REQUEST"
    ACCOUNT_APPROVED = "ACCOUNT_APPROVED"
    ACCOUNT_REJECTED = "ACCOUNT_REJECTED"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    related_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
