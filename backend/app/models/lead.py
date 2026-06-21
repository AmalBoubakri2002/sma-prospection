import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Double, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeadStatus:
    """Cycle de vie complet du dossier de conception (§11). Seul COLLECTE est
    produit par l'Agent Veille ; les suivants seront posés par les prochains agents."""

    COLLECTE = "COLLECTE"
    ENRICHI = "ENRICHI"
    QUALIFIE = "QUALIFIE"
    EMAIL_GENERE = "EMAIL_GENERE"
    EN_ATTENTE_VALIDATION = "EN_ATTENTE_VALIDATION"
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    SYNCHRONISE_CRM = "SYNCHRONISE_CRM"
    CONTACTE = "CONTACTE"
    REPONDU = "REPONDU"
    SANS_REPONSE = "SANS_REPONSE"


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("campaign_id", "siret", name="uq_leads_campaign_siret"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )

    company_name: Mapped[str] = mapped_column(String(255))
    siret: Mapped[str] = mapped_column(String(14), index=True)
    secteur: Mapped[str | None] = mapped_column(String(10))
    taille_entreprise: Mapped[str | None] = mapped_column(String(10))
    adresse: Mapped[str | None] = mapped_column(String(500))
    telephone: Mapped[str | None] = mapped_column(String(20))
    site_web: Mapped[str | None] = mapped_column(String(255))

    # Champs remplis par l'Agent Enrichissement
    email: Mapped[str | None] = mapped_column(String(255))
    prenom_dirigeant: Mapped[str | None] = mapped_column(String(100))
    nom_dirigeant: Mapped[str | None] = mapped_column(String(100))
    titre_dirigeant: Mapped[str | None] = mapped_column(String(100))
    ca: Mapped[int | None] = mapped_column(Integer())
    ca_n1: Mapped[int | None] = mapped_column(Integer())
    resultat_net: Mapped[int | None] = mapped_column(Integer())
    date_creation: Mapped[date | None] = mapped_column(Date())
    score_intent: Mapped[float | None] = mapped_column(Double())
    latitude: Mapped[float | None] = mapped_column(Double())
    longitude: Mapped[float | None] = mapped_column(Double())

    status: Mapped[str] = mapped_column(String(30), default=LeadStatus.COLLECTE)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
