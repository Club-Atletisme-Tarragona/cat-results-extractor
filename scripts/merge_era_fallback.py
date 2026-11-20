#!/usr/bin/env python3
"""Merge era-parser rows with extract_catt fallback rows for one JSON.

Some era sheets (2013-2016 promocio/territorial) mix two layouts: the season's
era-parser captured the field events (Llargada multi-attempt tables), while the
new `parse_promocio_series` fallback recovers the track series (60 m with
'11"6' hand times) that the era parser never read. Neither tool alone produces
the complete sheet.

This script runs the fallback against the source PDF and appends only the rows
the stored JSON does not already have, keyed by (name, mark) so an attempt is
never duplicated. regen_season.py's `head >= stored` guard cannot express this
(the fallback finds FEWER rows than stored, because it only reads one of the
two layouts), so this merge is the safe path for mixed-layout sheets.

Usage:
    python3 scripts/merge_era_fallback.py --season 2016           # dry run
    python3 scripts/merge_era_fallback.py --season 2016 --apply
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extract_catt import parse_promocio_series  # noqa: E402

SEASONS_DIR = ROOT / "seasons"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    targets = sorted((SEASONS_DIR / args.season / "json").glob("*.json"))
    stats = Counter()
    with tempfile.TemporaryDirectory(prefix="era-merge-") as work:
        work = Path(work)
        for path in targets:
            data = json.loads(path.read_text(encoding="utf-8"))
            stored = data.get("results", [])
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
            extra = parse_promocio_series(txt)
            if not extra:
                stats["no_fallback_rows"] += 1
                continue
            known = {(r.get("athlete_name", "").upper().replace(",", "").strip(),
                      r.get("performance", "")) for r in stored}
            added = []
            for r in extra:
                name = r["atleta_nom"].strip()
                # Rows without a name (relay teams the sheet lists by club
                # only) cannot be identified: skip them, do not store
                # placeholder athletes.
                if not name:
                    stats["unnamed_skipped"] += 1
                    continue
                key = (name.upper().replace(",", "").strip(), r["marca"])
                if key not in known:
                    added.append(r)
                    known.add(key)
            if not added:
                stats["nothing_new"] += 1
                continue
            if args.apply:
                for r in added:
                    stored.append({
                        "athlete_name": r["atleta_nom"],
                        "athlete_dob": "",
                        "athlete_id": r["atleta_licencia"],
                        "performance": r["marca"],
                        "discipline": r["prova"],
                        "wind": r.get("vent"),
                        "position": None,
                        "raw_discipline_name": r["prova"],
                    })
                data["results"] = stored
                data["total_results"] = len(stored)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
                os.replace(tmp, path)
            stats["merged"] += 1
            stats["rows_added"] += len(added)
            print(f"+{len(added):>3} | {len(stored):>3} -> {len(stored)+len(added):>3} | {path.name}")

    print(f"\n{args.season}: {dict(stats)}")
    print("APPLIED" if args.apply else "DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
