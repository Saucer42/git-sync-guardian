"""The safe bidirectional sync sequence (Section 9 of the build plan).

A built-in alternative to a raw ``git pull`` that consolidates safely: fetch,
enumerate unmerged remote branches and ask which to merge (never auto-merge),
optionally commit local tracked changes, merge with ``--no-ff``, then pull and
push. All of this runs *after* a verified snapshot so even a surprise
fast-forward that clobbers an untracked file is recoverable.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import gitio, inventory, report
from .snapshot import SnapshotError, create_snapshot, restore_missing


@dataclass
class SyncOptions:
    remote: str = "origin"
    branch: str = "main"
    assume_yes: bool = False
    tmp_root: str | None = None
    input_fn: callable = input


def sync(cwd: str | None = None, options: SyncOptions | None = None) -> int:
    options = options or SyncOptions()

    if not gitio.is_git_repo(cwd):
        report.error("Not inside a git repository.")
        return 1

    root = gitio.repo_root(cwd)

    # --- Snapshot first: everything below runs under protection -----------
    rels = gitio.untracked_files(cwd)
    entries = inventory.inventory(root, rels)
    report.info(f"Untracked files at risk ({len(rels)}):")
    report.info(inventory.format_table(entries))
    try:
        snap = create_snapshot(root, rels, tmp_root=options.tmp_root)
    except SnapshotError as exc:
        report.error(f"SNAPSHOT FAILED: {exc}")
        report.error("Refusing to sync without a verified backup.")
        return 1
    report.success(report.snapshot_line(snap))

    # --- 1. Fetch + show divergence ---------------------------------------
    report.info("")
    report.info(f"Fetching {options.remote} --prune ...")
    gitio.fetch(options.remote, cwd=cwd, prune=True)
    report.info(gitio.status_short(cwd).rstrip())

    # --- 2. Enumerate unmerged remote branches ----------------------------
    candidates = gitio.unmerged_remote_branches(
        options.branch, remote=options.remote, cwd=cwd
    )
    chosen: list[str] = []
    if candidates:
        report.info("")
        report.info(f"Remote branches not merged into '{options.branch}':")
        for ref in candidates:
            s = gitio.branch_summary(ref, options.branch, cwd=cwd)
            report.info(
                f"  - {s['ref']}: {s['commits']} commit(s), {s['files']} file(s), "
                f"{s['author']} @ {s['date']} - {s['subject']}"
            )
        if options.assume_yes:
            report.info(
                "Refusing to auto-merge branches even with --yes; skipping merges."
            )
        else:
            chosen = _ask_which_to_merge(candidates, options.input_fn)

    # --- 3. Optionally commit local tracked changes -----------------------
    if gitio.has_staged_or_unstaged_changes(cwd) and not options.assume_yes:
        if _confirm("Commit local tracked changes first? [y/N] ", options.input_fn):
            msg = options.input_fn("Commit message: ").strip() or "gsg sync: local changes"
            gitio.commit_all(msg, cwd=cwd)

    # --- 4. Merge chosen branches with --no-ff ----------------------------
    for ref in chosen:
        report.info(f"Merging {ref} --no-ff ...")
        res = gitio.merge(ref, no_ff=True, cwd=cwd)
        if not res.ok:
            report.error(
                f"Merge of {ref} failed (likely conflicts). Resolve manually, "
                f"then re-run. Snapshot kept at {snap.path}."
            )
            _post_verify(root, rels, snap)
            return 1

    # --- 5. Pull then push -------------------------------------------------
    report.info("")
    report.info(f"Pulling {options.remote}/{options.branch} (no-rebase) ...")
    pull_res = gitio.pull(options.remote, options.branch, rebase=False, cwd=cwd)
    if not pull_res.ok:
        report.error("Pull failed - resolve manually. Snapshot kept.")
        _post_verify(root, rels, snap)
        return 1

    report.info(f"Pushing to {options.remote}/{options.branch} ...")
    push_res = gitio.push(options.remote, options.branch, cwd=cwd)
    if not push_res.ok:
        report.warn("Push failed - you may need to pull/resolve and push manually.")

    # --- Post-flight verify ------------------------------------------------
    report.info("")
    return _post_verify(root, rels, snap)


def _post_verify(root, rels, snap) -> int:
    result = restore_missing(root, rels, snap)
    return report.render_restore(result, snap)


def _ask_which_to_merge(candidates: list[str], input_fn) -> list[str]:
    try:
        ans = input_fn(
            "Which to merge? (comma-separated names, 'all', or blank to skip): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return []
    if not ans:
        return []
    if ans.lower() == "all":
        return list(candidates)
    wanted = {x.strip() for x in ans.split(",") if x.strip()}
    return [c for c in candidates if c in wanted or c.split("/", 1)[-1] in wanted]


def _confirm(prompt: str, input_fn) -> bool:
    try:
        ans = input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() in ("y", "yes")
