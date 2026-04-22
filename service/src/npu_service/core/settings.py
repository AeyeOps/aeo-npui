"""Shared settings for the operator console."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Operator console settings."""

    model_config = SettingsConfigDict(
        env_prefix="NPU_CONSOLE_",
        case_sensitive=False,
    )

    windows_root: str = Field(default="C:\\dev\\npu")
    wsl_root: Path = Field(default=Path("/mnt/c/dev/npu"))
    dashboard_width_guard: int = Field(default=2)
    dashboard_capture_metrics: bool = Field(default=True)
    dashboard_ui_log_override: Path | None = Field(default=None)
    chat_startup_artifact_override: Path | None = Field(default=None)

    @property
    def scripts_dir(self) -> Path:
        return self.wsl_root / "scripts"

    @property
    def artifacts_dir(self) -> Path:
        return self.wsl_root / "artifacts"

    @property
    def event_log(self) -> Path:
        return self.scripts_dir / "npu-events.jsonl"

    @property
    def dashboard_ui_log(self) -> Path:
        return self.dashboard_ui_log_override or (
            self.artifacts_dir / "chat" / "dashboard-ui-latest.jsonl"
        )

    @property
    def chat_startup_artifact(self) -> Path:
        return self.chat_startup_artifact_override or (
            self.artifacts_dir / "chat" / "startup-last.txt"
        )

    @property
    def e2e_artifacts_dir(self) -> Path:
        return self.artifacts_dir / "e2e"


def load_settings() -> Settings:
    """Load operator settings."""

    return Settings()
