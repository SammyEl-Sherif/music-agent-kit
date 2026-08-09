# track-downloader

Give it a YouTube link; get the highest-quality audio as a **WAV** dropped
straight into your central library folder (`~/Music/Track Collection` by
default), named to match the rest of your yt-dlp downloads:
`<title> [<video id>].wav`.

## What it does

- Downloads the **best audio stream** with `yt-dlp` and extracts to WAV with
  `ffmpeg`, embedding the video's metadata.
- **Idempotent** — the video id in the filename is the key; a link you've
  already downloaded is skipped and the existing file's path printed.
- Never overwrites or deletes anything; failed downloads leave nothing behind.
- Prints each result as `TRACK: <absolute path>` and reveals it in Finder.
- Files-only: it never touches the rekordbox database. After downloading,
  import the file into rekordbox yourself (drag it into the Collection) — it's
  already in the central folder, so nothing needs relocating.

Quality note: YouTube serves lossy audio (~130 kbps Opus); the WAV wraps that
stream losslessly. It's the best YouTube offers, not studio lossless.

## Prerequisites

- `brew install yt-dlp ffmpeg` (or `pip3 install yt-dlp`)

## Usage

Ask in plain language — *"download this track: <url>"* — or run directly:

```sh
python3 scripts/grab_track.py "https://www.youtube.com/watch?v=..." 
python3 scripts/grab_track.py "<url1>" "<url2>"          # several at once
python3 scripts/grab_track.py "<url>" -o ~/somewhere     # different folder
```

Playlist links download only the linked video, never the whole playlist.

Self-check (no network needed): `python3 scripts/test_downloader.py`

Only download content you have the rights to.
