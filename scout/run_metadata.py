"""RunMetadata — frozen dataclass capturing full context for a single test run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from scout.config import ScoutConfig
from scout.git import GitInfo


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    timestamp: str
    scenario: str
    app: str | None = None
    app_version: str | None = None
    env: str | None = None
    commit: str | None = None
    branch: str | None = None
    scout_version: str = ""


def build_metadata(
    *,
    config: ScoutConfig,
    git: GitInfo,
    scenario: str,
    env: str | None = None,
) -> RunMetadata:
    """Assemble a RunMetadata from config, git context, and runtime args.

    scout_version is read from the installed package metadata; falls back to
    "dev" when the package is not installed (e.g. during development).
    """
    try:
        scout_version = version("scout")
    except PackageNotFoundError:
        scout_version = "dev"

    return RunMetadata(
        run_id=str(uuid.uuid4()),
        timestamp=datetime.now(tz=UTC).isoformat(),
        scenario=scenario,
        app=config.app,
        app_version=config.app_version,
        env=env,
        commit=git.commit,
        branch=git.branch,
        scout_version=scout_version,
    )
