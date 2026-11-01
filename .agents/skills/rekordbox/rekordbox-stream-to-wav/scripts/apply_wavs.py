#!/usr/bin/env python3
"""Put the downloaded WAVs into the playlist in place of its streaming entries.

Dry run by default; --apply writes. Uses the shared apply_core safety helpers:
refuses while rekordbox is running, saves a permanent master.db backup and an
in-app snapshot under 'Claude Backups' first, commits adds before removals,
and tombstones removals the way rekordbox does so Cloud Library Sync keeps them.

Modes:
    replace (default)  each WAV takes its streaming entry's position and the
                       streaming entry is removed from this playlist
    append             WAVs are added at the end; streaming entries stay

Only this playlist changes. The streaming tracks stay in the collection and in
any other playlist.

Usage:
    python3 apply_wavs.py manifest.json                    # dry run
    python3 apply_wavs.py manifest.json --apply
    python3 apply_wavs.py manifest.json --apply --mode append
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "rekordbox"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from apply_core import (  # noqa: E402
    DB_BACKUP_DIRNAME, add_with_attr_bypass, content_in_playlist, find_db_path,
    rekordbox_running, renumber_after_removals, snapshot_playlists, tombstone_remove,
)
from rb_common import build_playlist_index, get_db  # noqa: E402
from stream_common import DEFAULT_LIBRARY, find_wav, load_manifest  # noqa: E402


def live_rows(db, tables, playlist_id):
    rows = (db.get_playlist_songs()
            .filter(tables.DjmdSongPlaylist.PlaylistID == playlist_id,
                    tables.DjmdSongPlaylist.rb_local_deleted == 0).all())
    return sorted(rows, key=lambda r: int(r.TrackNo or 0))


def existing_track(db, tables, playlist_id, wav, video_id):
    """The collection track for this video, if any. Matches the exact path, or
    any file named '... [<id>].<ext>' elsewhere (an earlier download in another
    folder), preferring one already in the playlist so it isn't added twice."""
    exact = db.get_content(FolderPath=str(wav)).first()
    if exact:
        return exact
    same_id = (db.get_content()
               .filter(tables.DjmdContent.FolderPath.like(f"% [{video_id}].%"),
                       tables.DjmdContent.rb_local_deleted == 0).all())
    in_playlist = [c for c in same_id if content_in_playlist(db, tables, playlist_id, c.ID)]
    return (in_playlist or same_id or [None])[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("--apply", action="store_true", help="Write. Without it, dry run.")
    ap.add_argument("--mode", choices=("replace", "append"), default="replace")
    ap.add_argument("-l", "--library", default=DEFAULT_LIBRARY,
                    help="Folder the WAVs were downloaded to.")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    pid = manifest["playlist"]["id"]
    library = Path(args.library).expanduser()

    db = get_db()
    from pyrekordbox.db6 import tables

    rows_by_id = {str(r.ID): r for r in live_rows(db, tables, pid)}
    plan, problems = [], []
    for t in manifest["tracks"]:
        if not t.get("pick"):
            continue
        wav = find_wav(library, t["pick"]["video_id"])
        row = rows_by_id.get(t["song_id"])
        if wav is None:
            problems.append(f"{t['position']}: WAV for {t['pick']['video_id']} not downloaded")
        elif row is None or row.Content.FolderPath != t["folder_path"]:
            problems.append(f"{t['position']}: streaming entry is no longer in the playlist")
        else:
            existing = existing_track(db, tables, pid, wav, t["pick"]["video_id"])
            plan.append((t, row, wav, existing))
    if problems:
        print("Cannot apply:\n  " + "\n  ".join(problems))
        print("Re-run find_streams.py if the playlist changed, or download_picks.py for missing files.")
        return 1

    print(f"{manifest['playlist']['path']}: {len(plan)} streaming entries -> WAVs ({args.mode})")
    for t, _, wav, existing in plan:
        note = ""
        if existing:
            where = "already in this playlist" if content_in_playlist(db, tables, pid, existing.ID) \
                else "already in collection"
            note = f"  ({where}: {existing.FolderPath})"
        print(f"  {t['position']:>4}  {t['service']:<10} {t['name']}\n        -> {wav.name}{note}")
        if existing and existing.FolderPath != str(wav):
            print(f"        (uses the existing file; {wav.name} in the library folder is a spare copy)")
    if not args.apply:
        print("\nDry run. Pass --apply to write.")
        return 0
    if not plan:
        print("Nothing to do.")
        return 0

    if rekordbox_running():
        raise SystemExit("rekordbox is running. Quit it, then run this again.")

    db_path = find_db_path(db)
    if not db_path or not db_path.exists():
        raise SystemExit("Could not locate master.db to back it up. Nothing written.")
    backup_dir = db_path.parent / DB_BACKUP_DIRNAME
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / f"{db_path.stem}-{datetime.now():%Y%m%d-%H%M%S}{db_path.suffix}"
    shutil.copy2(db_path, backup)
    print(f"\nBacked up database -> {backup}")

    try:
        snaps = snapshot_playlists(
            db, tables, build_playlist_index(db),
            [(pid, manifest["playlist"]["path"], manifest["playlist"]["name"])],
            datetime.now().strftime("%Y-%m-%d | %H:%M"))
        db.commit()
    except Exception as e:
        db.rollback()
        raise SystemExit(f"Snapshot failed, nothing written: {e}")
    for s in snaps:
        print(f"Snapshot -> {s['backup_path']} ({s['tracks']} tracks)")

    # Adds first. In replace mode each WAV goes directly above its streaming
    # entry, which then shifts down one and is removed below.
    used_paths, added = set(), 0
    try:
        for t, row, wav, existing in plan:
            content = existing or db.add_content(wav, Title=t["pick"].get("title") or t["name"])
            used_paths.add(content.FolderPath)
            if content_in_playlist(db, tables, pid, content.ID):
                continue
            added += 1
            if args.mode == "replace":
                db.session.refresh(row)
                add_with_attr_bypass(db, pid, content.ID, track_no=int(row.TrackNo))
            else:
                add_with_attr_bypass(db, pid, content.ID)
        db.commit()
    except Exception as e:
        db.rollback()
        raise SystemExit(f"Adding WAVs failed, rolled back. Restore point: {backup}\nError: {e}")
    print(f"Added {added} WAVs. {len(plan) - added} were already in the playlist.")

    if args.mode == "replace":
        try:
            now = datetime.now()
            removed = [tombstone_remove(db, tables, row.ID, now) for _, row, _, _ in plan]
            renumber_after_removals(db, tables, pid, removed, now)
            db.commit()
        except Exception as e:
            db.rollback()
            raise SystemExit(f"Removing streaming entries failed; the WAVs are in, so the playlist "
                             f"has both copies. Restore point: {backup}\nError: {e}")
        print(f"Removed {len(removed)} streaming entries.")

    final = live_rows(db, tables, pid)
    numbered = [int(r.TrackNo) for r in final] == list(range(1, len(final) + 1))
    present = used_paths <= {r.Content.FolderPath for r in final}
    print(f"\n{manifest['playlist']['path']} now has {len(final)} tracks. "
          f"Positions contiguous: {numbered}. All WAVs present: {present}.")
    if not (numbered and present):
        print(f"Check the playlist in rekordbox. Restore point: {backup}")
        return 1
    print(f"Backup: {backup}")
    print("Open rekordbox and analyze the new tracks (BPM, key, waveform).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
