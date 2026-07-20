import uuid
from datetime import date, datetime

from pydantic import BaseModel


class LeadResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    company_name: str
    siret: str
    secteur: str | None
    taille_entreprise: str | None
    adresse: str | None
    telephone: str | None
    site_web: str | None
    email: str | None
    prenom_dirigeant: str | None
    nom_dirigeant: str | None
    titre_dirigeant: str | None
    ca: int | None
    ca_n1: int | None
    resultat_net: int | None
    date_creation: date | None
    score_exploitabilite: float | None
    latitude: float | None
    longitude: float | None
    # Champs scoring
    score: float | None
    label_scoring: str | None
    confidence_score: float | None
    scored_at: datetime | None
    shap_explication: str | None
    # Champs rédaction
    objet_email: str | None
    contenu_email: str | None
    email_genere_at: datetime | None
    status: str
    created_at: datetime
    enriched_at: datetime | None

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    page: int
    page_size: int
