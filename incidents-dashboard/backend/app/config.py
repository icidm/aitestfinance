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
        # CORS deny wildcard: never return ["*"] — fail-closed to safe localhost defaults
        if not raw or raw.strip() == "*":
            return ["http://localhost:8000", "http://localhost:3000"]
        # Support comma-separated; also handle JSON list string — filter out any wildcard entries
        if raw.strip().startswith("["):
            import json

            try:
                parsed = json.loads(raw)
                # filter wildcard and empty entries
                filtered = [o.strip() for o in parsed if isinstance(o, str) and o.strip() != "*" and o.strip()]
                return filtered if filtered else ["http://localhost:8000", "http://localhost:3000"]
            except Exception:
                pass
        origins = [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]
        return origins if origins else ["http://localhost:8000", "http://localhost:3000"]


settings = Settings()
# Fail closed if SECRET_KEY too short (except tests may override)
try:
    settings.validate_secret()
except RuntimeError:
    # Allow import in tests where env may be not set; actual startup will check again
    pass
