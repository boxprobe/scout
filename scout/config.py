"""Load app.json project configuration from delivery repo root."""

import json
from dataclasses import dataclass
from pathlib import Path

from scout.matcher.noise import DiffIgnoreConfig, load_diff_ignore


@dataclass(frozen=True)
class AppConfig:
    name: str
    web_base_url: str
    api_base_url: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 900


def load_app_config(repo_root: Path) -> AppConfig:
    """Load app.json from repo root directory.

    Raises FileNotFoundError if app.json does not exist.
    """
    app_json = repo_root / "app.json"
    if not app_json.exists():
        raise FileNotFoundError(f"app.json not found in {repo_root}")

    data = json.loads(app_json.read_text(encoding="utf-8"))

    return AppConfig(
        name=data["name"],
        web_base_url=data["web_base_url"],
        api_base_url=data.get("api_base_url"),
        viewport_width=data.get("viewport_width", 1280),
        viewport_height=data.get("viewport_height", 900),
    )


def load_diff_ignore_config(repo_root: Path) -> DiffIgnoreConfig:
    """Load diff_ignore.json from repo root. Returns empty config if missing."""
    path = repo_root / "diff_ignore.json"
    if not path.exists():
        return DiffIgnoreConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    return load_diff_ignore(data)


def override_urls(config: AppConfig, base_url: str | None, api_url: str | None) -> AppConfig:
    """Return a new AppConfig with URL overrides applied."""
    if not base_url and not api_url:
        return config
    return AppConfig(
        name=config.name,
        web_base_url=base_url or config.web_base_url,
        api_base_url=api_url or config.api_base_url,
        viewport_width=config.viewport_width,
        viewport_height=config.viewport_height,
    )
