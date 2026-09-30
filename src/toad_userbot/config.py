"""Configuration.

Two sources, each with a single responsibility:

* :class:`Settings` — process environment (``.env``): secrets and filesystem paths.
* :class:`AppConfig` — ``config.yaml``: behaviour of the userbot. Contains no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from toad_userbot.recorder.policy import DEFAULT_COMMAND_WORDS

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]


class RuntimeSettings(BaseSettings):
    """Paths and logging. Needs no secrets, so the container healthcheck can use it alone."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path("data")
    config_path: Path = Path("config.yaml")
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"
    git_commit: str = "unknown"

    @property
    def paths(self) -> Paths:
        return Paths(self.data_dir)


class Settings(RuntimeSettings):
    """Full process settings, including Telegram API credentials."""

    tg_api_id: int = Field(gt=0)
    tg_api_hash: SecretStr


@dataclass(frozen=True, slots=True)
class Paths:
    """Every file the userbot writes lives under ``data_dir``."""

    data_dir: Path

    @property
    def session(self) -> Path:
        return self.data_dir / "userbot.session"

    @property
    def database(self) -> Path:
        return self.data_dir / "userbot.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "userbot.log"

    @property
    def heartbeat(self) -> Path:
        return self.data_dir / "heartbeat"

    def ensure(self) -> None:
        """Create the data directories if they do not exist."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ControlConfig(_Section):
    prefix: str = Field(default=".", min_length=1, max_length=3)


class RecorderConfig(_Section):
    enabled: bool = True
    command_words: tuple[str, ...] = DEFAULT_COMMAND_WORDS

    @field_validator("command_words")
    @classmethod
    def _normalize_words(cls, words: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(word.casefold() for word in words if word.strip())


class LogFileConfig(_Section):
    max_bytes: int = Field(default=5_000_000, gt=0)
    backups: int = Field(default=3, ge=0)


class AppConfig(_Section):
    """Contents of ``config.yaml``."""

    chat_id: int | None = None
    bot_username: str = "toadbot"
    control: ControlConfig = ControlConfig()
    recorder: RecorderConfig = RecorderConfig()
    log_file: LogFileConfig = LogFileConfig()

    @field_validator("bot_username")
    @classmethod
    def _normalize_username(cls, username: str) -> str:
        normalized = username.strip().removeprefix("@").casefold()
        if not normalized:
            msg = "bot_username must not be empty"
            raise ValueError(msg)
        return normalized


class ConfigError(Exception):
    """Raised when ``config.yaml`` cannot be read or validated."""


def load_app_config(path: Path) -> AppConfig:
    """Load ``config.yaml``. A missing file yields the defaults."""
    if not path.exists():
        return AppConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        msg = f"cannot read {path}: {exc}"
        raise ConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"{path} must contain a mapping at the top level"
        raise ConfigError(msg)
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        msg = f"invalid {path}:\n{exc}"
        raise ConfigError(msg) from exc
