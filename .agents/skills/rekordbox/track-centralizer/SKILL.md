---
name: track-centralizer
description: >-
  Locate every track in the rekordbox collection on disk and centralize the
  files into ONE user-specified folder, then walk the user through relocating
  them inside rekordbox. Scans the encrypted master.db (read-only) for every
  track's file path, classifies each one (movable / already centralized /
  missing on disk / streaming / excluded), plans collision-safe targets that
  NEVER rename a file (same-name files go to numbered _conflicts/ subfolders so
  rekordbox's relocate-by-filename still works), shows the user the plan (sizes,
  free space, name conflicts, probable duplicate files), then — with rekordbox
  closed and after explicit confirmation — moves the files with verified
  copy-then-delete for cross-volume moves and writes an undo manifest. It NEVER
  writes the rekordbox database: the last step is prompting the user to relocate
  the missing tracks in rekordbox itself (Auto Relocate pointed at the new
  folder). Use whenever the user wants their music files gathered into one
  place: "centralize my rekordbox collection", "consolidate my library into one
  folder", "move all my tracks into ~/Music", "my tracks are scattered across
  Downloads/Desktop/old drives, put them in one spot", "collect every file
  rekordbox uses into a single folder so I can back it up / relocate it."
---

# track-centralizer

Find every audio file the rekordbox collection points at, **move** them all into
one folder the user chooses, and then hand the last step to the user: relocating
the tracks inside rekordbox so the database points at the new home. Files move;
the database is **never** written by this skill.

## Why it works this way

- rekordbox stores its library in an **encrypted** SQLite database (`master.db`);
  the scan reads it via `pyrekordbox` (install once with
  `pip3 install pyrekordbox --break-system-packages`). Reading is safe with
  rekordbox open.
- **Filenames are sacred.** rekordbox re-links missing tracks by filename, so a
  moved file must keep its exact basename. Two different files with the same
  name are both kept — the extras go to `_conflicts/2/`, `_conflicts/3/`, …
  under the destination, names unchanged.
- **Moving is the risky half, so it's engineered to never lose a file**: atomic
  rename on the same volume; copy → verify → rename → delete-source across
  volumes; never overwrites; every completed move is logged immediately to an
  undo manifest.
- Scripts live in `scripts/` and run with `python3` from any directory (shared
  helpers are found via `sys.path`).

## The workflow

### Step 1 — Get the destination

Ask for the destination folder if not given (e.g. `~/Music/rekordbox-library`).
It doesn't need to exist yet. If parts of the library should stay put (e.g. an
external drive), collect those as `--exclude-path` terms.

### Step 2 — Scan and plan (read-only; rekordbox may stay open)

```
python3 scripts/scan_tracks.py --dest "~/Music/rekordbox-library" --out /tmp/rb-centralize-plan.json
```

Optional: `--exclude-path "/Volumes/Archive,OldDrive"` to leave matching paths
alone. Relay the printed summary to the user faithfully:

- counts per class: **to_move**, **already** (under dest), **missing** (DB
  points at a file that isn't on disk — this skill can't fix those; suggest
  checking unmounted drives), **excluded**, **non_local** (streaming tracks)
- GB to move, how much crosses volumes, free space on the destination (flag a
  shortfall — do not proceed past one)
- **name conflicts** headed for `_conflicts/` and **probable duplicate files**
  (same name + size; suggest `playlist-dedupe` afterwards)
- where the files live today (source-folder breakdown)

### Step 3 — Confirm, then move (rekordbox CLOSED)

Dry-run first and show it:

```
python3 scripts/centralize.py /tmp/rb-centralize-plan.json
```

Get the user's **explicit go-ahead**, have them **quit rekordbox fully** (the
script refuses to run while it's open), then:

```
python3 scripts/centralize.py /tmp/rb-centralize-plan.json --execute
```

(`--verify-hash` for SHA-256 verification of cross-volume copies, if the user
wants it.) Report: moved count, any skips (skipped files stay at their original
paths — nothing is ever lost), and the **manifest path** — the user should keep
it until they're happy; `undo_centralize.py <manifest> --execute` reverses the
whole run.

### Step 4 — Prompt the user to relocate in rekordbox

This is a **required** step — until it's done, every moved track shows a `!`
missing-file icon in rekordbox. Walk the user through it:

1. Open rekordbox. Add the new central folder under **Preferences → Advanced →
   Database → Auto Relocate Search Folders**.
2. **File → Display All Missing Files**, select all rows, right-click →
   **Auto Relocate**. rekordbox re-links each track to the same-named file in
   the new folder. All cues, grids, playlists, and play data survive — only the
   path changes.
3. If any files landed in `_conflicts/` subfolders, warn the user: those share
   a filename, so Auto Relocate may pick the wrong copy. Relocate those few
   manually (right-click the track → **Relocate** → pick the exact file in its
   `_conflicts/<n>/` folder — the plan JSON says which file went where).

### Step 5 — Verify

After the user relocates, re-run the Step 2 scan with the same `--dest`:
everything previously `to_move` should now read `already`, and the missing
count should be unchanged. Report the result; if stragglers remain, list them.

## Guardrails

- **Never writes the rekordbox database** — no exceptions. Re-pointing tracks
  is done by the user inside rekordbox (Step 4).
- **Never renames, overwrites, or deletes a file.** Moves only, original
  basenames kept; an occupied target path skips that move and reports it.
- **Scan/dry-run are safe with rekordbox open; `--execute` refuses unless
  rekordbox is fully quit**, for both centralize and undo.
- **Do not proceed** past a free-space warning, and never invent handling for
  `missing` tracks — report them and move on.
- Cross-volume moves are copy-verify-then-delete: a crash can leave a stray
  `.part` file, never a lost track.
- The undo manifest at `<dest>/_centralize/manifest-<ts>.jsonl` is the record
  of everything done — always tell the user where it is.
- Sidecar files (e.g. Serato `.asd`) are not in the rekordbox DB and are not
  moved; mention this if the user's folders contain them.
