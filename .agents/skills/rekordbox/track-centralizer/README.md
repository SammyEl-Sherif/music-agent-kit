# track-centralizer

Gather every audio file your rekordbox collection points at into **one folder
you choose**, safely, then re-link the tracks inside rekordbox. For libraries
that have grown scattered across `Downloads`, `Desktop`, old folders, and
half-migrated drives.

## What it does

1. **Scans** your collection (reads the encrypted `master.db` via
   `pyrekordbox`) and finds where every file actually lives — including files
   already in the destination, files missing from disk, and streaming tracks.
2. **Plans** a collision-safe move: filenames are never changed (rekordbox
   re-links by filename), so same-named files are kept side by side in
   numbered `_conflicts/` subfolders instead of being renamed or clobbered.
3. **Moves** the files after you confirm — atomic renames on the same volume,
   copy-verify-then-delete across volumes, an undo manifest written as it
   goes. Nothing is ever overwritten or deleted.
4. **Guides you through relocating in rekordbox** (Auto Relocate pointed at
   the new folder), because this skill never writes the rekordbox database —
   your cues, grids, playlists, and play counts are untouched.

## Prerequisites

- macOS/Linux, `python3`
- `pip3 install pyrekordbox --break-system-packages`
- Enough free space on the destination volume for the files that cross
  volumes (same-volume moves need none — the scan tells you both numbers)

## Usage

Ask in plain language — *"centralize my collection into
~/Music/rekordbox-library"* — or run the scripts directly:

```sh
# 1. scan + plan (read-only; rekordbox can stay open)
python3 scripts/scan_tracks.py --dest ~/Music/rekordbox-library \
    --out /tmp/rb-centralize-plan.json

# 2. see exactly what would move
python3 scripts/centralize.py /tmp/rb-centralize-plan.json

# 3. quit rekordbox, then move for real
python3 scripts/centralize.py /tmp/rb-centralize-plan.json --execute

# 4. in rekordbox: File > Display All Missing Files > select all >
#    Auto Relocate (search folder = your new library folder)

# changed your mind? reverse the whole run:
python3 scripts/undo_centralize.py \
    ~/Music/rekordbox-library/_centralize/manifest-<ts>.jsonl --execute
```

## Safety notes

- The rekordbox **database is never written** — re-linking happens inside
  rekordbox itself, so worst case is tracks showing "missing" until you
  relocate (or undo).
- Files are only ever **moved**, never renamed, overwritten, or deleted;
  cross-volume moves verify the copy before removing the original.
- The moving and undo steps refuse to run while rekordbox is open.
- Every run writes a manifest under `<dest>/_centralize/` that
  `undo_centralize.py` can replay in reverse.
- Self-check (no database needed): `python3 scripts/test_centralize.py`
