"""git-sync-guardian: a safety wrapper around destructive git operations.

Before any command that can silently delete *untracked* files, gsg snapshots
every untracked file to a timestamped folder outside the repo, runs the
operation, then verifies nothing vanished - and auto-restores anything that did.
"""

__version__ = "0.1.0"

OVERRIDE_TOKEN = "yes, override gsg guardrail"
