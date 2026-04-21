"""Git context reader — reads commit hash and branch for run metadata tagging."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitInfo:
    commit: str | None = None
    branch: str | None = None


def _run_git(cmd: list[str], cwd: Path | None) -> str | None:
    """Run a git command and return stdout stripped, or None on any failure."""
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def git_info(cwd: Path | None = None) -> GitInfo:
    """Return GitInfo for the git repo at *cwd* (defaults to process cwd).

    - Not a repo → GitInfo() with both fields None
    - Detached HEAD → commit present, branch None
    - Git not installed or timeout → GitInfo() with both fields None
    """
    commit = _run_git(["git", "rev-parse", "HEAD"], cwd)
    branch = _run_git(["git", "symbolic-ref", "--short", "HEAD"], cwd)
    return GitInfo(commit=commit, branch=branch)
