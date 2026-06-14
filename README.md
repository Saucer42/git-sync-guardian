# git-sync-guardian (`gsg`)

> A safety wrapper around destructive git operations. Before any command that
> can silently delete **untracked** files (`git clean`, `reset --hard`,
> `checkout -f`, a hard `pull`), it snapshots every untracked file to a
> timestamped folder **outside** the repo, runs the operation, then verifies
> nothing vanished — and auto-restores anything that did.

## The incident (why this exists)

Git protects *tracked* files. It does nothing for untracked ones. A single
`git clean -fd`, a `reset --hard`, or some sync tool's "discard working tree"
can erase hours of uncommitted, never-added work and leave **no reflog trace** —
`git fsck` finds nothing because the files were never objects.

This actually happened: ~24 untracked source files were silently destroyed by a
working-tree-only operation, recoverable only because the repo happened to live
in a cloud-synced folder with an online recycle bin. `git-sync-guardian` exists
so that recovery is never down to luck. It makes the snapshot-before-destruction
discipline automatic.

If you've ever lost untracked work, you already understand this tool.

## 15-second demo

```sh
$ echo "hours of work" > scratch.py        # untracked, never `git add`ed

$ gsg guard -- git clean -fd
Command : git clean -fd
Tier    : blocked (`git clean` can delete untracked files)

!! BLOCKED COMMAND ...
To proceed, type exactly:  yes, override gsg guardrail
Override token: yes, override gsg guardrail

Untracked files at risk (1):
  * scratch.py    13 B
Snapshot: /tmp/gsg-20260614-101500 (1 files, 0.0 KB)

Running: git clean -fd
Removing scratch.py

!! 1 of 1 untracked file(s) VANISHED and were auto-restored from:
   /tmp/gsg-20260614-101500
     restored: scratch.py
```

`scratch.py` is back. The operation ran, the loss was detected by checking the
disk (not git status), and the file was restored from the snapshot.

## Install

```sh
pipx install git-sync-guardian      # recommended
# or
pip install git-sync-guardian
```

Python 3.11+, standard library only — nothing else to trust.

### Optional shell shim (opt-in)

Make `gsg` muscle memory by routing the dangerous git verbs through it:

```sh
gsg install-alias            # prints a snippet for your shell; review, then add it
```

This is never installed silently — you copy the snippet into your rc file.

## What it does

```
gsg guard -- <any git command>     # snapshot, run it, verify, auto-restore
gsg sync  [--remote origin] [--branch main]   # safe bidirectional sync
gsg snapshot                        # snapshot untracked files now, print path
gsg restore <snapshot-path>         # manually restore from a snapshot
gsg prune  [--older-than 7d]        # delete old $TMP/gsg-* snapshots
gsg recover-help                    # print the recovery cheat-sheet
gsg --version
```

### What it guards vs. blocks

| Tier | Commands | Behaviour |
| --- | --- | --- |
| **Guarded** | `pull`, `merge` (non-ff), `fetch`, `rebase` | snapshot + verify + one-line confirm |
| **Blocked** | `clean`, `reset --hard`, `checkout -f/--force`, `merge -X theirs/ours`, `stash drop/clear`, `rm -r --cached`, anything with `--force` | requires a verbatim override token, *then* still snapshots first |

The override gate is deliberate friction. To run a blocked command you must type,
exactly:

```
yes, override gsg guardrail
```

Even with the override, the snapshot runs and is **verified** before the
dangerous operation executes. If the snapshot can't be created or verified, the
operation is **refused** — never run without a backup.

Tune the lists per-repo with `.gsg.toml` (see `.gsg.toml.example`).

### The safe `sync` sequence

`gsg sync` is a safer alternative to a raw `git pull`:

1. `git fetch origin --prune` and show divergence.
2. Enumerate remote branches not merged into your base, summarize each, and ask
   which to merge — it **never** auto-merges.
3. Optionally commit local tracked changes.
4. Merge chosen branches with `--no-ff`.
5. `git pull --no-rebase`, then `git push`.

All of it runs *after* a verified snapshot, so even a surprise fast-forward that
clobbers an untracked file is recoverable.

## Recovery cheat-sheet

Lost files *without* gsg running? See [RECOVERY.md](RECOVERY.md) or run
`gsg recover-help`. Short version: check your **cloud provider's web recycle
bin** first (~30-day retention, highest success rate); `git fsck` finds nothing
for always-untracked files.

## FAQ: "Why not just commit everything?"

Because work-in-progress, generated artifacts, scratch files, and local
experiments legitimately stay untracked. You shouldn't have to pollute history
to be safe from `git clean`. gsg protects exactly the files git ignores.

## License

MIT — see [LICENSE](LICENSE).
