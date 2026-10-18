
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REDIS_URL:str
    ENVIRONMENT: str = "development"
    # Optional so the app boots without a key; investigations then fail
    # with a clear error instead of the whole service refusing to start.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    GEMINI_TIMEOUT_SECONDS: int = 30

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.ENVIRONMENT == "production" and (
            len(self.JWT_SECRET_KEY) < 32
            or self.JWT_SECRET_KEY == "development-only-change-me"
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a random value of at least "
                "32 characters in production"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
