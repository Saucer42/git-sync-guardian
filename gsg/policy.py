"""Classify git invocations into safe / guarded / blocked tiers.

Defaults are deliberately conservative (Section 7 of the build plan). Teams can
tune the subcommand lists via ``.gsg.toml`` but the shipped defaults block the
genuinely destructive variants behind a verbatim override token.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older interpreters
    tomllib = None  # type: ignore[assignment]

from . import OVERRIDE_TOKEN

SAFE = "safe"
GUARDED = "guarded"
BLOCKED = "blocked"

# Subcommands that warrant a snapshot + verify but no override (Section 7).
DEFAULT_GUARDED = {"pull", "merge", "fetch", "rebase"}

# Subcommands always blocked behind the override token (any variant).
DEFAULT_BLOCKED_SUBCOMMANDS = {"clean"}


@dataclass
class Policy:
    guarded: set[str] = field(default_factory=lambda: set(DEFAULT_GUARDED))
    blocked: set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_SUBCOMMANDS))
    override_token: str = OVERRIDE_TOKEN


@dataclass
class Decision:
    tier: str
    reason: str


def load_policy(repo_root: str | None = None) -> Policy:
    """Load a :class:`Policy`, merging ``.gsg.toml`` over the defaults."""
    policy = Policy()
    if not repo_root or tomllib is None:
        return policy
    config_path = os.path.join(repo_root, ".gsg.toml")
    if not os.path.isfile(config_path):
        return policy
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return policy
    section = data.get("policy", {})
    if isinstance(section.get("guarded_subcommands"), list):
        policy.guarded = set(section["guarded_subcommands"])
    if isinstance(section.get("blocked_subcommands"), list):
        policy.blocked = set(section["blocked_subcommands"])
    if isinstance(section.get("override_token"), str):
        policy.override_token = section["override_token"]
    return policy


def _strip_git(tokens: list[str]) -> list[str]:
    toks = list(tokens)
    if toks and toks[0] == "git":
        toks = toks[1:]
    return toks


def classify(tokens: list[str], policy: Policy | None = None) -> Decision:
    """Decide the tier for a git command given as a token list.

    ``tokens`` may or may not include a leading ``git``.
    """
    policy = policy or Policy()
    toks = _strip_git(tokens)
    if not toks:
        return Decision(SAFE, "empty command")

    sub = toks[0]
    rest = toks[1:]

    # --- Blocked tier: genuinely destructive to the working tree ----------
    if sub in policy.blocked:
        return Decision(BLOCKED, f"`git {sub}` can delete untracked files")

    if sub == "reset" and "--hard" in rest:
        return Decision(BLOCKED, "`reset --hard` discards working-tree changes")

    if sub == "checkout" and ("-f" in rest or "--force" in rest):
        return Decision(BLOCKED, "`checkout --force` overwrites working-tree files")

    if sub == "merge" and _has_strategy_option(rest):
        return Decision(BLOCKED, "`merge -X theirs/ours` can silently overwrite files")

    if sub == "stash" and rest and rest[0] in ("drop", "clear"):
        return Decision(BLOCKED, f"`stash {rest[0]}` permanently discards stashed work")

    if sub == "rm" and "--cached" in rest and _has_recursive(rest):
        return Decision(BLOCKED, "`rm -r --cached` can leave/lose working-tree files")

    if "--force" in rest:
        return Decision(BLOCKED, "`--force` against the working tree is destructive")
    # Bare ``-f`` is destructive for these subcommands; for others (e.g. fetch
    # -f) it is benign, so only block where it touches the working tree.
    if "-f" in rest and sub in ("clean", "checkout", "restore"):
        return Decision(BLOCKED, f"`git {sub} -f` is destructive to the working tree")

    # --- Guarded tier: snapshot + verify, lightweight confirm -------------
    if sub in policy.guarded:
        return Decision(GUARDED, f"`git {sub}` may move/overwrite the working tree")

    return Decision(SAFE, "not a guarded or blocked command")


def _has_strategy_option(rest: list[str]) -> bool:
    for i, tok in enumerate(rest):
        if tok == "-X" and i + 1 < len(rest) and rest[i + 1] in ("theirs", "ours"):
            return True
        if tok.startswith("-X") and tok[2:] in ("theirs", "ours"):
            return True
        if tok.startswith("--strategy-option=") and tok.split("=", 1)[1] in (
            "theirs",
            "ours",
        ):
            return True
    return False


def _has_recursive(rest: list[str]) -> bool:
    for tok in rest:
        if tok == "-r" or tok == "--recursive":
            return True
        # combined short flags like -rf
        if tok.startswith("-") and not tok.startswith("--") and "r" in tok[1:]:
            return True
    return False
