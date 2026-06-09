import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: str = "commercial"

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ("commercial", "admin"):
            raise ValueError("Rôle invalide")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
