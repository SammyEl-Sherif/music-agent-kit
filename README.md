# music-agent-kit

A git-backed context repo of [Claude Code](https://claude.com/claude-code)
skills for doing things with music — managing a
[rekordbox](https://rekordbox.com) library, Ableton workflows, and standalone
audio utilities. Clone it, launch Claude inside it, and ask in plain language.

The rekordbox skills are adapted from
[sean-a-Wilson/rekordbox-skills](https://github.com/sean-a-Wilson/rekordbox-skills)
by Sean Wilson ([@moontripdisco](https://www.instagram.com/moontripdisco)) —
credit to him for the design and implementation.

> macOS / Linux only. Skill **discovery** relies on `.claude/skills/` symlinks
> committed to the repo, which don't resolve on Windows.

## Available skills

### rekordbox

- **[playlist-dedupe](.agents/skills/rekordbox/playlist-dedupe/)** — find and
  prune duplicate tracks in a playlist (or the whole library), keeping the
  best-quality copy. Version-aware; reviews every group with you before
  changing anything.
- **[upgrade-finder](.agents/skills/rekordbox/upgrade-finder/)** — scan a
  playlist for low-bitrate tracks and find higher-quality copies of the same
  recording already in your library. Read-only report, optional apply step.
- **[version-finder](.agents/skills/rekordbox/version-finder/)** — ask "what
  versions of this track do I have?" and get a read-only table of every
  version, edit, and remix in your library. Changes nothing.
- **[rekordbox-metadata](.agents/skills/rekordbox/rekordbox-metadata/)** —
  clean, identify, and enrich track metadata: scan for broken tags, parse
  messy filenames, look up MusicBrainz/Discogs, review and approve proposals,
  apply to audio tags with backups, then sync into rekordbox via Reload Tag.

### ableton

- Scaffolded, nothing here yet — see
  [the folder README](.agents/skills/ableton/README.md) for conventions and
  ideas on deck.

### utils

- **[audio-converter](.agents/skills/utils/audio-converter/)** — convert audio
  between WAV, AIFF, and AAC using macOS's built-in `afconvert` (nothing to
  install). Non-destructive; refuses lossy→lossless and same-format
  conversions.
- **[vocals](.agents/skills/utils/vocals/)** — give it a YouTube link; yt-dlp
  downloads the audio, demucs splits it, and you get an isolated vocal WAV at
  a path you choose (`--out-dir`).

Each skill's own README explains what it does and how to use it.

## How it's laid out

- Canonical skill files live under `.agents/skills/<domain>/<name>/`
  (domains: `rekordbox/`, `ableton/`, `utils/`).
- Helper code shared within a domain lives once under
  `.agents/shared/<domain>/`; skill scripts import it via `sys.path` — one
  copy on disk, no symlinks.
- Committed symlinks `.claude/skills/<name> ->
  ../../.agents/skills/<domain>/<name>` are what Claude Code discovers (it
  only scans `.claude/skills/`).

See [AGENTS.md](AGENTS.md) for the full conventions, routing table, and how to
add a skill.

## Getting started

1. Clone this repo and install [Claude Code](https://claude.com/claude-code).
2. Install what the skills you'll use need:

   ```sh
   pip3 install pyrekordbox --break-system-packages   # rekordbox DB skills
   brew install yt-dlp ffmpeg && pip3 install demucs  # vocals util
   ```

3. Launch Claude from inside the repo (add your rekordbox library dir if
   you'll use those skills):

   ```sh
   claude --add-dir ~/Library/Pioneer/rekordbox
   ```

4. Ask for the thing — e.g. *"dedupe my 'Disco' playlist"* or *"grab the
   vocals from this YouTube link and put them in ~/Music/samples."*
