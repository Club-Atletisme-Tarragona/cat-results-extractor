#!/usr/bin/env python3
"""Repair mechanical performance-format defects in legacy season JSONs.

Scope (agreed 2026-11-19): the fixes that are pure notation, verified by
inspection, and reversible. Anything ambiguous is left untouched and listed.

Rules, applied only when the row's `discipline` exists in DISCIPLINES.md and
the target `format` column is known:

  1. NULS / NUL / NULL mark      -> row dropped (Catalan "no mark"; same class
                                    as X/r, carries no result)
  2. target mm:ss.cc, value "SS.cc" sub-minute, and sub-minute is physically
     possible for that distance  -> prefix "0:" (400 metres llisos 59.45 ->
                                    0:59.45). Distances where a sub-minute
                                    time is impossible are NOT touched.
  3. target mm:ss.cc, value "MM:SS" (seconds dropped by an old parser)
                                 -> append ".00"
  4. target ss.cc, value "MM:SS.cc" -> convert to total seconds (1:07.15 ->
                                    67.15). DISCIPLINES.md declares ss.cc for
                                    sprints and short relays, so a minute-form
                                    value is a notation defect, not a value.
  5. target ss.cc or m.cm, value with one decimal ("7.5") -> pad to two
                                    decimals ("7.50").
  6. target mm:ss.cc / HH:mm:ss.cc, value "MM:SS.d" (one decimal)
                                 -> pad ("3:32.6" -> "3:32.60").
  7. target HH:mm:ss(.cc) (10.000m marxa and the long road events)
                                 -> supply the hour ("53:47.50" ->
                                    "0:53:47.50", "53:58" -> "0:53:58.00").

Everything else is reported as UNHANDLED for manual/era-parser work.

`raw_discipline_name`, athlete fields and totals are never touched; only
`performance` changes (and whole rows for NULS). Files are written through a
sibling temp file + os.replace so an interrupted run cannot truncate a JSON.

Usage:
    python3 scripts/repair_legacy_performance_formats.py --dry-run
    python3 scripts/repair_legacy_performance_formats.py --apply
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["seasons/*/json/*.json"]
MARKERS = {"DNS", "DNF", "DQ", "RET", "N.P.", "NP", "RET.", "NM", "RT"}
NO_MARK = {"NULS", "NUL", "NULL"}
# Distances whose sub-minute time is physically possible (llisos / tanques).
SUB_MINUTE_OK = {300: 30.0, 400: 42.0, 500: 55.0}


def load_formats():
    formats = {}
    with open(os.path.join(REPO, "DISCIPLINES.md"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(?:ASC|DESC)\s*\|\s*([^|]+?)\s*\|", line)
            if m and m.group(1) != "name":
                formats[m.group(1)] = m.group(2).strip()
    return formats


def distance_of(discipline):
    """Metres for a track/marxa discipline name, else None."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})?|\d{3,5})\s*(?:metres|m\b)", discipline)
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


def repair(value, fmt, discipline):
    """Return (new_value, rule_id) or (None, None) when nothing applies."""
    p = value.strip()
    if not p or p in MARKERS:
        return None, None

    if p.upper() in NO_MARK:
        return "", "1-nomark"

    # Rule 2: sub-minute ss.cc into a mm:ss.cc discipline
    if fmt == "mm:ss.cc" and re.fullmatch(r"\d{1,2}\.\d{2}", p):
        dist = distance_of(discipline)
        floor = SUB_MINUTE_OK.get(dist) if dist else None
        if floor is not None and floor <= float(p) < 60.0:
            return f"0:{p}", "2-subminute"
        return None, None  # implausible for the distance: leave for review

    # Rule 3: MM:SS with the seconds dropped
    if fmt == "mm:ss.cc" and re.fullmatch(r"\d{1,3}:\d{2}", p):
        return f"{p}.00", "3-mmss"

    # Rule 4: minute-form value under a ss.cc discipline
    if fmt == "ss.cc" and re.fullmatch(r"\d{1,3}:\d{2}\.\d{2}", p):
        mm, ss = p.split(":")
        return f"{int(mm) * 60 + float(ss):.2f}", "4-minute-form"

    # Rule 5: single decimal
    if fmt in ("ss.cc", "m.cm") and re.fullmatch(r"\d{1,3}\.\d", p):
        return f"{p}0", "5-one-decimal"

    # Rule 6: minute-form with a single decimal ("3:32.6" -> "3:32.60").
    # Old parsers dropped the last centisecond digit; the value is intact.
    if fmt in ("mm:ss.cc", "HH:mm:ss.cc") and re.fullmatch(r"\d{1,3}:\d{2}\.\d", p):
        return f"{p}0", "6-mmss-one-decimal"

    # Rule 7: hour component for HH:mm:ss(.cc) disciplines. A 10.000m walk can
    # exceed 59 minutes (masters/women's masters), so the DB row is right and
    # the value must carry the hour: "53:47.50" -> "0:53:47.50".
    if fmt in ("HH:mm:ss.cc", "HH:mm:ss"):
        if re.fullmatch(r"\d{1,3}:\d{2}\.\d{2}", p):          # MM:SS.cc
            return f"0:{p}", "7-hour-component"
        if re.fullmatch(r"\d{1,3}:\d{2}", p):                   # MM:SS
            return f"0:{p}.00" if fmt == "HH:mm:ss.cc" else f"0:{p}", "7-hour-component"
        if fmt == "HH:mm:ss.cc":
            m = re.fullmatch(r"(\d{1,3}:\d{2}:\d{2})\.(\d)", p)
            if m:                                                # H:MM:SS.d
                return f"{m.group(1)}.{m.group(2)}0", "7-hour-component"
            if re.fullmatch(r"\d{1,3}:\d{2}:\d{2}", p):        # H:MM:SS
                return f"{p}.00", "7-hour-component"

    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    formats = load_formats()
    rules = Counter()
    unhandled = []
    touched = []
    dropped_rows = 0
    total_rows = 0

    for pattern in TARGETS:
        for path in sorted(glob.glob(os.path.join(REPO, pattern))):
            if os.sep + "imported" + os.sep in path:
                continue
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            results = data.get("results") or []
            total_rows += len(results)
            changed = False
            kept = []
            for r in results:
                fmt = formats.get(str(r.get("discipline", "")).strip())
                if fmt is None:
                    kept.append(r)
                    continue
                old = str(r.get("performance", ""))
                new, rule = repair(old, fmt, str(r.get("discipline", "")))
                if rule == "1-nomark":
                    dropped_rows += 1
                    rules[rule] += 1
                    changed = True
                    continue
                if new is not None and new != old:
                    r["performance"] = new
                    rules[rule] += 1
                    changed = True
                    if len(touched) < 400:
                        touched.append((os.path.relpath(path, REPO), r.get("athlete_name"),
                                        r.get("discipline"), old, new, rule))
                elif new is None and old and old not in MARKERS:
                    if not re.match(
                        r"^\d{1,2}\.\d{2}$|^\d{1,3}:\d{2}\.\d{2}$|^\d{1,2}:\d{2}:\d{2}\.\d{2}$|^\d{1,2}:\d{2}:\d{2}(?:\.\d{1,2})?$|^\d{3,5}$",
                        old,
                    ):
                        unhandled.append((os.path.relpath(path, REPO), r.get("athlete_name"),
                                          r.get("discipline"), old))
                kept.append(r)
            if changed:
                data["results"] = kept
                data["total_results"] = len(kept)
                if args.apply:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, indent=2, ensure_ascii=False)
                        fh.write("\n")  # repo convention: every JSON ends with a newline
                    os.replace(tmp, path)

    print(f"scanned {total_rows} results")
    print("\nfixes by rule:")
    for rule, count in sorted(rules.items()):
        print(f"  {rule:18s} {count}")
    print(f"  {'TOTAL FIXED':18s} {sum(rules.values())}")
    if dropped_rows:
        print(f"  (of which {dropped_rows} rows dropped as no-mark)")
    print(f"\nunhandled values left for manual/era-parser work: {len(unhandled)}")
    for u in unhandled[:25]:
        print("   ", u[0], "|", str(u[1])[:24], "|", u[2][:32], "|", u[3])
    if touched:
        print("\nsample of changes:")
        for t in touched[:15]:
            print(f"   {t[0].split('/')[-1][:42]:44s} {t[2][:28]:30s} {t[3]:>9s} -> {t[4]:<9s} [{t[5]}]")
    print("\nDRY RUN - nothing written" if not args.apply else "\nAPPLIED - files written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
