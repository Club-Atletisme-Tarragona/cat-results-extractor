#!/usr/bin/env python3
"""Re-extract stored season JSONs with the current extractor and reconcile.

Seasons extracted with older extractor versions undercount exactly the event
types the extractor learned later (all jump/throw attempts, relay legs, masters
marks, combined sub-events). This script re-downloads each stored PDF, extracts
it with HEAD `extract_catt.py`, and rewrites the JSON only when HEAD finds at
least as many rows as stored — a season is regenerated, never regressed.

Every decision is logged: file, stored rows, HEAD rows, action (kept/updated/
HEAD-sparse/download-failed/extract-failed). Rows are compared, not merged: if
HEAD finds fewer rows than stored, the file is LEFT ALONE for a human to look
at, because that means the old parser covered a format HEAD does not (as of
2026-11 that is the case for the 2016 tabular format).

After all seasons are re-extracted, run the standard pipeline:
    python3 scripts/update_disciplines.py --season <s>
    python3 scripts/add_internal_id.py --season <s>

Usage:
    python3 scripts/regen_season.py --season 2017            # dry run: log only
    python3 scripts/regen_season.py --season 2017 --apply    # rewrite JSONs
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEASONS_DIR = ROOT / "seasons"
EXTRACT_CATT = ROOT / "extract_catt.py"


def rows_of(path):
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("results", []))
    except Exception:
        return -1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", required=True, help="season folder, e.g. 2017")
    ap.add_argument("--apply", action="store_true", help="rewrite the JSONs")
    args = ap.parse_args()

    season_dir = SEASONS_DIR / args.season / "json"
    targets = sorted(season_dir.glob("*.json"))
    if not targets:
        print(f"no JSONs in {season_dir}")
        return 1

    with tempfile.TemporaryDirectory(prefix=f"regen-{args.season}-") as work:
        work = Path(work)
        stats = {"updated": 0, "kept": 0, "head_sparse": 0, "download_fail": 0,
                 "extract_fail": 0}
        lines = []
        for path in targets:
            data = json.loads(path.read_text(encoding="utf-8"))
            stored = len(data.get("results", []))
            src = data.get("event_src") or ""
            name = path.name

            pdf = work / name.replace(".json", ".pdf")
            dl = subprocess.run(
                ["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "90",
                 "-o", str(pdf), src],
                capture_output=True, timeout=120)
            if dl.returncode != 0 or not pdf.exists() or pdf.stat().st_size == 0 \
                    or pdf.read_bytes()[:4] != b"%PDF":
                stats["download_fail"] += 1
                lines.append(f"download_fail | {stored:>4} | {name}")
                continue

            out_json = work / name
            ex = subprocess.run(
                [sys.executable, str(EXTRACT_CATT), str(pdf), src, "--quiet"],
                capture_output=True, timeout=300, cwd=str(work))
            if ex.returncode != 0 or not out_json.exists():
                stats["extract_fail"] += 1
                lines.append(f"extract_fail   | {stored:>4} | {name}")
                continue

            head = rows_of(out_json)
            if head < 0:
                stats["extract_fail"] += 1
                lines.append(f"extract_fail   | {stored:>4} | {name} (bad JSON)")
                continue
            if head < stored:
                # HEAD does not cover a format the old parser did: never regress.
                stats["head_sparse"] += 1
                lines.append(f"HEAD-sparse    | {stored:>4} -> {head:>4} | {name}")
                continue

            new_data = json.loads(out_json.read_text(encoding="utf-8"))
            # keep provenance consistent with the stored file; a regenerated
            # header must never be emptier than the stored one (the header
            # parser misses text dates such as "1 de febrer de 2020").
            for k in ("event_src", "event_date", "event_name", "event_location"):
                if not (new_data.get(k) or "").strip():
                    new_data[k] = data.get(k) or ""
            if args.apply:
                path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
            stats["updated"] += 1
            lines.append(f"updated        | {stored:>4} -> {head:>4} | {name}")

    report = ROOT / "reports" / f"regen_{args.season}.log"
    report.parent.mkdir(exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"season {args.season}: {len(targets)} files | "
          + ", ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"log: {report}")
    print("APPLIED" if args.apply else "DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
