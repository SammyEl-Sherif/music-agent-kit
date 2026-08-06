---
name: vocals
description: >-
  Take a YouTube link, download its audio with the yt-dlp CLI, and split it into
  stems with demucs (two-stems mode), leaving an isolated a-cappella vocal WAV
  on disk and printing its absolute path as the final line of output. Accepts an
  --out-dir option to choose where the vocal file lands (default: the current
  directory) and a --keep-instrumental flag to also keep the no-vocals stem.
  Use this whenever the user wants vocals pulled from a YouTube video -- e.g.
  "grab the vocals from this YouTube link", "rip an acapella of <url>",
  "isolate/extract the vocal from this video", "I need a vocal sample from this
  song", "split this YouTube track into stems and give me the vocal" -- including
  loose phrasings like "get me just the singing from this". Standalone: touches
  files only, never any DJ-software database. Only use on content the user has
  the rights to sample.
---

# vocals

Take a **YouTube link**, download the audio via **yt-dlp**, split it with
**demucs** (two-stems mode: vocals vs. everything else), and leave a raw vocal
WAV at a path of the user's choosing. The script prints the final absolute path
as its last line (`VOCALS: /path/to/file.wav`) — relay that path to the user so
they can go listen to the sample.

## Prerequisites

Three CLI tools; the script checks for each and prints install hints if missing:

- `yt-dlp` — `brew install yt-dlp` (or `pip3 install yt-dlp`)
- `ffmpeg` — `brew install ffmpeg` (yt-dlp uses it to extract WAV)
- `demucs` — `pip3 install demucs` (add `--break-system-packages` if pip refuses)

First demucs run downloads its model weights (~300 MB) automatically.

## The workflow

### Step 1 — Confirm the link and destination

Establish the YouTube URL and where the user wants the vocal file. If they
didn't say where, the default is the **current directory** — mention that rather
than silently choosing. Remind the user (once, briefly) that this is for content
they have the rights to sample.

### Step 2 — Run it

```
python3 scripts/vocals.py "<youtube-url>" --out-dir <dir>
```

Options:
- `-o / --out-dir <dir>` — where the vocal WAV is placed (default: `.`).
  Created if it doesn't exist.
- `--keep-instrumental` — also keep the `no_vocals` stem (the full backing
  track) next to the vocals.
- `--model htdemucs` — demucs model (default `htdemucs`; `htdemucs_ft` is
  slower but slightly cleaner).
- `--device cpu` — torch device (default `cpu`; Apple's MPS backend cannot run
  htdemucs, so leave the default on a Mac; pass `cuda` on an NVIDIA machine).

Demucs runs on CPU by default and takes roughly 1–3× the track length — tell
the user it may take a few minutes and let it run.

### Step 3 — Relay the result

The last line of output is `VOCALS: <absolute path>`. Give the user that path
(and the instrumental's, if kept). Offer to play it, open its folder, or feed
it into another skill (e.g. audio-converter to compress it).

## Guardrails

- **Files only, non-destructive.** Downloads and writes into a temp dir, then
  moves the requested outputs to `--out-dir`. Never touches any rekordbox or
  Ableton data, never overwrites existing files silently.
- **Rights.** Only use on content the user has the rights to download and
  sample; if a download fails with an age/region/paywall error, report it —
  don't try to work around it.
- **One video per run.** `--no-playlist` is forced, so a playlist URL downloads
  only the linked video.
- Vocal isolation is a model, not magic — heavily layered or effected vocals
  can come out with artifacts. Suggest `--model htdemucs_ft` if quality
  disappoints.
