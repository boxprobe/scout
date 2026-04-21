"""Tests for scout/config.py — load scout.yml project configuration."""

from pathlib import Path

import pytest

from scout.config import ScoutConfig, load_config


def test_load_config_from_yaml(tmp_path: Path) -> None:
    """Full config with app slug and explicit data_dir loads correctly."""
    data_dir = tmp_path / "scout-data"
    config_file = tmp_path / "scout.yml"
    config_file.write_text(
        f"app: my-app\n"
        f"app_version: '1.2.3'\n"
        f"data_dir: {data_dir}\n"
    )

    config = load_config(config_file)

    assert config.app == "my-app"
    assert config.app_version == "1.2.3"
    assert config.data_dir == data_dir


def test_load_config_defaults(tmp_path: Path) -> None:
    """Config file without data_dir gets default .scout directory."""
    config_file = tmp_path / "scout.yml"
    config_file.write_text("app: my-app\n")

    config = load_config(config_file)

    assert config.app == "my-app"
    assert config.data_dir == Path(".scout")


def test_load_config_no_file(tmp_path: Path) -> None:
    """Missing scout.yml returns all defaults; app is None."""
    config_file = tmp_path / "scout.yml"

    config = load_config(config_file)

    assert config.app is None
    assert config.app_version is None
    assert config.data_dir == Path(".scout")


def test_load_config_empty_file(tmp_path: Path) -> None:
    """Empty scout.yml returns all defaults."""
    config_file = tmp_path / "scout.yml"
    config_file.write_text("")

    config = load_config(config_file)

    assert config.app is None
    assert config.app_version is None
    assert config.data_dir == Path(".scout")


def test_data_dir_expands_tilde(tmp_path: Path) -> None:
    """Tilde in data_dir is expanded to the user home directory."""
    config_file = tmp_path / "scout.yml"
    config_file.write_text("app: my-app\ndata_dir: ~/scout-data\n")

    config = load_config(config_file)

    assert not str(config.data_dir).startswith("~")
    assert config.data_dir == Path("~/scout-data").expanduser()


def test_scout_config_is_frozen() -> None:
    """ScoutConfig is a frozen dataclass (immutable)."""
    config = ScoutConfig(app="test-app")
    with pytest.raises(Exception):  # noqa: B017
        config.app = "other"  # type: ignore[misc]
