#!/usr/bin/env python3
"""Self-checks for the workflow plumbing: review-file parsing, backup creation,
rollback, metadata preservation, and sync-status tracking. Uses a temp dir and
plain files — no mutagen, no network, no real music library."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rbm_store as store  # noqa: E402
from rbm_tags import merge_changes  # noqa: E402

FAILURES = []


def check(desc, cond):
    if not cond:
        FAILURES.append(desc)


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    review_dir = tmp / "review"
    backup_dir = tmp / "backups"

    # --- review file round-trip and validation
    rows = [
        {"file_path": str(tmp / "a.mp3"), "original_filename": "a.mp3",
         "cleaned_title": "Song A", "proposed_artist": "Artist A",
         "confidence": "0.95", "source": "musicbrainz", "status": "pending"},
        {"file_path": str(tmp / "b.mp3"), "original_filename": "b.mp3",
         "cleaned_title": "Song B", "proposed_artist": "Artist B",
         "confidence": "0.55", "source": "none", "status": "ambiguous"},
    ]
    store.save_review_csv(review_dir, rows)
    loaded = store.load_review_csv(review_dir)
    check("review row count", len(loaded) == 2)
    check("review preserves values", loaded[0]["proposed_artist"] == "Artist A")
    check("review preserves status", loaded[1]["status"] == "ambiguous")
    check("all columns present", set(store.REVIEW_COLUMNS) <= set(loaded[0].keys()))

    # a manually edited value must survive a round-trip exactly
    loaded[0]["proposed_artist"] = "Hand-Corrected Artist"
    loaded[0]["status"] = "approved"
    store.save_review_csv(review_dir, loaded)
    again = store.load_review_csv(review_dir)
    check("manual edit preserved exactly", again[0]["proposed_artist"] == "Hand-Corrected Artist")

    # invalid status rejected
    (review_dir / store.REVIEW_CSV).write_text(
        ",".join(store.REVIEW_COLUMNS) + "\n" + ",".join(["x"] * len(store.REVIEW_COLUMNS)) + "\n"
    )
    try:
        store.load_review_csv(review_dir)
        check("invalid status detected", False)
    except store.StoreError:
        pass

    # --- backup creation + rollback
    f1, f2 = tmp / "a.mp3", tmp / "b.mp3"
    f1.write_bytes(b"ORIGINAL-A")
    f2.write_bytes(b"ORIGINAL-B")
    bset = store.create_backup(backup_dir, [f1, f2])
    check("backup set exists", bset.exists() and (bset / "manifest.json").exists())
    check("backup copies content", (bset / "0000__a.mp3").read_bytes() == b"ORIGINAL-A")
    check("latest_backup finds it", store.latest_backup(backup_dir) == bset)

    f1.write_bytes(b"MODIFIED-A")  # simulate an apply
    f2.write_bytes(b"MODIFIED-B")
    results = store.restore_backup(bset)
    check("rollback restores all", all(res == "restored" for _, res in results))
    check("rollback content A", f1.read_bytes() == b"ORIGINAL-A")
    check("rollback content B", f2.read_bytes() == b"ORIGINAL-B")

    # --- preservation of existing metadata (merge rules)
    current = {"title": "Kept Title", "artist": "", "genre": "House"}
    proposed = {"title": "New Title", "artist": "New Artist", "genre": "", "year": "1999"}
    to_write, skipped = merge_changes(current, proposed, allow_overwrite=False)
    check("empty current gets filled", to_write.get("artist") == "New Artist")
    check("non-empty preserved w/o approval", "title" not in to_write and "title" in skipped)
    check("empty proposed never blanks a tag", "genre" not in to_write)
    check("new field written", to_write.get("year") == "1999")
    to_write, _ = merge_changes(current, proposed, allow_overwrite=True)
    check("approved overwrite allowed", to_write.get("title") == "New Title")
    to_write, _ = merge_changes({"title": "Same"}, {"title": "Same"}, allow_overwrite=True)
    check("identical value is a no-op", "title" not in to_write)

    # --- sync status tracking
    rows = [
        {"file_path": "/x/a.mp3", "source": "mb", "confidence": "0.9", "status": "applied"},
        {"file_path": "/x/b.mp3", "source": "mb", "confidence": "0.9", "status": "applied"},
        {"file_path": "/x/c.mp3", "source": "mb", "confidence": "0.9", "status": "rejected"},
    ]
    n = store.set_status(rows, {"/x/a.mp3"}, "applied", "synced")
    check("targeted sync marks one", n == 1 and rows[0]["status"] == "synced")
    check("untargeted row untouched", rows[1]["status"] == "applied")
    check("rejected can never become synced", rows[2]["status"] == "rejected")
    n = store.set_status(rows, None, "applied", "synced")
    check("bulk sync marks remaining applied", n == 1 and rows[1]["status"] == "synced")
    store.write_sync_lists(review_dir, rows)
    done = (review_dir / store.SYNC_DONE).read_text().strip().splitlines()
    pending = (review_dir / store.SYNC_PENDING).read_text().strip()
    check("sync-done list written", sorted(done) == ["/x/a.mp3", "/x/b.mp3"])
    check("sync-pending now empty", pending == "")

    # --- audit log shape
    store.append_audit(review_dir, {"file_path": "/x/a.mp3", "original_metadata": {"title": "t"},
                                    "proposed_metadata": {}, "applied_metadata": {},
                                    "lookup_sources": "mb", "confidence": "0.9",
                                    "approval_status": "approved", "file_update_status": "applied",
                                    "rekordbox_sync_status": "synced", "error": ""})
    import json
    lines = (review_dir / store.AUDIT_LOG).read_text().strip().splitlines()
    entry = json.loads(lines[-1])
    check("audit has timestamp", "timestamp" in entry)
    check("audit has sync status", entry["rekordbox_sync_status"] == "synced")

# --- rekordbox staleness detection (pure logic; no DB needed)
from rbmeta import rekordbox_staleness_flags  # noqa: E402

f = rekordbox_staleness_flags({"title": "Real Title", "artist": "Real Artist"},
                              "some_file_name", "", "some_file_name")
check("stale when rb shows filename stem", "rekordbox_title_stale" in f)
check("stale when rb artist empty", "rekordbox_artist_stale" in f)
f = rekordbox_staleness_flags({"title": "Real Title", "artist": "Real Artist"},
                              "Real Title", "Real Artist", "whatever")
check("in-sync track not stale", f == [])
f = rekordbox_staleness_flags({}, "Anything", "Anyone", "stem")
check("untagged file never stale", f == [])
f = rekordbox_staleness_flags({"title": "New Title"}, "Old Title", "", "stem")
check("differing title is stale", f == ["rekordbox_title_stale"])

if FAILURES:
    print(f"FAILED {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("OK: all workflow checks passed")
