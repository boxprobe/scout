"""Load app.json project configuration from delivery repo root."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    name: str
    web_base_url: str
    api_base_url: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 900
    app_version: str | None = None


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
        app_version=str(data["app_version"]) if data.get("app_version") is not None else None,
    )
