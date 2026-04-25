from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BU_",
        env_file=".env",
        extra="ignore",
    )

    fernet_key: str = Field(..., description="Fernet key for credential encryption")
    data_dir: Path = Field(default=Path("./var"))
    database_url: str | None = None
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    auth_password: str | None = None

    @field_validator("fernet_key")
    @classmethod
    def _check_fernet_key(cls, v: str) -> str:
        if not v:
            raise ValueError("BU_FERNET_KEY is required")
        return v

    def model_post_init(self, _: object) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url is None:
            self.database_url = f"sqlite:///{self.data_dir}/bulk-unsubscribe.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
