import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    commercial_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Paramètres de ciblage SIRENE
    codes_naf: Mapped[list] = mapped_column(JSON)          # ["62.01Z", "62.02A"]
    codes_postaux: Mapped[list] = mapped_column(JSON)      # ["75008", "75009"]
    tranches_effectifs: Mapped[list] = mapped_column(JSON) # ["12", "21", "22"]
    quota: Mapped[int] = mapped_column(Integer, default=50)

    # Résultats
    estimated_prospects: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
