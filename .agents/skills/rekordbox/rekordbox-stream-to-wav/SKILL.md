---
name: rekordbox-stream-to-wav
description: >-
  Replace the Spotify and SoundCloud streaming tracks in a rekordbox playlist
  with WAV files downloaded from YouTube, so the playlist works offline and on
  CDJs. ASKS which playlist first. Reads the encrypted master.db (read-only),
  lists the playlist's streaming entries, names the Spotify ones (rekordbox
  encrypts their artist/title) from Spotify's public embed page, searches
  YouTube for each track preferring a real extended mix, then an official
  upload whose length matches, and rejects other remixers' versions, lyric
  videos, live sets and slowed/sped-up uploads. Every pick is reviewed with the
  user before downloading. Downloads via the track-downloader skill into
  ~/Music/Track Collection, then -- with rekordbox closed, after a permanent DB
  backup and an in-app playlist snapshot -- imports the WAVs and puts each one in
  its streaming entry's position (or appends them, if the user prefers). Use
  whenever the user wants streaming tracks in a playlist turned into real
  files: "download the Spotify tracks in my playlist", "replace the SoundCloud
  tracks with WAVs", "make this playlist work offline", "get local copies of
  the streaming tracks in <playlist>", "convert my streaming tracks to files",
  "stream to wav". Only for content the user has the rights to download.
---

# rekordbox-stream-to-wav

Turn a playlist's **Spotify and SoundCloud entries into WAV files**. Find each
track on YouTube, review the matches with the user, download them, and swap
them into the playlist in the same positions.

Scripts live in `scripts/` (run with `python3`, from any directory). They use
the shared rekordbox helpers in `.agents/shared/rekordbox/` and the
`utils/track-downloader` skill for downloads. Each step reads or writes one
manifest JSON; keep it in a fresh temp folder, e.g. `/tmp/stream-to-wav/`.

Needs `pyrekordbox` (`pip3 install pyrekordbox --break-system-packages`),
`yt-dlp` and `ffmpeg` (`brew install yt-dlp ffmpeg`).

## Workflow

### 1. Ask which playlist

Always ask. Don't assume one from earlier in the conversation. Then resolve the
name:

```
python3 .agents/shared/rekordbox/resolve_playlist.py "<name>"
```

If several match, show their paths and track counts and ask which one. Never
pick a playlist under `Claude Backups`.

### 2. List the streaming tracks (read-only, rekordbox can stay open)

```
python3 scripts/find_streams.py <playlist_id> -o /tmp/stream-to-wav/manifest.json
```

It prints every SoundCloud and Spotify entry with its position. If there are
none, say so and stop. A track it couldn't name is skipped. Say which ones.

### 3. Search YouTube

```
python3 scripts/search_youtube.py /tmp/stream-to-wav/manifest.json
```

Each track ends up with one of:
- **pick**: same song and version, and the length checks out. A real extended
  mix (at least 20s longer than the streaming copy) beats the original.
- **suggestion**: the title matches but the length doesn't. rekordbox's stored
  length is sometimes wrong for SoundCloud tracks (about 600s), but a
  suggestion can also be the wrong song. Never download one without the user
  saying yes.
- **no confident match**: often a SoundCloud-only remix.

### 4. Review every pick with the user

Read the manifest and show one table: position, track, the YouTube title and
duration of the pick, and the link `https://youtu.be/<id>`. Mark extended mixes,
suggestions (with both lengths), and tracks with no match. Look over the
candidates yourself too. Flag anything that looks off, like a different
remixer, a lyric or visualizer upload when an official audio exists, or an
"Extended Mix" only seconds longer than the original (probably mislabeled).

Change picks with:

```
python3 scripts/set_pick.py manifest.json --accept 5,39           # take suggestions
python3 scripts/set_pick.py manifest.json 12 <video id or URL>    # override
python3 scripts/set_pick.py manifest.json 12 none                 # skip
python3 scripts/search_youtube.py manifest.json --only 12         # search again
```

`--title "Artist - Title"` on an override sets the name rekordbox will show.
Picks default to the clean "Artist - Title", since YouTube titles often leave
out the artist.

Remind the user once that downloading is only for content they have the rights
to.

### 5. Download

```
python3 scripts/download_picks.py /tmp/stream-to-wav/manifest.json
```

This calls track-downloader with every pick. WAVs land in
`~/Music/Track Collection` as `<title> [<video id>].wav`, and a video that's
already there is skipped. Files only, so rekordbox can stay open. Report any
`MISSING` line.

### 6. Ask how to add them, then get rekordbox closed

Ask: **replace** (default: each WAV takes its streaming entry's spot, and the
streaming entry leaves this playlist) or **append** (WAVs at the end, streaming
entries stay). Either way only this playlist changes. The streaming tracks stay
in the collection and in other playlists.

Writing while rekordbox is open can corrupt the library. Ask the user to quit
it, and check with `pgrep -x rekordbox` before going on.

### 7. Dry run, then apply

```
python3 scripts/apply_wavs.py manifest.json                  # dry run
python3 scripts/apply_wavs.py manifest.json --apply [--mode append]
```

The dry run refuses if a WAV is missing or the playlist changed since step 2.
If the playlist changed, run step 2 again. On `--apply` it:
1. refuses if rekordbox is running
2. copies `master.db` into `rekordbox-db-backups/` beside it (kept forever)
3. snapshots the playlist under `Claude Backups` in rekordbox
4. imports each WAV (reusing it if it's already in the collection) and adds it
   above its streaming entry, then commits
5. removes the streaming entries the way rekordbox does (tombstoned, so Cloud
   Library Sync keeps the removal) and renumbers
6. checks that positions are contiguous and every WAV is present

### 8. Report

Tell the user:
- how many were replaced, the tracks left as streaming (and why), and the backup path
- to open rekordbox and **analyze the new tracks**: imported files have no BPM,
  key or waveform until then
- if asked about quality: YouTube audio is lossy (~130 kbps Opus) in a WAV
  container. It's the best YouTube has, not studio lossless.

## Guardrails

- Read-only until step 7. Only `apply_wavs.py --apply` writes the database, and
  only with rekordbox closed and a fresh backup taken.
- Never download a suggestion, or anything else, the user hasn't seen.
- Never touches other playlists, cue points, beat grids, or the streaming
  tracks' collection entries. Never deletes or overwrites audio files.
- Spotify names come from an unofficial page that may change. If names come
  back empty, say so. Don't guess.

Self-check (no database or network): `python3 scripts/test_stream_to_wav.py`
