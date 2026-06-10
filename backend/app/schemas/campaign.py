import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

_VALID_STATUSES = {"pending", "running", "done", "failed"}


class CampaignCreate(BaseModel):
    sector: str
    country: str
    sizes: list[str]
    functions: list[str]
    min_score: int = 70
    sources: list[str]
    estimated_prospects: int = 0

    @field_validator("min_score")
    @classmethod
    def score_range(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError("Le score doit être entre 0 et 100")
        return v

    @field_validator("sizes", "functions", "sources")
    @classmethod
    def not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("La liste ne peut pas être vide")
        return v


class CampaignResponse(BaseModel):
    id: uuid.UUID
    commercial_id: uuid.UUID
    sector: str
    country: str
    sizes: list[str]
    functions: list[str]
    min_score: int
    sources: list[str]
    estimated_prospects: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"Statut invalide. Valeurs acceptées : {_VALID_STATUSES}")
        return v
