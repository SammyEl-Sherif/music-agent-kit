#!/usr/bin/env python3
"""track-downloader — download a YouTube link's audio as WAV into the music
library folder (default: ~/Music/Track Collection).

yt-dlp grabs the best audio stream and ffmpeg extracts it to WAV. Files are
named "<title> [<video id>].wav" — the same convention yt-dlp downloads
already in the library use — and the video id makes downloads idempotent: if
that id's WAV is already in the folder, nothing is re-downloaded and the
existing path is printed. Never overwrites anything.

Each final path is printed as a "TRACK: <abs path>" line so the caller (human
or agent) can grab it programmatically.

WAV from YouTube is a lossless container around a lossy source stream (~130
kbps Opus) -- best quality YouTube offers, but not studio lossless.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INSTALL_HINTS = {
    "yt-dlp": "brew install yt-dlp   (or: pip3 install yt-dlp)",
    "ffmpeg": "brew install ffmpeg",
}

DEFAULT_OUT = "~/Music/Track Collection"
NAME_TMPL = "%(title)s [%(id)s].%(ext)s"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def check_deps() -> None:
    missing = [tool for tool in INSTALL_HINTS if shutil.which(tool) is None]
    if missing:
        lines = [f"missing required tool(s): {', '.join(missing)}"]
        lines += [f"  install {t}: {INSTALL_HINTS[t]}" for t in missing]
        die("\n".join(lines))


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, **kw)


def existing_download(out_dir: Path, video_id: str) -> Path | None:
    """The video id embedded in the filename is the idempotence key: a prior
    download of this id, whatever its title was at the time, means skip.
    (No glob here: '[' in a filename is a glob character class.)"""
    suffix = f" [{video_id}].wav"
    hits = sorted(p for p in out_dir.iterdir()
                  if p.is_file() and p.name.endswith(suffix))
    return hits[0] if hits else None


def probe(url: str) -> tuple[str, str]:
    """Resolve the URL to (title, video id) without downloading anything."""
    proc = run(
        ["yt-dlp", "--no-playlist", "--print", "%(title)s\n%(id)s", url],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        die(f"yt-dlp could not read {url}:\n{proc.stderr.strip()}")
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        die(f"could not resolve title/id for {url}")
    return lines[0], lines[1]


def download_wav(url: str, workdir: Path) -> Path:
    """Download the URL's audio, extract to WAV, embed metadata; return path."""
    proc = run(
        [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "wav",
            "--embed-metadata",
            "--no-simulate",
            "--print", "after_move:filepath",
            "-o", str(workdir / NAME_TMPL),
            url,
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        die(f"yt-dlp failed:\n{proc.stderr.strip()}")
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if not lines:
        die("yt-dlp reported success but printed no file path")
    wav = Path(lines[-1])
    if not wav.exists():
        die(f"yt-dlp reported {wav} but the file does not exist")
    return wav


def place(wav: Path, out_dir: Path) -> Path:
    """Move the finished WAV into out_dir without ever overwriting: an
    unexpected name clash gets a ' (2)' style suffix (the file isn't in
    rekordbox yet, so renaming is still safe here)."""
    target = out_dir / wav.name
    n = 2
    while target.exists():
        target = out_dir / f"{wav.stem} ({n}){wav.suffix}"
        n += 1
    shutil.move(str(wav), target)
    return target


def main() -> None:
    p = argparse.ArgumentParser(
        description="Download YouTube audio as WAV into the music library folder."
    )
    p.add_argument("urls", nargs="+", help="YouTube (or any yt-dlp-supported) URLs")
    p.add_argument(
        "-o", "--out-dir", default=DEFAULT_OUT,
        help=f"destination folder (default: {DEFAULT_OUT})",
    )
    p.add_argument(
        "--no-reveal", action="store_true",
        help="don't reveal the downloaded file(s) in Finder when done",
    )
    args = p.parse_args()

    check_deps()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[Path] = []
    for url in args.urls:
        title, video_id = probe(url)
        prior = existing_download(out_dir, video_id)
        if prior:
            print(f"already in library, skipping download: {prior.name}")
            results.append(prior)
            continue
        print(f"downloading: {title} [{video_id}]")
        with tempfile.TemporaryDirectory(prefix="track-dl-") as tmp:
            wav = download_wav(url, Path(tmp))
            results.append(place(wav, out_dir))

    if not args.no_reveal and sys.platform == "darwin" and shutil.which("open"):
        subprocess.run(["open", "-R", str(results[-1])], check=False)

    for path in results:
        print(f"TRACK: {path}")


if __name__ == "__main__":
    main()
