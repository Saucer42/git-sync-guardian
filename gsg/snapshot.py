"""Create, verify, and restore from snapshots of untracked files.

Design principle #1: the snapshot is sacred. If it cannot be created or verified
(disk full, permission denied, file-count mismatch) we abort - the dangerous
operation must never run without a verified backup.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be created or verified. Callers must abort."""


@dataclass
class Snapshot:
    path: str
    files: list[str]  # repo-relative paths captured
    total_bytes: int

    @property
    def count(self) -> int:
        return len(self.files)


@dataclass
class RestoreResult:
    restored: list[str] = field(default_factory=list)
    unrecoverable: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)

    @property
    def missing_count(self) -> int:
        return len(self.restored) + len(self.unrecoverable)


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def create_snapshot(root: str, rels: list[str], tmp_root: str | None = None) -> Snapshot:
    """Mirror every path in ``rels`` into a fresh ``gsg-<stamp>`` snapshot dir.

    Raises :class:`SnapshotError` on any copy failure or a final count mismatch.
    """
    base = tmp_root or tempfile.gettempdir()
    stamp = _timestamp()
    snap_path = os.path.join(base, f"gsg-{stamp}")
    # Avoid colliding with a same-second snapshot.
    suffix = 1
    while os.path.exists(snap_path):
        snap_path = os.path.join(base, f"gsg-{stamp}-{suffix}")
        suffix += 1

    try:
        os.makedirs(snap_path, exist_ok=False)
    except OSError as exc:
        raise SnapshotError(f"cannot create snapshot dir {snap_path}: {exc}") from exc

    captured: list[str] = []
    total = 0
    for rel in rels:
        src = os.path.join(root, rel)
        dst = os.path.join(snap_path, rel)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)  # copy2 preserves mtime
            total += os.path.getsize(dst)
            captured.append(rel)
        except OSError as exc:
            raise SnapshotError(
                f"failed to snapshot {rel!r}: {exc} - aborting before any "
                f"destructive operation"
            ) from exc

    # Verify by file count: what is on disk under the snapshot must match what
    # we intended to capture.
    on_disk = _count_files(snap_path)
    if on_disk != len(rels):
        raise SnapshotError(
            f"snapshot verification failed: expected {len(rels)} file(s), "
            f"found {on_disk} under {snap_path}"
        )

    return Snapshot(path=snap_path, files=captured, total_bytes=total)


def _count_files(root: str) -> int:
    n = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        n += len(filenames)
    return n


def restore_missing(root: str, rels: list[str], snapshot: Snapshot) -> RestoreResult:
    """Post-flight: any inventoried path absent *from disk* is restored.

    Per design principle #3 we test ``os.path.exists`` directly, not git's
    untracked list - a sync may legitimately have *committed* a previously
    untracked file (now tracked, still on disk -> not missing).
    """
    result = RestoreResult()
    for rel in rels:
        if os.path.exists(os.path.join(root, rel)):
            result.present.append(rel)
            continue
        # Genuinely gone from disk - try to bring it back.
        src = os.path.join(snapshot.path, rel)
        if not os.path.exists(src):
            result.unrecoverable.append(rel)
            continue
        dst = os.path.join(root, rel)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            result.restored.append(rel)
        except OSError:
            result.unrecoverable.append(rel)
    return result


def restore_all(snapshot_path: str, root: str) -> list[str]:
    """Manual restore: copy every file under ``snapshot_path`` back into ``root``."""
    if not os.path.isdir(snapshot_path):
        raise SnapshotError(f"not a snapshot directory: {snapshot_path}")
    restored: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(snapshot_path):
        for name in filenames:
            src = os.path.join(dirpath, name)
            rel = os.path.relpath(src, snapshot_path)
            dst = os.path.join(root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            restored.append(rel)
    restored.sort()
    return restored
