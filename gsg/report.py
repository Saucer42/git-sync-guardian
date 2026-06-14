"""End-of-run reporting. Loud on restore (design principle #4)."""

from __future__ import annotations

import sys

from .snapshot import RestoreResult, Snapshot

# Minimal ANSI; disabled when not a tty or NO_COLOR is set.
import os

_USE_COLOR = sys.stderr.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def info(msg: str) -> None:
    print(msg)


def warn(msg: str) -> None:
    print(_c("33", msg), file=sys.stderr)


def error(msg: str) -> None:
    print(_c("31", msg), file=sys.stderr)


def success(msg: str) -> None:
    print(_c("32", msg))


def snapshot_line(snap: Snapshot) -> str:
    kb = snap.total_bytes / 1024.0
    return f"Snapshot: {snap.path} ({snap.count} files, {kb:.1f} KB)"


def render_restore(result: RestoreResult, snap: Snapshot) -> int:
    """Print the post-flight verdict. Returns a process exit code.

    0 - all present.
    0 - some missing but fully auto-restored (loud warning, not a failure).
    2 - one or more files were unrecoverable (hard error, manual recovery).
    """
    total = len(result.present) + result.missing_count
    if result.missing_count == 0:
        success(f"All {total} untracked file(s) present after the operation.")
        return 0

    if result.restored:
        warn("")
        warn("=" * 70)
        warn(
            f"!! {len(result.restored)} of {total} untracked file(s) VANISHED "
            f"and were auto-restored from:"
        )
        warn(f"   {snap.path}")
        for rel in result.restored:
            warn(f"     restored: {rel}")
        warn(
            "This means the operation deleted untracked work. Investigate why - "
            "this is the failure mode gsg exists to catch."
        )
        warn("=" * 70)

    if result.unrecoverable:
        error("")
        error("=" * 70)
        error(
            f"!! {len(result.unrecoverable)} file(s) are MISSING from disk AND "
            f"from the snapshot - manual recovery required:"
        )
        for rel in result.unrecoverable:
            error(f"     LOST: {rel}")
        error("See RECOVERY.md or run `gsg recover-help`.")
        error("=" * 70)
        return 2

    return 0
