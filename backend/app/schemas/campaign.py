import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

_VALID_STATUSES = {"pending", "running", "done", "failed"}


class CampaignCreate(BaseModel):
    codes_naf: list[str]
    codes_postaux: list[str]
    tranches_effectifs: list[str]
    quota: int = 50
    estimated_prospects: int = 0

    @field_validator("quota")
    @classmethod
    def quota_range(cls, v: int) -> int:
        if not 1 <= v <= 500:
            raise ValueError("Le quota doit être entre 1 et 500")
        return v

    @field_validator("codes_naf", "codes_postaux", "tranches_effectifs")
    @classmethod
    def not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("La liste ne peut pas être vide")
        return v


class CampaignResponse(BaseModel):
    id: uuid.UUID
    commercial_id: uuid.UUID
    codes_naf: list[str]
    codes_postaux: list[str]
    tranches_effectifs: list[str]
    quota: int
    estimated_prospects: int
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


class AgentTaskSummary(BaseModel):
    agent_name: str
    status: str
    attempts: int
    error: str | None = None


class CampaignStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    leads_collected: int
    task: AgentTaskSummary | None = None
