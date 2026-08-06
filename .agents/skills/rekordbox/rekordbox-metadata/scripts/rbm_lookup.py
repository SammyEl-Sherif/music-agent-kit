"""MusicBrainz (primary) and Discogs (secondary) lookup for rekordbox-metadata.

stdlib-only HTTP (urllib). Both APIs are rate-limited to ~1 request/second and
every response is cached on disk, so re-runs are free. Credentials come from
rbm_config.load_env() and are used solely in the request — never logged,
never written to the cache, review files, or reports.

If a source is unreachable it is reported as degraded and lookups continue with
whatever sources remain. No source -> no candidates. We never invent metadata.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "music-agent-kit/rekordbox-metadata/0.1 (https://github.com/local; personal library tool)"
RATE_LIMIT_SECONDS = 1.1
_last_request_ts = 0.0


class LookupCache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def get(self, key: str):
        entry = self.data.get(key)
        return entry["result"] if entry else None

    def put(self, key: str, result):
        self.data[key] = {"result": result, "ts": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data))


def _throttled_get(url: str, headers: dict) -> dict:
    global _last_request_ts
    wait = RATE_LIMIT_SECONDS - (time.time() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    _last_request_ts = time.time()
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def mb_search(artist: str, title: str, cache: LookupCache) -> list[dict]:
    """Search MusicBrainz recordings; return candidate dicts (may be empty)."""
    query_parts = [f'recording:"{title}"']
    if artist:
        query_parts.append(f'artist:"{artist}"')
    query = " AND ".join(query_parts)
    key = "mb:" + query
    cached = cache.get(key)
    if cached is not None:
        return cached
    url = (
        "https://musicbrainz.org/ws/2/recording/?"
        + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 5})
    )
    data = _throttled_get(url, {})
    candidates = []
    for rec in data.get("recordings", []):
        credit = "".join(
            (c.get("name") or c.get("artist", {}).get("name", "")) + (c.get("joinphrase") or "")
            for c in rec.get("artist-credit", [])
        ).strip()
        release = (rec.get("releases") or [{}])[0]
        candidates.append({
            "source": "musicbrainz",
            "source_id": rec.get("id", ""),
            "artist": credit,
            "title": rec.get("title", ""),
            "album": release.get("title", ""),
            "album_artist": "",
            "label": "",
            "genre": "",
            "year": (release.get("date") or "")[:4],
            "isrc": "",
            "duration": (rec.get("length") or 0) / 1000.0,
            "mb_score": rec.get("score", 0),
        })
    cache.put(key, candidates)
    return candidates


def discogs_search(artist: str, title: str, token: str, cache: LookupCache) -> list[dict]:
    """Search Discogs releases; returns release-level candidates (label/genre/
    year evidence mostly). Requires a token; without one returns []."""
    if not token:
        return []
    key = f"dc:{artist}|{title}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    url = "https://api.discogs.com/database/search?" + urllib.parse.urlencode({
        "artist": artist, "track": title, "type": "release", "per_page": 5,
    })
    # Token goes in the Authorization header only — never in the URL, so it can
    # never end up in a cache key, log line, or error message.
    data = _throttled_get(url, {"Authorization": f"Discogs token={token}"})
    candidates = []
    for res in data.get("results", []):
        full = res.get("title", "")  # "Artist - Release Title"
        d_artist, _, d_release = full.partition(" - ")
        genres = (res.get("genre") or []) + (res.get("style") or [])
        candidates.append({
            "source": "discogs",
            "source_id": str(res.get("id", "")),
            "artist": d_artist.strip(),
            "title": title,  # search matched our track query; release has no track titles
            "album": d_release.strip(),
            "album_artist": d_artist.strip(),
            "label": (res.get("label") or [""])[0],
            "genre": ", ".join(genres[:2]),
            "year": str(res.get("year") or ""),
            "isrc": "",
            "duration": 0,
            "version_unknown": True,  # release search carries no track-level version info
        })
    cache.put(key, candidates)
    return candidates


def lookup_track(clues: dict, sources: list[str], token: str, cache: LookupCache) -> tuple[list[dict], list[str]]:
    """Query enabled sources for one track. Returns (candidates, errors)."""
    artist = clues.get("artist") or ""
    title = clues.get("title") or ""
    if not title:
        return [], ["no usable title to search with"]
    candidates: list[dict] = []
    errors: list[str] = []
    if "musicbrainz" in sources:
        try:
            candidates += mb_search(artist, title, cache)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            errors.append(f"musicbrainz unavailable: {getattr(e, 'reason', e)}")
    if "discogs" in sources:
        if not token:
            errors.append("discogs skipped: no DISCOGS_TOKEN in env/.env")
        else:
            try:
                candidates += discogs_search(artist, title, token, cache)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                errors.append(f"discogs unavailable: {getattr(e, 'reason', e)}")
    return candidates, errors


def sources_agree(mb: dict | None, dc: dict | None) -> bool:
    """Cross-source agreement: same artist (loosely) from both databases."""
    if not mb or not dc:
        return False
    from rbm_scoring import similarity
    return similarity(mb.get("artist", ""), dc.get("artist", "")) > 0.85
