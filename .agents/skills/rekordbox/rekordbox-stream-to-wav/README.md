# rekordbox-stream-to-wav

Turns the **Spotify and SoundCloud tracks in a rekordbox playlist into WAV
files** from YouTube, so the playlist works offline and on CDJs. Each WAV takes
its streaming track's spot in the playlist.

## What it does

1. Asks which playlist, then lists its streaming entries. rekordbox encrypts
   Spotify artist and title fields, so those names come from Spotify's public
   embed page.
2. Searches YouTube for each track. It prefers a real extended mix, then an
   official upload whose length matches. It rejects other remixers' versions,
   lyric videos, live sets, and slowed or sped-up uploads.
3. Shows you every match to approve, override, or skip. A title match with the
   wrong length is only a suggestion, never downloaded unless you say yes.
4. Downloads the approved matches with [track-downloader](../../utils/track-downloader/)
   into `~/Music/Track Collection`.
5. With rekordbox closed, imports the WAVs and puts each one in place of its
   streaming entry, or appends them if you prefer.

## Safety

- Read-only until the last step. rekordbox can stay open until then.
- Before writing: a permanent copy of `master.db` in `rekordbox-db-backups/`,
  and an in-app snapshot of the playlist under **Claude Backups**.
- Only the chosen playlist changes. The streaming tracks stay in your
  collection and in other playlists.
- After importing, analyze the new tracks in rekordbox (BPM, key, waveform).

Quality note: YouTube audio is lossy (~130 kbps Opus) inside a WAV. It's the
best YouTube offers, not studio lossless. Only for content you have the rights
to download.

## Prerequisites

- `pip3 install pyrekordbox --break-system-packages`
- `brew install yt-dlp ffmpeg`

## Usage

Ask in plain language: *"replace the streaming tracks in my halloween playlist
with WAVs"*. Or run the steps yourself:

```sh
python3 scripts/find_streams.py <playlist_id> -o /tmp/stream-to-wav/manifest.json
python3 scripts/search_youtube.py /tmp/stream-to-wav/manifest.json
python3 scripts/set_pick.py /tmp/stream-to-wav/manifest.json 12 <video id>   # optional
python3 scripts/download_picks.py /tmp/stream-to-wav/manifest.json
python3 scripts/apply_wavs.py /tmp/stream-to-wav/manifest.json           # dry run
python3 scripts/apply_wavs.py /tmp/stream-to-wav/manifest.json --apply   # rekordbox closed
```

Self-check (no database or network): `python3 scripts/test_stream_to_wav.py`
