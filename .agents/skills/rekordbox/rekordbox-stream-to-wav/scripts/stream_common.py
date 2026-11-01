"""Pure helpers shared by the rekordbox-stream-to-wav scripts.

Nothing here opens the rekordbox database or the network, so it is covered by
test_stream_to_wav.py without either.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_LIBRARY = "~/Music/Track Collection"

# rekordbox stores streaming tracks as DjmdContent rows whose FolderPath is a
# service URI instead of a file path.
STREAM_PREFIXES = {
    "spotify:track:": "spotify",
    "soundcloud:tracks:": "soundcloud",
}

# rekordbox encrypts Spotify artist/title fields with this prefix.
ENCRYPTED_PREFIX = "$A7:"

# Words that mark a YouTube upload as something other than the studio track.
JUNK_WORDS = ("live", "slowed", "sped up", "reverb", "1 hour", "full set",
              "dj set", "mashup", "karaoke", "instrumental", "cover", "reaction",
              "lyrics")
EXTENDED_WORDS = ("extended", "club mix", "12\"", "night version")
# Words that make a bracketed part of a title a version tag, e.g. "(X Remix)".
VERSION_WORDS = {"remix", "edit", "mix", "flip", "rework", "dub", "bootleg", "vip"}
# Uploader promo text in SoundCloud titles, dropped before searching.
PROMO = re.compile(r"\b(free (download|dl)|out now|with no outro|no outro|premiere)\b.*$", re.I)

# Words too generic to prove two titles are the same song.
GENERIC_WORDS = {"the", "a", "an", "and", "of", "to", "in", "on", "my", "me", "i", "u",
                 "feat", "ft", "featuring", "with", "x", "vs", "mix", "remix", "edit",
                 "version", "original", "extended", "radio", "official", "audio",
                 "video", "visualizer", "lyric", "music", "hd", "4k", "full", "stream",
                 "remaster", "remastered", "flip", "rework", "dub", "this", "club"}
MIN_COVERAGE = 0.8
# An "extended" upload must run at least this much longer than the original.
EXTENDED_MIN_GAIN = 20


def stream_source(folder_path: str | None) -> tuple[str, str] | None:
    """('spotify', id) or ('soundcloud', id) for a streaming row, else None."""
    for prefix, service in STREAM_PREFIXES.items():
        if (folder_path or "").startswith(prefix):
            return service, folder_path[len(prefix):]
    return None


def readable(text: str | None) -> str:
    """The field as plain text, or '' if rekordbox encrypted it."""
    text = (text or "").strip()
    return "" if text.startswith(ENCRYPTED_PREFIX) else text


def clean_title(title: str) -> str:
    """The title without uploader promo text like 'FREE DOWNLOAD'."""
    return PROMO.sub("", title or "").strip(" -|")


def display_name(artist: str, title: str) -> str:
    """'Artist - Title'. A title that already contains ' - ' carries its own
    artist (SoundCloud's artist field is often just the uploader)."""
    artist, title = artist.strip(), clean_title(title)
    if not artist or " - " in title or title.lower().startswith(artist.lower()):
        return title
    return f"{artist} - {title}"


def search_query(artist: str, title: str) -> str:
    """A YouTube search string from the display name, brackets and dashes flattened."""
    text = display_name(artist, title)
    text = re.sub(r"[()\[\]{}|｜]", " ", text)
    text = re.sub(r"\s+-\s+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(text: str) -> set[str]:
    """Distinctive lowercase words in a title: no generic mix words or bare numbers."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", ""))
    return {w for w in words if w not in GENERIC_WORDS and not w.isdigit()}


def drop_feat(text: str) -> str:
    """Remove featured-artist credits, which uploads often leave out."""
    return re.sub(r"[(\[]?\b(feat|ft|featuring)\b\.?[^)\]]*[)\]]?", " ", text or "", flags=re.I)


def coverage(want: str, got: str) -> float:
    """Share of `want`'s distinctive words that appear in `got` (1.0 if none)."""
    need = title_tokens(drop_feat(want))
    return len(need & title_tokens(got)) / len(need) if need else 1.0


def foreign_version(want: str, got: str) -> bool:
    """True if `got` names a remix or edit by someone `want` doesn't mention, e.g.
    the track is 'Da Fonk' and the upload is 'Da Fonk (Solarce Brothers Remix)'.
    'No Place (Essaii Jersey Club Remix)' still matches 'No Place (Essaii Remix)'."""
    have = title_tokens(want)
    for part in re.findall(r"[(\[]([^)\]]*)[)\]]", got or ""):
        part = drop_feat(part)
        if VERSION_WORDS & set(re.findall(r"[a-z]+", part.lower())):
            names = title_tokens(part)
            if names and not names & have:
                return True
    return False


def score_candidate(cand: dict, length: int, want: str = "") -> float:
    """Rank one YouTube result for a track of `length` seconds. Higher is better.

    The upload must be the same song and version as `want` (the track title).
    Among those it prefers a real extended mix (clearly longer than the
    streaming copy), then an official upload whose duration matches. Long mixes,
    live sets and edited uploads (slowed, sped up, lyric videos) sink. This only
    suggests a pick; the agent reviews every one with the user.
    """
    title = (cand.get("title") or "").lower()
    channel = (cand.get("channel") or "").lower()
    dur = int(cand.get("duration") or 0)
    score = 0.0

    if not dur or dur > 15 * 60:
        return -100.0
    if want:
        if coverage(want, f"{cand.get('title')} {cand.get('channel')}") < MIN_COVERAGE:
            return -50.0
        if foreign_version(want, cand.get("title") or ""):
            return -50.0
    if any(w in title for w in JUNK_WORDS):
        score -= 30
    if channel.endswith("- topic") or "official" in title or "official" in channel:
        score += 8

    labelled_ext = any(w in title for w in EXTENDED_WORDS)
    if not length:
        return score + (15 if labelled_ext else 0)
    diff = dur - length
    if labelled_ext and EXTENDED_MIN_GAIN <= diff <= 6 * 60:
        score += 35
    elif abs(diff) <= 5:
        score += 20
    else:
        score -= min(abs(diff) / 10, 25)
    return score


def rank_candidates(cands: list[dict], length: int, want: str = "") -> list[dict]:
    """Candidates with a 'score' field, best first. `want` is the track's title."""
    scored = [{**c, "score": round(score_candidate(c, length, want), 1)} for c in cands]
    return sorted(scored, key=lambda c: c["score"], reverse=True)


def find_wav(library: Path, video_id: str) -> Path | None:
    """The track-downloader WAV for this video id. Matches on the
    ' [<id>].wav' suffix without globbing, since '[' is a glob character."""
    suffix = f" [{video_id}].wav"
    hits = sorted(p for p in library.iterdir() if p.is_file() and p.name.endswith(suffix))
    return hits[0] if hits else None


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_manifest(path: str | Path, manifest: dict) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
