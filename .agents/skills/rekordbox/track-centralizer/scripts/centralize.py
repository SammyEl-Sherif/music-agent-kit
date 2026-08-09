#!/usr/bin/env python3
"""Execute (or dry-run) a centralize plan produced by scan_tracks.py.

This is the ONLY script in this skill that moves files. It never touches the
rekordbox database -- after it runs, the moved tracks show as missing in
rekordbox until the user relocates them (that's the intended workflow).

Safety model:
  * DRY RUN by default -- prints exactly what it would do, touches nothing.
    Pass --execute to move.
  * Refuses to --execute while rekordbox is running (moving files underneath
    the live app is asking for trouble).
  * Same-volume moves are atomic renames. Cross-volume moves copy to a
    `.part` file, verify the byte size (and the SHA-256 with --verify-hash),
    atomically rename into place, and only THEN delete the source. A crash
    can leave a stray .part file but can never lose a track.
  * Basenames are never changed and existing files are never overwritten --
    an unexpected file at a target path skips that move and reports it.
  * Every completed move is appended immediately to a JSONL manifest at
    <dest>/_centralize/manifest-<timestamp>.jsonl, so a crash mid-run leaves
    an accurate record and undo_centralize.py can reverse everything.

Usage:
  python3 centralize.py /tmp/rb-centralize-plan.json              # dry run
  python3 centralize.py /tmp/rb-centralize-plan.json --execute
  python3 centralize.py ... --execute --verify-hash               # paranoid
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "rekordbox"))
from apply_core import rekordbox_running  # noqa: E402


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def move_file(src: str, dst: str, verify_hash: bool = False,
              force_copy: bool = False) -> None:
    """Move src to dst without ever being able to lose the file. Raises on any
    problem; the caller records the failure and continues."""
    if os.path.exists(dst):
        raise FileExistsError(f"target already exists: {dst}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    same_dev = (not force_copy and
                os.stat(src).st_dev == os.stat(os.path.dirname(dst)).st_dev)
    if same_dev:
        os.rename(src, dst)
        return
    part = dst + ".part"
    try:
        shutil.copy2(src, part)
        if os.path.getsize(part) != os.path.getsize(src):
            raise IOError(f"size mismatch after copy: {src}")
        if verify_hash and sha256(part) != sha256(src):
            raise IOError(f"hash mismatch after copy: {src}")
        os.replace(part, dst)
    except BaseException:
        if os.path.exists(part):
            os.remove(part)
        raise
    os.remove(src)


def apply_plan(plan: dict, execute: bool, verify_hash: bool = False,
               out=print) -> dict:
    dest = plan["dest"]
    to_move = [i for i in plan["items"] if i["status"] == "to_move"]
    result = {"moved": 0, "skipped": [], "manifest": None}

    if not to_move:
        out("Nothing to move -- every track is already centralized (or unreachable).")
        return result

    if not execute:
        out(f"DRY RUN -- {len(to_move)} files would move into {dest} "
            f"(no files touched). First few:")
        for it in to_move[:10]:
            flag = "  [conflict slot]" if it["conflict"] else ""
            out(f"  {it['path']}\n    -> {it['target']}{flag}")
        if len(to_move) > 10:
            out(f"  ... and {len(to_move) - 10} more")
        out("Pass --execute to move them.")
        return result

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_dir = os.path.join(dest, "_centralize")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest = os.path.join(manifest_dir, f"manifest-{stamp}.jsonl")
    result["manifest"] = manifest

    with open(manifest, "w") as mf:
        mf.write(json.dumps({"type": "header", "dest": dest,
                             "planned": len(to_move)}) + "\n")
        for it in to_move:
            src, dst = it["path"], it["target"]
            try:
                if not os.path.isfile(src):
                    raise FileNotFoundError(f"source vanished since scan: {src}")
                move_file(src, dst, verify_hash=verify_hash)
            except Exception as e:
                result["skipped"].append({"path": src, "error": str(e)})
                out(f"  SKIPPED {src}\n    {e}")
                continue
            mf.write(json.dumps({"from": src, "to": dst,
                                 "size": it["size"]}) + "\n")
            mf.flush()
            result["moved"] += 1

    out(f"\nMoved {result['moved']} of {len(to_move)} files into {dest}")
    if result["skipped"]:
        out(f"Skipped {len(result['skipped'])} (listed above) -- nothing was lost, "
            "they are still at their original paths.")
    out(f"Manifest (for undo): {manifest}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", help="JSON plan from scan_tracks.py")
    ap.add_argument("--execute", action="store_true",
                    help="actually move files (default: dry run)")
    ap.add_argument("--verify-hash", action="store_true",
                    help="SHA-256 verify every cross-volume copy (slower)")
    args = ap.parse_args()

    with open(args.plan) as f:
        plan = json.load(f)

    if args.execute and rekordbox_running():
        raise SystemExit("rekordbox is running -- quit it fully before moving "
                         "files, then re-run with --execute.")

    result = apply_plan(plan, execute=args.execute, verify_hash=args.verify_hash)
    if result["skipped"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
