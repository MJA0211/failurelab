import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FAILURELAB_",
        env_file=os.environ.get("FAILURELAB_ENV_FILE", ".env") or None,
        extra="ignore",
        env_ignore_empty=True,
    )

    data_dir: Path = Path("var")
    host: str = "127.0.0.1"
    port: int = 8787
    database_url: str = ""
    model_mode: Literal["baseline", "chat"] = "baseline"
    model_base_url: str = "https://router.huggingface.co/v1"
    model_name: str = "Qwen/Qwen3-235B-A22B-Instruct-2507:novita"
    model_api_key: SecretStr = SecretStr("")
    model_vision: bool = False
    retrieval_mode: Literal["lexical", "hybrid"] = "lexical"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    github_token: SecretStr = SecretStr("")
    webhook_secret: SecretStr = SecretStr("")
    github_repositories: str = ""
    api_token: SecretStr = SecretStr("")
    seed_demo: bool = True
    worker_enabled: bool = True
    runner_url: str = ""
    runner_token: SecretStr = SecretStr("")
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)
    max_model_calls: int = Field(default=3, ge=1, le=5)
    max_experiments: int = Field(default=2, ge=1, le=3)
    max_artifact_bytes: int = Field(default=8_000_000, ge=1024, le=50_000_000)
    lease_seconds: int = Field(default=600, ge=60)

    @model_validator(mode="after")
    def check_configuration(self):
        if (
            self.host not in {"localhost", "127.0.0.1", "::1"}
            and not self.api_token.get_secret_value()
        ):
            raise ValueError("An API token is required when binding outside loopback")
        if self.model_mode == "chat" and not self.model_api_key.get_secret_value():
            raise ValueError(
                "Chat mode requires MODEL_API_KEY; baseline is a separate explicit mode"
            )
        return self

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir.resolve().as_posix()}/failurelab.db"

    @property
    def allowed_repositories(self) -> set[str]:
        return {r.strip().lower() for r in self.github_repositories.split(",") if r.strip()}

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "artifacts").mkdir(exist_ok=True)
