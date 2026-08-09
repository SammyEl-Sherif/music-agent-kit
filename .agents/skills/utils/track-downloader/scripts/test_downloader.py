#!/usr/bin/env python3
"""Self-check for track-downloader. No network, no yt-dlp: exercises the
idempotence lookup and the never-overwrite placement logic with temp files.

Run: python3 test_downloader.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grab_track import existing_download, place  # noqa: E402

CHECKS = []


def check(name, cond):
    CHECKS.append((name, bool(cond)))
    print(("  ok  " if cond else "  FAIL") + f"  {name}")


def main():
    root = Path(tempfile.mkdtemp(prefix="track-dl-test-"))
    try:
        out = root / "library"
        out.mkdir()
        (out / "Some Song [abc123XYZ-_].wav").write_text("x")

        check("existing id found regardless of title",
              existing_download(out, "abc123XYZ-_")
              == out / "Some Song [abc123XYZ-_].wav")
        check("unknown id -> None", existing_download(out, "zzzzzzzzzzz") is None)
        check("id in title text alone doesn't match",
              existing_download(out, "Some") is None)

        src = root / "New Song [id111111111].wav"
        src.write_text("new")
        placed = place(src, out)
        check("clean place keeps exact name",
              placed == out / "New Song [id111111111].wav" and placed.read_text() == "new")

        clash = root / "New Song [id111111111].wav"
        clash.write_text("clash")
        placed2 = place(clash, out)
        check("name clash gets (2) suffix, nothing overwritten",
              placed2 == out / "New Song [id111111111] (2).wav"
              and placed.read_text() == "new" and placed2.read_text() == "clash")

        clash3 = root / "New Song [id111111111].wav"
        clash3.write_text("clash3")
        check("further clashes count up",
              place(clash3, out) == out / "New Song [id111111111] (3).wav")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    failed = [n for n, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
