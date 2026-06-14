import os

from gsg import OVERRIDE_TOKEN
from gsg.guard import GuardOptions, guard
from tests.conftest import make_untracked


def test_guard_clean_survives_with_override(tmp_repo, snap_root):
    make_untracked(tmp_repo, "scratch.py", "hours of work\n")
    opts = GuardOptions(
        assume_yes=True, override=OVERRIDE_TOKEN, tmp_root=snap_root
    )
    rc = guard(["git", "clean", "-fd"], cwd=str(tmp_repo), options=opts)
    # File was deleted by clean then auto-restored -> survives.
    assert os.path.exists(os.path.join(str(tmp_repo), "scratch.py"))
    # restore happened, but it is not a hard error -> rc 0
    assert rc == 0


def test_guard_blocked_without_token_does_not_run(tmp_repo, snap_root):
    make_untracked(tmp_repo, "scratch.py", "important\n")
    opts = GuardOptions(assume_yes=True, override="wrong", tmp_root=snap_root)
    rc = guard(["git", "clean", "-fd"], cwd=str(tmp_repo), options=opts)
    assert rc == 1
    # The clean never ran, so the file is still there untouched.
    assert os.path.exists(os.path.join(str(tmp_repo), "scratch.py"))


def test_guard_reset_hard_restores_untracked(tmp_repo, snap_root):
    make_untracked(tmp_repo, "notes.md", "draft\n")
    opts = GuardOptions(
        assume_yes=True, override=OVERRIDE_TOKEN, tmp_root=snap_root
    )
    rc = guard(["git", "reset", "--hard"], cwd=str(tmp_repo), options=opts)
    # reset --hard does not touch untracked files, so it should remain present.
    assert os.path.exists(os.path.join(str(tmp_repo), "notes.md"))
    assert rc == 0


def test_guard_abort_when_snapshot_fails(tmp_repo, tmp_path):
    make_untracked(tmp_repo, "scratch.py")
    bad = tmp_path / "not-a-dir"
    bad.write_text("x")  # a file, not a dir -> snapshot mkdir fails
    opts = GuardOptions(
        assume_yes=True,
        override=OVERRIDE_TOKEN,
        tmp_root=str(bad),
    )
    rc = guard(["git", "clean", "-fd"], cwd=str(tmp_repo), options=opts)
    assert rc == 1
    # Snapshot failed -> clean must NOT have run -> file still present.
    assert os.path.exists(os.path.join(str(tmp_repo), "scratch.py"))


def test_guard_guarded_confirm_yes(tmp_repo, snap_root):
    make_untracked(tmp_repo, "wip.txt")
    opts = GuardOptions(assume_yes=True, tmp_root=snap_root)
    # status is safe; use a guarded op that won't need network: merge of HEAD
    rc = guard(["git", "merge", "HEAD"], cwd=str(tmp_repo), options=opts)
    assert os.path.exists(os.path.join(str(tmp_repo), "wip.txt"))
    assert rc == 0
