"""Configuration loading.

Two sources, kept separate on purpose:
  * `config.yaml`  — non-secret tuning (weights, thresholds, endpoints). Versioned.
  * `.env`         — secrets (API keys). Never committed.

`load_config()` returns the parsed YAML as a plain dict (cached). `Settings`
reads API keys from the environment with a `DYOR_` prefix.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    """Locate the project root holding config.yaml, data/, and .cache/.

    Works for both an editable/source checkout (this file at <root>/dyor/config.py)
    and a non-editable `pip install .` (code copied into site-packages, while the
    data/config live in the run directory). Resolution order:
      1. $DYOR_HOME if set — explicit override for production/containers.
      2. the package parent, if it actually contains config.yaml (source layout).
      3. the current working directory, if it contains config.yaml (installed
         layout — pm2/systemd run with cwd set to the project dir).
      4. the package parent as a last resort (preserves the original behaviour).
    """
    env_home = os.environ.get("DYOR_HOME")
    if env_home:
        return Path(env_home).resolve()
    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / "config.yaml").is_file():
        return pkg_parent
    cwd = Path.cwd()
    if (cwd / "config.yaml").is_file():
        return cwd
    return pkg_parent


PROJECT_ROOT = _resolve_project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class Settings(BaseSettings):
    """Secrets + runtime overrides, read from environment / `.env`.

    All keys are optional — the free core runs with none of them (a GitHub
    token is merely recommended for higher rate limits).
    """

    model_config = SettingsConfigDict(
        env_prefix="DYOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: str | None = None
    coingecko_api_key: str | None = None
    santiment_api_key: str | None = None
    defillama_api_key: str | None = None  # Pro — unlocks emissions/unlocks endpoints
    alert_webhook: str | None = None      # Slack/Discord-compatible URL for `dyor refresh`

    # Stage 2 paid add-ons
    tokenterminal_api_key: str | None = None
    coinglass_api_key: str | None = None
    cryptorank_api_key: str | None = None
    glassnode_api_key: str | None = None
    nansen_api_key: str | None = None
    messari_api_key: str | None = None


@functools.lru_cache(maxsize=4)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Parse and cache `config.yaml`."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
