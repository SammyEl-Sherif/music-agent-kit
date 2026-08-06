"""Filename / title cleaning for rekordbox-metadata.

Pure string logic, no I/O — everything here is deterministic and covered by
test_cleaning.py. The contract: never discard remix/edit/live/version
information, never apply title case, never invent data. We only normalize
separators, strip technical junk, and split the pieces apart.
"""
from __future__ import annotations

import re

# Words that, when present in a bracketed group or trailing segment, mark it as
# version information to PRESERVE (moved to version_info, never deleted).
VERSION_TRIGGERS = {
    "mix", "remix", "remixes", "edit", "re-edit", "reedit", "dub", "version",
    "instrumental", "acapella", "accapella", "cappella", "vip", "live",
    "bootleg", "mashup", "rework", "refix", "flip", "remaster", "remastered",
    "acoustic", "demo", "dubplate", "cover", "interpretation",
}

# Generic mix descriptors: "(Club Mix)" has no remixer; "(Eric Prydz Remix)" does.
GENERIC_MIX_WORDS = {
    "original", "extended", "club", "radio", "vocal", "dub", "instrumental",
    "vip", "alt", "alternative", "short", "long", "full", "clean", "dirty",
    "official", "album", "single", "classic", "old", "new", "main", "stereo",
    "mono", "the", "a", "re", "edit", "mix", "remix", "version", "remaster",
    "remastered", "bootleg", "rework", "refix", "flip", "acoustic", "demo",
    "7\"", "12\"", "7''", "12''", "7", "12", "inch",
}

# Standalone trailing tokens that are technical noise, not music info.
TECH_TOKENS = {
    "web", "webrip", "rip", "vinylrip", "cdrip", "promo", "retail", "cbr",
    "vbr", "mp3", "flac", "wav", "m4a", "aac", "aiff", "hq", "hd", "4k",
    "128", "160", "192", "224", "256", "320", "kbps",
}

# A bracketed group is junk (removed entirely) if it contains one of these.
JUNK_GROUP_RE = re.compile(
    r"official\s+(?:video|audio|music\s+video|visualizer)|lyric\s+video|"
    r"lyrics?\s+video|visualizer|audio\s+only|free\s+(?:dl|download)|"
    r"out\s+now|premiere|full\s+stream|nocopyright|copyright\s+free|"
    r"\d{2,4}\s*kbps|www\.|\.com|\.net|\.org|monstercat\s+release",
    re.IGNORECASE,
)

URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b\S+\.(?:com|net|org|info)\b\S*", re.IGNORECASE)
# yt-dlp-style video-id suffix: an 11-char [id] bracket group (e.g. [kl0wXWFppQo])
YOUTUBE_ID_RE = re.compile(r"[(\[][A-Za-z0-9_-]{11}[)\]]")
FEAT_RE = re.compile(r"\b(?:feat\.?|ft\.?|featuring)\s+(.+)", re.IGNORECASE)
GROUP_RE = re.compile(r"[(\[]([^()\[\]]+)[)\]]")
TRACKNUM_RE = re.compile(
    r"^\s*(?:\d{1,2}[-.]\d{2}[\s\-‐‒–—._)\]]+|\d{1,3}\s*[-‐‒–—._)\]]+\s*)"
)
KBPS_RE = re.compile(r"^\d{2,4}\s?kbps$", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s\-_,.]+", text.lower()) if t]


def normalize_separators(s: str) -> str:
    s = s.replace("_", " ")
    for dash in "‒–—‐":
        s = s.replace(dash, "-")
    s = re.sub(r"\s*[|•]\s*", " - ", s)
    s = re.sub(r"\s*-\s*-+\s*", " - ", s)  # repeated hyphens -> one separator
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def strip_track_number(s: str) -> str:
    """Remove leading filename numbering ("01 - ", "01.", "1-01 ") but keep
    numbers that are part of the title ("99 Luftballons" has no separator)."""
    return TRACKNUM_RE.sub("", s)


def strip_junk(s: str) -> str:
    s = URL_RE.sub(" ", s)

    def _yt_id(m: re.Match) -> str:
        inner = m.group(0)[1:-1]
        # A plain single-case word ("[COUNTRYBOYZ]") is title text, not an id;
        # real video ids mix case, digits, or -_ .
        if inner.isalpha() and (inner.islower() or inner.isupper() or inner.istitle()):
            return m.group(0)
        return " "

    s = YOUTUBE_ID_RE.sub(_yt_id, s)
    s = GROUP_RE.sub(lambda m: " " if JUNK_GROUP_RE.search(m.group(1)) else m.group(0), s)
    # Peel technical tokens off the end (WEB 320, FLAC, 320kbps ...)
    parts = s.strip().split(" ")
    while parts:
        tail = parts[-1].lower().strip("[]()")
        if tail in TECH_TOKENS or KBPS_RE.match(tail):
            parts.pop()
        else:
            break
    s = " ".join(parts)
    s = re.sub(r"\(\s*\)|\[\s*\]", " ", s)  # empty groups left behind
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s.strip()


def _is_version_group(text: str) -> bool:
    return any(t in VERSION_TRIGGERS for t in _tokens(text))


def _extract_remixer(version_text: str) -> str:
    """"Eric Prydz Remix" -> "Eric Prydz"; "Club Mix" -> "" (generic)."""
    m = re.match(
        r"^(.*?)\s+(?:remix|rework|refix|flip|bootleg|edit|re-edit|dub|mix|version)e?s?$",
        version_text.strip(), re.IGNORECASE,
    )
    if not m:
        return ""
    prefix = m.group(1).strip()
    if not prefix:
        return ""
    if all(t in GENERIC_MIX_WORDS for t in _tokens(prefix)):
        return ""
    return prefix


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        key = it.lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def split_versions(title: str) -> tuple[str, list[str], str, str]:
    """Pull version groups, featured artists, and remixer out of a title.
    Returns (base_title, versions, featured, remixer)."""
    versions: list[str] = []
    featured = ""
    remixer = ""

    def _take(m: re.Match) -> str:
        nonlocal featured, remixer
        inner = m.group(1).strip()
        fm = FEAT_RE.match(inner)
        if fm:
            featured = fm.group(1).strip()
            return " "
        if _is_version_group(inner):
            versions.append(inner)
            if not remixer:
                remixer = _extract_remixer(inner)
            return " "
        return m.group(0)  # unknown group: leave it in the title untouched

    base = GROUP_RE.sub(_take, title)

    # Inline feat without parentheses: "Song feat. Kim"
    fm = FEAT_RE.search(base)
    if fm and not featured:
        featured = fm.group(1).strip()
        base = base[: fm.start()].rstrip(" -")

    # Trailing " - Club Mix" style segment
    if " - " in base:
        head, _, tail = base.rpartition(" - ")
        if tail and _is_version_group(tail):
            versions.append(tail.strip())
            if not remixer:
                remixer = _extract_remixer(tail.strip())
            base = head

    base = re.sub(r"\s+", " ", base).strip(" -")
    return base, _dedupe_preserve(versions), featured, remixer


def parse_filename(stem: str) -> dict:
    """Parse an audio filename stem into artist/title/version parts.

    Returns a dict with: artist, title, version_info, featured, remixer.
    Empty string means "could not determine" — never a guess.
    """
    # Track numbers are stripped from the RAW stem: "03_Artist" still shows its
    # "_" separator there, which normalization would blur into a plain space.
    s = strip_track_number(stem)
    s = normalize_separators(s)
    s = strip_junk(s)

    artist = ""
    rest = s
    if " - " in s:
        artist, _, rest = s.partition(" - ")
        artist = artist.strip()

    # feat. inside the artist half belongs to featured
    featured_from_artist = ""
    fm = FEAT_RE.search(artist)
    if fm:
        featured_from_artist = fm.group(1).strip()
        artist = artist[: fm.start()].rstrip(" ,-")

    title, versions, featured, remixer = split_versions(rest.strip())
    featured = featured or featured_from_artist

    # Duplicated artist prefix inside the title ("Artist - Artist - Title")
    if artist and title.lower().startswith(artist.lower() + " - "):
        title = title[len(artist) + 3:]

    return {
        "artist": artist,
        "title": title.strip(),
        "version_info": "; ".join(versions),
        "featured": featured,
        "remixer": remixer,
    }


def clean_tag_title(title: str) -> dict:
    """Clean an existing (possibly messy) title TAG the same way, without the
    artist-split step unless the tag itself embeds 'Artist - Title'."""
    s = strip_junk(normalize_separators(strip_track_number(title)))
    base, versions, featured, remixer = split_versions(s)
    return {
        "title": base.strip(),
        "version_info": "; ".join(versions),
        "featured": featured,
        "remixer": remixer,
        "embedded_artist": base.partition(" - ")[0].strip() if " - " in base else "",
    }


def proposed_display_title(cleaned_title: str, version_info: str) -> str:
    """The title we'd actually write: base plus the preserved version tag."""
    if not version_info:
        return cleaned_title
    parts = [v.strip() for v in version_info.split(";") if v.strip()]
    return cleaned_title + "".join(f" ({p})" for p in parts)
