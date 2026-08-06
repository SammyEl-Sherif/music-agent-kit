"""Embedded-tag read/write for rekordbox-metadata, via mutagen.

Only these logical fields are ever touched:
    title artist album albumartist remixer label genre year isrc

Nothing else — audio content, filenames, and every rekordbox-side field (cues,
grids, playlists, ratings, My Tags) live outside the audio file's tag block and
are structurally out of reach of this module.

Fields a format can't safely carry are skipped and reported, never forced.
"""
from __future__ import annotations

from pathlib import Path

FIELDS = ["title", "artist", "album", "albumartist", "remixer", "label", "genre", "year", "isrc"]

INSTALL_HINT = "pip3 install mutagen --break-system-packages"


class TagError(Exception):
    pass


def _mutagen():
    try:
        import mutagen  # noqa: F401
        return mutagen
    except ImportError:
        raise TagError(f"mutagen is not installed — install with: {INSTALL_HINT}")


# logical field -> ID3 frame (mp3/aiff/wav)
ID3_FRAMES = {
    "title": "TIT2", "artist": "TPE1", "album": "TALB", "albumartist": "TPE2",
    "remixer": "TPE4", "label": "TPUB", "genre": "TCON", "year": "TDRC", "isrc": "TSRC",
}

# logical field -> vorbis comment (flac)
VORBIS_KEYS = {
    "title": "title", "artist": "artist", "album": "album",
    "albumartist": "albumartist", "remixer": "remixer", "label": "organization",
    "genre": "genre", "year": "date", "isrc": "isrc",
}

# logical field -> mp4 atom (m4a); missing entries are unsupported there
MP4_ATOMS = {
    "title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb",
    "albumartist": "aART", "genre": "\xa9gen", "year": "\xa9day",
}

SUPPORTED_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".wav", ".aiff", ".aif"}


def _open(path: Path):
    mutagen = _mutagen()
    audio = mutagen.File(str(path))
    if audio is None:
        raise TagError(f"unrecognized or unreadable audio file: {path}")
    return audio


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".mp3":
        return "id3"
    if ext in (".wav", ".aiff", ".aif"):
        return "id3"
    if ext == ".flac":
        return "vorbis"
    if ext in (".m4a", ".mp4"):
        return "mp4"
    raise TagError(f"unsupported format: {ext}")


def duration_seconds(path: Path) -> float:
    try:
        audio = _open(path)
        return float(getattr(audio.info, "length", 0) or 0)
    except Exception:
        return 0.0


def read_tags(path: Path) -> dict:
    """Best-effort read of the logical fields. Missing fields are absent."""
    audio = _open(path)
    kind = _kind(path)
    out: dict = {}
    tags = audio.tags
    if tags is None:
        return out
    if kind == "id3":
        for field, frame in ID3_FRAMES.items():
            if frame in tags:
                out[field] = str(tags[frame].text[0]) if getattr(tags[frame], "text", None) else str(tags[frame])
    elif kind == "vorbis":
        for field, key in VORBIS_KEYS.items():
            if key in tags:
                out[field] = str(tags[key][0])
    elif kind == "mp4":
        for field, atom in MP4_ATOMS.items():
            if atom in tags:
                val = tags[atom]
                out[field] = str(val[0]) if isinstance(val, list) else str(val)
    return {k: v for k, v in out.items() if v}


def write_tags(path: Path, changes: dict) -> tuple[list[str], dict]:
    """Write the given logical field values (all non-empty strings).

    Returns (written_fields, skipped: {field: reason}). Never deletes a frame,
    never touches fields not present in `changes`.
    """
    audio = _open(path)
    kind = _kind(path)
    written: list[str] = []
    skipped: dict = {}

    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception as e:
            raise TagError(f"cannot create a tag block on {path.name}: {e}")

    if kind == "id3":
        import mutagen.id3 as id3mod
        for field, value in changes.items():
            frame_name = ID3_FRAMES.get(field)
            if not frame_name:
                skipped[field] = "no ID3 mapping"
                continue
            frame_cls = getattr(id3mod, frame_name)
            audio.tags.setall(frame_name, [frame_cls(encoding=3, text=[str(value)])])
            written.append(field)
    elif kind == "vorbis":
        for field, value in changes.items():
            audio.tags[VORBIS_KEYS[field]] = [str(value)]
            written.append(field)
    elif kind == "mp4":
        for field, value in changes.items():
            atom = MP4_ATOMS.get(field)
            if not atom:
                skipped[field] = "not representable in MP4 tags"
                continue
            audio.tags[atom] = [str(value)]
            written.append(field)

    if written:
        audio.save()
    return written, skipped


def merge_changes(current: dict, proposed: dict, allow_overwrite: bool) -> tuple[dict, dict]:
    """Decide which proposed fields actually get written.

    Rules (the preservation contract, tested in test_workflow.py):
      - empty/blank proposed values are never written (we never blank a tag)
      - identical values are skipped (no-op)
      - a non-empty current value is only replaced when allow_overwrite is True
        (i.e. the row was explicitly approved in the review file)
    Returns (to_write, skipped_reasons).
    """
    to_write: dict = {}
    skipped: dict = {}
    for field in FIELDS:
        new = str(proposed.get(field) or "").strip()
        if not new:
            continue
        cur = str(current.get(field) or "").strip()
        if cur == new:
            continue
        if cur and not allow_overwrite:
            skipped[field] = f"existing value preserved ({cur!r})"
            continue
        to_write[field] = new
    return to_write, skipped
