"""Tests for scout/config.py — load app.json project configuration."""

import json
from pathlib import Path

import pytest

from scout.config import AppConfig, load_app_config


def test_load_app_config_full(tmp_path: Path) -> None:
    """Full app.json with all fields loads correctly."""
    app_json = tmp_path / "app.json"
    app_json.write_text(json.dumps({
        "name": "Admin UI",
        "web_base_url": "http://localhost:9000/app",
        "api_base_url": "http://localhost:9000/admin",
        "viewport_width": 1440,
        "viewport_height": 900,
    }))
    config = load_app_config(tmp_path)
    assert config.name == "Admin UI"
    assert config.web_base_url == "http://localhost:9000/app"
    assert config.api_base_url == "http://localhost:9000/admin"
    assert config.viewport_width == 1440


def test_load_app_config_minimal(tmp_path: Path) -> None:
    """Minimal app.json with only required fields."""
    app_json = tmp_path / "app.json"
    app_json.write_text(json.dumps({"name": "my-app", "web_base_url": "http://localhost"}))
    config = load_app_config(tmp_path)
    assert config.name == "my-app"
    assert config.app_version is None


def test_load_app_config_with_version(tmp_path: Path) -> None:
    """app.json with optional app_version field."""
    app_json = tmp_path / "app.json"
    app_json.write_text(json.dumps({
        "name": "my-app",
        "web_base_url": "http://localhost",
        "app_version": "2.3.1",
    }))
    config = load_app_config(tmp_path)
    assert config.app_version == "2.3.1"


def test_load_app_config_no_file(tmp_path: Path) -> None:
    """Missing app.json raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_app_config(tmp_path)


def test_app_config_is_frozen(tmp_path: Path) -> None:
    """AppConfig is immutable."""
    app_json = tmp_path / "app.json"
    app_json.write_text(json.dumps({"name": "x", "web_base_url": "http://x"}))
    config = load_app_config(tmp_path)
    with pytest.raises(Exception):  # noqa: B017
        config.name = "other"  # type: ignore[misc]
