"""Tests for scout.git module."""

import os
import subprocess
from pathlib import Path

from scout.git import GitInfo, git_info

# Common env vars to avoid git config issues in tmp repos
_GIT_ENV = {
    **os.environ,
    "GIT_COMMITTER_NAME": "Test User",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_AUTHOR_NAME": "Test User",
    "GIT_AUTHOR_EMAIL": "test@example.com",
}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:  # type: ignore[type-arg]
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )


def _make_repo(path: Path) -> str:
    """Initialize a git repo in path, make one commit, return commit SHA."""
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test User"], path)

    (path / "README.md").write_text("hello")
    _git(["add", "."], path)
    _git(["commit", "-m", "initial commit"], path)

    result = _git(["rev-parse", "HEAD"], path)
    return result.stdout.strip()


def test_git_info_in_repo(tmp_path: Path) -> None:
    """In a valid git repo, returns 40-char commit hash and branch name."""
    sha = _make_repo(tmp_path)
    info = git_info(cwd=tmp_path)

    assert info.commit == sha
    assert len(info.commit) == 40  # type: ignore[arg-type]
    assert info.branch == "main"


def test_git_info_not_a_repo(tmp_path: Path) -> None:
    """In a directory without .git, both fields are None."""
    info = git_info(cwd=tmp_path)

    assert info == GitInfo()
    assert info.commit is None
    assert info.branch is None


def test_git_info_detached_head(tmp_path: Path) -> None:
    """In detached HEAD state, commit is present and branch is None."""
    sha = _make_repo(tmp_path)
    _git(["checkout", sha], tmp_path)

    info = git_info(cwd=tmp_path)

    assert info.commit == sha
    assert info.branch is None
