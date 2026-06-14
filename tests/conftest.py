"""Shared fixtures: a throwaway git repo per test."""

from __future__ import annotations

import os
import subprocess

import pytest


def _git(args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def tmp_repo(tmp_path):
    """A fresh git repo with one tracked commit. Returns its path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    # Throwaway repos must not depend on the host's commit-signing setup.
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "tracked.txt").write_text("tracked content\n")
    _git(["add", "tracked.txt"], repo)
    _git(["commit", "-m", "initial"], repo)
    return repo


@pytest.fixture
def snap_root(tmp_path):
    """A writable directory to use as the snapshot tmp root."""
    d = tmp_path / "snaps"
    d.mkdir()
    return str(d)


def make_untracked(repo, rel, content="data\n"):
    path = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(
        rel
    ) else None
    with open(path, "w") as fh:
        fh.write(content)
    return rel
