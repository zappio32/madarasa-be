from functools import lru_cache
import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "postgresql+psycopg://madarasa:madarasa@localhost:5432/madarasa"
    jwt_secret_key: str = "development-only-change-me-32-characters"
    jwt_access_token_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]
    initial_admin_email: str = "madarasa123@gmail.com"
    initial_admin_password: str = ""
    media_storage: str = "local"
    local_media_path: str = "./var/uploads"
    storage_endpoint: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = ""
    storage_region: str = "auto"
    max_upload_size_mb: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                parsed = json.loads(value)
                if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                    raise ValueError("CORS_ORIGINS must be a JSON string array or comma-separated origins.")
                return parsed
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def validate_production(self) -> None:
        if self.environment == "production":
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key == "development-only-change-me-32-characters":
                raise ValueError("Set a unique JWT_SECRET_KEY with at least 32 characters.")
            if self.media_storage != "s3":
                raise ValueError("Production media storage must use persistent S3-compatible storage.")
            if not all((self.storage_bucket, self.storage_access_key, self.storage_secret_key)):
                raise ValueError("Configure all object-storage credentials before production startup.")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
