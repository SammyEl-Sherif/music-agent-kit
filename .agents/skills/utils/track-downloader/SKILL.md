---
name: track-downloader
description: >-
  Take a YouTube link (or several) and download the highest-quality audio as a
  WAV straight into the user's central music library folder, ~/Music/Track
  Collection by default (--out-dir overrides). Uses the yt-dlp CLI (bestaudio +
  ffmpeg WAV extraction, metadata embedded), names files "<title> [<video
  id>].wav" to match the library's existing convention, and is idempotent by
  video id -- a link already downloaded is skipped and its existing path
  printed. Never overwrites or deletes anything, prints each final absolute
  path as a "TRACK: <path>" line, and ends by reminding the user to import the
  new file into rekordbox (it NEVER touches the rekordbox database).
  Standalone: files only. Use whenever the user wants a YouTube track
  downloaded for their library -- e.g. "download this track", "grab this
  YouTube link as a wav", "add this song to my collection", "rip the audio
  from this video", "download these links into my Track Collection" --
  including loose phrasings like "get me this song". Only for content the user
  has the rights to download.
---

# track-downloader

Take a **YouTube link**, download its best audio via **yt-dlp**, extract it to
**WAV**, and land it in the user's central library folder —
**`~/Music/Track Collection`** by default. The script prints each final path as
a `TRACK: <abs path>` line; relay it to the user.

Honest quality note: YouTube's best audio stream is lossy (~130 kbps Opus).
The WAV is a faithful, rekordbox-friendly container of that stream — the best
YouTube offers, not studio lossless. Mention this only if the user asks about
quality.

## Prerequisites

- `yt-dlp` — `brew install yt-dlp` (or `pip3 install yt-dlp`)
- `ffmpeg` — `brew install ffmpeg` (yt-dlp uses it to extract WAV)

The script checks both and prints install hints if missing.

## The workflow

### Step 1 — Confirm the link(s)

Get the YouTube URL(s). The destination defaults to `~/Music/Track Collection`
— only ask if the user indicates somewhere else. Remind the user (once,
briefly) this is for content they have the rights to download.

### Step 2 — Run it

```
python3 scripts/grab_track.py "<youtube-url>" [more urls...]
```

Options:
- `-o / --out-dir <dir>` — destination folder (default:
  `~/Music/Track Collection`). Created if it doesn't exist.
- `--no-reveal` — skip the Finder reveal of the downloaded file.

Behavior worth relaying:
- Files are named `<title> [<video id>].wav`, matching the yt-dlp naming
  already used across the library.
- **Idempotent**: if a WAV with that video id already exists in the folder,
  the download is skipped and the existing path printed — say so rather than
  presenting it as newly downloaded.
- Playlist URLs download only the linked video (`--no-playlist`). If the user
  explicitly wants a whole playlist, run the script once per video URL.

### Step 3 — Prompt the user to import into rekordbox

The file is on disk but **rekordbox doesn't know about it yet** — this skill
never touches the database. Tell the user to import it: drag the file from
Finder into the rekordbox Collection (or a playlist), or use rekordbox's
import. Since it's already inside the central library folder, no further
moving or relocating is ever needed.

## Guardrails

- **Never touches the rekordbox database** — importing is the user's move.
- **Never overwrites or deletes** — an unexpected name clash gets a
  ` (2)` suffix (safe: the file isn't in rekordbox yet).
- Downloads go to a temp dir first; only the finished WAV is moved into the
  library, so a failed download leaves no partial file behind.
- Don't loosen `--no-playlist` yourself; a playlist link that fans out into
  dozens of downloads should be the user's explicit choice.
- Only for content the user has the rights to download.
