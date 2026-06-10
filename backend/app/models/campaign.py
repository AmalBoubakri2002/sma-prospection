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

    # Paramètres de ciblage
    sector: Mapped[str] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(50))
    sizes: Mapped[list] = mapped_column(JSON)       # ["50-200", "201-500"]
    functions: Mapped[list] = mapped_column(JSON)   # ["ceo", "dsi"]
    min_score: Mapped[int] = mapped_column(Integer, default=70)
    sources: Mapped[list] = mapped_column(JSON)     # ["sirene", "linkedin"]

    # Résultats
    estimated_prospects: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending → running → done | failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
