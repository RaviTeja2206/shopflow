from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "order-service"
    environment: str = "development"
    log_level: str = "INFO"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://shopflow:shopflow_secret@postgres:5432/shopflow"
    redis_url: str = "redis://redis:6379/0"
    kafka_bootstrap_servers: str = "kafka:9092"

    # Inter-service URLs — use Docker service names as hostnames
    product_service_url: str = "http://product-service:8000"
    user_service_url: str = "http://user-service:8000"

    secret_key: str = "change-this-in-production"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
