"""Configuration loader for AutoCustomizeResume.

Loads config.yaml and .env, provides typed access to all settings.
"""

from __future__ import annotations

import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class UserConfig:
    first_name: str
    last_name: str
    phone: str
    email: str
    linkedin: str
    website: str
    degree: str
    university: str


@dataclass(frozen=True)
class NamingConfig:
    output_resume: str
    output_cover: str
    history_resume: str
    history_cover: str


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key_env: str

    @property
    def api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(
                f"API key not found. Set the '{self.api_key_env}' environment variable "
                f"(or add it to your .env file)."
            )
        return key


@dataclass(frozen=True)
class CoverLetterConfig:
    enabled: bool
    template: str
    style: str
    signature_path: str


@dataclass(frozen=True)
class PathsConfig:
    master_resume: str
    jd_file: str
    output_dir: str
    history_dir: str


@dataclass(frozen=True)
class WatcherConfig:
    debounce_seconds: float


@dataclass(frozen=True)
class Config:
    user: UserConfig
    naming: NamingConfig
    llm: LLMConfig
    cover_letter: CoverLetterConfig
    paths: PathsConfig
    watcher: WatcherConfig


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


_MISSING = object()


def _get(data: dict, key: str, section: str, default: Any = _MISSING) -> Any:
    """Get a value from a dict with a clear error if missing and no default.

    If the key is absent or its value is None (YAML null), the default is used.
    If no default was provided, raises ConfigError.
    """
    if not isinstance(data, dict):
        raise ConfigError(f"Expected '{section}' to be a YAML mapping, got {type(data).__name__}")
    val = data.get(key, _MISSING)
    if val is _MISSING or val is None:
        if default is _MISSING:
            raise ConfigError(f"Missing required config: {section}.{key}")
        return default
    return val


def _get_str(data: dict, key: str, section: str, default: Any = _MISSING) -> str:
    """Get a string value, coercing non-string scalars to str."""
    val = _get(data, key, section, default)
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    raise ConfigError(
        f"{section}.{key} must be a string, got {type(val).__name__}: {val!r}"
    )


def _get_bool(data: dict, key: str, section: str, default: Any = _MISSING) -> bool:
    """Get a boolean value, coercing common string literals."""
    val = _get(data, key, section, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        lower = val.strip().lower()
        if lower in ("true", "yes", "1", "on"):
            return True
        if lower in ("false", "no", "0", "off"):
            return False
    raise ConfigError(
        f"{section}.{key} must be a boolean, got {type(val).__name__}: {val!r}"
    )


def _get_int(data: dict, key: str, section: str, default: Any = _MISSING) -> int:
    """Get an integer value with a clear error on failure."""
    val = _get(data, key, section, default)
    try:
        return int(val)
    except (ValueError, TypeError):
        raise ConfigError(
            f"{section}.{key} must be an integer, got {type(val).__name__}: {val!r}"
        )


def _get_float(data: dict, key: str, section: str, default: Any = _MISSING) -> float:
    """Get a float value with a clear error on failure."""
    val = _get(data, key, section, default)
    try:
        return float(val)
    except (ValueError, TypeError):
        raise ConfigError(
            f"{section}.{key} must be a number, got {type(val).__name__}: {val!r}"
        )


def load_config(config_path: str = "config.yaml") -> Config:
    """Load and validate the configuration file.

    Also loads .env if present, and checks that tectonic is installed.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        A validated Config object.

    Raises:
        ConfigError: If the config file is missing, invalid, or incomplete.
    """
    # Load .env if present
    dotenv_path = Path(config_path).parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)

    # Load YAML
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}\n"
            f"Copy config.example.yaml to config.yaml and fill in your details."
        )

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

    # Parse sections
    user_raw = _get(raw, "user", "root")
    user = UserConfig(
        first_name=_get_str(user_raw, "first_name", "user"),
        last_name=_get_str(user_raw, "last_name", "user"),
        phone=_get_str(user_raw, "phone", "user", default=""),
        email=_get_str(user_raw, "email", "user", default=""),
        linkedin=_get_str(user_raw, "linkedin", "user", default=""),
        website=_get_str(user_raw, "website", "user", default=""),
        degree=_get_str(user_raw, "degree", "user", default=""),
        university=_get_str(user_raw, "university", "user", default=""),
    )

    if not user.first_name.strip():
        raise ConfigError("user.first_name cannot be empty — required for file naming")
    if not user.last_name.strip():
        raise ConfigError("user.last_name cannot be empty — required for file naming")

    naming_raw = _get(raw, "naming", "root")
    naming = NamingConfig(
        output_resume=_get_str(naming_raw, "output_resume", "naming"),
        output_cover=_get_str(naming_raw, "output_cover", "naming"),
        history_resume=_get_str(naming_raw, "history_resume", "naming"),
        history_cover=_get_str(naming_raw, "history_cover", "naming"),
    )

    llm_raw = _get(raw, "llm", "root")
    llm = LLMConfig(
        base_url=_get_str(llm_raw, "base_url", "llm"),
        model=_get_str(llm_raw, "model", "llm"),
        api_key_env=_get_str(llm_raw, "api_key_env", "llm"),
    )

    cl_raw = _get(raw, "cover_letter", "root")
    cover_letter = CoverLetterConfig(
        enabled=_get_bool(cl_raw, "enabled", "cover_letter"),
        template=_get_str(cl_raw, "template", "cover_letter"),
        style=_get_str(cl_raw, "style", "cover_letter", default=""),
        signature_path=_get_str(cl_raw, "signature_path", "cover_letter", default=""),
    )

    paths_raw = _get(raw, "paths", "root")
    paths = PathsConfig(
        master_resume=_get_str(paths_raw, "master_resume", "paths"),
        jd_file=_get_str(paths_raw, "jd_file", "paths"),
        output_dir=_get_str(paths_raw, "output_dir", "paths"),
        history_dir=_get_str(paths_raw, "history_dir", "paths"),
    )

    watcher_raw = _get(raw, "watcher", "root")
    debounce_seconds = _get_float(watcher_raw, "debounce_seconds", "watcher")
    if not math.isfinite(debounce_seconds) or debounce_seconds <= 0:
        raise ConfigError(
            "watcher.debounce_seconds must be a positive finite number"
        )
    watcher = WatcherConfig(
        debounce_seconds=debounce_seconds,
    )

    config = Config(
        user=user,
        naming=naming,
        llm=llm,
        cover_letter=cover_letter,
        paths=paths,
        watcher=watcher,
    )

    # Check tectonic is available
    _check_tectonic()

    return config


def _check_tectonic():
    """Verify tectonic is installed and accessible."""
    if shutil.which("tectonic") is None:
        raise ConfigError(
            "tectonic is not installed or not on PATH.\n"
            "Install it:\n"
            "  macOS:  brew install tectonic\n"
            "  Linux:  https://tectonic-typesetting.github.io/en-US/install.html\n"
            "  cargo:  cargo install tectonic"
        )
