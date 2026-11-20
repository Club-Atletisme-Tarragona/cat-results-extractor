#!/usr/bin/env python3
"""Backfill the export-contract fields into the stored season JSONs.

Contract (odd/tasks/timing-short-track.md): every stored JSON gains
"is_short_track": bool at file level and "timing": "electronic"|"manual"
per row, absent -> electronic. This script does NOT re-extract: it derives
both fields from what is already stored (the event name, the URL, the row
marks), so era-parser files get the same contract without touching their
rows.

Idempotent; writes via temp file + os.replace; dry-run by default.

Usage:
    python3 scripts/backfill_timing_contract.py            # dry run
    python3 scripts/backfill_timing_contract.py --apply
    python3 scripts/backfill_timing_contract.py --season 2005 --apply
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extract_catt import detect_short_track, timing_from_mark  # noqa: E402

SEASONS_DIR = ROOT / "seasons"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--season", help="limit to one season (e.g. 2005)")
    args = ap.parse_args()

    pattern = f"{args.season or '*'}/json/*.json"
    files = sorted(SEASONS_DIR.glob(pattern))
    stats = Counter()
    examples = {"manual": []}

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stats["bad_json"] += 1
            continue
        changed = False

        st = detect_short_track(data.get("event_name") or "",
                                data.get("event_src") or "")
        if data.get("is_short_track") != st:
            data["is_short_track"] = st
            changed = True
        stats["short_track" if st else "aire_lliure"] += 1

        for r in data.get("results", []):
            t = timing_from_mark(r.get("performance"))
            if r.get("timing") != t:
                r["timing"] = t
                changed = True
            stats[f"timing_{t}"] += 1
            if t == "manual" and len(examples["manual"]) < 10:
                examples["manual"].append(
                    (path.name[:34], r.get("discipline", "")[:18], r.get("performance")))

        if changed and args.apply:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
            os.replace(tmp, path)
        stats["files_touched"] += 1 if changed else 0

    print(f"files: {len(files)} | touched: {stats['files_touched']}")
    print(f"short_track={stats['short_track']} aire_lliure={stats['aire_lliure']}")
    print(f"timing electronic={stats['timing_electronic']} manual={stats['timing_manual']}")
    if examples["manual"]:
        print("manual samples:")
        for e in examples["manual"]:
            print(f"  {e[0]:36s} {e[1]:20s} {e[2]}")
    print("APPLIED" if args.apply else "DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
