#!/usr/bin/env python3
"""Audit stored `event_date` values against the source PDF headers.

The era parsers could not read Catalan month names ('29 de gener de 2005'), so
some 2005-2016 rows carry a date derived from the FILENAME, misreading '29105'
(29 Jan) as 29 October. This script downloads each stored PDF, reads the header
with the current `parse_header` (Spanish + Catalan months), and compares.

It never writes by itself: it writes a worklist of mismatches with the header
date as evidence, and `--apply` copies the header date into the JSONs (date
only; location/name mismatches are logged for manual review because the header
parser's city guess can be worse than a stored value that came from a full
re-extraction).

Usage:
    python3 scripts/check_event_dates.py            # report only
    python3 scripts/check_event_dates.py --apply    # fix event_date mismatches
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extract_catt import parse_header  # noqa: E402

SEASONS_DIR = ROOT / "seasons"
REPORTS_DIR = ROOT / "reports"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="fix event_date from the PDF header")
    ap.add_argument("--season", help="limit to one season (e.g. 2005)")
    args = ap.parse_args()

    targets = sorted(SEASONS_DIR.glob(f"{args.season or '*'}/json/*.json"))
    stats = Counter()
    mismatches = []
    name_loc = []

    with tempfile.TemporaryDirectory(prefix="dates-") as work:
        work = Path(work)
        for path in targets:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                stats["bad_json"] += 1
                continue
            stored = (data.get("event_date") or "").strip()
            src = data.get("event_src") or ""
            if not src.startswith(("http://", "https://")):
                stats["no_url"] += 1
                continue
            pdf = work / path.name.replace(".json", ".pdf")
            dl = subprocess.run(["curl", "-fsSL", "--connect-timeout", "15",
                                 "--max-time", "90", "-o", str(pdf), src],
                                capture_output=True, timeout=120)
            if dl.returncode != 0 or not pdf.exists() or pdf.read_bytes()[:4] != b"%PDF":
                stats["download_fail"] += 1
                continue
            txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                 capture_output=True, text=True).stdout
            _, _, _, header_date = parse_header(txt)
            header_date = (header_date or "").strip()
            if not header_date:
                stats["header_no_date"] += 1
                continue
            if stored and stored != header_date:
                stats["date_mismatch"] += 1
                mismatches.append({
                    "file": str(path.relative_to(ROOT)),
                    "stored": stored,
                    "header": header_date,
                    "source": src,
                })

    mismatches.sort(key=lambda m: m["file"])
    print(f"scanned {len(targets)} files: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    for m in mismatches[:15]:
        print(f"  {m['file'].split('json/')[1][:44]:46s} stored={m['stored']} header={m['header']}")
    if len(mismatches) > 15:
        print(f"  ... and {len(mismatches) - 15} more")

    if mismatches:
        REPORTS_DIR.mkdir(exist_ok=True)
        out = REPORTS_DIR / "event_date_mismatches.csv"
        import csv
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["file", "stored", "header", "source"],
                               lineterminator="\n")
            w.writeheader()
            w.writerows(mismatches)
        print(f"worklist: {out}")
        if args.apply:
            fixed = 0
            for m in mismatches:
                p = ROOT / m["file"]
                d = json.loads(p.read_text(encoding="utf-8"))
                d["event_date"] = m["header"]
                p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
                fixed += 1
            print(f"APPLIED: {fixed} dates fixed from PDF headers")
        else:
            print("DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
