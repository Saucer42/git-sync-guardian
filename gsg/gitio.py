"""Thin subprocess wrappers around ``git``.

Everything that shells out to git lives here so the rest of the package stays
testable and the git surface stays auditable.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    """A git invocation exited non-zero (when failure was not expected)."""

    def __init__(self, args, returncode, stderr):
        self.args = args
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}"
        )


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_git(args, cwd=None, check=True, capture=True) -> GitResult:
    """Run ``git <args>`` and return a :class:`GitResult`.

    ``args`` is a list of arguments *without* the leading ``git``. When
    ``capture`` is False the child inherits stdout/stderr (used when we hand the
    terminal to the wrapped command).
    """
    cmd = ["git", *args]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
    )
    result = GitResult(
        returncode=proc.returncode,
        stdout=proc.stdout or "" if capture else "",
        stderr=proc.stderr or "" if capture else "",
    )
    if check and not result.ok:
        raise GitError(args, result.returncode, result.stderr)
    return result


def is_git_repo(cwd=None) -> bool:
    res = run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd, check=False)
    return res.ok and res.stdout.strip() == "true"


def repo_root(cwd=None) -> str:
    """Absolute path of the working-tree root (``git rev-parse --show-toplevel``)."""
    return run_git(["rev-parse", "--show-toplevel"], cwd=cwd).stdout.strip()


def untracked_files(cwd=None) -> list[str]:
    """The at-risk set: untracked, not-ignored files, as repo-relative paths."""
    res = run_git(
        ["ls-files", "--others", "--exclude-standard", "-z"],
        cwd=cwd,
    )
    return [p for p in res.stdout.split("\0") if p]


def status_short(cwd=None) -> str:
    return run_git(["status", "-sb"], cwd=cwd).stdout


def current_branch(cwd=None) -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).stdout.strip()


def has_staged_or_unstaged_changes(cwd=None) -> bool:
    res = run_git(["status", "--porcelain"], cwd=cwd)
    for line in res.stdout.splitlines():
        # Anything other than untracked ("??") counts as a tracked change.
        if line and not line.startswith("??"):
            return True
    return False


def fetch(remote="origin", cwd=None, prune=True) -> GitResult:
    args = ["fetch", remote]
    if prune:
        args.append("--prune")
    return run_git(args, cwd=cwd, check=False, capture=False)


def unmerged_remote_branches(base, remote="origin", cwd=None) -> list[str]:
    """Remote-tracking branches not yet merged into ``base``.

    Excludes the base branch itself and any symbolic ``HEAD`` ref.
    """
    res = run_git(
        ["branch", "-r", "--no-merged", base, "--format=%(refname:short)"],
        cwd=cwd,
        check=False,
    )
    if not res.ok:
        return []
    out = []
    for line in res.stdout.splitlines():
        name = line.strip()
        if not name or "->" in name:
            continue
        if name in (f"{remote}/{base}", base):
            continue
        out.append(name)
    return out


def branch_summary(ref, base, cwd=None) -> dict:
    """Commit count / author / date / subject / file-count for ``ref`` vs ``base``."""
    range_spec = f"{base}..{ref}"
    count = run_git(
        ["rev-list", "--count", range_spec], cwd=cwd, check=False
    ).stdout.strip()
    tip = run_git(
        ["log", "-1", "--format=%an|%ad|%s", "--date=short", ref],
        cwd=cwd,
        check=False,
    ).stdout.strip()
    author, date, subject = "?", "?", "?"
    if "|" in tip:
        parts = tip.split("|", 2)
        if len(parts) == 3:
            author, date, subject = parts
    files = run_git(
        ["diff", "--name-only", range_spec], cwd=cwd, check=False
    ).stdout.splitlines()
    return {
        "ref": ref,
        "commits": count or "0",
        "files": len([f for f in files if f]),
        "author": author,
        "date": date,
        "subject": subject,
    }


def commit_all(message, cwd=None) -> GitResult:
    run_git(["add", "-A"], cwd=cwd)
    return run_git(["commit", "-m", message], cwd=cwd, check=False, capture=False)


def merge(ref, no_ff=True, cwd=None) -> GitResult:
    args = ["merge"]
    if no_ff:
        args.append("--no-ff")
    args.append(ref)
    return run_git(args, cwd=cwd, check=False, capture=False)


def pull(remote="origin", branch=None, rebase=False, cwd=None) -> GitResult:
    args = ["pull", "--rebase" if rebase else "--no-rebase", remote]
    if branch:
        args.append(branch)
    return run_git(args, cwd=cwd, check=False, capture=False)


def push(remote="origin", branch=None, cwd=None) -> GitResult:
    args = ["push", remote]
    if branch:
        args.append(branch)
    return run_git(args, cwd=cwd, check=False, capture=False)
