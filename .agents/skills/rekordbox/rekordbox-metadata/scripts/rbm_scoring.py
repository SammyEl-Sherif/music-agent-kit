"""Candidate scoring for rekordbox-metadata. Pure logic, tested by test_scoring.py.

Scores a lookup candidate against a local track on a 0..1 scale and explains
why. A version-marker conflict (track says "Club Mix", candidate is the plain
mix) hard-caps the score at 0.6 — a wrong version is worse than no match.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from rbm_cleaning import VERSION_TRIGGERS, _tokens, split_versions

STRONG = 0.90      # strong candidate; show for approval
POSSIBLE = 0.75    # possible; requires explicit approval
VERSION_CONFLICT_CAP = 0.60

WEIGHTS = {
    "title": 0.30,
    "artist": 0.25,
    "version": 0.15,
    "duration": 0.10,
    "album": 0.05,
    "label": 0.05,
    "year": 0.05,
    "agreement": 0.05,
}


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def version_markers(title: str, version_info: str = "") -> set[str]:
    """The set of version-trigger tokens carried by a title + version string."""
    _, versions, _, _ = split_versions(title or "")
    text = " ".join(versions) + " " + (version_info or "")
    return {t for t in _tokens(text) if t in VERSION_TRIGGERS}


def score_candidate(track: dict, cand: dict, cross_agreement: bool = False) -> tuple[float, list[str]]:
    """Score `cand` against `track`. Both are dicts of metadata fields.

    track: title, artist, version_info, duration, album, label, year (best known)
    cand:  title, artist, duration, album, label, year, source
    Returns (score 0..1, list of human-readable reasons).
    """
    reasons: list[str] = []
    score = 0.0

    # Title: compare base titles (versions handled separately)
    t_base, _, _, _ = split_versions(track.get("title") or "")
    c_base, _, _, _ = split_versions(cand.get("title") or "")
    ts = similarity(t_base, c_base)
    score += WEIGHTS["title"] * ts
    reasons.append(f"title {ts:.2f} ({t_base!r} vs {c_base!r})")

    a_s = similarity(track.get("artist") or "", cand.get("artist") or "")
    score += WEIGHTS["artist"] * a_s
    reasons.append(f"artist {a_s:.2f}")

    # Version markers: match -> full credit; mismatch -> conflict cap. A
    # candidate whose title lacks our track's markers IS a mismatch (it's the
    # plain mix) — unless the source can't carry track-level version info at
    # all (cand["version_unknown"], e.g. Discogs release search), which is
    # merely absence of evidence and gets half credit.
    tv = version_markers(track.get("title") or "", track.get("version_info") or "")
    cv = version_markers(cand.get("title") or "", cand.get("version_info") or "")
    conflict = False
    if cand.get("version_unknown"):
        score += WEIGHTS["version"] * 0.5
        reasons.append("version unknown for this source (release-level match)")
    elif tv == cv:
        score += WEIGHTS["version"]
        if tv:
            reasons.append(f"version markers match: {sorted(tv)}")
    else:
        conflict = True
        reasons.append(f"VERSION CONFLICT: track {sorted(tv) or ['plain']} vs candidate {sorted(cv) or ['plain']}")

    td, cd = track.get("duration") or 0, cand.get("duration") or 0
    if td and cd:
        diff = abs(td - cd)
        if diff <= 3:
            score += WEIGHTS["duration"]
            reasons.append(f"duration matches (±{diff:.0f}s)")
        elif diff <= 8:
            score += WEIGHTS["duration"] * 0.5
            reasons.append(f"duration close (±{diff:.0f}s)")
        else:
            reasons.append(f"duration differs by {diff:.0f}s")
    else:
        score += WEIGHTS["duration"] * 0.5  # no evidence either way

    for field in ("album", "label"):
        s = similarity(track.get(field) or "", cand.get(field) or "")
        if s > 0.8:
            score += WEIGHTS[field]
            reasons.append(f"{field} matches")

    ty, cy = str(track.get("year") or ""), str(cand.get("year") or "")
    if ty and cy and ty[:4] == cy[:4]:
        score += WEIGHTS["year"]
        reasons.append(f"year matches ({cy[:4]})")

    if cross_agreement:
        score += WEIGHTS["agreement"]
        reasons.append("MusicBrainz and Discogs agree")

    if conflict:
        score = min(score, VERSION_CONFLICT_CAP)

    return round(min(score, 1.0), 3), reasons


def classify(score: float) -> str:
    if score >= STRONG:
        return "strong"
    if score >= POSSIBLE:
        return "possible"
    return "ambiguous"
