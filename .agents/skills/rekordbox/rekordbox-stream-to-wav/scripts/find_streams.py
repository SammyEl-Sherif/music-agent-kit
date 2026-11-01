#!/usr/bin/env python3
"""List a playlist's Spotify and SoundCloud entries and write a manifest.

Read-only, so rekordbox can stay open. SoundCloud names are stored in plain
text. rekordbox encrypts Spotify artist/title fields, so those are resolved
from Spotify's public embed page (no account needed). That page is not an
official API and may change; unresolved tracks are flagged, not guessed.

Usage:
    python3 find_streams.py <playlist_id> -o manifest.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "rekordbox"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rb_common import build_playlist_index, get_db, playlist_path  # noqa: E402
from stream_common import display_name, readable, save_manifest, stream_source  # noqa: E402

EMBED_URL = "https://open.spotify.com/embed/track/{}"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def spotify_name(track_id: str) -> tuple[str, str]:
    """(artist, title) from the Spotify embed page, or ('', '') on failure."""
    req = urllib.request.Request(EMBED_URL.format(track_id),
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        entity = json.loads(NEXT_DATA.search(html).group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except Exception:
        return "", ""
    artists = ", ".join(a.get("name", "") for a in entity.get("artists") or [])
    return artists, entity.get("name") or entity.get("title") or ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("playlist_id")
    ap.add_argument("-o", "--out", required=True, help="Manifest JSON to write.")
    args = ap.parse_args()

    db = get_db()
    from pyrekordbox.db6 import tables

    index = build_playlist_index(db)
    node = index.get(str(args.playlist_id))
    if node is None:
        raise SystemExit(f"No playlist with id {args.playlist_id}")
    if getattr(node, "SmartList", None):
        raise SystemExit("That is a smart playlist; its contents can't be edited.")
    if playlist_path(index, str(args.playlist_id)).startswith("Claude Backups"):
        raise SystemExit("That is a Claude Backups snapshot; pick the live playlist instead.")

    rows = (db.get_playlist_songs()
            .filter(tables.DjmdSongPlaylist.PlaylistID == str(args.playlist_id),
                    tables.DjmdSongPlaylist.rb_local_deleted == 0).all())
    rows.sort(key=lambda r: int(r.TrackNo or 0))

    tracks = []
    for pos, row in enumerate(rows, 1):
        content = row.Content
        source = stream_source(content.FolderPath)
        if not source:
            continue
        service, source_id = source
        artist = readable(content.ArtistName) if hasattr(content, "ArtistName") else ""
        title = readable(content.Title)
        if service == "spotify" and not title:
            artist, title = spotify_name(source_id)
        tracks.append({
            "position": pos,
            "song_id": str(row.ID),
            "content_id": str(content.ID),
            "service": service,
            "source_id": source_id,
            "folder_path": content.FolderPath,
            "artist": artist,
            "title": title,
            "name": display_name(artist, title) if title else "",
            "length": int(content.Length or 0),
            "candidates": [],
            "pick": None,
            "suggestion": None,
        })

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "playlist": {"id": str(args.playlist_id), "name": node.Name,
                     "path": playlist_path(index, str(args.playlist_id)),
                     "track_count": len(rows)},
        "tracks": tracks,
    }
    save_manifest(args.out, manifest)

    unresolved = [t for t in tracks if not t["name"]]
    counts = {s: sum(1 for t in tracks if t["service"] == s) for s in ("spotify", "soundcloud")}
    print(f"{manifest['playlist']['path']}: {len(rows)} tracks, "
          f"{counts['soundcloud']} SoundCloud, {counts['spotify']} Spotify")
    for t in tracks:
        print(f"  {t['position']:>4}  {t['service']:<10} {t['name'] or '(name not found)'}")
    if unresolved:
        print(f"\n{len(unresolved)} track(s) could not be named; they are skipped unless you fill in 'name'.")
    print(f"\nManifest: {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
