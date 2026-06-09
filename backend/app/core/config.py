from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


settings = Settings()
