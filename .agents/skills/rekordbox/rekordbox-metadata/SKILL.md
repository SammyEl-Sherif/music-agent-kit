---
name: rekordbox-metadata
description: >-
  Clean, identify, enrich, and synchronize music metadata for a rekordbox
  library using a safe audio-file-tag workflow: scan a music directory for
  tracks with missing/malformed/suspicious tags, clean titles and extract
  artist/version info from filenames, look up candidates on MusicBrainz
  (primary) and Discogs (secondary), score and rank matches, generate an
  editable review CSV, apply ONLY user-approved changes to embedded audio tags
  (timestamped backup + audit log first), then guide the user through
  rekordbox's Reload Tag workflow to pull the new tags in. Subcommands: scan,
  clean --dry-run, lookup, review, apply, sync, undo. v1 NEVER touches the
  rekordbox database, cue points, beat grids, playlists, ratings, or My Tags,
  and never renames/moves/deletes files. Use this whenever the user wants to
  fix, clean up, enrich, or complete track metadata/tags for their rekordbox
  library or music folder -- e.g. "fix the metadata on these tracks", "my
  titles are full of underscores and WEB 320 junk", "find the proper
  artist/title/year for these files", "tag my untagged downloads", "sync the
  fixed tags into rekordbox."
---

# rekordbox-metadata

Clean, identify, enrich, and synchronize music metadata for a rekordbox
library. Runs entirely locally, preserves original files and DJ data, and
requires human approval before anything ambiguous or destructive.

**Three different things — never conflate them when talking to the user:**

1. **Audio-file embedded metadata** (ID3 / Vorbis / MP4 tags) — what `apply`
   writes.
2. **Reloading that metadata into rekordbox** — rekordbox keeps its own copy in
   its database; it only picks up changed file tags via **Reload Tag** (the
   `sync` step). *Never claim rekordbox has been updated until Reload Tag has
   been completed and confirmed by the user.*
3. **rekordbox-specific data** — cue points, beat grids, hot/memory cues,
   playlists, ratings, play counts, My Tags. This skill never touches any of
   it, in any mode.

## Setup

- `pip3 install mutagen --break-system-packages` (tag read/write).
- MusicBrainz needs no key. Discogs needs a token in `DISCOGS_TOKEN` (env var
  or a local `.env`); without it, lookups run in degraded MusicBrainz-only mode
  and say so. **Never echo, log, or write credentials anywhere.**
- Config lives in `rekordbox-metadata.yaml` (cwd, then `~/.config/`). The first
  `scan` creates a default; have the user confirm `music_directory`,
  `backup_directory`, and `review_directory` before doing anything else.
- **First run must be on sample/copied files, not the real library** — walk
  through scan → lookup → review → apply → undo on a small copy (or point
  `music_directory` at a test folder) before pointing it at real music.

All commands are `python3 scripts/rbmeta.py <subcommand>` (add
`--config <path>` to use a non-default config). `/rekordbox-metadata <sub>`
maps 1:1 onto these subcommands.

## The workflow

### 1. `scan` — find problem tracks (read-only)

```
python3 scripts/rbmeta.py scan [--limit N] [--from-rekordbox]
```

Walks `music_directory` (mp3/flac/m4a/wav/aiff), reads embedded tags, and flags
tracks with missing artist/title, placeholder artists, filename-shaped titles
(underscores, leading track numbers, WEB/320-style junk), or artist embedded in
the title. Writes `scan.json` to the review directory. Relay the counts and the
flagged list.

`--from-rekordbox` scans the **rekordbox Collection** instead of a folder: it
enumerates every Collection track's file path via pyrekordbox (**read-only**,
never writes the DB; needs `pip3 install pyrekordbox --break-system-packages`)
and scans those exact files wherever they live on disk. Prefer this when the
user's library spans many folders — it guarantees every scanned file is one
rekordbox actually references, reports Collection entries whose files are
missing, and additionally lists tracks whose FILE tags are newer than what
rekordbox displays (those need a Reload Tag, not a lookup).

### 2. `clean --dry-run` — preview title cleanup (writes nothing)

```
python3 scripts/rbmeta.py clean --dry-run
```

Shows, per flagged track: current tags vs. the parsed proposal
(artist / title / version / feat / remixer) derived from the filename. The
parser strips track numbers, underscores, junk brackets, and tech suffixes, and
**preserves version info** (Original/Extended/Club Mix, Radio Edit, Remix, Dub,
Instrumental, VIP, Live, Acapella, Bootleg, Mashup, remixer credits, feat.
artists). It never title-cases and never guesses — unknown stays empty.

### 3. `lookup` — fetch and score candidates (read-only, network)

```
python3 scripts/rbmeta.py lookup [--max N]
```

Queries MusicBrainz first, Discogs second (rate-limited ~1 req/s, disk-cached,
so re-runs are free). Each candidate is scored 0–1 on title/artist/version/
duration/album/label/year plus cross-source agreement. **A version conflict
(file says Club Mix, candidate is the plain mix) hard-caps the score at 0.6** —
remixes, edits, VIPs, bootlegs, and common titles are exactly where wrong
matches happen. Bands: ≥0.90 strong; 0.75–0.89 possible (explicit approval);
<0.75 ambiguous (no recommendation, top candidates shown with reasons). The
first search result is never auto-chosen. Writes `review.csv` +
`review-candidates.json`. If a source is down or unauthenticated, lookups
continue degraded and the problem is reported — metadata is never invented.

### 4. `review` — inspect and decide (gate 1)

```
python3 scripts/rbmeta.py review                 # show everything + why
python3 scripts/rbmeta.py review --approve 1,3   # or 'all'; --reject likewise
```

Show the user every row: current → proposed values, source, confidence, and the
match reasons; for ambiguous rows, the top candidates with per-candidate
reasoning. The user approves by editing the CSV's `status` column to
`approved` (they may also correct any proposed value — **manual edits are
preserved exactly** and never overwritten by new API results unless they ask
for a fresh lookup) or via `--approve`. Statuses: pending / approved /
rejected / ambiguous / applied / failed / sync_pending / synced / sync_failed.

### 5. `apply` — write approved tags (gate 2)

```
python3 scripts/rbmeta.py apply          # dry run: full plan, nothing written
python3 scripts/rbmeta.py apply --yes    # write, after the user confirms
```

Only `approved` rows are touched. The dry run shows the file count, every
field's old → new value, source, and confidence — **show this to the user and
get explicit confirmation before running `--yes`.** With `--yes` it: creates a
timestamped backup set of every file about to change (under
`backup_directory`), writes tags via mutagen (ID3 for mp3/wav/aiff, Vorbis for
flac, MP4 atoms for m4a — fields a format can't carry are skipped and
reported), never blanks an existing tag, and appends before/after values to
`audit-log.jsonl`. Rows become `applied` (or `failed` with the error). It then
prints the reload list — and reminds you that **rekordbox itself is still
unchanged**.

### 6. `sync` — get the changes into rekordbox (gate 3)

```
python3 scripts/rbmeta.py sync                # instructions + pending list
python3 scripts/rbmeta.py sync --mark-synced  # ONLY after the user confirms
```

Confirms the apply + backup happened, then walks the user through it: open
rekordbox → select exactly the listed tracks in Collection → right-click →
**Reload Tag** → verify. Warn them: Reload Tag replaces rekordbox's
title/artist/album fields with the file's tags, so they must not reload tracks
whose rekordbox-side metadata they want to keep (cues/grids/playlists/ratings/
My Tags are unaffected by Reload Tag). Ask the user to confirm the reload is
done; only then run `--mark-synced` (subset via `--files`; failures via
`--mark-failed`). This writes the final sync report. There is no GUI
automation in v1 — the manual walkthrough is the supported path.

### 7. `undo` — roll back

```
python3 scripts/rbmeta.py undo         # show what would be restored
python3 scripts/rbmeta.py undo --yes   # restore the most recent backup set
```

Restores every file from the latest backup set, logs it, and flips the review
rows back. If a restored track was already reloaded in rekordbox, tell the user
to Reload Tag it again so rekordbox shows the restored values.

## Safety rules (non-negotiable)

- Steps 1–4 never write to music files. Only `apply --yes` writes, and only to
  the nine tag fields (title, artist, album, albumartist, remixer, label,
  genre, year, isrc) of approved rows.
- Never delete, move, or rename files. Never touch audio content. Never touch
  the rekordbox database, cues, grids, playlists, ratings, or My Tags —
  **direct DB editing is deliberately not implemented in v1.**
- Never apply low-confidence or unapproved matches; never treat a title-only
  match as definitive; never auto-pick the first result.
- Never blank an existing tag; existing non-empty values change only via an
  approved row.
- Never claim rekordbox is updated before the user confirms Reload Tag.
- Never expose API credentials in output, logs, review files, or reports.
- Do not run any of this against the user's real library until the whole
  cycle has been demonstrated on samples/copies.

## Tests

`python3 scripts/test_cleaning.py`, `test_scoring.py`, `test_workflow.py` —
no network, no library, no mutagen needed. Run them after changing the parser,
scorer, or store logic.
