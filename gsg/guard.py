"""The guard-an-arbitrary-command flow: pre-flight, run, post-flight."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from . import gitio, inventory, policy, report
from .snapshot import Snapshot, SnapshotError, create_snapshot, restore_missing


@dataclass
class GuardOptions:
    assume_yes: bool = False
    override: str | None = None  # pre-supplied override token (non-interactive)
    tmp_root: str | None = None
    input_fn: callable = input  # injectable for tests


def guard(
    command: list[str],
    cwd: str | None = None,
    options: GuardOptions | None = None,
) -> int:
    """Snapshot, (gate), run ``command``, verify, auto-restore, report.

    ``command`` is the git invocation as a token list (with or without leading
    ``git``). Returns a process exit code.
    """
    options = options or GuardOptions()

    if not gitio.is_git_repo(cwd):
        report.error("Not inside a git repository.")
        return 1

    root = gitio.repo_root(cwd)
    pol = policy.load_policy(root)
    decision = policy.classify(command, pol)

    report.info(f"Command : git {' '.join(_strip_git(command))}")
    report.info(f"Tier    : {decision.tier} ({decision.reason})")

    # --- Override gate for blocked commands --------------------------------
    if decision.tier == policy.BLOCKED:
        if not _pass_override_gate(decision, pol, options):
            report.error("Override not given - command refused. Nothing was run.")
            return 1

    # --- Pre-flight: inventory + verified snapshot -------------------------
    rels = gitio.untracked_files(cwd)
    entries = inventory.inventory(root, rels)
    report.info("")
    report.info(f"Untracked files at risk ({len(rels)}):")
    report.info(inventory.format_table(entries))

    try:
        snap = create_snapshot(root, rels, tmp_root=options.tmp_root)
    except SnapshotError as exc:
        report.error(f"SNAPSHOT FAILED: {exc}")
        report.error("Refusing to run the operation without a verified backup.")
        return 1

    report.info("")
    report.success(report.snapshot_line(snap))

    # --- Lightweight confirm for guarded tier ------------------------------
    if decision.tier == policy.GUARDED and not options.assume_yes:
        if not _confirm(
            f"Proceed with `git {' '.join(_strip_git(command))}`? [y/N] ",
            options.input_fn,
        ):
            report.warn("Aborted by user. Snapshot kept at " + snap.path)
            return 1

    # --- Run the wrapped command -------------------------------------------
    report.info("")
    report.info(f"Running: git {' '.join(_strip_git(command))}")
    rc = _run_command(_strip_git(command), cwd=cwd)
    report.info(f"(exit {rc})")

    # --- Post-flight: verify presence on disk + auto-restore ---------------
    result = restore_missing(root, rels, snap)
    report.info("")
    restore_rc = report.render_restore(result, snap)

    # If the wrapped command itself failed, surface that, but a successful
    # restore of vanished files is the more important signal.
    if restore_rc != 0:
        return restore_rc
    return rc


def _run_command(git_args: list[str], cwd: str | None) -> int:
    proc = subprocess.run(["git", *git_args], cwd=cwd)
    return proc.returncode


def _strip_git(tokens: list[str]) -> list[str]:
    return tokens[1:] if tokens and tokens[0] == "git" else list(tokens)


def _pass_override_gate(
    decision: policy.Decision, pol: policy.Policy, options: GuardOptions
) -> bool:
    token = pol.override_token
    report.warn("")
    report.warn("!! BLOCKED COMMAND " + "!" * 51)
    report.warn(f"Reason: {decision.reason}.")
    report.warn(
        "Operations like this can silently and permanently delete untracked "
        "files - work that was never `git add`ed leaves no reflog trace and "
        "cannot be recovered with `git fsck`."
    )
    report.warn(
        "gsg will still snapshot first, but you must explicitly accept the risk."
    )
    report.warn(f'To proceed, type exactly:  {token}')
    report.warn("!" * 70)

    if options.override is not None:
        return options.override.strip() == token

    try:
        typed = options.input_fn(f"Override token: ")
    except (EOFError, KeyboardInterrupt):
        return False
    return typed.strip() == token


def _confirm(prompt: str, input_fn) -> bool:
    try:
        ans = input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() in ("y", "yes")
