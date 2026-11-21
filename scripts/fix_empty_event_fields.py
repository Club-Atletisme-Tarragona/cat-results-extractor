#!/usr/bin/env python3
"""Fix empty event_date / event_src fields (issue #20).

Root cause: a handful of season source JSONs were extracted without an
event_date (PDF header date never parsed) or without an event_src (manual
extraction before provenance was enforced).

Fix strategy (data-driven, no date guessing):

1. Source JSONs with empty event_date: fill from a small verified table
   built by reading the cached PDF headers (each date was confirmed both
   in the PDF header text and in the URL-encoded filename, e.g.
   resulterritpromovalls50414.pdf -> 5-04-14).
2. Source JSONs with empty event_src: fill from URLs reconstructed from
   sibling PDFs of the same series and verified with HTTP 200.
3. Final audit: report any remaining season JSON with an empty event_date or
   event_src. Never invent a value.

The retired `athletes/` aggregates were the third consumer of these fields;
they no longer exist (issue #20 closed as discarded), so the fixer only
maintains `seasons/*/json/`.

Idempotent: running twice is a no-op the second time.

Usage:
    python scripts/fix_empty_event_fields.py            # apply
    python scripts/fix_empty_event_fields.py --dry-run  # report only
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Verified facts (from PDF headers + URL-encoded dates, HTTP-verified srcs)
# ---------------------------------------------------------------------------

# season JSON -> event_date (confirmed in cached PDF headers)
SOURCE_DATES = {
    "seasons/2014/json/resulterritpromovalls50414.json": "5/4/2014",
    "seasons/2013/json/resultrobadacambrils60413.json": "6/4/2013",
    "seasons/2016/json/resulcontrolterritamposta50316.json": "5/3/2016",
    "seasons/2015/json/resultrofeunastic70315.json": "7/3/2015",
    "seasons/2016/json/resulterritpromoamposta70516.json": "7/5/2016",
    "seasons/2016/json/resulcnatlocalcambrils80516.json": "8/5/2016",
    "seasons/2015/json/resulcontrolcep71114.json": "7/11/2014",
}

# season JSON -> event_src (reconstructed from sibling-series URL pattern,
# verified HTTP 200 at fix time)
SOURCE_SRCS = {
    "seasons/2010/json/resulcontrolfacvac26510.json":
        "http://old.fcatletisme.cat/Pairelliure/pairelliure2010/resulcontrolfacvac26510.pdf",
    "seasons/2011/json/resulcontrolcadet-juvenilterrassa14511.json":
        "https://old.fcatletisme.cat/Pairelliure/pairelliure2011/resulcontrolcadet-juvenilterrassa14511.pdf",
}


# season JSON -> (wrong event_date, correct event_date). Dates recovered from
# the cached PDF headers after the contract tests flagged impossible calendar
# dates (31/11/2010, 30/2/2013):
#   resulcllancaments31110.pdf  header: "31 de gener de 2010"  -> 31/1/2010
#   resulcatabsolutpc30213.pdf  header: "Sabadell, 3 febrero 2013" -> 3/2/2013
# (the old extractor misread the DDMMYY filename encoding)
SOURCE_DATE_OVERRIDES = {
    "seasons/2010/json/resulcllancaments31110.json": ("31/11/2010", "31/1/2010"),
    "seasons/2013/json/resulcatabsolutpc30213.json": ("30/2/2013", "3/2/2013"),
}


def norm_src(src: str) -> str:
    """Normalize a src URL for matching (scheme-insensitive)."""
    return src.replace("https://", "").replace("http://", "").strip().lower()


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def fix_sources(dry_run: bool) -> None:
    """Fill event_date / event_src in the known source JSONs."""

    for rel, (wrong, correct) in SOURCE_DATE_OVERRIDES.items():
        path = ROOT / rel
        data = load_json(path)
        current = (data.get("event_date") or "").strip()
        if current == correct:
            pass
        elif current == wrong:
            print(f"  override: {rel} {wrong!r} -> {correct!r}")
            if not dry_run:
                data["event_date"] = correct
                save_json(path, data)
        else:
            print(f"  WARN: {rel} has date {current!r}, expected {wrong!r} or {correct!r}")

    for rel, date in SOURCE_DATES.items():
        path = ROOT / rel
        data = load_json(path)
        src = data.get("event_src", "")
        if not src:
            print(f"  WARN: {rel} has no event_src; cannot index date by src")
            continue
        if data.get("event_date") and data["event_date"] != date:
            print(f"  WARN: {rel} already has date {data['event_date']!r} != {date!r}; keeping existing")
        elif not data.get("event_date"):
            print(f"  date: {rel} -> {date}")
            if not dry_run:
                data["event_date"] = date
                save_json(path, data)

    for rel, src in SOURCE_SRCS.items():
        path = ROOT / rel
        data = load_json(path)
        name = data.get("event_name", "")
        date = data.get("event_date", "")
        if data.get("event_src") and data["event_src"] != src:
            print(f"  WARN: {rel} already has src {data['event_src']!r} != {src!r}; keeping existing")
        elif not data.get("event_src"):
            print(f"  src:  {rel} -> {src}")
            if not dry_run:
                data["event_src"] = src
                save_json(path, data)


def audit() -> None:
    empty_date = empty_src = 0
    for pattern in ("seasons/*/json/*.json",):
        for path in sorted(ROOT.glob(pattern)):
            if "imported" in path.parts:
                continue
            data = load_json(path)
            if not (data.get("event_date") or "").strip():
                empty_date += 1
            if not (data.get("event_src") or "").strip():
                empty_src += 1
    print(f"AUDIT seasons/: empty event_date={empty_date}, empty event_src={empty_src}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("== 1. Fix known source JSONs ==")
    fix_sources(args.dry_run)

    print("\n== 2. Final audit ==")
    audit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
