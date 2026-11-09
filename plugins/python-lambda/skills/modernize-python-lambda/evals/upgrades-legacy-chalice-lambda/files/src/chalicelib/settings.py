from typing import Optional

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    database_dsn: Optional[str]
    database_path: str = "/tmp/inventory.db"
    log_level: str = "INFO"

    @validator("database_dsn", pre=True, always=True)
    def build_dsn(cls, v, values):
        return v or f"sqlite:///{values['database_path']}"


settings = Settings()
