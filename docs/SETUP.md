# Setup

How to get the music-agent-kit skills working in your own Claude Code.

Works on macOS. Linux works for the skills that don't need rekordbox. Windows
isn't supported: skill discovery uses symlinks that don't resolve there.

## 1. Install Claude Code

Follow [claude.com/claude-code](https://claude.com/claude-code), then check it
runs:

```sh
claude --version
```

## 2. Install what the skills need

| Skills | Needs | Install |
| --- | --- | --- |
| Every rekordbox skill | `pyrekordbox` (reads rekordbox's encrypted `master.db`) | `pip3 install pyrekordbox --break-system-packages` |
| track-downloader, rekordbox-stream-to-wav, vocals | `yt-dlp`, `ffmpeg` | `brew install yt-dlp ffmpeg` |
| vocals | `demucs` | `pip3 install demucs` |
| audio-converter | nothing (uses macOS `afconvert`) | |

The rekordbox skills expect rekordbox 6 or 7 with its library in the default
place, `~/Library/Pioneer/rekordbox`. Downloads go to `~/Music/Track Collection`,
which is created if it's missing.

Check `pyrekordbox` can open your library:

```sh
python3 -c "from pyrekordbox import Rekordbox6Database as D; print(D().get_content().count(), 'tracks')"
```

If that fails with a key or decryption error, see the
[pyrekordbox docs](https://pyrekordbox.readthedocs.io) for your rekordbox
version.

## 3. Get the skills

```sh
git clone https://github.com/SammyEl-Sherif/music-agent-kit.git
cd music-agent-kit
```

### Option A: use them inside the repo

Launch Claude from the repo. Add the rekordbox folder so Claude can read your
library:

```sh
claude --add-dir ~/Library/Pioneer/rekordbox
```

The skills load from the repo's `.claude/skills/` folder. Type `/` in Claude to
see them.

### Option B: use them from any folder

Link the skills you want into your global skills folder. Run this from the
repo:

```sh
mkdir -p ~/.claude/skills
for s in .claude/skills/*; do
  ln -s "$(cd "$s" && pwd -P)" ~/.claude/skills/"$(basename "$s")"
done
```

Keep the cloned repo where it is. The links point into it, and skills share
code under `.agents/shared/`. Copying a single skill folder on its own won't
work.

## 4. Use them

Ask in plain language, for example:

- *"Replace the streaming tracks in my halloween playlist with WAVs"*
  (rekordbox-stream-to-wav)
- *"Dedupe my Disco playlist"* (playlist-dedupe)
- *"Download this track: <YouTube link>"* (track-downloader)

Any skill that changes your rekordbox library asks you to quit rekordbox first.
It saves a full copy of `master.db` in
`~/Library/Pioneer/rekordbox/rekordbox-db-backups/` before writing.

## Updating

```sh
cd music-agent-kit && git pull
```

Linked skills (option B) update with the repo.

## Check it works

Each skill with logic has a self-check that needs no library or network:

```sh
python3 .agents/skills/rekordbox/rekordbox-stream-to-wav/scripts/test_stream_to_wav.py
python3 .agents/skills/utils/track-downloader/scripts/test_downloader.py
```

Only download content you have the rights to.
