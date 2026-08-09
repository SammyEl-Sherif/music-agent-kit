# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, etc.) working in this repo.
`CLAUDE.md` points here.

## What this repo is

A git-backed context repo of agent **skills for doing things with music** —
clone it, launch an agent inside it, and ask in plain language. Skills are
grouped by domain:

- **`rekordbox/`** — managing a [rekordbox](https://rekordbox.com) DJ library
  (adapted from [sean-a-Wilson/rekordbox-skills](https://github.com/sean-a-Wilson/rekordbox-skills)).
- **`ableton/`** — Ableton Live workflows (scaffolded; skills to come).
- **`utils/`** — standalone audio utilities that belong to no one app.

## Skills & routing

Each skill lives under `.agents/skills/<domain>/<name>/` and has its own
`SKILL.md` (execution instructions) and `README.md` (overview). Route to a
skill when the user's request matches:

| Skill | What it does | Route here when… |
| --- | --- | --- |
| **[rekordbox/playlist-dedupe](.agents/skills/rekordbox/playlist-dedupe/)** | Finds and prunes duplicate tracks in a playlist or the whole library, keeping the best-quality copy; version-aware and reviews every group with the user before writing. | The user wants to clean up, dedupe, find duplicates in, or remove repeated / lower-quality tracks from a rekordbox playlist or library — e.g. *"this playlist has a bunch of dupes"* or *"I have the same song twice in different quality."* |
| **[rekordbox/upgrade-finder](.agents/skills/rekordbox/upgrade-finder/)** | Scans a playlist's low-bitrate (≤320k) tracks and searches the whole library for a higher-quality file of the same recording (lossless beats lossy, then higher bitrate). Read-only report; optional opt-in apply step. | The user wants to find higher-quality versions they already own — e.g. *"are there better copies of these tracks?"*, *"which of these MP3s do I have a FLAC/WAV of?"*, *"find upgrades for my Disco playlist."* |
| **[rekordbox/version-finder](.agents/skills/rekordbox/version-finder/)** | Takes an `"Artist - Song Title"` query and scans the whole library for every version/edit/remix the user owns, printing a read-only table (Version, Format, Bitrate, BPM, Key, Playlists), one row per file. | The user wants to know what versions of a track they have — e.g. *"what versions of <artist - title> do I have?"*, *"what remixes of X are in my library?"*, *"do I have the extended mix of …?"* |
| **[rekordbox/rekordbox-metadata](.agents/skills/rekordbox/rekordbox-metadata/)** | Cleans, identifies, enriches, and syncs music metadata: scans for missing/suspicious tags, parses filenames, looks up MusicBrainz + Discogs, scores candidates, and applies only user-approved changes to embedded audio tags (backup + audit log), then guides rekordbox's Reload Tag sync. Never touches the rekordbox DB, cues, grids, playlists, or My Tags. | The user wants to fix, clean, enrich, or complete track metadata/tags — e.g. *"fix the metadata on these tracks"*, *"my titles are full of underscores and WEB 320 junk"*, *"find the proper artist/title for these files"*, *"tag my untagged downloads"*, *"sync the fixed tags into rekordbox."* |
| **[rekordbox/track-centralizer](.agents/skills/rekordbox/track-centralizer/)** | Locates every file the collection points at, moves them all into one user-chosen folder (collision-safe, never renames, undo manifest, DB never written), then walks the user through re-linking in rekordbox via Auto Relocate. | The user wants their music files gathered into one place — e.g. *"centralize my collection into one folder"*, *"my tracks are scattered across Downloads and old drives, consolidate them"*, *"move everything rekordbox uses into ~/Music so I can back it up."* |
| **[utils/audio-converter](.agents/skills/utils/audio-converter/)** | Converts audio files between WAV, AIFF, and AAC using macOS's built-in `afconvert` (no installs). Touches files only; refuses lossy→lossless and same-format conversions. | The user wants to convert, transcode, or change the format of audio files — e.g. *"convert these AIFFs to WAV"*, *"compress this folder to AAC for the CDJs"*, *"shrink these files."* (MP3 not supported yet.) |
| **[utils/track-downloader](.agents/skills/utils/track-downloader/)** | Downloads a YouTube link's best audio as WAV straight into `~/Music/Track Collection` (or `--out-dir`), named `<title> [<video id>].wav`; idempotent by video id, never overwrites, then prompts the user to import into rekordbox. | The user wants a YouTube track downloaded for their library — e.g. *"download this track"*, *"grab this link as a wav"*, *"add this song to my collection."* |
| **[utils/vocals](.agents/skills/utils/vocals/)** | Downloads a YouTube link's audio with yt-dlp, splits it with demucs (two-stems), and leaves an isolated vocal WAV at a chosen `--out-dir`, printing its absolute path. | The user wants vocals pulled from a YouTube video — e.g. *"grab the vocals from this link"*, *"rip an acapella of <url>"*, *"I need a vocal sample from this song"*, *"split this into stems and give me the vocal."* |

Ableton has no skills yet — see
[.agents/skills/ableton/README.md](.agents/skills/ableton/README.md) for the
scaffold and ideas.

When a skill matches, load its `SKILL.md` and follow it — the skill's own docs
are authoritative for its workflow, schema, and guardrails.

## How it's laid out

- Canonical skill files live under `.agents/skills/<domain>/<name>/` — **edit
  these.**
- Code shared across a domain's skills lives **once** under
  `.agents/shared/<domain>/`. For rekordbox that is `rb_common.py` (DB access,
  matching, ranking), `resolve_playlist.py`, `apply_core.py` (the write
  engine), and the canonical `references/data-model.md`. Do not re-copy these
  into a skill. Skill scripts reach them by putting the shared dir on
  `sys.path` (see *Adding a new skill*) — plain Python imports, no symlinks.
- A committed symlink `.claude/skills/<name> ->
  ../../.agents/skills/<domain>/<name>` is what Claude Code's skill discovery
  scans (it only looks in `.claude/skills/`, not `.agents/`). Symlink names are
  flat; the domain lives in the target path. Edits under `.agents/skills/`
  take effect immediately — never edit through the symlink path.
- Discovery symlinks resolve on macOS/Linux but **not Windows** — the repo's
  only Windows limitation.

## Adding a new skill

1. **Create the skill folder** at `.agents/skills/<domain>/<name>/` containing:
   - `SKILL.md` — agent execution instructions, with YAML frontmatter (`name`
     and a thorough `description`; the description is what triggers routing,
     so spell out what the skill does and when to use it, with example user
     phrasings).
   - `README.md` — always include one, written for a human: what it does,
     prerequisites, usage, safety notes.
   - `scripts/` for any code. **Reuse the domain's shared helpers** in
     `.agents/shared/<domain>/` rather than copying them. Put the shared dir
     on `sys.path` first with this stanza, then import normally:

     ```python
     import sys
     from pathlib import Path
     sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "<domain>"))
     from rb_common import get_db, track_facts  # etc.
     ```

     `parents[4]` resolves `.agents/skills/<domain>/<name>/scripts/<file>.py`
     up to `.agents/`, so `.agents/shared/<domain>/` is found from any skill,
     run from anywhere. `references/` holds deeper notes; link the domain's
     shared `references/` docs instead of restating them.
2. **Create the discovery symlink** (relative target so it resolves on any
   clone):

   ```sh
   ln -s ../../.agents/skills/<domain>/<name> .claude/skills/<name>
   ```

3. **Register it** — add a row to the *Skills & routing* table above and an
   entry to `README.md`'s *Available skills* list.
4. **Verify**: `readlink .claude/skills/<name>` resolves, and the skill loads
   when you launch Claude in the repo.

## Working in this repo

- **Launch**: start the agent in this repo so the `.claude/skills/` symlinks
  load the skills. For the rekordbox skills, also grant library access:

  ```sh
  claude --add-dir ~/Library/Pioneer/rekordbox
  ```

- **Running a skill's scripts**: each script puts its shared dir on `sys.path`
  via a `__file__`-relative stanza, so it runs from any working directory:

  ```sh
  python3 .agents/skills/rekordbox/playlist-dedupe/scripts/test_matcher.py
  ```

- **Dependencies**: rekordbox DB skills need
  `pip3 install pyrekordbox --break-system-packages` (`master.db` is encrypted
  SQLCipher — always open it through `pyrekordbox`, never plain `sqlite3`).
  The vocals util needs `yt-dlp`, `ffmpeg` (brew) and `demucs` (pip). The
  audio-converter needs nothing (macOS built-ins).
- **Tests**: each skill with logic worth testing has a self-check script that
  needs no database or network — run them after changing shared code:

  ```sh
  python3 .agents/skills/rekordbox/playlist-dedupe/scripts/test_matcher.py
  python3 .agents/skills/rekordbox/upgrade-finder/scripts/test_matcher.py
  python3 .agents/skills/rekordbox/version-finder/scripts/test_matcher.py
  python3 .agents/skills/rekordbox/track-centralizer/scripts/test_centralize.py
  python3 .agents/skills/utils/audio-converter/scripts/test_convert.py
  python3 .agents/skills/utils/track-downloader/scripts/test_downloader.py
  ```
