#!/usr/bin/env python3
"""vocals — download a YouTube track and isolate its vocal stem.

Pipeline (both stages are external CLIs, this script just orchestrates):
  1. yt-dlp downloads the video's audio and extracts it to WAV.
  2. demucs (two-stems mode) splits that WAV into vocals + instrumental.

The isolated vocal WAV is moved into --out-dir and its absolute path is
printed as the final line of output, prefixed "VOCALS:", so the caller (human
or agent) can grab the path programmatically.

All intermediate files (the downloaded audio, demucs's working tree) live in a
temp directory and are deleted on exit; only the requested outputs are kept.
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
    "demucs": "pip3 install demucs   (add --break-system-packages if pip refuses)",
}


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


def download_audio(url: str, workdir: Path) -> Path:
    """Download the URL's audio as WAV via the yt-dlp CLI; return the file path."""
    out_tmpl = str(workdir / "%(title)s.%(ext)s")
    proc = run(
        [
            "yt-dlp",
            "--no-playlist",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "wav",
            "--no-simulate",
            "--print", "after_move:filepath",
            "-o", out_tmpl,
            url,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        die(f"yt-dlp failed:\n{proc.stderr.strip()}")
    # --print after_move:filepath emits the final path of each downloaded file.
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if not lines:
        die("yt-dlp reported success but printed no file path")
    audio = Path(lines[-1])
    if not audio.exists():
        die(f"yt-dlp reported {audio} but the file does not exist")
    print(f"downloaded: {audio.name}")
    return audio


def separate_vocals(audio: Path, workdir: Path, model: str, device: str) -> tuple[Path, Path]:
    """Run demucs in two-stems mode; return (vocals, instrumental) WAV paths."""
    sep_root = workdir / "separated"
    proc = run(
        ["demucs", "--two-stems", "vocals", "-n", model, "-d", device,
         "-o", str(sep_root), str(audio)],
        stdout=None,  # demucs prints its own progress bar; let it through
    )
    if proc.returncode != 0:
        die("demucs failed (see output above)")
    stem_dir = sep_root / model / audio.stem
    vocals = stem_dir / "vocals.wav"
    instrumental = stem_dir / "no_vocals.wav"
    if not vocals.exists():
        die(f"expected demucs output {vocals} not found")
    return vocals, instrumental


def safe_name(title: str) -> str:
    return re.sub(r'[/\\:]', "_", title).strip() or "track"


def main() -> None:
    p = argparse.ArgumentParser(
        description="Download a YouTube link and isolate the vocal stem (yt-dlp + demucs)."
    )
    p.add_argument("url", help="YouTube (or any yt-dlp-supported) URL")
    p.add_argument(
        "-o", "--out-dir", default=".",
        help="directory to place the vocal WAV in (default: current directory)",
    )
    p.add_argument(
        "--keep-instrumental", action="store_true",
        help="also keep the instrumental (no_vocals) stem alongside the vocals",
    )
    p.add_argument(
        "--model", default="htdemucs",
        help="demucs model name (default: htdemucs)",
    )
    p.add_argument(
        "--device", default="cpu",
        help="torch device for demucs (default: cpu -- Apple's MPS backend "
             "cannot run htdemucs; pass 'cuda' on an NVIDIA machine)",
    )
    p.add_argument(
        "--no-reveal", action="store_true",
        help="don't open the enclosing folder in Finder when done",
    )
    args = p.parse_args()

    check_deps()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vocals-") as tmp:
        workdir = Path(tmp)
        audio = download_audio(args.url, workdir)
        vocals, instrumental = separate_vocals(audio, workdir, args.model, args.device)

        base = safe_name(audio.stem)
        vocals_out = out_dir / f"{base} (vocals).wav"
        shutil.move(str(vocals), vocals_out)
        if args.keep_instrumental and instrumental.exists():
            inst_out = out_dir / f"{base} (instrumental).wav"
            shutil.move(str(instrumental), inst_out)
            print(f"instrumental: {inst_out}")

    # Reveal the result in Finder: opens the enclosing folder with the vocal
    # file selected. macOS only; skipped elsewhere or with --no-reveal.
    if not args.no_reveal and sys.platform == "darwin" and shutil.which("open"):
        subprocess.run(["open", "-R", str(vocals_out)], check=False)

    # Final line, machine-readable: the isolated vocal sample's absolute path.
    print(f"VOCALS: {vocals_out}")


if __name__ == "__main__":
    main()
