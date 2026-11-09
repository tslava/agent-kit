from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_dsn: Optional[str] = None
    database_path: str = "/tmp/inventory.db"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def build_dsn(self) -> "Settings":
        if not self.database_dsn:
            self.database_dsn = f"sqlite:///{self.database_path}"
        return self


settings = Settings()
