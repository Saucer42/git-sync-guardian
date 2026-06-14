import os

import pytest

from gsg import gitio
from gsg.snapshot import (
    SnapshotError,
    create_snapshot,
    restore_all,
    restore_missing,
)
from tests.conftest import make_untracked


def test_create_snapshot_counts_and_bytes(tmp_repo, snap_root):
    make_untracked(tmp_repo, "a.txt", "hello\n")
    make_untracked(tmp_repo, "sub/b.txt", "world!!\n")
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    snap = create_snapshot(str(tmp_repo), rels, tmp_root=snap_root)
    assert snap.count == 2
    assert snap.total_bytes > 0
    assert os.path.exists(os.path.join(snap.path, "a.txt"))
    assert os.path.exists(os.path.join(snap.path, "sub", "b.txt"))


def test_snapshot_preserves_mtime(tmp_repo, snap_root):
    make_untracked(tmp_repo, "a.txt")
    src = os.path.join(str(tmp_repo), "a.txt")
    os.utime(src, (100000, 100000))
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    snap = create_snapshot(str(tmp_repo), rels, tmp_root=snap_root)
    assert os.stat(os.path.join(snap.path, "a.txt")).st_mtime == 100000


def test_snapshot_aborts_on_unwritable_tmp(tmp_repo, tmp_path):
    make_untracked(tmp_repo, "a.txt")
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    # A regular file as the tmp root makes the snapshot mkdir fail for any user.
    bad = tmp_path / "not-a-dir"
    bad.write_text("x")
    with pytest.raises(SnapshotError):
        create_snapshot(str(tmp_repo), rels, tmp_root=str(bad))


def test_restore_missing_brings_back_deleted_file(tmp_repo, snap_root):
    make_untracked(tmp_repo, "a.txt", "keep me\n")
    make_untracked(tmp_repo, "b.txt", "also\n")
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    snap = create_snapshot(str(tmp_repo), rels, tmp_root=snap_root)

    os.remove(os.path.join(str(tmp_repo), "a.txt"))  # simulate destruction
    result = restore_missing(str(tmp_repo), rels, snap)

    assert result.restored == ["a.txt"]
    assert "b.txt" in result.present
    assert os.path.exists(os.path.join(str(tmp_repo), "a.txt"))
    assert (
        open(os.path.join(str(tmp_repo), "a.txt")).read() == "keep me\n"
    )


def test_restore_missing_does_not_flag_committed_file(tmp_repo, snap_root):
    # A file that becomes tracked (committed) still exists on disk -> present.
    make_untracked(tmp_repo, "a.txt")
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    snap = create_snapshot(str(tmp_repo), rels, tmp_root=snap_root)
    gitio.run_git(["add", "a.txt"], cwd=str(tmp_repo))
    gitio.run_git(["commit", "-m", "now tracked"], cwd=str(tmp_repo))
    result = restore_missing(str(tmp_repo), rels, snap)
    assert result.missing_count == 0
    assert result.present == ["a.txt"]


def test_restore_all_manual(tmp_repo, snap_root):
    make_untracked(tmp_repo, "x/y.txt", "content\n")
    rels = gitio.untracked_files(cwd=str(tmp_repo))
    snap = create_snapshot(str(tmp_repo), rels, tmp_root=snap_root)
    os.remove(os.path.join(str(tmp_repo), "x", "y.txt"))
    restored = restore_all(snap.path, str(tmp_repo))
    assert restored == [os.path.join("x", "y.txt")]
    assert os.path.exists(os.path.join(str(tmp_repo), "x", "y.txt"))
