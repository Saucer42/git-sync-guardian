"""Command-line dispatch: guard | sync | snapshot | restore | prune | ..."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time

from . import __version__, gitio, inventory, report
from .guard import GuardOptions, guard
from .recovery import RECOVERY_TEXT
from .snapshot import SnapshotError, create_snapshot, restore_all
from .sync import SyncOptions, sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gsg",
        description="git-sync-guardian: snapshot untracked files before "
        "destructive git operations, then verify and auto-restore.",
    )
    parser.add_argument(
        "--version", action="version", version=f"gsg {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    p_guard = sub.add_parser(
        "guard", help="snapshot, run a git command, verify, auto-restore"
    )
    p_guard.add_argument(
        "-y", "--yes", action="store_true", help="skip the lightweight confirm"
    )
    p_guard.add_argument(
        "--override",
        metavar="TOKEN",
        help="pre-supply the verbatim override token (non-interactive)",
    )
    p_guard.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        help="-- <git command>, e.g. -- git clean -fd",
    )

    p_sync = sub.add_parser("sync", help="safe bidirectional sync sequence")
    p_sync.add_argument("--remote", default="origin")
    p_sync.add_argument("--branch", default="main")
    p_sync.add_argument("-y", "--yes", action="store_true")

    sub.add_parser("snapshot", help="snapshot untracked files now, print the path")

    p_restore = sub.add_parser("restore", help="manually restore from a snapshot")
    p_restore.add_argument("snapshot_path")

    p_prune = sub.add_parser("prune", help="delete old $TMP/gsg-* snapshots")
    p_prune.add_argument(
        "--older-than",
        default="7d",
        help="age threshold, e.g. 24h, 7d, 30m (never younger than 24h)",
    )
    p_prune.add_argument(
        "--dry-run", action="store_true", help="list what would be deleted"
    )

    sub.add_parser("recover-help", help="print the recovery cheat-sheet")

    p_alias = sub.add_parser(
        "install-alias", help="print/install shell aliases routing git through gsg"
    )
    p_alias.add_argument(
        "--shell", choices=["bash", "zsh", "fish"], help="target shell"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "guard":
        return _cmd_guard(args)
    if args.command == "sync":
        return _cmd_sync(args)
    if args.command == "snapshot":
        return _cmd_snapshot(args)
    if args.command == "restore":
        return _cmd_restore(args)
    if args.command == "prune":
        return _cmd_prune(args)
    if args.command == "recover-help":
        print(RECOVERY_TEXT)
        return 0
    if args.command == "install-alias":
        return _cmd_install_alias(args)

    parser.print_help()
    return 1


def _cmd_guard(args) -> int:
    rest = list(args.rest)
    if rest and rest[0] == "--":
        rest = rest[1:]
    if not rest:
        report.error("Usage: gsg guard -- <git command>")
        return 1
    opts = GuardOptions(assume_yes=args.yes, override=args.override)
    return guard(rest, options=opts)


def _cmd_sync(args) -> int:
    opts = SyncOptions(remote=args.remote, branch=args.branch, assume_yes=args.yes)
    return sync(options=opts)


def _cmd_snapshot(args) -> int:
    if not gitio.is_git_repo():
        report.error("Not inside a git repository.")
        return 1
    root = gitio.repo_root()
    rels = gitio.untracked_files()
    entries = inventory.inventory(root, rels)
    report.info(f"Untracked files ({len(rels)}):")
    report.info(inventory.format_table(entries))
    try:
        snap = create_snapshot(root, rels)
    except SnapshotError as exc:
        report.error(f"SNAPSHOT FAILED: {exc}")
        return 1
    report.success(report.snapshot_line(snap))
    print(snap.path)
    return 0


def _cmd_restore(args) -> int:
    if not gitio.is_git_repo():
        report.error("Not inside a git repository.")
        return 1
    root = gitio.repo_root()
    try:
        restored = restore_all(args.snapshot_path, root)
    except SnapshotError as exc:
        report.error(str(exc))
        return 1
    report.success(f"Restored {len(restored)} file(s) into {root}:")
    for rel in restored:
        report.info(f"  {rel}")
    return 0


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
# Design principle #6: snapshots persist; never younger than 24h.
_MIN_AGE_SECONDS = 24 * 3600


def _parse_duration(text: str) -> int:
    m = _DURATION_RE.match(text)
    if not m:
        raise ValueError(f"invalid duration {text!r} (use e.g. 24h, 7d, 30m)")
    return int(m.group(1)) * _UNIT_SECONDS[m.group(2)]


def _cmd_prune(args) -> int:
    import tempfile

    try:
        threshold = _parse_duration(args.older_than)
    except ValueError as exc:
        report.error(str(exc))
        return 1
    if threshold < _MIN_AGE_SECONDS:
        report.warn(
            f"--older-than {args.older_than} is below the 24h floor; "
            f"using 24h to keep recent snapshots safe."
        )
        threshold = _MIN_AGE_SECONDS

    base = tempfile.gettempdir()
    now = time.time()
    pruned = 0
    for name in sorted(os.listdir(base)):
        if not name.startswith("gsg-"):
            continue
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        age = now - os.path.getmtime(path)
        if age < threshold:
            continue
        if args.dry_run:
            report.info(f"would delete: {path} ({age / 3600:.1f}h old)")
        else:
            shutil.rmtree(path, ignore_errors=True)
            report.info(f"deleted: {path}")
        pruned += 1
    if pruned == 0:
        report.info("No snapshots old enough to prune.")
    return 0


def _cmd_install_alias(args) -> int:
    shell = args.shell
    if shell is None:
        shell = os.path.basename(os.environ.get("SHELL", "")) or "bash"
    snippets = {
        "bash": (
            "# git-sync-guardian: route dangerous git verbs through gsg\n"
            "git() {\n"
            "  case \"$1\" in\n"
            "    clean|reset|checkout) command gsg guard -- git \"$@\" ;;\n"
            "    *) command git \"$@\" ;;\n"
            "  esac\n"
            "}\n"
        ),
        "zsh": (
            "# git-sync-guardian: route dangerous git verbs through gsg\n"
            "git() {\n"
            "  case \"$1\" in\n"
            "    clean|reset|checkout) command gsg guard -- git \"$@\" ;;\n"
            "    *) command git \"$@\" ;;\n"
            "  esac\n"
            "}\n"
        ),
        "fish": (
            "# git-sync-guardian: route dangerous git verbs through gsg\n"
            "function git\n"
            "  switch $argv[1]\n"
            "    case clean reset checkout\n"
            "      command gsg guard -- git $argv\n"
            "    case '*'\n"
            "      command git $argv\n"
            "  end\n"
            "end\n"
        ),
    }
    snippet = snippets.get(shell, snippets["bash"])
    rcfile = {
        "bash": "~/.bashrc",
        "zsh": "~/.zshrc",
        "fish": "~/.config/fish/functions/git.fish",
    }.get(shell, "~/.bashrc")
    report.info(
        f"# Add the following to {rcfile} to route git clean/reset/checkout\n"
        f"# through gsg (opt-in; review before installing):\n"
    )
    print(snippet)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
