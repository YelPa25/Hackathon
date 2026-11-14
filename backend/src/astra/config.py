from os import getenv
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
DATASET_NAME = "ASTRA_90day_dataset_v1"
PACKAGED_DATASET = PROJECT_DIR / "data-source" / DATASET_NAME
DEFAULT_ORIGINS = ("http://127.0.0.1:5180", "http://localhost:5180")


def default_dataset_dir() -> Path:
    return PACKAGED_DATASET if PACKAGED_DATASET.exists() else PROJECT_DIR / DATASET_NAME


class Settings(BaseModel):
    environment: Literal["development", "test"] = "development"
    database_path: Path = BACKEND_DIR / "var" / "astra.sqlite3"
    dataset_dir: Path = Field(default_factory=default_dataset_dir)
    cors_origins: tuple[str, ...] = DEFAULT_ORIGINS

    @field_validator("cors_origins")
    @classmethod
    def require_local_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        for origin in origins:
            url = urlsplit(origin)
            if (url.scheme not in {"http", "https"} or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or url.netloc != origin.split("://", 1)[1] or url.username is not None
                    or url.port is None or url.path or url.query or url.fragment):
                raise ValueError("CORS origins must be explicit loopback HTTP(S) origins with ports.")
        return origins

    @model_validator(mode="after")
    def keep_database_outside_sources(self) -> "Settings":
        self.database_path = (BACKEND_DIR / self.database_path).resolve()
        self.dataset_dir = (PROJECT_DIR / self.dataset_dir).resolve()
        protected = (self.dataset_dir, PROJECT_DIR / DATASET_NAME, PROJECT_DIR / "data-source")
        if any(self.database_path.is_relative_to(path.resolve()) for path in protected):
            raise ValueError("The SQLite path must be outside the dataset directory.")
        return self

    @classmethod
    def from_environment(cls) -> "Settings":
        origins = getenv("ASTRA_CORS_ORIGINS")
        return cls(
            environment=getenv("ASTRA_ENV", "development"),
            database_path=Path(getenv("ASTRA_DB_PATH", "var/astra.sqlite3")),
            dataset_dir=Path(getenv("ASTRA_DATASET_DIR", str(default_dataset_dir()))),
            cors_origins=DEFAULT_ORIGINS if origins is None else tuple(
                origin.strip() for origin in origins.split(",") if origin.strip()
            ),
        )
