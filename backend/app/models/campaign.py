import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
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

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Seuil de qualification — leads avec score >= score_minimum passent en QUALIFIE
    # 0.65 (2026-07-07) : reproduit la sélectivité empirique de l'ancien seuil 0.50
    # sur l'échelle corrigée du modèle (barème /7 + calibration isotonique, voir
    # ml/train_scoring_model.py) — l'ancien 0.50 datait du modèle bugué qui
    # plafonnait à ~0.79 et laissait passer des leads déficitaires.
    score_minimum: Mapped[float] = mapped_column(default=0.65)

    # Résultats
    estimated_prospects: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
