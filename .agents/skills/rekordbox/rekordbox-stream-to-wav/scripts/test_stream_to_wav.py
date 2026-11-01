#!/usr/bin/env python3
"""Self-check for rekordbox-stream-to-wav. Needs no database or network."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stream_common import (  # noqa: E402
    clean_title, display_name, find_wav, rank_candidates, readable, search_query, stream_source,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok  {msg}")


check(stream_source("spotify:track:abc") == ("spotify", "abc"), "spotify uri")
check(stream_source("soundcloud:tracks:123") == ("soundcloud", "123"), "soundcloud uri")
check(stream_source("/Users/x/Music/a.wav") is None, "local file is not a stream")

check(readable("$A7:v1:abc==:def==") == "", "encrypted field reads as empty")
check(readable(" Prospa ") == "Prospa", "plain field passes through")

check(display_name("MPH", "One Sixty") == "MPH - One Sixty", "artist joined")
check(display_name("MPH", "MPH - Raw") == "MPH - Raw", "artist not repeated")
check(display_name("", "Pile Up") == "Pile Up", "no artist")

check(search_query("Prospa - This Rhythm (feat. RAHH)") == "Prospa This Rhythm feat. RAHH",
      "query flattens brackets")

cands = [
    {"video_id": "set", "duration": 3600, "channel": "DJ Mag", "title": "Prospa DJ Set"},
    {"video_id": "lyr", "duration": 191, "channel": "7clouds", "title": "Prospa - This Rhythm (Lyrics)"},
    {"video_id": "off", "duration": 191, "channel": "CircoLoco Records", "title": "Prospa - This Rhythm"},
    {"video_id": "ext", "duration": 259, "channel": "Club Catalogue", "title": "Prospa - This Rhythm (Extended Mix)"},
]
ranked = [c["video_id"] for c in rank_candidates(cands, 190, "This Rhythm (feat. RAHH)")]
check(ranked[0] == "ext", "extended mix ranks first")
check(ranked[1] == "off", "matching original beats lyric video")
check(ranked[-1] == "set", "hour-long set ranks last")

wrong = [{"video_id": "w", "duration": 185, "channel": "HNTR", "title": "Shook Ones, Pt III (Extended Mix)"},
         {"video_id": "r", "duration": 185, "channel": "Eazy", "title": "Mobb Deep - Shook Ones (Eazy Remix)"}]
ranked = rank_candidates(wrong, 185, "Shook Ones (Eazy Remix)")
check(ranked[0]["video_id"] == "r" and ranked[1]["score"] < 0, "different remix is rejected")
topic = [{"video_id": "t", "duration": 301, "channel": "Arma - Topic", "title": "GOOD LIFE"}]
check(rank_candidates(topic, 301, "GOOD LIFE")[0]["score"] > 10, "topic upload without artist matches")

fake_ext = [{"video_id": "x", "duration": 195, "channel": "a", "title": "Song (Extended Mix)"},
            {"video_id": "o", "duration": 191, "channel": "Artist - Topic", "title": "Song"}]
check(rank_candidates(fake_ext, 190, "Song")[0]["video_id"] == "o", "mislabelled 'extended' gets no bonus")

other = [{"video_id": "s", "duration": 367, "channel": "Mochakk", "title": "Da Fonk (feat. Joni) [Solarce Brothers Extended Remix]"},
         {"video_id": "o", "duration": 367, "channel": "Mochakk", "title": "Da Fonk (feat. Joni)"}]
ranked = rank_candidates(other, 366, "Da Fonk (feat. Joni)")
check(ranked[0]["video_id"] == "o" and ranked[1]["score"] < 0, "another remixer's version is rejected")
own = [{"video_id": "e", "duration": 323, "channel": "Defected", "title": "I Got Nothing (Ferreck Dawn Extended Remix)"},
       {"video_id": "a", "duration": 172, "channel": "Ferreck Dawn", "title": "I Got Nothing (Ferreck Dawn Mix) (Official Audio)"}]
check(rank_candidates(own, 171, "I Got Nothing - Ferreck Dawn Mix")[0]["video_id"] == "e",
      "extended version of the same remix wins")
vis = [{"video_id": "v", "duration": 287, "channel": "Nina Simone", "title": "See-Line Woman (Mochakk Mix / Visualizer)"}]
check(rank_candidates(vis, 287, "See-Line Woman - Mochakk Mix")[0]["score"] > 10, "visualizer tag is not a remix")

check(display_name("francesco verrillo", "Shakedown - At Night (Edit)", uploader=True)
      == "Shakedown - At Night (Edit)", "uploader dropped when title has its own artist")
check(display_name("Jamie Jones", "Gets Like That - Jamie Jones Remix")
      == "Jamie Jones - Gets Like That - Jamie Jones Remix", "real artist kept on a ' - Remix' title")
check(clean_title("Song (Flip) FREE DOWNLOAD WITH NO OUTRO") == "Song (Flip)", "promo text stripped")

ya = [{"video_id": "y", "duration": 385, "channel": "PHM", "title": "Late Replies - Give It To Ya (Original Mix)"}]
check(rank_candidates(ya, 210, "Give It To Me")[0]["score"] < 0, "'Give It To Ya' is not 'Give It To Me'")

iou = [{"video_id": "e", "duration": 271, "channel": "Tentendo", "title": "IOU (Extended Mix)"},
       {"video_id": "r", "duration": 232, "channel": "Sidekick", "title": "Tentendo - IOU (with BRUX)"}]
check(rank_candidates(iou, 229, "IOU (with BRUX)")[0]["video_id"] == "e", "'(with X)' credit not required")
orig = [{"video_id": "o", "duration": 396, "channel": "Label", "title": "Jay de Lys - Control (Original Mix)"},
        {"video_id": "r", "duration": 218, "channel": "Jay de Lys - Topic", "title": "Control"}]
check(rank_candidates(orig, 217, "Control")[0]["video_id"] == "o", "long 'Original Mix' counts as extended")

with tempfile.TemporaryDirectory() as tmp:
    lib = Path(tmp)
    (lib / "Song [abc123XYZ_-].wav").touch()
    (lib / "Other [zzz].wav").touch()
    check(find_wav(lib, "abc123XYZ_-") == lib / "Song [abc123XYZ_-].wav", "finds wav by id")
    check(find_wav(lib, "nope") is None, "missing id")

print("all checks passed")
