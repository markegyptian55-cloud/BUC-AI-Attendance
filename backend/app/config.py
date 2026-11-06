from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "change-this-in-production-to-a-secure-random-64-char-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DATABASE_URL: str = "sqlite:///../data/attendance.db"
    API_URL: str = "http://127.0.0.1:8000"
    CORS_ORIGINS: str = "http://localhost:8501,http://127.0.0.1:8501"
    MATCH_THRESHOLD: float = 0.60
    SIDE_MATCH_THRESHOLD: float = 0.55
    DET_SIZE: int = 320
    MAX_UPLOAD_MB: int = 5

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
