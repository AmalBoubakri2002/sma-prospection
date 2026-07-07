import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

_VALID_STATUSES = {"pending", "running", "done", "failed"}


def _validate_score_range(v: float) -> float:
    if not 0.0 <= v <= 1.0:
        raise ValueError("Le seuil de qualification doit être entre 0.0 et 1.0")
    return v


class CampaignCreate(BaseModel):
    name: str | None = None
    codes_naf: list[str]
    codes_postaux: list[str]
    tranches_effectifs: list[str]
    quota: int = 50
    estimated_prospects: int = 0
    # 0.65 (2026-07-07) : voir models/campaign.py pour le contexte de la recalibration
    score_minimum: float = 0.65

    @field_validator("quota")
    @classmethod
    def quota_range(cls, v: int) -> int:
        if not 1 <= v <= 500:
            raise ValueError("Le quota doit être entre 1 et 500")
        return v

    _validate_score_minimum = field_validator("score_minimum")(_validate_score_range)

    @field_validator("codes_naf", "codes_postaux", "tranches_effectifs")
    @classmethod
    def not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("La liste ne peut pas être vide")
        return v


class CampaignResponse(BaseModel):
    id: uuid.UUID
    commercial_id: uuid.UUID
    name: str | None = None
    codes_naf: list[str]
    codes_postaux: list[str]
    tranches_effectifs: list[str]
    quota: int
    estimated_prospects: int
    score_minimum: float
    status: str
    created_at: datetime
    leads_count: int = 0

    model_config = {"from_attributes": True}


class CampaignStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"Statut invalide. Valeurs acceptées : {_VALID_STATUSES}")
        return v


class ScoreMinimumUpdate(BaseModel):
    score_minimum: float

    _validate_score_minimum = field_validator("score_minimum")(_validate_score_range)


class AgentTaskSummary(BaseModel):
    agent_name: str
    status: str
    attempts: int
    error: str | None = None


class CampaignStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    # Compteurs de leads par étape du pipeline
    leads_collectes: int = 0
    leads_enrichis: int = 0
    leads_qualifies: int = 0
    leads_ecartes: int = 0
    leads_email_genere: int = 0
    leads_en_validation: int = 0
    leads_valides: int = 0
    leads_rejetes: int = 0
    # Tâche agent actuellement active (ou dernière terminée)
    task: AgentTaskSummary | None = None
