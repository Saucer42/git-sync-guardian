"""Recovery guidance for losses that happened *without* the guardian running.

Single source of truth for both ``gsg recover-help`` and RECOVERY.md.
"""

RECOVERY_TEXT = """\
Recovering untracked files lost without gsg
===========================================

Untracked files were never git objects, so git itself usually cannot help.
Work through these fallbacks in order - highest success rate first.

1. Cloud-storage online recycle bin  (best odds)
   If the repo lives in Dropbox / OneDrive / Google Drive, open the provider's
   *web* interface and check its recycle bin / trash. These keep deleted files
   for ~30 days and capture deletions that bypass the OS recycle bin.
     - Dropbox:      Deleted files  (web)
     - OneDrive:     Recycle bin    (web)
     - Google Drive: Trash          (web)

2. Cloud version history on the parent folder
   Some providers keep per-folder version history even for deletions. Check the
   version history of the directory that contained the files.

3. git fsck / git log  (only if the file was EVER committed)
     git fsck --lost-found
     git log --all --oneline -- <path>
   These return nothing for files that were always untracked - they were never
   written to the object store.

4. OS recycle bin  (usually empty)
   `git clean` and most sync tools delete files directly, bypassing the OS
   Trash / Recycle Bin. Check anyway, but expect nothing.

The lesson: snapshot before destruction. That is exactly what gsg automates -
run dangerous commands through `gsg guard -- ...` or use `gsg sync`.
"""
