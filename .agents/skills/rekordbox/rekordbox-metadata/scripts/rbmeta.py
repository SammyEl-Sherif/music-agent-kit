#!/usr/bin/env python3
"""rekordbox-metadata — clean, identify, enrich, and sync music metadata.

Subcommands: scan | clean | lookup | review | apply | sync | undo
Run any of them with -h for options. v1 works purely on audio-file tags: it
NEVER opens or edits the rekordbox database. Getting changes into rekordbox is
the guided Reload Tag workflow in `sync`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rbm_cleaning as cleaning
import rbm_config as config
import rbm_scoring as scoring
import rbm_store as store

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".wav", ".aiff", ".aif"}
PLACEHOLDER_ARTISTS = {"unknown", "unknown artist", "various", "various artists", "va", "artist", "n/a", "none"}


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def get_config(args) -> tuple[dict, Path]:
    try:
        return config.load_config(args.config)
    except config.ConfigError as e:
        fail(str(e))


# ---------------------------------------------------------------- scan

def looks_suspicious(tags: dict, stem: str) -> list[str]:
    flags = []
    artist = (tags.get("artist") or "").strip()
    title = (tags.get("title") or "").strip()
    if not artist:
        flags.append("missing_artist")
    elif artist.lower() in PLACEHOLDER_ARTISTS:
        flags.append("placeholder_artist")
    if not title:
        flags.append("missing_title")
    else:
        tl = title.lower()
        if "_" in title or cleaning.TRACKNUM_RE.match(title):
            flags.append("title_looks_like_filename")
        elif any(tok in cleaning.TECH_TOKENS for tok in tl.split()):
            flags.append("title_has_tech_tags")
        elif title == stem:
            flags.append("title_equals_filename")
        if not artist and " - " in title:
            flags.append("artist_embedded_in_title")
    return flags


def rekordbox_staleness_flags(tags: dict, rb_title: str, rb_artist: str, stem: str) -> list[str]:
    """Pure helper: does rekordbox's stored metadata lag the file's tags?
    (i.e. the track needs a Reload Tag, not a lookup)."""
    flags = set()
    ft = (tags.get("title") or "").strip()
    fa = (tags.get("artist") or "").strip()
    rb_title = (rb_title or "").strip()
    rb_artist = (rb_artist or "").strip()
    if ft and (not rb_title or rb_title == stem or rb_title != ft):
        flags.add("rekordbox_title_stale")
    if fa and (not rb_artist or rb_artist != fa):
        flags.add("rekordbox_artist_stale")
    return sorted(flags)


def collect_rekordbox_tracks():
    """READ-ONLY enumeration of the rekordbox Collection: every track's file
    path plus the Title/Artist rekordbox currently displays. Never writes."""
    try:
        from pyrekordbox import Rekordbox6Database
    except ImportError:
        fail("pyrekordbox is not installed — install with: pip3 install pyrekordbox --break-system-packages")
    db = Rekordbox6Database()
    out = []
    for c in db.get_content():
        fp = c.FolderPath or ""
        if not fp or getattr(c, "rb_local_deleted", 0):
            continue
        out.append({
            "path": fp,
            "rb_title": c.Title or "",
            "rb_artist": (c.Artist.Name if c.Artist else "") or "",
        })
    return out


def cmd_scan(args):
    cfg_path = config.find_config(args.config)
    if cfg_path is None:
        created = config.create_default_config()
        print(f"No config found — created a default at: {created}")
        print("Edit music_directory (and the backup/review dirs) there, then re-run scan.")
        return
    cfg, cfg_path = get_config(args)

    try:
        import rbm_tags as tags_mod
    except Exception as e:  # pragma: no cover
        fail(str(e))

    rb_meta: dict[str, dict] = {}
    if args.from_rekordbox:
        collection = collect_rekordbox_tracks()
        entries = []
        for t in collection:
            p = Path(t["path"])
            if p.suffix.lower() in AUDIO_EXTS:
                entries.append(p)
                rb_meta[str(p)] = t
        if args.limit:
            entries = entries[: args.limit]
        files = entries
        print(f"Scanning {len(files)} tracks from the rekordbox Collection (read-only) …")
        source = "rekordbox collection"
    else:
        music_dir = cfg["music_directory"]
        if not music_dir.exists():
            fail(f"music_directory does not exist: {music_dir}")
        files = sorted(p for p in music_dir.rglob("*") if p.suffix.lower() in AUDIO_EXTS and p.is_file())
        if args.limit:
            files = files[: args.limit]
        print(f"Scanning {len(files)} audio files under {music_dir} …")
        source = str(music_dir)

    tracks, errors, missing = [], [], []
    for f in files:
        if not f.exists():
            missing.append(str(f))
            continue
        try:
            tags = tags_mod.read_tags(f)
            dur = tags_mod.duration_seconds(f)
        except tags_mod.TagError as e:
            errors.append(f"{f}: {e}")
            continue
        flags = looks_suspicious(tags, f.stem)
        parsed = cleaning.parse_filename(f.stem)
        track = {
            "file_path": str(f),
            "original_filename": f.name,
            "tags": tags,
            "duration": round(dur, 1),
            "flags": flags,
            "parsed": parsed,
        }
        rb = rb_meta.get(str(f))
        if rb:
            track["rekordbox"] = {"title": rb["rb_title"], "artist": rb["rb_artist"]}
            track["rb_stale"] = rekordbox_staleness_flags(tags, rb["rb_title"], rb["rb_artist"], f.stem)
        tracks.append(track)

    flagged = [t for t in tracks if t["flags"]]
    stale = [t for t in tracks if t.get("rb_stale")]
    payload = {"music_directory": source, "scanned": len(tracks), "flagged": len(flagged), "tracks": tracks}
    out = store.save_scan(cfg["review_directory"], payload)

    print(f"\nScanned {len(tracks)} files; {len(flagged)} flagged as missing/suspicious.")
    if missing:
        print(f"{len(missing)} Collection entries point at files that no longer exist (first 5):")
        for m in missing[:5]:
            print(f"  ! {m}")
    if errors:
        print(f"{len(errors)} unreadable files (first 5):")
        for e in errors[:5]:
            print(f"  ! {e}")
    for t in flagged[:40]:
        print(f"  - {t['original_filename']}  [{', '.join(t['flags'])}]")
    if len(flagged) > 40:
        print(f"  … and {len(flagged) - 40} more")
    if stale:
        print(f"\n{len(stale)} track(s) have file tags newer than what rekordbox shows (need Reload Tag, not lookup):")
        for t in stale[:15]:
            print(f"  ~ {t['original_filename']}  [{', '.join(t['rb_stale'])}]")
        if len(stale) > 15:
            print(f"  … and {len(stale) - 15} more")
    print(f"\nScan results: {out}")
    print("Next: `clean --dry-run` to preview title cleanup, then `lookup`.")


# ---------------------------------------------------------------- clean

def cmd_clean(args):
    if not args.dry_run:
        fail("clean only supports --dry-run in v1 (cleanup is applied via the review+apply flow)")
    cfg, _ = get_config(args)
    scan = store.load_scan(cfg["review_directory"])
    flagged = [t for t in scan["tracks"] if t["flags"]]
    if not flagged:
        print("Nothing flagged — no cleanup to propose.")
        return
    print(f"Proposed cleanup for {len(flagged)} flagged tracks (dry run, nothing written):\n")
    for t in flagged:
        p = t["parsed"]
        cur = t["tags"]
        print(f"  {t['original_filename']}")
        print(f"    current tags : artist={cur.get('artist', '—')!r}  title={cur.get('title', '—')!r}")
        print(f"    proposed     : artist={p['artist'] or '—'!r}  title={p['title'] or '—'!r}"
              + (f"  version={p['version_info']!r}" if p["version_info"] else "")
              + (f"  feat={p['featured']!r}" if p["featured"] else "")
              + (f"  remixer={p['remixer']!r}" if p["remixer"] else ""))
    print("\nNo files were modified. Next: `lookup` to fetch metadata candidates.")


# ---------------------------------------------------------------- lookup

def cmd_lookup(args):
    cfg, _ = get_config(args)
    import rbm_lookup as lookup
    scan = store.load_scan(cfg["review_directory"])
    flagged = [t for t in scan["tracks"] if t["flags"]]
    if args.max:
        flagged = flagged[: args.max]
    if not flagged:
        print("Nothing flagged — nothing to look up.")
        return

    creds = config.load_env()
    token = creds.get("discogs_token", "")
    cache = lookup.LookupCache(cfg["review_directory"] / "lookup-cache.json")
    sources = [str(s) for s in cfg.get("sources", ["musicbrainz", "discogs"])]

    rows, all_candidates, degraded = [], {}, set()
    print(f"Looking up {len(flagged)} tracks via {', '.join(sources)} (rate-limited; cached)…")
    for t in flagged:
        p, tags = t["parsed"], t["tags"]
        clues = {
            "artist": p["artist"] or tags.get("artist", ""),
            "title": p["title"] or tags.get("title", "") or Path(t["file_path"]).stem,
            "version_info": p["version_info"],
            "duration": t["duration"],
            "album": tags.get("album", ""),
            "label": tags.get("label", ""),
            "year": tags.get("year", ""),
        }
        candidates, errors = lookup.lookup_track(clues, sources, token, cache)
        for err in errors:
            degraded.add(err)

        mb_best = next((c for c in candidates if c["source"] == "musicbrainz"), None)
        dc_best = next((c for c in candidates if c["source"] == "discogs"), None)
        agree = lookup.sources_agree(mb_best, dc_best)

        scored = []
        for c in candidates:
            s, reasons = scoring.score_candidate(clues, c, cross_agreement=agree)
            scored.append({**c, "confidence": s, "reasons": reasons})
        scored.sort(key=lambda c: c["confidence"], reverse=True)
        best = scored[0] if scored else None
        all_candidates[t["file_path"]] = scored[:5]

        conf = best["confidence"] if best else 0.0
        status = "ambiguous" if scoring.classify(conf) == "ambiguous" else "pending"
        rows.append({
            "file_path": t["file_path"],
            "original_filename": t["original_filename"],
            "original_title": tags.get("title", ""),
            "cleaned_title": p["title"],
            "current_artist": tags.get("artist", ""),
            "proposed_artist": (best or {}).get("artist", "") or p["artist"],
            "album": (best or {}).get("album", ""),
            "album_artist": (best or {}).get("album_artist", ""),
            "remixer": p["remixer"],
            "label": (best or {}).get("label", ""),
            "genre": (best or {}).get("genre", ""),
            "year": (best or {}).get("year", ""),
            "isrc": (best or {}).get("isrc", ""),
            "version_info": p["version_info"],
            "source": (best or {}).get("source", "none"),
            "confidence": f"{conf:.2f}",
            "status": status,
            "proposed_title": cleaning.proposed_display_title(p["title"], p["version_info"])
                              if p["title"] else "",
            "match_notes": "; ".join((best or {}).get("reasons", [])[:3]),
        })

    csv_path = store.save_review_csv(cfg["review_directory"], rows)
    (cfg["review_directory"] / store.REVIEW_JSON).write_text(json.dumps(all_candidates, indent=1))

    n_pending = sum(1 for r in rows if r["status"] == "pending")
    n_amb = sum(1 for r in rows if r["status"] == "ambiguous")
    print(f"\nWrote {len(rows)} rows -> {csv_path}")
    print(f"  {n_pending} with a credible candidate (pending)  |  {n_amb} ambiguous (no auto-recommendation)")
    if degraded:
        print("\nDegraded sources (lookups continued without them):")
        for d in sorted(degraded):
            print(f"  ! {d}")
    print("\nNext: `review` to inspect, then edit the CSV's status column to approve.")


# ---------------------------------------------------------------- review

def _print_row(i: int, r: dict):
    print(f"[{i}] {r['original_filename']}   status={r['status']}  confidence={r['confidence']}  source={r['source']}")
    print(f"    artist: {r['current_artist'] or '—'!r} -> {r['proposed_artist'] or '—'!r}")
    print(f"    title : {r['original_title'] or '—'!r} -> {r['proposed_title'] or r['cleaned_title'] or '—'!r}")
    extras = {k: r[k] for k in ("album", "label", "genre", "year", "isrc", "remixer", "version_info") if r.get(k)}
    if extras:
        print(f"    also  : {', '.join(f'{k}={v}' for k, v in extras.items())}")
    if r.get("match_notes"):
        print(f"    why   : {r['match_notes']}")


def cmd_review(args):
    cfg, _ = get_config(args)
    rows = store.load_review_csv(cfg["review_directory"])

    if args.approve or args.reject:
        targets = args.approve or args.reject
        to_status = "approved" if args.approve else "rejected"
        idxs = set(range(1, len(rows) + 1)) if targets == "all" else {int(x) for x in targets.split(",")}
        changed = 0
        for i, r in enumerate(rows, 1):
            if i in idxs and r["status"] in ("pending", "ambiguous", "approved", "rejected"):
                r["status"] = to_status
                changed += 1
        store.save_review_csv(cfg["review_directory"], rows)
        print(f"Marked {changed} row(s) {to_status}.")
        return

    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"Review file: {cfg['review_directory'] / store.REVIEW_CSV}")
    print("Status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
    for i, r in enumerate(rows, 1):
        _print_row(i, r)

    cand_file = cfg["review_directory"] / store.REVIEW_JSON
    if cand_file.exists() and any(r["status"] == "ambiguous" for r in rows):
        candidates = json.loads(cand_file.read_text())
        print("\nTop candidates for ambiguous rows (no auto-recommendation below 0.75):")
        for i, r in enumerate(rows, 1):
            if r["status"] != "ambiguous":
                continue
            print(f"\n[{i}] {r['original_filename']}:")
            for c in candidates.get(r["file_path"], [])[:3]:
                print(f"    {c['confidence']:.2f}  {c['artist']} - {c['title']}  ({c['source']})")
                for reason in c["reasons"][:3]:
                    print(f"          · {reason}")
    print(
        "\nTo approve: edit the CSV's status column to `approved` (you may also correct any "
        "proposed value — manual edits are preserved exactly), or use `review --approve 1,3,5`."
    )


# ---------------------------------------------------------------- apply

def cmd_apply(args):
    cfg, _ = get_config(args)
    import rbm_tags as tags_mod
    rows = store.load_review_csv(cfg["review_directory"])
    approved = [r for r in rows if r["status"] == "approved"]
    if not approved:
        fail("no rows are marked `approved` in the review file — nothing to apply")

    plans = []
    for r in approved:
        f = Path(r["file_path"])
        if not f.exists():
            plans.append((r, None, {}, {"__file__": "file not found"}))
            continue
        if f.suffix.lower() not in tags_mod.SUPPORTED_EXTS:
            plans.append((r, None, {}, {"__file__": f"unsupported format {f.suffix}"}))
            continue
        current = tags_mod.read_tags(f)
        proposed = {
            "title": r.get("proposed_title") or r.get("cleaned_title"),
            "artist": r.get("proposed_artist"),
            "album": r.get("album"), "albumartist": r.get("album_artist"),
            "remixer": r.get("remixer"), "label": r.get("label"),
            "genre": r.get("genre"), "year": r.get("year"), "isrc": r.get("isrc"),
        }
        to_write, skipped = tags_mod.merge_changes(current, proposed, allow_overwrite=True)
        plans.append((r, current, to_write, skipped))

    writable = [(r, cur, w, s) for r, cur, w, s in plans if w]
    print(f"{len(approved)} approved row(s); {len(writable)} file(s) have field changes to write:\n")
    for r, cur, to_write, skipped in plans:
        print(f"  {r['original_filename']}  (source={r['source']}, confidence={r['confidence']})")
        for field, val in to_write.items():
            print(f"     {field}: {(cur or {}).get(field, '—')!r} -> {val!r}")
        for field, why in skipped.items():
            print(f"     {field}: skipped — {why}")
        if not to_write:
            print("     (no effective changes)")

    if not args.yes:
        print("\nDry run — nothing written. Re-run with --yes after the user confirms.")
        return
    if not writable:
        print("\nNothing to write.")
        return

    backup_set = store.create_backup(cfg["backup_directory"], [Path(r["file_path"]) for r, *_ in writable])
    print(f"\nBackup created: {backup_set}")

    applied = failed = 0
    for r, current, to_write, _ in writable:
        f = Path(r["file_path"])
        entry = {
            "file_path": str(f),
            "original_metadata": current,
            "proposed_metadata": to_write,
            "lookup_sources": r["source"],
            "confidence": r["confidence"],
            "approval_status": "approved",
            "rekordbox_sync_status": "sync_pending",
        }
        try:
            written, _ = tags_mod.write_tags(f, to_write)
            r["status"] = "applied"
            applied += 1
            entry.update({"applied_metadata": {k: to_write[k] for k in written},
                          "file_update_status": "applied", "error": ""})
        except (tags_mod.TagError, OSError) as e:
            r["status"] = "failed"
            failed += 1
            entry.update({"applied_metadata": {}, "file_update_status": "failed", "error": str(e)})
        store.append_audit(cfg["review_directory"], entry)

    for r, cur, w, s in plans:
        if not w and r["status"] == "approved" and "__file__" in s:
            r["status"] = "failed"
            store.append_audit(cfg["review_directory"], {
                "file_path": r["file_path"], "original_metadata": {}, "proposed_metadata": {},
                "applied_metadata": {}, "lookup_sources": r["source"], "confidence": r["confidence"],
                "approval_status": "approved", "file_update_status": "failed",
                "rekordbox_sync_status": "n/a", "error": s["__file__"],
            })

    store.save_review_csv(cfg["review_directory"], rows)
    store.write_sync_lists(cfg["review_directory"], rows)
    print(f"\nApplied: {applied}  Failed: {failed}")
    print(f"Audit log: {cfg['review_directory'] / store.AUDIT_LOG}")
    print(f"Rekordbox reload list: {cfg['review_directory'] / store.SYNC_PENDING}")
    print("\nIMPORTANT: only the AUDIO FILES changed. rekordbox has NOT been updated yet —")
    print("run `sync` for the guided Reload Tag workflow.")


# ---------------------------------------------------------------- sync

def cmd_sync(args):
    cfg, _ = get_config(args)
    rows = store.load_review_csv(cfg["review_directory"])
    pending = [r for r in rows if r["status"] in ("applied", "sync_pending")]

    if args.mark_synced or args.mark_failed:
        subset = set(args.files) if args.files else None
        target = "synced" if args.mark_synced else "sync_failed"
        n = 0
        for from_status in ("applied", "sync_pending"):
            n += store.set_status(rows, subset, from_status, target)
        store.save_review_csv(cfg["review_directory"], rows)
        store.write_sync_lists(cfg["review_directory"], rows)
        for r in rows:
            if r["status"] == target and (subset is None or r["file_path"] in subset):
                store.append_audit(cfg["review_directory"], {
                    "file_path": r["file_path"], "original_metadata": {}, "proposed_metadata": {},
                    "applied_metadata": {}, "lookup_sources": r["source"], "confidence": r["confidence"],
                    "approval_status": "approved", "file_update_status": "applied",
                    "rekordbox_sync_status": target, "error": "",
                })
        report = cfg["review_directory"] / f"sync-report-{store.ts()}.md"
        synced = [r["file_path"] for r in rows if r["status"] == "synced"]
        failed = [r["file_path"] for r in rows if r["status"] == "sync_failed"]
        still = [r["file_path"] for r in rows if r["status"] in ("applied", "sync_pending")]
        report.write_text(
            "# rekordbox sync report\n\n"
            f"- synced: {len(synced)}\n- sync_failed: {len(failed)}\n- still pending: {len(still)}\n\n"
            + "".join(f"- [synced] {p}\n" for p in synced)
            + "".join(f"- [FAILED] {p}\n" for p in failed)
            + "".join(f"- [pending] {p}\n" for p in still)
        )
        print(f"Marked {n} row(s) {target}. Report: {report}")
        return

    if not pending:
        print("No files are pending rekordbox synchronization.")
        return
    backup = store.latest_backup(cfg["backup_directory"])
    print(f"{len(pending)} file(s) have updated tags awaiting a rekordbox reload.")
    print(f"Backup on disk: {backup or 'NONE FOUND — investigate before proceeding'}\n")
    print("Manual Reload Tag workflow (rekordbox is NOT updated until you finish this):")
    print("  1. Open rekordbox.")
    print("  2. In Collection, locate and select exactly these tracks:")
    for r in pending:
        print(f"       - {r['original_filename']}")
    print("  3. Right-click the selection and choose `Reload Tag`.")
    print("  4. WARNING: Reload Tag overwrites rekordbox's Title/Artist/Album/etc. with the")
    print("     values now in the audio files. Do NOT reload tracks whose rekordbox-side")
    print("     metadata you want to keep. Cues, grids, playlists, ratings and My Tags are")
    print("     not touched by Reload Tag.")
    print("  5. Verify a couple of tracks show the new metadata in rekordbox.")
    print("\nWhen the user confirms the reload is done, run: sync --mark-synced")
    print("(or `sync --mark-failed --files <path>` for tracks that didn't take).")
    print(f"Full path list: {cfg['review_directory'] / store.SYNC_PENDING}")


# ---------------------------------------------------------------- undo

def cmd_undo(args):
    cfg, _ = get_config(args)
    backup_set = store.latest_backup(cfg["backup_directory"])
    if backup_set is None:
        fail(f"no backup sets found under {cfg['backup_directory']}")
    manifest = json.loads((backup_set / "manifest.json").read_text())
    print(f"Most recent backup set: {backup_set}  ({len(manifest['files'])} file(s))")
    for entry in manifest["files"]:
        print(f"  - {entry['original']}")
    if not args.yes:
        print("\nDry run — nothing restored. Re-run with --yes after the user confirms.")
        return
    results = store.restore_backup(backup_set)
    ok = sum(1 for _, res in results if res == "restored")
    for original, res in results:
        marker = "✓" if res == "restored" else "!"
        print(f"  {marker} {original}: {res}")
        store.append_audit(cfg["review_directory"], {
            "file_path": original, "original_metadata": {}, "proposed_metadata": {},
            "applied_metadata": {}, "lookup_sources": "", "confidence": "",
            "approval_status": "undo", "file_update_status": res,
            "rekordbox_sync_status": "sync_pending", "error": "" if res == "restored" else res,
        })
    try:
        rows = store.load_review_csv(cfg["review_directory"])
        restored_paths = {o for o, res in results if res == "restored"}
        for r in rows:
            if r["file_path"] in restored_paths and r["status"] in ("applied", "synced", "sync_pending"):
                r["status"] = "approved"
        store.save_review_csv(cfg["review_directory"], rows)
        store.write_sync_lists(cfg["review_directory"], rows)
    except store.StoreError:
        pass
    print(f"\nRestored {ok}/{len(results)} file(s) from {backup_set.name}.")
    print("If any restored track was already reloaded in rekordbox, reload it again so")
    print("rekordbox shows the restored (original) tags.")


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(prog="rbmeta", description=__doc__)
    p.add_argument("--config", help="path to rekordbox-metadata.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="scan the music directory for missing/suspicious metadata")
    s.add_argument("--limit", type=int, help="scan at most N files")
    s.add_argument("--from-rekordbox", action="store_true",
                   help="scan the files in the rekordbox Collection (read-only DB access) "
                        "instead of walking music_directory")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("clean", help="preview filename/title cleanup (dry run only)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_clean)

    s = sub.add_parser("lookup", help="search MusicBrainz + Discogs and build the review file")
    s.add_argument("--max", type=int, help="look up at most N flagged tracks")
    s.set_defaults(func=cmd_lookup)

    s = sub.add_parser("review", help="display proposed changes and candidates")
    s.add_argument("--approve", help="row numbers to approve, e.g. 1,3,5 or 'all'")
    s.add_argument("--reject", help="row numbers to reject")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("apply", help="apply approved changes to audio tags (backup first)")
    s.add_argument("--yes", action="store_true", help="actually write (default: dry run)")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("sync", help="guided rekordbox Reload Tag workflow")
    s.add_argument("--mark-synced", action="store_true", help="mark pending rows synced (after user confirms)")
    s.add_argument("--mark-failed", action="store_true", help="mark rows sync_failed")
    s.add_argument("--files", nargs="*", help="limit marking to these file paths")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("undo", help="restore the most recent audio-file backup")
    s.add_argument("--yes", action="store_true", help="actually restore (default: dry run)")
    s.set_defaults(func=cmd_undo)

    args = p.parse_args()
    try:
        args.func(args)
    except store.StoreError as e:
        fail(str(e))


if __name__ == "__main__":
    main()
