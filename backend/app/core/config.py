from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    gemini_model: str = "gemini-3.1-flash-lite"
    app_name: str = "Enterprise Knowledge Assistant"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    tesseract_cmd: str = (
    "C:/Program Files/Tesseract-OCR/tesseract.exe"
    )
    ocr_languages: str = "vie+eng"
    database_url: str = (
        "postgresql+psycopg://rag_user:rag_password@localhost:5432/enterprise_rag"
    )
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    gemini_api_key: str = ""
    jwt_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
