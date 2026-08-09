#!/usr/bin/env python3
"""Reverse a centralize run using its JSONL manifest: move every file recorded
in the manifest back to its original path (recreating source folders as
needed). Dry run by default; --execute to actually move. Never overwrites --
if something now sits at the original path, that entry is skipped and
reported. Never touches the rekordbox database.

Usage:
  python3 undo_centralize.py <dest>/_centralize/manifest-<ts>.jsonl
  python3 undo_centralize.py <manifest> --execute
"""

from __future__ import annotations

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "rekordbox"))
from apply_core import rekordbox_running  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from centralize import move_file  # noqa: E402


def undo(manifest_path: str, execute: bool, out=print) -> dict:
    moves = []
    with open(manifest_path) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("type") != "header":
                moves.append(rec)

    result = {"restored": 0, "skipped": []}
    if not execute:
        out(f"DRY RUN -- would move {len(moves)} files back to their original "
            "paths. Pass --execute to do it.")
        return result

    # Reverse order, so a partially undone run can simply be re-run.
    for rec in reversed(moves):
        src, dst = rec["to"], rec["from"]
        try:
            if not os.path.isfile(src):
                raise FileNotFoundError(f"not found (already restored?): {src}")
            move_file(src, dst)
        except Exception as e:
            result["skipped"].append({"path": src, "error": str(e)})
            out(f"  SKIPPED {src}\n    {e}")
            continue
        result["restored"] += 1

    out(f"\nRestored {result['restored']} of {len(moves)} files.")
    if result["skipped"]:
        out(f"Skipped {len(result['skipped'])} (listed above); files remain "
            "where they are.")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest", help="manifest-<timestamp>.jsonl from centralize.py")
    ap.add_argument("--execute", action="store_true",
                    help="actually move files back (default: dry run)")
    args = ap.parse_args()

    if args.execute and rekordbox_running():
        raise SystemExit("rekordbox is running -- quit it fully before undoing.")

    result = undo(args.manifest, execute=args.execute)
    if result["skipped"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
