from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    REDIS_URL: str
    ANTHROPIC_API_KEY: str
    SECRET_KEY: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    RULES_CACHE_TTL_SECONDS: int = 60

    AMOUNT_SOFT_LIMIT: float = 10000.0
    AMOUNT_HARD_LIMIT: float = 50000.0
    VELOCITY_1H_THRESHOLD: int = 5
    VELOCITY_24H_THRESHOLD: int = 20
    IMPOSSIBLE_TRAVEL_HOURS: int = 2
    IMPOSSIBLE_TRAVEL_KM: float = 500.0


settings = Settings()
