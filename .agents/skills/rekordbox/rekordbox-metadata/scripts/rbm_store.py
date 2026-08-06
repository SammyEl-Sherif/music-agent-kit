"""Persistence for rekordbox-metadata: scan results, the review file, backups,
the audit log, and sync-status tracking. All plain files under the configured
review/backup directories so the user can read and edit everything.
"""
from __future__ import annotations

import csv
import json
import shutil
import time
from pathlib import Path

REVIEW_COLUMNS = [
    "file_path", "original_filename", "original_title", "cleaned_title",
    "current_artist", "proposed_artist", "album", "album_artist", "remixer",
    "label", "genre", "year", "isrc", "version_info", "source", "confidence",
    "status",
    # extras beyond the required minimum:
    "proposed_title", "match_notes",
]

STATUSES = {
    "pending", "approved", "rejected", "ambiguous", "applied", "failed",
    "sync_pending", "synced", "sync_failed",
}

SCAN_FILE = "scan.json"
REVIEW_CSV = "review.csv"
REVIEW_JSON = "review-candidates.json"
AUDIT_LOG = "audit-log.jsonl"
SYNC_PENDING = "sync-pending.txt"
SYNC_DONE = "sync-done.txt"


class StoreError(Exception):
    pass


def ts() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S")


# ---------- scan ----------

def save_scan(review_dir: Path, payload: dict) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    p = review_dir / SCAN_FILE
    p.write_text(json.dumps(payload, indent=1))
    return p


def load_scan(review_dir: Path) -> dict:
    p = review_dir / SCAN_FILE
    if not p.exists():
        raise StoreError(f"no scan results at {p} — run the scan command first")
    return json.loads(p.read_text())


# ---------- review file ----------

def save_review_csv(review_dir: Path, rows: list[dict]) -> Path:
    review_dir.mkdir(parents=True, exist_ok=True)
    p = review_dir / REVIEW_CSV
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in REVIEW_COLUMNS})
    return p


def load_review_csv(review_dir: Path) -> list[dict]:
    p = review_dir / REVIEW_CSV
    if not p.exists():
        raise StoreError(f"no review file at {p} — run the lookup command first")
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, 2):  # 2 = first data line in the CSV
        status = (row.get("status") or "").strip()
        if status not in STATUSES:
            raise StoreError(
                f"review file line {i}: invalid status {status!r} "
                f"(valid: {', '.join(sorted(STATUSES))})"
            )
    return rows


def set_status(rows: list[dict], file_paths: set[str] | None, from_status: str, to_status: str) -> int:
    """Move rows (optionally limited to file_paths) from one status to another.
    Returns how many changed. Only from_status rows transition — enforced."""
    changed = 0
    for row in rows:
        if row.get("status") != from_status:
            continue
        if file_paths is not None and row.get("file_path") not in file_paths:
            continue
        row["status"] = to_status
        changed += 1
    return changed


# ---------- backups ----------

def create_backup(backup_dir: Path, files: list[Path]) -> Path:
    """Copy every file into a new timestamped backup set with a manifest.
    Returns the backup set directory."""
    dest = backup_dir / f"apply-{ts()}"
    dest.mkdir(parents=True, exist_ok=False)
    manifest = []
    for i, f in enumerate(files):
        copy_name = f"{i:04d}__{f.name}"
        shutil.copy2(f, dest / copy_name)
        manifest.append({"original": str(f), "backup": copy_name})
    (dest / "manifest.json").write_text(json.dumps({"timestamp": ts(), "files": manifest}, indent=1))
    return dest


def latest_backup(backup_dir: Path) -> Path | None:
    if not backup_dir.exists():
        return None
    sets = sorted(p for p in backup_dir.iterdir() if p.is_dir() and p.name.startswith("apply-"))
    return sets[-1] if sets else None


def restore_backup(backup_set: Path) -> list[tuple[str, str]]:
    """Copy every backed-up file over its original. Returns (original, result)
    pairs; result is 'restored' or an error string. Never deletes anything."""
    manifest_path = backup_set / "manifest.json"
    if not manifest_path.exists():
        raise StoreError(f"backup set {backup_set} has no manifest.json")
    manifest = json.loads(manifest_path.read_text())
    results = []
    for entry in manifest["files"]:
        original = Path(entry["original"])
        backup_file = backup_set / entry["backup"]
        try:
            if not backup_file.exists():
                raise FileNotFoundError(f"missing backup copy {backup_file.name}")
            shutil.copy2(backup_file, original)
            results.append((str(original), "restored"))
        except OSError as e:
            results.append((str(original), f"error: {e}"))
    return results


# ---------- audit log ----------

def append_audit(review_dir: Path, entry: dict) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    with open(review_dir / AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- sync tracking ----------

def write_sync_lists(review_dir: Path, rows: list[dict]) -> None:
    pending = [r["file_path"] for r in rows if r.get("status") in ("applied", "sync_pending")]
    done = [r["file_path"] for r in rows if r.get("status") == "synced"]
    (review_dir / SYNC_PENDING).write_text("\n".join(pending) + ("\n" if pending else ""))
    (review_dir / SYNC_DONE).write_text("\n".join(done) + ("\n" if done else ""))
