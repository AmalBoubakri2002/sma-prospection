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


class CommercialRegister(BaseModel):
    """Inscription publique d'un commercial — toujours en attente de validation admin."""

    email: str
    password: str
    full_name: str | None = None

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
