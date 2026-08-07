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
        if kind == "id3":
            # rekordbox (and Pioneer hardware) only read ID3v2.3 — mutagen's
            # default v2.4 tags are invisible there, especially in WAV chunks.
            audio.save(v2_version=3)
            if path.suffix.lower() == ".wav":
                _uppercase_wav_id3_chunk(path)
                # rekordbox reads WAV metadata from the RIFF LIST/INFO chunk,
                # not ID3 — write both so rekordbox AND ID3-aware tools see it.
                _rewrite_wav_info_chunk(path, read_tags(path))
        else:
            audio.save()
    return written, skipped


# logical field -> RIFF INFO subchunk id (what rekordbox reads for WAV)
INFO_IDS = {
    "title": b"INAM", "artist": b"IART", "album": b"IPRD",
    "genre": b"IGNR", "year": b"ICRD",
}


def _rewrite_wav_info_chunk(path: Path, fields: dict) -> bool:
    """Rebuild the WAV with a LIST/INFO chunk carrying the given fields,
    placed before the data chunk. Existing INFO subchunks we don't set (e.g.
    ISFT encoder) are preserved; every other chunk passes through untouched.
    Audio bytes are never modified; the file is replaced atomically."""
    import os
    import struct
    import tempfile

    with open(path, "rb") as fh:
        riff = fh.read(12)
        if riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
            return False
        chunks = []  # (cid, data)
        while True:
            hdr = fh.read(8)
            if len(hdr) < 8:
                break
            cid, size = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            data = fh.read(size)
            if size % 2:
                fh.read(1)
            chunks.append((cid, data))

    # Collect subchunks from any existing INFO list, ours winning
    preserved: dict[bytes, bytes] = {}
    for cid, data in chunks:
        if cid == b"LIST" and data[:4] == b"INFO":
            pos = 4
            while pos + 8 <= len(data):
                sub, ssize = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
                preserved[sub] = data[pos + 8:pos + 8 + ssize]
                pos += 8 + ssize + (ssize % 2)

    for field, sub_id in INFO_IDS.items():
        val = str(fields.get(field) or "").strip()
        if val:
            preserved[sub_id] = val.encode("utf-8") + b"\x00"

    info = b"INFO"
    for sub_id, val in preserved.items():
        if not val.endswith(b"\x00"):
            val += b"\x00"
        info += sub_id + struct.pack("<I", len(val)) + val + (b"\x00" if len(val) % 2 else b"")

    out = b""
    info_written = False
    for cid, data in chunks:
        if cid == b"LIST" and data[:4] == b"INFO":
            continue  # replaced by the rebuilt INFO list
        if cid == b"data" and not info_written:
            out += b"LIST" + struct.pack("<I", len(info)) + info + (b"\x00" if len(info) % 2 else b"")
            info_written = True
        out += cid + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    if not info_written:
        out += b"LIST" + struct.pack("<I", len(info)) + info + (b"\x00" if len(info) % 2 else b"")

    payload = b"WAVE" + out
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".wav.tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"RIFF" + struct.pack("<I", len(payload)) + payload)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def _uppercase_wav_id3_chunk(path: Path) -> bool:
    """Rename mutagen's lowercase 'id3 ' RIFF chunk to 'ID3 '. rekordbox only
    recognizes the uppercase id; mutagen reads either, so this is lossless."""
    import struct
    with open(path, "r+b") as fh:
        if fh.read(4) != b"RIFF":
            return False
        pos = 12
        while True:
            fh.seek(pos)
            hdr = fh.read(8)
            if len(hdr) < 8:
                return False
            cid, size = hdr[:4], struct.unpack("<I", hdr[4:8])[0]
            if cid == b"id3 ":
                fh.seek(pos)
                fh.write(b"ID3 ")
                return True
            pos += 8 + size + (size % 2)


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
