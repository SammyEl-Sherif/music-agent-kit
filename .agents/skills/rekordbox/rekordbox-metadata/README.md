# rekordbox-metadata

Clean, identify, enrich, and synchronize music metadata for a rekordbox
library — safely. Everything runs locally, original files are backed up before
any change, and nothing is written without your approval.

v1 works purely on the **audio files' embedded tags** (ID3/Vorbis/MP4). It
never opens or edits the rekordbox database; changes reach rekordbox through
its own **Reload Tag** action, with a guided walkthrough. Cue points, beat
grids, playlists, ratings, and My Tags are never touched.

## The pipeline

| Command | What it does | Writes? |
| --- | --- | --- |
| `scan` | Find tracks with missing/suspicious artist & title tags | no |
| `clean --dry-run` | Preview filename→metadata cleanup (`01 - Daft_Punk_-_One_More_Time_(Club_Mix)_WEB_320.mp3` → Daft Punk / One More Time / Club Mix) | no |
| `lookup` | Search MusicBrainz + Discogs, score candidates, build `review.csv` | no |
| `review` | Show proposals, confidence, and reasoning; approve/reject | review file only |
| `apply` | Write approved changes to audio tags (backup + audit log first) | audio tags |
| `sync` | Guided rekordbox Reload Tag workflow + status tracking | review file only |
| `undo` | Restore the most recent backup set | audio files (restore) |

Match confidence: ≥0.90 strong, 0.75–0.89 needs explicit approval, <0.75
ambiguous (top candidates shown with reasons, nothing recommended). A version
mismatch — your file is the Club Mix, the candidate is the plain mix — caps
confidence at 0.6, so remixes/edits/bootlegs never slip through on a title
match.

## Setup

```sh
pip3 install mutagen --break-system-packages
```

Optional but recommended: a Discogs token in your environment or `.env`
(`DISCOGS_TOKEN=...`) — without it, lookups are MusicBrainz-only. Credentials
never appear in logs or generated files.

First run of `scan` creates `rekordbox-metadata.yaml`; edit
`music_directory`, `backup_directory`, and `review_directory` there.

## Usage

```sh
cd .agents/skills/rekordbox/rekordbox-metadata/scripts
python3 rbmeta.py scan
python3 rbmeta.py clean --dry-run
python3 rbmeta.py lookup
python3 rbmeta.py review          # then edit review.csv: status -> approved
python3 rbmeta.py apply           # dry run
python3 rbmeta.py apply --yes     # backup + write
python3 rbmeta.py sync            # Reload Tag walkthrough
python3 rbmeta.py sync --mark-synced   # after you confirm the reload
python3 rbmeta.py undo --yes      # roll back the last apply
```

Or just ask Claude: *"scan my library for broken metadata"*, *"fix the tags on
these downloads and sync them into rekordbox."*

## Safety model

- Timestamped full-file backups before every apply; `undo` restores the latest
  set. `audit-log.jsonl` records old/new values for every change.
- Only `approved` review rows are applied; your manual edits to the review file
  are preserved exactly.
- Existing tags are never blanked; files are never renamed, moved, or deleted.
- rekordbox is only ever updated by rekordbox itself (Reload Tag) — the skill
  tracks `sync_pending`/`synced` status and never claims sync happened without
  your confirmation.
- Test the whole cycle on sample files (point `music_directory` at a copy)
  before running it against your real library.

## Tests

```sh
python3 test_cleaning.py && python3 test_scoring.py && python3 test_workflow.py
```

No network, no music library, no mutagen required.
