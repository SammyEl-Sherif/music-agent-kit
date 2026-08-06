#!/usr/bin/env python3
"""Self-checks for rbm_cleaning — no network, no library, no mutagen needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rbm_cleaning import (  # noqa: E402
    clean_tag_title, parse_filename, proposed_display_title, strip_track_number,
)

FAILURES = []


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


# The canonical example from the spec
p = parse_filename("01 - Daft_Punk_-_One_More_Time_(Club_Mix)_WEB_320")
check("spec example artist", p["artist"], "Daft Punk")
check("spec example title", p["title"], "One More Time")
check("spec example version", p["version_info"], "Club Mix")
check("spec example remixer (generic mix -> none)", p["remixer"], "")

# Track-number removal
check("tracknum dash", strip_track_number("01 - Song"), "Song")
check("tracknum dot", strip_track_number("07. Song"), "Song")
check("tracknum underscorey", parse_filename("03_Artist_-_Song")["artist"], "Artist")
check("disc-track", strip_track_number("1-01 Song"), "Song")
check("number IS the title", strip_track_number("99 Luftballons"), "99 Luftballons")

# Artist/title separation incl. en dash
p = parse_filename("Nena – 99 Luftballons")
check("en dash artist", p["artist"], "Nena")
check("en dash title", p["title"], "99 Luftballons")
check("no separator -> no artist guess", parse_filename("some random name")["artist"], "")

# Remix / version detection
p = parse_filename("Cerrone - Supernature (Eric Prydz Remix)")
check("remixer extracted", p["remixer"], "Eric Prydz")
check("remix version kept", p["version_info"], "Eric Prydz Remix")
p = parse_filename("Artist - Song (Extended Mix)")
check("extended kept", p["version_info"], "Extended Mix")
check("extended has no remixer", p["remixer"], "")
p = parse_filename("Artist - Song - Radio Edit")
check("trailing dash version", p["version_info"], "Radio Edit")
check("trailing dash title", p["title"], "Song")
p = parse_filename("Artist - Song (Live)")
check("live kept", p["version_info"], "Live")

# Featured artists
p = parse_filename("Modjo - Lady (feat. Yann Destal)")
check("feat in parens", p["featured"], "Yann Destal")
p = parse_filename("Artist feat. MC Someone - Song")
check("feat in artist half", p["featured"], "MC Someone")
check("feat stripped from artist", p["artist"], "Artist")

# Technical suffix removal
p = parse_filename("Artist - Song WEB FLAC")
check("tech suffix removed", p["title"], "Song")
p = parse_filename("Artist - Song [Official Video] 320kbps")
check("junk group + kbps removed", p["title"], "Song")
p = parse_filename("Artist - Song (Official Audio)")
check("official audio group removed", p["title"], "Song")

# Normalization but NOT title-casing
p = parse_filename("MGMT - Electric Feel")
check("case preserved upper", p["artist"], "MGMT")
p = parse_filename("sebastiAn - Ross Ross Ross")
check("case preserved mixed", p["artist"], "sebastiAn")

# Duplicated artist text
p = parse_filename("Daft Punk - Daft Punk - One More Time")
check("doubled artist deduped", p["title"], "One More Time")
p = parse_filename("Artist - Song (Love Break) (Love Break)")
check("doubled unknown group left alone", p["title"].count("(Love Break)"), 2)

# Version info is never discarded when reconstructing the display title
check("display title with version", proposed_display_title("One More Time", "Club Mix"),
      "One More Time (Club Mix)")
check("display title no version", proposed_display_title("One More Time", ""), "One More Time")

# Tag-title cleanup
c = clean_tag_title("One_More_Time_(Club_Mix)_WEB")
check("tag clean title", c["title"], "One More Time")
check("tag clean version", c["version_info"], "Club Mix")

if FAILURES:
    print(f"FAILED {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("OK: all cleaning checks passed")
