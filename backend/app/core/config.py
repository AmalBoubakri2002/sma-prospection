from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Chemin absolu vers backend/.env, indépendant du répertoire de lancement
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    # App
    PROJECT_NAME: str = "SMA Prospection"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://sma_user:sma_password@localhost:5433/sma_db"

    # JWT
    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

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


settings = Settings()
