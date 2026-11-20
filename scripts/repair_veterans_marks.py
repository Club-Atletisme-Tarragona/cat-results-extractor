#!/usr/bin/env python3
"""Repair masters rows where COEF or % was stored instead of MARCA.

A veterans line ends with four fixed columns:

    ... intents...  MARCA  COEF  %  PUNTS
    X 24,90 29,13 29,28 28,97 X  29,28  69,23  42,29  8

The 2005-2016 parsers sometimes took a later column, storing 69.23 (COEF) or
42.29 (%) as the athlete's mark. This script repairs a row ONLY when the
precondition is verifiable in the source PDF:

  * the athlete's line is found in the PDF text;
  * the stored performance equals the COEF (3rd from the end) or the %
    (2nd from the end) column of that line;
  * the corrected value is the 4th column from the end (MARCA, the best mark).

Anything else - line not found, layout with fewer trailing columns, stored value
not matching either derived column - is left untouched and reported, because a
slow old athlete and a stored percentage look alike and guessing is forbidden
(AGENTS.md). Rows that collapse to the same athlete+discipline+mark after the
repair were the SAME attempt recorded twice (once as COEF, once as %), so the
duplicate is removed and logged, never silently.

Usage:
    python3 scripts/repair_veterans_marks.py            # dry run
    python3 scripts/repair_veterans_marks.py --apply
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# Same ceilings as check_veterans_marks.py: a corrected value beyond them is
# not a mark, which means the PDF layout is not MARCA COEF % PUNTS and the
# column arithmetic is wrong for that file. Leave those rows for manual work.
_CEILINGS = [
    (re.compile(r"60\s*m|100\s*m", re.I), 40.0),
    (re.compile(r"200\s*m", re.I), 90.0),
    (re.compile(r"400\s*m", re.I), 180.0),
    (re.compile(r"llargada|longitud|triple", re.I), 9.5),
    (re.compile(r"al[cç]ada|altura", re.I), 2.6),
    (re.compile(r"perxa|p[eé]rtiga", re.I), 6.5),
    (re.compile(r"pes\b|peso", re.I), 25.0),
    (re.compile(r"disc", re.I), 80.0),
    (re.compile(r"javelina|jabalina", re.I), 100.0),
    (re.compile(r"martell|martillo", re.I), 90.0),
]


def plausible(discipline, value):
    try:
        v = float(value)
    except ValueError:
        return False
    for pattern, limit in _CEILINGS:
        if pattern.search(discipline or ""):
            return v <= limit
    return True


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "reports"
SUSPECTS = REPORTS_DIR / "veterans_marks_suspect.csv"

_NUM = re.compile(r"^\d{1,3}[.,]\d{1,3}$|^\d{1,3}$")


def numeric_cols(line):
    return [c.replace(",", ".") for c in line.split() if _NUM.match(c)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--csv", default=str(SUSPECTS))
    args = ap.parse_args()

    suspects = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    by_src = defaultdict(list)
    for r in suspects:
        by_src[r["source"]].append(r)

    stats = {"repaired": 0, "dedup": 0, "left": 0}
    log = []

    with tempfile.TemporaryDirectory(prefix="vetmarks-") as work:
        work = Path(work)
        for src, rows in sorted(by_src.items()):
            pdf = work / re.sub(r"[^A-Za-z0-9.-]", "_", src)[-60:]
            dl = subprocess.run(["curl", "-fsSL", "--connect-timeout", "15",
                                 "--max-time", "90", "-o", str(pdf), src],
                                capture_output=True, timeout=120)
            if dl.returncode != 0 or not pdf.exists() or pdf.read_bytes()[:4] != b"%PDF":
                for r in rows:
                    stats["left"] += 1
                    log.append(f"left (download) | {r['file'].split('json/')[1]} | {r['athlete_name']} {r['discipline']} {r['performance']}")
                continue
            txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                 capture_output=True, text=True).stdout
            lines = txt.splitlines()

            pending = {}  # (file, key) -> corrected mark, for dedup decisions
            for r in rows:
                path = ROOT / r["file"]
                fam = r["athlete_name"].split()[0].upper()[:10]
                cand = [ln for ln in lines
                        if "tarragona" in ln.lower() and fam in ln.upper()]
                if len(cand) != 1:
                    stats["left"] += 1
                    log.append(f"left (line x{len(cand)}) | {r['file'].split('json/')[1]} | {r['athlete_name']} {r['discipline']} {r['performance']}")
                    continue
                cols = numeric_cols(cand[0])
                if len(cols) < 4:
                    stats["left"] += 1
                    log.append(f"left (cols={len(cols)}) | {r['file'].split('json/')[1]} | {r['athlete_name']}")
                    continue
                coef, pct, marca = cols[-3], cols[-2], cols[-4]
                stored = r["performance"].strip()
                if not plausible(r["discipline"], marca):
                    stats["left"] += 1
                    log.append(f"left (marca implausible) | {r['file'].split('json/')[1]} | {r['athlete_name']} {r['discipline']} marca={marca}")
                    continue
                if stored not in (coef, pct):
                    stats["left"] += 1
                    log.append(f"left (no match) | {r['file'].split('json/')[1]} | {r['athlete_name']} {r['discipline']} stored={stored} coef={coef} pct={pct}")
                    continue
                pending[(r["file"], r["athlete_name"], r["discipline"], stored)] = marca

            # apply per file. A suspect row is a GHOST attempt: the old parser
            # read the trailing COEF/% columns as if they were attempts, and a
            # value only becomes suspect when it is impossible for the event,
            # so it can never be a real attempt. When the athlete's real mark
            # (the MARCA column) is already stored among their attempts, the
            # ghost row is DELETED; only when the mark is missing entirely is
            # the row rewritten with it - never both, which would duplicate an
            # attempt.
            edits = defaultdict(list)
            for (rfile, name, disc, stored), marca in pending.items():
                edits[rfile].append((name, disc, stored, marca))

            for rfile, jobs in edits.items():
                path = ROOT / rfile
                data = json.loads(path.read_text(encoding="utf-8"))
                for name, disc, stored, marca in jobs:
                    already = any(r.get("athlete_name") == name
                                  and r.get("discipline") == disc
                                  and r.get("performance") == marca
                                  for r in data.get("results", []))
                    out, done = [], 0
                    for row in data.get("results", []):
                        if (row.get("athlete_name") == name
                                and row.get("discipline") == disc
                                and row.get("performance") == stored and not done):
                            done = 1
                            if already:
                                stats["dedup"] += 1
                                log.append(f"deleted ghost   | {rfile.split('json/')[1]} | {name} {disc} {stored} (marca {marca} ya almacenada)")
                                continue
                            row["performance"] = marca
                            stats["repaired"] += 1
                            log.append(f"repaired       | {rfile.split('json/')[1]} | {name} {disc} {stored} -> {marca}")
                        out.append(row)
                    data["results"] = out
                    data["total_results"] = len(out)
                if args.apply:
                    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")

    log_path = REPORTS_DIR / "veterans_marks_repair.log"
    log_path.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"repaired={stats['repaired']} dedup={stats['dedup']} left={stats['left']}")
    print(f"log: {log_path}")
    print("APPLIED" if args.apply else "DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
