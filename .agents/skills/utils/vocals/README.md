# vocals

Give it a YouTube link, get back an isolated a-cappella vocal WAV.

Under the hood: [yt-dlp](https://github.com/yt-dlp/yt-dlp) downloads the
audio, [demucs](https://github.com/facebookresearch/demucs) splits it into
**vocals** and **everything else** (two-stems mode), and the vocal stem is
moved wherever you asked. The script's last output line is the absolute path
to the vocal file.

## Prerequisites

```sh
brew install yt-dlp ffmpeg
pip3 install demucs        # add --break-system-packages if pip refuses
```

The first demucs run downloads its model weights (~300 MB).

## Usage

```sh
cd .agents/skills/utils/vocals/scripts

# vocal WAV lands in the current directory
python3 vocals.py "https://www.youtube.com/watch?v=..."

# choose where it goes, and keep the instrumental too
python3 vocals.py "https://www.youtube.com/watch?v=..." \
  --out-dir ~/Music/samples --keep-instrumental
```

Output:

```
VOCALS: /Users/you/Music/samples/Song Title (vocals).wav
```

Or just ask Claude: *"grab the vocals from this YouTube link and put them in
~/Music/samples"*.

## Notes

- Demucs runs on CPU by default (Apple's MPS backend can't run htdemucs;
  `--device cuda` works on NVIDIA machines). A ~4-minute track separates in
  about a minute on an Apple Silicon CPU.
- `--model htdemucs_ft` is slower but slightly cleaner than the default.
- Non-destructive: intermediates live in a temp dir and are cleaned up; only
  the stems you asked for are kept.
- Only use on content you have the rights to download and sample.
