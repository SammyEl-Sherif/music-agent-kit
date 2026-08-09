#!/usr/bin/env python3
"""Self-check for track-centralizer. Needs no database and no network: builds a
throwaway source tree in a temp dir, plans targets, dry-runs, executes, and
undoes, asserting at each step that no file is ever lost or renamed.

Run: python3 test_centralize.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from centralize import apply_plan, move_file  # noqa: E402
from scan_tracks import CONFLICT_DIR, classify, plan_targets  # noqa: E402
from undo_centralize import undo  # noqa: E402

CHECKS = []


def check(name, cond):
    CHECKS.append((name, bool(cond)))
    print(("  ok  " if cond else "  FAIL") + f"  {name}")


def item(path, size, status="to_move"):
    return {"content_id": "0", "artist": "", "title": "", "path": path,
            "size": size, "status": status, "target": None,
            "conflict": False, "dupe_suspect": False}


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def main():
    root = tempfile.mkdtemp(prefix="rb-centralize-test-")
    try:
        run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    failed = [n for n, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


def run(root):
    # scan_tracks.main realpaths --dest before classifying; mirror that here
    # (matters on macOS, where the temp dir is a /var -> /private/var symlink).
    root = os.path.realpath(root)
    dest = os.path.join(root, "central")

    print("classify:")
    write(os.path.join(root, "a", "one.wav"), "x")
    check("local file outside dest -> to_move",
          classify(os.path.join(root, "a", "one.wav"), dest, []) == "to_move")
    check("nonexistent path -> missing",
          classify(os.path.join(root, "nope.wav"), dest, []) == "missing")
    check("empty path -> non_local", classify("", dest, []) == "non_local")
    check("exclude term wins",
          classify(os.path.join(root, "a", "one.wav"), dest, ["/a/"]) == "excluded")
    write(os.path.join(dest, "in.wav"), "x")
    check("file under dest -> already",
          classify(os.path.join(dest, "in.wav"), dest, []) == "already")

    print("plan_targets:")
    items = [
        item(os.path.join(root, "a", "one.wav"), 10),
        item(os.path.join(root, "b", "one.wav"), 10),   # collision, same size
        item(os.path.join(root, "c", "one.wav"), 99),   # collision, diff size
        item(os.path.join(root, "a", "two.wav"), 5),
        item(os.path.join(root, "a", "in.wav"), 7),     # name taken in dest
        item(os.path.join(root, "gone.wav"), 0, "missing"),
    ]
    plan_targets(items, dest, existing_names={"in.wav"})
    by = {i["path"]: i for i in items}
    check("first claimant gets dest root",
          by[os.path.join(root, "a", "one.wav")]["target"] == os.path.join(dest, "one.wav"))
    check("second claimant -> _conflicts/2, name kept",
          by[os.path.join(root, "b", "one.wav")]["target"]
          == os.path.join(dest, CONFLICT_DIR, "2", "one.wav"))
    check("third claimant -> _conflicts/3",
          by[os.path.join(root, "c", "one.wav")]["target"]
          == os.path.join(dest, CONFLICT_DIR, "3", "one.wav"))
    check("same name+size flagged dupe_suspect",
          by[os.path.join(root, "a", "one.wav")]["dupe_suspect"]
          and by[os.path.join(root, "b", "one.wav")]["dupe_suspect"])
    check("different size not flagged",
          not by[os.path.join(root, "c", "one.wav")]["dupe_suspect"])
    check("name already in dest -> conflict slot",
          by[os.path.join(root, "a", "in.wav")]["target"]
          == os.path.join(dest, CONFLICT_DIR, "2", "in.wav"))
    check("missing item gets no target", by[os.path.join(root, "gone.wav")]["target"] is None)

    print("apply_plan:")
    for it in items:
        if it["status"] == "to_move":
            write(it["path"], "data-" + os.path.basename(it["path"]) + it["path"])
    plan = {"dest": dest, "items": items}
    quiet = lambda *a: None  # noqa: E731

    apply_plan(plan, execute=False, out=quiet)
    check("dry run moves nothing",
          all(os.path.isfile(i["path"]) for i in items if i["status"] == "to_move"))

    res = apply_plan(plan, execute=True, out=quiet)
    movable = [i for i in items if i["status"] == "to_move"]
    check("all planned files moved", res["moved"] == len(movable) and not res["skipped"])
    check("sources gone", not any(os.path.exists(i["path"]) for i in movable))
    check("targets exist with content intact",
          all(os.path.isfile(i["target"]) and
              open(i["target"]).read().endswith(i["path"]) for i in movable))
    check("manifest written", res["manifest"] and os.path.isfile(res["manifest"]))
    with open(res["manifest"]) as f:
        lines = [json.loads(l) for l in f]
    check("manifest = header + one line per move", len(lines) == 1 + len(movable))

    print("move_file safety:")
    write(os.path.join(root, "s.wav"), "src")
    write(os.path.join(root, "t.wav"), "existing")
    try:
        move_file(os.path.join(root, "s.wav"), os.path.join(root, "t.wav"))
        check("refuses to overwrite", False)
    except FileExistsError:
        check("refuses to overwrite", True)
    check("source intact after refusal",
          open(os.path.join(root, "s.wav")).read() == "src"
          and open(os.path.join(root, "t.wav")).read() == "existing")
    move_file(os.path.join(root, "s.wav"), os.path.join(root, "s2.wav"),
              verify_hash=True, force_copy=True)
    check("copy path (force_copy+hash) moves and deletes source",
          open(os.path.join(root, "s2.wav")).read() == "src"
          and not os.path.exists(os.path.join(root, "s.wav"))
          and not os.path.exists(os.path.join(root, "s2.wav.part")))

    print("undo:")
    undo(res["manifest"], execute=False, out=quiet)
    check("undo dry run moves nothing",
          all(os.path.isfile(i["target"]) for i in movable))
    ures = undo(res["manifest"], execute=True, out=quiet)
    check("undo restores every file",
          ures["restored"] == len(movable) and not ures["skipped"]
          and all(os.path.isfile(i["path"]) for i in movable)
          and not any(os.path.exists(i["target"]) for i in movable))
    ures2 = undo(res["manifest"], execute=True, out=quiet)
    check("re-running undo skips cleanly, restores nothing twice",
          ures2["restored"] == 0 and len(ures2["skipped"]) == len(movable))


if __name__ == "__main__":
    main()
