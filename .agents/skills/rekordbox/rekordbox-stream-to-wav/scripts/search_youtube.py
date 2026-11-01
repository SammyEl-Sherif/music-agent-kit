#!/usr/bin/env python3
"""Search YouTube for every named track in a manifest and pick a match.

Runs two yt-dlp searches per track (the name, and the name plus "extended
mix"), ranks the results with stream_common.score_candidate, and stores the
top candidates plus a `pick` in the manifest. A title match whose length
disagrees with rekordbox's is stored as a `suggestion` instead, never a pick.
Review every pick with the user before downloading; set_pick.py changes them.

Usage:
    python3 search_youtube.py manifest.json
    python3 search_youtube.py manifest.json --only 9,10   # re-search positions
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stream_common import clean_title, load_manifest, rank_candidates, save_manifest, search_query  # noqa: E402

KEEP = 6
PICK_MIN_SCORE = 10


def yt_search(query: str, n: int = 6) -> list[dict]:
    out = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print",
         "%(id)s\t%(duration)s\t%(channel)s\t%(title)s", f"ytsearch{n}:{query}"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    results = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        vid, dur, channel, title = parts
        try:
            dur_s = int(float(dur))
        except ValueError:
            dur_s = 0
        results.append({"video_id": vid, "duration": dur_s, "channel": channel, "title": title})
    return results


def search_track(t: dict) -> str:
    """Fill in t's candidates, pick and suggestion. Returns a one-line label."""
    query = search_query(t["artist"], t["title"])
    seen, cands = set(), []
    for q in (query, f"{query} extended mix"):
        for c in yt_search(q):
            if c["video_id"] not in seen:
                seen.add(c["video_id"])
                cands.append(c)

    want = clean_title(t["title"])
    ranked = rank_candidates(cands, t["length"], want)
    # rekordbox's stored length is sometimes wrong for SoundCloud tracks. If
    # nothing matches on length, rank on title alone, but only as a suggestion.
    unverified = not ranked or ranked[0]["score"] < PICK_MIN_SCORE
    if unverified:
        ranked = rank_candidates(cands, 0, want)
    t["candidates"] = ranked[:KEEP]
    best = t["candidates"][0] if t["candidates"] else None

    t["pick"] = t["suggestion"] = None
    if best and not unverified:
        t["pick"] = {"video_id": best["video_id"], "title": t["name"]}
        return f"{best['title']} ({best['score']})"
    if best and best["score"] >= 0:
        t["suggestion"] = {"video_id": best["video_id"], "title": t["name"]}
        return (f"SUGGESTION, length differs ({best['duration']}s vs {t['length']}s): "
                f"{best['title']}")
    return "no confident match"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("--only", help="Comma-separated playlist positions to (re)search.")
    args = ap.parse_args()
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is missing: brew install yt-dlp")

    manifest = load_manifest(args.manifest)
    only = {int(p) for p in args.only.split(",")} if args.only else None

    for t in manifest["tracks"]:
        if only is not None and t["position"] not in only:
            continue
        if not t["name"]:
            print(f"{t['position']:>4}  skipped: no name")
            continue
        label = search_track(t)
        print(f"{t['position']:>4}  {t['name']}\n        -> {label}")
        save_manifest(args.manifest, manifest)

    picked = sum(1 for t in manifest["tracks"] if t["pick"])
    suggested = sum(1 for t in manifest["tracks"] if t.get("suggestion"))
    print(f"\n{picked}/{len(manifest['tracks'])} picked, {suggested} need your call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
