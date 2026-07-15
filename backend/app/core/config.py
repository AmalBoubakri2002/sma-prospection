from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Chemin absolu vers backend/.env, indépendant du répertoire de lancement
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

_DEFAULT_SECRET = "change_me_in_production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # App
    PROJECT_NAME: str = "SMA Prospection"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://sma_user:sma_password@localhost:5433/sma_db"

    # JWT
    SECRET_KEY: str = _DEFAULT_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    @model_validator(mode="after")
    def check_secret_key(self) -> "Settings":
        if not self.DEBUG and self.SECRET_KEY == _DEFAULT_SECRET:
            raise ValueError(
                "SECRET_KEY doit être modifiée en production. "
                "Définissez SECRET_KEY dans votre fichier .env."
            )
        return self

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Premier admin — créé automatiquement au démarrage si la table users est vide
    FIRST_ADMIN_EMAIL: str = "admin@prospectai.fr"
    FIRST_ADMIN_PASSWORD: str = "Admin1234!"
    FIRST_ADMIN_NAME: str = "Administrateur"

    # API SIRENE (INSEE) — Agent Veille
    INSEE_API_KEY: str = ""
    INSEE_SIRENE_BASE_URL: str = "https://api.insee.fr/api-sirene/3.11"
    SIRENE_PAGE_SIZE: int = 20
    SIRENE_REQUEST_DELAY_SECONDS: float = 2.0

    # Workers agents
    WORKER_POLL_INTERVAL_SECONDS: float = 5.0

    # INPI RNE — comptes annuels (data.inpi.fr). Pas de clé API statique :
    # l'authentification se fait par login (email/mot de passe du compte
    # data.inpi.fr) contre registre-national-entreprises.inpi.fr/api/sso/login,
    # qui renvoie un token temporaire — voir app/agents/enrichissement/inpi.py.
    INPI_USERNAME: str = ""
    INPI_PASSWORD: str = ""

    # NVIDIA API (OpenAI-compatible) — Agent Rédaction
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    REDACTION_MODEL: str = "mistralai/mistral-nemotron"
    # Optionnel : modèle utilisé à partir de la 2e tentative si REDACTION_MODEL échoue
    # (ex : fonction NVIDIA dégradée) — vide = pas de bascule, on reste sur REDACTION_MODEL.
    REDACTION_FALLBACK_MODEL: str = ""
    REDACTION_REQUEST_DELAY_SECONDS: float = 1.0
    NVIDIA_API_TIMEOUT_SECONDS: float = 60.0  # timeout par appel (évite les blocages infinis)

    # Agent Rédaction — évaluation (backend/eval/) : modèle juge pour le scoring
    # qualitatif LLM-as-judge. Vide = réutilise REDACTION_MODEL (attention au biais
    # d'auto-évaluation dans ce cas).
    REDACTION_EVAL_JUDGE_MODEL: str = ""

    # CRM Odoo 17 — Agent CRM (app/services/odoo_client.py)
    ODOO_URL: str = "http://localhost:8069"
    ODOO_DB: str = "odoo"
    ODOO_USERNAME: str = ""
    ODOO_PASSWORD: str = ""
    ODOO_WEBHOOK_SECRET: str = ""
    # Envoi effectif de l'email de prospection via le module mail d'Odoo après
    # la synchronisation d'un lead validé (statut CONTACTE). En dev, l'email
    # part vers Mailpit (http://localhost:8025) — aucun prospect réel contacté.
    ODOO_SEND_EMAILS: bool = True
    # Expéditeur de repli si le commercial n'a pas d'adresse email exploitable.
    ODOO_EMAIL_FROM_DEFAULT: str = "prospection@sma-prospectai.fr"


settings = Settings()
