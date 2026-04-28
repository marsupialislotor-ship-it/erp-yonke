from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "ERP Yonke"
    app_env: str = "development"
    app_version: str = "1.0.0"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"

    # ── Base de datos ─────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/erp_yonke"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/erp_yonke"

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 2
    jwt_refresh_token_expire_days: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Firebase ─────────────────────────────────────────────────────────────
    firebase_project_id: str = ""
    firebase_credentials_path: str = "firebase-credentials.json"

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


# Singleton — importar desde aquí en todo el proyecto
settings = Settings()