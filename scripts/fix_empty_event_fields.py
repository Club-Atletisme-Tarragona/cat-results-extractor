#!/usr/bin/env python3
"""Fix empty event_date / event_src fields (issue #20).

Root cause: a handful of season source JSONs were extracted without an
event_date (PDF header date never parsed) or without an event_src (manual
extraction before provenance was enforced). The aggregator copies these
fields verbatim into athletes/, so the gaps propagated downstream.

Fix strategy (data-driven, no date guessing):

1. Source JSONs with empty event_date: fill from a small verified table
   built by reading the cached PDF headers (each date was confirmed both
   in the PDF header text and in the URL-encoded filename, e.g.
   resulterritpromovalls50414.pdf -> 5-04-14).
2. Source JSONs with empty event_src: fill from URLs reconstructed from
   sibling PDFs of the same series and verified with HTTP 200.
3. athletes/ files: for every result row with an empty event_date, look up
   the date by event_src in the (now complete) source-JSON map; for every
   row with an empty event_src, look up the src by (event_name, event_date)
   in the source-JSON map. Never invent a value: rows that cannot be
   matched are reported and left untouched.

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


def fix_sources(dry_run: bool) -> dict:
    """Fill event_date / event_src in the known source JSONs.

    Returns maps: norm_src -> date, (event_name, event_date) -> src.
    """
    src_to_date: dict[str, str] = {}
    key_to_src: dict[tuple[str, str], str] = {}

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
        src_to_date[norm_src(src)] = date

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
        if name and date:
            key_to_src[(name.upper(), date)] = src

    return src_to_date, key_to_src


def build_source_maps() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Scan all source JSONs (seasons/ + json/) and build lookup maps."""
    src_to_date: dict[str, str] = {}
    key_to_src: dict[tuple[str, str], str] = {}
    for pattern in ("seasons/*/**/*.json", "json/*.json", "json/**/*.json"):
        for path in sorted(ROOT.glob(pattern)):
            if "athletes" in path.parts or "imported" in path.parts:
                continue
            try:
                data = load_json(path)
            except (json.JSONDecodeError, OSError):
                continue
            src = (data.get("event_src") or "").strip()
            date = (data.get("event_date") or "").strip()
            name = (data.get("event_name") or "").strip()
            if src and date:
                src_to_date.setdefault(norm_src(src), date)
            if name and date and src:
                key_to_src.setdefault((name.upper(), date), src)
    return src_to_date, key_to_src


def fix_athletes(src_to_date, key_to_src, dry_run: bool) -> None:
    files = sorted((ROOT / "athletes").glob("*.json"))
    fixed_date = 0
    fixed_src = 0
    unresolved: list[tuple[str, int, str, str]] = []
    touched: set[str] = set()

    for path in files:
        data = load_json(path)
        changed = False
        for i, row in enumerate(data.get("results", [])):
            if not row.get("event_date") and row.get("event_src"):
                date = src_to_date.get(norm_src(row["event_src"]))
                if date:
                    row["event_date"] = date
                    fixed_date += 1
                    changed = True
                else:
                    unresolved.append((str(path), i, "event_date", row.get("event_src", "")))
            if not row.get("event_src") and row.get("event_date"):
                src = key_to_src.get(
                    ((row.get("event_name") or "").strip().upper(), row["event_date"])
                )
                if src:
                    row["event_src"] = src
                    fixed_src += 1
                    changed = True
                else:
                    unresolved.append(
                        (str(path), i, "event_src",
                         f"{row.get('event_name', '')} @ {row.get('event_date', '')}")
                    )
        if changed:
            touched.add(str(path))
            if not dry_run:
                save_json(path, data)

    print(f"\nathletes/: filled {fixed_date} event_date, {fixed_src} event_src "
          f"in {len(touched)} files (dry_run={dry_run})")
    if unresolved:
        print(f"UNRESOLVED rows left untouched: {len(unresolved)}")
        for fp, i, field, hint in unresolved[:20]:
            print(f"  {fp}[{i}] {field}: {hint}")


def audit() -> None:
    empty_date = empty_src = 0
    for path in sorted((ROOT / "athletes").glob("*.json")):
        data = load_json(path)
        for row in data.get("results", []):
            if not row.get("event_date"):
                empty_date += 1
            if not row.get("event_src"):
                empty_src += 1
    print(f"AUDIT athletes/: empty event_date={empty_date}, empty event_src={empty_src}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("== 1. Fix known source JSONs ==")
    fixed_src_to_date, fixed_key_to_src = fix_sources(args.dry_run)

    print("\n== 2. Scan all source JSONs for lookup maps ==")
    src_to_date, key_to_src = build_source_maps()
    # The just-fixed entries are authoritative even if a scan pass would skip
    src_to_date.update(fixed_src_to_date)
    key_to_src.update(fixed_key_to_src)
    print(f"  src->date map: {len(src_to_date)} entries; "
          f"(name,date)->src map: {len(key_to_src)} entries")

    print("\n== 3. Propagate into athletes/ ==")
    fix_athletes(src_to_date, key_to_src, args.dry_run)

    print("\n== 4. Final audit ==")
    audit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
