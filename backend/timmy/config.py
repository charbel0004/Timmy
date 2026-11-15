from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TIMMY_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    telemetry_enabled: bool = True
    telemetry_model_process_source: Literal["local", "unavailable"] = "local"
    telemetry_sample_seconds: float = Field(default=3, ge=1, le=60)
    telemetry_retention_days: int = Field(default=14, ge=1, le=365)
    telemetry_max_events: int = Field(default=2000, ge=100, le=10000)

    database_url: str = "sqlite:///./timmy.db"
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_hours: Annotated[int, Field(ge=1, le=24)] = 8
    activation_minutes: Annotated[int, Field(ge=5, le=1440)] = 60
    demo_mode: bool = False
    report_source: str | None = None
    report_timezone: str | None = None
    weekly_enabled: bool = False
    weekly_actor_id: int | None = Field(default=None, gt=0)
    weekly_project_ids: list[int] = Field(default_factory=list)
    document_root: Path = Path(".timmy-data/documents")
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_cache: Path = Path("~/.cache/timmy/whisper")
    piper_model: Path = Path("~/.cache/timmy/voices/en_US-lessac-medium.onnx")
    piper_speed: Annotated[float, Field(ge=0.5, le=2)] = 1.0
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: Annotated[str, Field(min_length=1)] = "qwen3.5"

    ollama_timeout_seconds: Annotated[float, Field(gt=0, le=600)] = 90
    ollama_connect_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 5
    ollama_max_tokens: Annotated[int, Field(ge=128, le=8192)] = 1024
    ollama_seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 42

    @field_validator("ollama_url")
    @classmethod
    def local_ollama_only(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.path not in {"", "/"}
            or url.query or url.fragment
        ):
            raise ValueError("Use a loopback HTTP origin for Ollama")
        return value.rstrip("/")

    @field_validator("frontend_origin")
    @classmethod
    def exact_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"} or not url.hostname
            or url.username or url.password or url.path or url.query or url.fragment
            or "*" in value
        ):
            raise ValueError("Use one exact HTTP(S) origin without a trailing slash")
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
