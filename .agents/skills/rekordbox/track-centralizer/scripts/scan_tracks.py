#!/usr/bin/env python3
"""Scan the whole rekordbox collection and plan moving every local audio file
into ONE destination folder.

READ-ONLY: reads the encrypted master.db via pyrekordbox and stats files on
disk; its only output is a JSON plan (plus a printed summary). It never writes
the database and never touches audio files, so rekordbox can stay open while
this runs.

Every DjmdContent row is classified:

  to_move    exists on disk, outside the destination -> gets a target path
  already    exists on disk, already under the destination
  missing    the DB path doesn't exist on disk (nothing we can do; reported)
  non_local  no filesystem path (streaming tracks etc.); skipped
  excluded   path matches an --exclude-path term; left alone, reported

Filename collisions are resolved so that rekordbox's relocate-by-filename
still works: the original basename is NEVER changed. The first claimant of a
name lands in the destination root; every later claimant (or any claimant
whose name already exists in the destination) is planned into a numbered
subfolder `_conflicts/2/`, `_conflicts/3/`, ... keeping its exact filename.
Two claimants with identical byte sizes are additionally flagged
`dupe_suspect` (probably the same file twice -- point the user at
playlist-dedupe).

Usage:
  python3 scan_tracks.py --dest ~/Music/rekordbox-library --out /tmp/rb-centralize-plan.json
  python3 scan_tracks.py --dest ... --exclude-path "/Volumes" --out ...
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "rekordbox"))
from rb_common import artist_name  # noqa: E402
from rb_common import get_db  # noqa: E402

CONFLICT_DIR = "_conflicts"


def classify(fp: str, dest: str, exclude_terms: list[str]) -> str:
    if not fp or not fp.startswith("/"):
        return "non_local"
    if any(term.lower() in fp.lower() for term in exclude_terms):
        return "excluded"
    if not os.path.isfile(fp):
        return "missing"
    real = os.path.realpath(fp)
    if real == dest or real.startswith(dest + os.sep):
        return "already"
    return "to_move"


def plan_targets(items: list[dict], dest: str, existing_names: set[str]) -> None:
    """Assign a `target` to every to_move item, in place. Deterministic
    (items are processed in path order) and collision-safe: basenames are kept
    verbatim, extra claimants of a taken name go to _conflicts/<n>/<name>."""
    taken = {n.casefold() for n in existing_names}
    slot: dict[str, int] = defaultdict(lambda: 1)
    by_name: dict[str, list[dict]] = defaultdict(list)

    for it in sorted((i for i in items if i["status"] == "to_move"),
                     key=lambda i: i["path"]):
        name = os.path.basename(it["path"])
        key = name.casefold()
        by_name[key].append(it)
        if key not in taken:
            taken.add(key)
            it["target"] = os.path.join(dest, name)
            it["conflict"] = False
        else:
            slot[key] += 1
            it["target"] = os.path.join(dest, CONFLICT_DIR, str(slot[key]), name)
            it["conflict"] = True

    # Same basename AND same byte size across claimants -> probably the same
    # file twice under different folders. Flag, never decide.
    for group in by_name.values():
        if len(group) < 2:
            continue
        sizes = defaultdict(list)
        for it in group:
            sizes[it["size"]].append(it)
        for same in sizes.values():
            if len(same) > 1:
                for it in same:
                    it["dupe_suspect"] = True


def source_breakdown(items: list[dict], depth: int = 3) -> dict[str, int]:
    """Count to_move files per source folder prefix (~3 levels deep) so the
    user can see where their library actually lives today."""
    counts: dict[str, int] = defaultdict(int)
    for it in items:
        if it["status"] != "to_move":
            continue
        parts = Path(it["path"]).parent.parts
        counts[str(Path(*parts[: depth + 1]))] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def nearest_existing(path: str) -> str:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return str(p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", required=True,
                    help="folder every track should end up in (created later by centralize.py)")
    ap.add_argument("--out", required=True, help="where to write the JSON plan")
    ap.add_argument("--exclude-path", default="",
                    help="comma-separated terms; a track whose path contains one is left alone")
    args = ap.parse_args()

    dest = os.path.realpath(os.path.expanduser(args.dest))
    exclude_terms = [t.strip() for t in args.exclude_path.split(",") if t.strip()]

    db = get_db()
    items: list[dict] = []
    for c in db.get_content():
        fp = c.FolderPath or ""
        status = classify(fp, dest, exclude_terms)
        size = 0
        if status in ("to_move", "already"):
            try:
                size = os.path.getsize(fp)
            except OSError:
                status = "missing"
        items.append({
            "content_id": str(c.ID),
            "artist": artist_name(c),
            "title": c.Title or "",
            "path": fp,
            "size": size,
            "status": status,
            "target": None,
            "conflict": False,
            "dupe_suspect": False,
        })

    existing_names = set(os.listdir(dest)) if os.path.isdir(dest) else set()
    plan_targets(items, dest, existing_names)

    to_move = [i for i in items if i["status"] == "to_move"]
    dest_dev = os.stat(nearest_existing(dest)).st_dev
    bytes_total = sum(i["size"] for i in to_move)
    bytes_cross = 0
    for i in to_move:
        try:
            if os.stat(i["path"]).st_dev != dest_dev:
                bytes_cross += i["size"]
        except OSError:
            pass
    free = shutil.disk_usage(nearest_existing(dest)).free

    counts = defaultdict(int)
    for i in items:
        counts[i["status"]] += 1

    plan = {
        "dest": dest,
        "counts": dict(counts),
        "bytes_to_move": bytes_total,
        "bytes_cross_device": bytes_cross,
        "free_bytes_dest": free,
        "conflicts": sum(1 for i in to_move if i["conflict"]),
        "dupe_suspects": sum(1 for i in to_move if i["dupe_suspect"]),
        "items": items,
    }
    with open(args.out, "w") as f:
        json.dump(plan, f, indent=1)

    gb = 1024 ** 3
    print(f"Collection rows scanned : {len(items)}")
    for status in ("to_move", "already", "missing", "excluded", "non_local"):
        if counts.get(status):
            print(f"  {status:<10}: {counts[status]}")
    print(f"To move   : {bytes_total / gb:.1f} GB "
          f"({bytes_cross / gb:.1f} GB crosses volumes and needs copying)")
    print(f"Dest free : {free / gb:.1f} GB on the volume holding {dest}")
    if plan["conflicts"]:
        print(f"Name conflicts -> {CONFLICT_DIR}/ subfolders: {plan['conflicts']}")
    if plan["dupe_suspects"]:
        print(f"Probable duplicate files (same name+size): {plan['dupe_suspects']}")
    print("\nWhere the to-move files live today:")
    for prefix, n in list(source_breakdown(items).items())[:15]:
        print(f"  {n:>5}  {prefix}")
    if bytes_cross > free:
        print("\nWARNING: not enough free space on the destination volume.")
    print(f"\nPlan written to {args.out}")


if __name__ == "__main__":
    main()
