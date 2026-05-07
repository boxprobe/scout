"""Tests for scout.run_metadata module."""

from scout.config import AppConfig
from scout.git import GitInfo
from scout.run_metadata import build_metadata


def _full_config() -> AppConfig:
    return AppConfig(name="medusa-admin", web_base_url="http://localhost")


def _full_git() -> GitInfo:
    return GitInfo(commit="abc123def456" * 3 + "abcd", branch="main")


def test_build_metadata_full_context() -> None:
    """All fields are populated when config and git info are complete."""
    config = _full_config()
    git = _full_git()

    meta = build_metadata(
        config=config, git=git, scenario="tests/login.py", env="staging",
        web_version="2.3.1", api_version="2.3.1",
        web_commit="abc123", api_commit="def456",
    )

    assert meta.scenario == "tests/login.py"
    assert meta.app == "medusa-admin"
    assert meta.web_version == "2.3.1"
    assert meta.api_version == "2.3.1"
    assert meta.web_commit == "abc123"
    assert meta.api_commit == "def456"
    assert meta.env == "staging"
    assert meta.scenario_commit is not None
    assert meta.run_id  # non-empty
    assert meta.timestamp  # non-empty
    assert isinstance(meta.scout_version, str)


def test_build_metadata_no_git() -> None:
    """commit and branch are None when GitInfo has no data."""
    config = _full_config()
    git = GitInfo()

    meta = build_metadata(config=config, git=git, scenario="smoke/basic.py")

    assert meta.web_commit is None
    assert meta.api_commit is None
    assert meta.scenario_commit is None
    assert meta.app == "medusa-admin"
    assert meta.scenario == "smoke/basic.py"


def test_build_metadata_no_version() -> None:
    """web_version and api_version are None when not specified."""
    config = AppConfig(name="medusa-admin", web_base_url="http://localhost")
    git = _full_git()

    meta = build_metadata(config=config, git=git, scenario="regression/api.py")

    assert meta.app == "medusa-admin"
    assert meta.web_version is None
    assert meta.api_version is None
    assert meta.web_commit is None
    assert meta.api_commit is None
    assert meta.scenario_commit == git.commit


def test_api_defaults_to_web() -> None:
    """api_version and api_commit fall back to web_* when not specified."""
    config = _full_config()
    git = _full_git()

    meta = build_metadata(
        config=config, git=git, scenario="s.py",
        web_version="2.14.0", web_commit="abc123",
    )

    assert meta.web_version == "2.14.0"
    assert meta.api_version == "2.14.0"
    assert meta.web_commit == "abc123"
    assert meta.api_commit == "abc123"


def test_run_id_is_unique() -> None:
    """Two successive calls produce different run_ids."""
    config = AppConfig(name="test-app", web_base_url="http://localhost")
    git = GitInfo()

    meta1 = build_metadata(config=config, git=git, scenario="s.py")
    meta2 = build_metadata(config=config, git=git, scenario="s.py")

    assert meta1.run_id != meta2.run_id


def test_run_metadata_is_frozen() -> None:
    """RunMetadata is immutable (frozen dataclass)."""
    import pytest

    config = AppConfig(name="test-app", web_base_url="http://localhost")
    git = GitInfo()
    meta = build_metadata(config=config, git=git, scenario="s.py")

    with pytest.raises((AttributeError, TypeError)):
        meta.run_id = "new-id"  # type: ignore[misc]


def test_timestamp_is_utc_iso8601() -> None:
    """timestamp is a valid ISO 8601 string ending with UTC offset."""
    from datetime import datetime

    config = AppConfig(name="test-app", web_base_url="http://localhost")
    git = GitInfo()
    meta = build_metadata(config=config, git=git, scenario="s.py")

    # Should parse without error
    dt = datetime.fromisoformat(meta.timestamp)
    # Should be UTC
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
