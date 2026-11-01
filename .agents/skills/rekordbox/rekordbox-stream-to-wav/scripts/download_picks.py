#!/usr/bin/env python3
"""Download every picked video in a manifest as WAV via track-downloader.

Calls the track-downloader skill's grab_track.py, so naming, idempotence and
"never overwrite" behave exactly as that skill does. Files only; the rekordbox
database is untouched.

Usage:
    python3 download_picks.py manifest.json [-o ~/Music/Track Collection]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stream_common import DEFAULT_LIBRARY, find_wav, load_manifest  # noqa: E402

GRAB = (Path(__file__).resolve().parents[3] / "utils" / "track-downloader"
        / "scripts" / "grab_track.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("-o", "--out-dir", default=DEFAULT_LIBRARY)
    args = ap.parse_args()
    if not GRAB.exists():
        raise SystemExit(f"track-downloader not found at {GRAB}")

    manifest = load_manifest(args.manifest)
    picks = [t["pick"]["video_id"] for t in manifest["tracks"] if t.get("pick")]
    if not picks:
        raise SystemExit("No picks in the manifest.")

    urls = [f"https://www.youtube.com/watch?v={v}" for v in picks]
    proc = subprocess.run([sys.executable, str(GRAB), "--no-reveal", "-o", args.out_dir, *urls])

    library = Path(args.out_dir).expanduser()
    missing = [v for v in picks if not find_wav(library, v)]
    print(f"\n{len(picks) - len(missing)}/{len(picks)} WAVs in {library}")
    for v in missing:
        print(f"  MISSING: {v}")
    return 1 if missing or proc.returncode else 0


if __name__ == "__main__":
    raise SystemExit(main())
