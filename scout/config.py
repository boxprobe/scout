"""Load scout.yml project configuration."""

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML


@dataclass(frozen=True)
class ScoutConfig:
    app: str | None = None
    app_version: str | None = None
    data_dir: Path = field(default_factory=lambda: Path(".scout"))


def load_config(path: Path) -> ScoutConfig:
    """Load a scout.yml config file and return a ScoutConfig.

    Missing file or empty file returns all defaults (app=None).
    Tilde in data_dir is expanded.
    """
    if not path.exists():
        return ScoutConfig()

    yaml = YAML()
    data = yaml.load(path)

    if not data:
        return ScoutConfig()

    app = data.get("app") or None
    app_version = str(data["app_version"]) if data.get("app_version") is not None else None

    raw_data_dir = data.get("data_dir")
    if raw_data_dir is not None:
        data_dir = Path(str(raw_data_dir)).expanduser()
    else:
        data_dir = Path(".scout")

    return ScoutConfig(app=app, app_version=app_version, data_dir=data_dir)
