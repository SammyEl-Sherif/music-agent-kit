#!/usr/bin/env python3
"""Self-checks for rbm_scoring — candidate scoring and ambiguity handling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rbm_scoring import POSSIBLE, STRONG, VERSION_CONFLICT_CAP, classify, score_candidate  # noqa: E402

FAILURES = []


def check(desc, cond):
    if not cond:
        FAILURES.append(desc)


TRACK = {
    "title": "One More Time", "artist": "Daft Punk", "version_info": "",
    "duration": 320, "album": "Discovery", "label": "Virgin", "year": "2001",
}

# Perfect match scores strong
perfect = {**TRACK, "source": "musicbrainz"}
s, reasons = score_candidate(TRACK, perfect, cross_agreement=True)
check(f"perfect match strong (got {s})", s >= STRONG)
check("perfect classified strong", classify(s) == "strong")

# Version conflict is hard-capped: track is the Club Mix, candidate is plain
club = {**TRACK, "title": "One More Time (Club Mix)", "version_info": "Club Mix"}
s, reasons = score_candidate(club, perfect)
check(f"version conflict capped at {VERSION_CONFLICT_CAP} (got {s})", s <= VERSION_CONFLICT_CAP)
check("conflict reason surfaced", any("CONFLICT" in r for r in reasons))
check("conflict is ambiguous, never auto", classify(s) == "ambiguous")

# Matching version markers score well
club_cand = {**perfect, "title": "One More Time (Club Mix)"}
s, _ = score_candidate(club, club_cand)
check(f"matching versions strong (got {s})", s >= STRONG)

# Wrong artist drags below strong
wrong_artist = {**perfect, "artist": "Stardust"}
s, _ = score_candidate(TRACK, wrong_artist)
check(f"wrong artist not strong (got {s})", s < STRONG)

# Duration mismatch costs the duration weight
long_cand = {**perfect, "duration": 500}
s_long, _ = score_candidate(TRACK, long_cand)
s_exact, _ = score_candidate(TRACK, perfect)
check("duration mismatch scores lower", s_long < s_exact)

# Classification bands: below 0.75 is ambiguous (never auto-applied)
check("0.74 ambiguous", classify(0.74) == "ambiguous")
check("0.75 possible", classify(POSSIBLE) == "possible")
check("0.89 possible", classify(0.89) == "possible")
check("0.90 strong", classify(STRONG) == "strong")

# Cross-source agreement adds, never exceeds 1.0
s_agree, _ = score_candidate(TRACK, perfect, cross_agreement=True)
s_alone, _ = score_candidate(TRACK, perfect, cross_agreement=False)
check("agreement bonus applied", s_agree > s_alone)
check("score bounded at 1.0", s_agree <= 1.0)

# Title-only match is never definitive
title_only = {"title": "One More Time", "artist": "", "duration": 0, "album": "", "label": "", "year": ""}
s, _ = score_candidate(TRACK, title_only)
check(f"title-only never strong (got {s})", classify(s) != "strong")

if FAILURES:
    print(f"FAILED {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("OK: all scoring checks passed")
