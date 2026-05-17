from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "notification-service"
    environment: str = "development"
    log_level: str = "INFO"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_consumer_group: str = "notification-service-group"
    redis_url: str = "redis://redis:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
