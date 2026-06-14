"""Tabulate the untracked files that are about to be put at risk."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Files at or below this size are usually noise (lockfiles, empty markers).
# Larger ones are the substantive work worth flagging in the table.
SUBSTANTIVE_BYTES = 1024


@dataclass
class FileEntry:
    rel: str
    size: int
    mtime: float

    @property
    def substantive(self) -> bool:
        return self.size > SUBSTANTIVE_BYTES


def inventory(root: str, rels: list[str]) -> list[FileEntry]:
    """Build a sorted inventory of ``rels`` (repo-relative) under ``root``.

    Paths that have already vanished are skipped (size/mtime unreadable).
    """
    entries: list[FileEntry] = []
    for rel in rels:
        abs_path = os.path.join(root, rel)
        try:
            st = os.stat(abs_path)
        except OSError:
            continue
        entries.append(FileEntry(rel=rel, size=st.st_size, mtime=st.st_mtime))
    entries.sort(key=lambda e: e.rel)
    return entries


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{size} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size} B"


def format_table(entries: list[FileEntry]) -> str:
    """Render an aligned table; substantive files (> 1 KB) get a ``*`` flag."""
    if not entries:
        return "  (no untracked files)"
    width = max(len(e.rel) for e in entries)
    width = min(max(width, 4), 80)
    lines = []
    for e in entries:
        flag = "*" if e.substantive else " "
        lines.append(f"  {flag} {e.rel:<{width}}  {_human(e.size):>9}")
    flagged = sum(1 for e in entries if e.substantive)
    total = sum(e.size for e in entries)
    lines.append(
        f"  -- {len(entries)} untracked file(s), {flagged} substantive (*), "
        f"{_human(total)} total"
    )
    return "\n".join(lines)
