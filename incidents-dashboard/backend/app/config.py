from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    DATABASE_URL_SYNC: str = "sqlite:///./app.db"
    SECRET_KEY: str = "change-me-please-32-chars-minimum-secret-key!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:3000"
    MAX_OFFSET: int = 10000
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def validate_secret(self):
        if len(self.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters")

    @property
    def cors_origins_list(self) -> List[str]:
        raw = self.CORS_ORIGINS
        if not raw or raw.strip() == "*":
            return ["*"]
        # Support comma-separated; also handle JSON list string
        if raw.strip().startswith("["):
            import json

            try:
                return json.loads(raw)
            except Exception:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()
# Fail closed if SECRET_KEY too short (except tests may override)
try:
    settings.validate_secret()
except RuntimeError:
    # Allow import in tests where env may be not set; actual startup will check again
    pass
