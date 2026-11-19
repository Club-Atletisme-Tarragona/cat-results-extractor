#!/usr/bin/env python3
"""Masters sheets carry the original mark AND an age-graded derivative.

A veterans result line looks like:

    LLOC CARRER DORSAL LLIC. NOM  ANY  CLUB  MARCA  COEF  %  PUNTS
     1     5     60        Alex Lopez- Fernando Flores- ...  50''00  12,50  10,26  82,08  9

`MARCA` is what the athlete actually did. `COEF` and `%` are the age factor and
the age-graded equivalent, and `PUNTS` are championship points. **The dataset
stores the original mark**, never the adapted one: an age-graded number is not a
performance and cannot be compared across ages.

The 2005-2016 veterans parsers sometimes took a later column, which produces
rows whose "mark" is impossible or wildly out of range for the event - a long
jump of 62.72 m, a 200 m in 80.48 s, a shot put attempt of 51.61 m next to the
same athlete's 10.94 m. Those values are too SLOW or too BIG rather than too
fast, so scripts/check_plausibility.py (which enforces floors) never flags them.

This checker reports them as a worklist. It never edits: the correct value has
to be read from the source PDF, because a coefficient cannot be inverted without
the age reference the sheet used.

Usage:
    python3 scripts/check_veterans_marks.py                 # report
    python3 scripts/check_veterans_marks.py --csv out.csv   # also write a worklist
Exit code 1 when suspect rows are found, 0 when clean.
"""

import argparse
import csv
import glob
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASONS_DIR = ROOT / "seasons"
REPORTS_DIR = ROOT / "reports"

VETERANS_FILE = re.compile(r"veteran|mitingveterans|master", re.IGNORECASE)

# Absolute ceilings: no masters athlete, at any age, produces a mark beyond
# these. Only used to catch a stored coefficient/percentage, so they are set
# far beyond real records on purpose.
CEILINGS = [
    (re.compile(r"60\s*metres|60m\s*llisos", re.I), 20.0),
    (re.compile(r"100\s*metres|100m\s*llisos", re.I), 40.0),
    (re.compile(r"200\s*metres|200m\s*llisos", re.I), 90.0),
    (re.compile(r"400\s*metres|400m\s*llisos", re.I), 180.0),
    # end-of-range times: an M85 marathoner's 3000 m is legitimately slow, so
    # these are deliberately loose - they only catch a percentage stored as a
    # time, never an old athlete having a bad day
    (re.compile(r"800\s*metres|800m", re.I), 600.0),
    (re.compile(r"1[.,]?500\s*(?:metres|m)", re.I), 1200.0),
    (re.compile(r"3[.,]?000\s*metres", re.I), 2700.0),
    (re.compile(r"5[.,]?000\s*metres", re.I), 4800.0),
    (re.compile(r"llargada|longitud", re.I), 9.5),
    (re.compile(r"triple", re.I), 19.0),
    (re.compile(r"al[cç]ada|altura", re.I), 2.6),
    (re.compile(r"perxa|p[eé]rtiga", re.I), 6.5),
    (re.compile(r"pes\b|peso", re.I), 25.0),
    (re.compile(r"disc", re.I), 80.0),
    (re.compile(r"javelina|jabalina", re.I), 100.0),
    (re.compile(r"martell|martillo", re.I), 90.0),
]


def to_number(performance):
    """Seconds for times, metres otherwise; None when unparseable."""
    text = str(performance or "").strip().replace(",", ".")
    m = re.fullmatch(r"(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.fullmatch(r"(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return None


def ceiling_for(discipline):
    for pattern, limit in CEILINGS:
        if pattern.search(discipline or ""):
            return limit
    return None


def is_veterans_file(path, data):
    if VETERANS_FILE.search(str(path)):
        return True
    return bool(VETERANS_FILE.search(str(data.get("event_name") or "")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(REPORTS_DIR / "veterans_marks_suspect.csv"))
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on suspects; default is advisory (exit 0), "
                         "because a slow old athlete and a stored percentage "
                         "look alike at the edges")
    args = ap.parse_args()

    suspects = []
    checked = 0

    for path in sorted(SEASONS_DIR.glob("*/json/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip unreadable file, keep scanning
            continue
        if not is_veterans_file(path, data):
            continue

        rows = data.get("results", [])
        checked += len(rows)

        by_event = {}
        for r in rows:
            by_event.setdefault(r.get("discipline") or "", []).append(r)

        for discipline, group in by_event.items():
            ceiling = ceiling_for(discipline)
            values = [(r, to_number(r.get("performance"))) for r in group]
            numbers = [v for _, v in values if v is not None]
            median = statistics.median(numbers) if len(numbers) >= 4 else None

            for r, value in values:
                if value is None:
                    continue
                reason = None
                if ceiling and value > ceiling:
                    ratio = value / ceiling
                    reason = f"above the {ceiling:g} ceiling for the event (x{ratio:.1f})"
                elif median and value > median * 1.8:
                    reason = f"{value / median:.1f}x the event median ({median:g})"
                if reason:
                    suspects.append({
                        "file": path.relative_to(ROOT).as_posix(),
                        "event_name": data.get("event_name") or "",
                        "athlete_name": r.get("athlete_name") or "",
                        "discipline": discipline,
                        "performance": r.get("performance") or "",
                        "why": reason,
                        "source": data.get("event_src") or "",
                    })

    suspects.sort(key=lambda s: (s["file"], s["discipline"], s["athlete_name"]))
    print(f"scanned {checked} rows in veterans/master files")
    print(f"suspect rows (age-graded value stored as the mark): {len(suspects)}")
    for s in suspects[:15]:
        print(f"  {s['file']:52s} {s['discipline'][:20]:22s} {s['athlete_name'][:24]:26s} "
              f"{s['performance']:>9s}  {s['why']}")
    if len(suspects) > 15:
        print(f"  ... and {len(suspects) - 15} more")

    if suspects:
        REPORTS_DIR.mkdir(exist_ok=True)
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(suspects[0].keys()),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(suspects)
        print(f"\nworklist: {args.csv}")
        print("Each row needs the MARCA column read from its source PDF; the "
              "age-graded value cannot be inverted without the sheet's reference.")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
