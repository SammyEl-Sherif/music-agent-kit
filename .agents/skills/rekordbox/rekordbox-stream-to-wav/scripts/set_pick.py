#!/usr/bin/env python3
"""Change the YouTube pick for one or more manifest tracks.

Usage:
    python3 set_pick.py manifest.json 12 dQw4w9WgXcQ            # use this video
    python3 set_pick.py manifest.json 12 https://youtu.be/...   # URL works too
    python3 set_pick.py manifest.json 12 none                   # skip this track
    python3 set_pick.py manifest.json 12 dQw4w9WgXcQ --title "Artist - Title"
    python3 set_pick.py manifest.json --accept 5,39             # take suggestions
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stream_common import load_manifest, save_manifest  # noqa: E402

VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})|^([\w-]{11})$")


def video_id(text: str) -> str:
    m = VIDEO_ID.search(text.strip())
    if not m:
        raise SystemExit(f"Not a YouTube video id or URL: {text}")
    return m.group(1) or m.group(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("position", nargs="?", type=int)
    ap.add_argument("video", nargs="?", help="Video id, URL, or 'none'.")
    ap.add_argument("--title", help="Name to give the track in rekordbox.")
    ap.add_argument("--accept", help="Comma-separated positions whose suggestion to accept.")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    by_pos = {t["position"]: t for t in manifest["tracks"]}

    if args.accept:
        for pos in (int(p) for p in args.accept.split(",")):
            t = by_pos.get(pos) or sys.exit(f"No streaming track at position {pos}")
            if not t.get("suggestion"):
                sys.exit(f"Position {pos} has no suggestion")
            t["pick"], t["suggestion"] = t["suggestion"], None
            print(f"{pos:>4}  {t['name']} -> {t['pick']['video_id']}")
    else:
        if args.position is None or args.video is None:
            ap.error("give a position and a video, or --accept")
        t = by_pos.get(args.position) or sys.exit(f"No streaming track at position {args.position}")
        if args.video.lower() == "none":
            t["pick"] = None
            print(f"{args.position:>4}  {t['name']} -> skipped")
        else:
            name = args.title or t["name"]
            t["pick"] = {"video_id": video_id(args.video), "title": name}
            t["suggestion"] = None
            print(f"{args.position:>4}  {name} -> {t['pick']['video_id']}")

    save_manifest(args.manifest, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
