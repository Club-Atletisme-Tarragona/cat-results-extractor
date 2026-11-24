#!/usr/bin/env python3
"""Move `is_short_track` from the file header to every result row (issue: the
consumer's contract validator rejects the key at header level).

The web app's `ImportPayloadContractValidator` treats the presence of
`is_short_track` in the header as a **hard error**, and the owner decided the
flag belongs to the mark, not the file: short track is a property of the mark.
A header-level key blocked the entire night-time auto-import (incident
2026-11-24), and each weekly run burned one quarantine attempt per file.

What this does, per file:
  * reads the header flag (missing header key = False),
  * writes `is_short_track` on **every** row of `results[]`,
  * removes the key from the header.

Row value: the row's own section wins when it says it (`PC`/`Pista Coberta` ->
true, `AL`/`Aire Lliure` -> false), because a mixed meet prints both; otherwise
the file flag. Same rule as `extract_catt.row_short_track()`.

Idempotent: a file already migrated is left byte-identical.

Usage:
    python3 scripts/migrate_short_track_to_rows.py --dry-run   # report only
    python3 scripts/migrate_short_track_to_rows.py             # apply
    python3 scripts/migrate_short_track_to_rows.py --season 2026
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extract_catt import _ROW_INDOOR_RE as _SECTION_INDOOR  # noqa: E402
from extract_catt import _ROW_OUTDOOR_RE as _SECTION_OUTDOOR  # noqa: E402

SEASONS = ROOT / "seasons"


def season_files(season=None):
    if season:
        dirs = [SEASONS / str(season) / "json"]
    else:
        dirs = sorted(p for p in SEASONS.glob("*/json") if p.is_dir())
    for directory in dirs:
        for path in sorted(directory.glob("*.json")):
            if "imported" in path.parts:
                continue
            yield path


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def migrate(path, dry_run):
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    file_flag = data.get("is_short_track")
    header_present = "is_short_track" in data

    rows = data.get("results") or []
    # A partially migrated file has rows the flag already and rows without it;
    # derive the file fallback from what is already stored instead of from the
    # header we are about to delete (that is what made the first version
    # re-write 196 files on every run).
    stored = [r["is_short_track"] for r in rows
              if isinstance(r.get("is_short_track"), bool)]
    if file_flag is None and stored:
        file_flag = any(stored)

    row_values = Counter()
    changed_rows = 0
    for row in rows:
        raw = row.get("raw_discipline_name") or row.get("discipline") or ""
        if _SECTION_INDOOR.search(raw):
            want = True
        elif _SECTION_OUTDOOR.search(raw):
            want = False
        elif isinstance(row.get("is_short_track"), bool):
            want = row["is_short_track"]
        else:
            want = bool(file_flag)
        row_values[want] += 1
        if row.get("is_short_track") is not want:
            row["is_short_track"] = want
            changed_rows += 1

    if header_present:
        del data["is_short_track"]

    touches = header_present or changed_rows
    if not touches:
        return ("clean", 0, False, row_values)
    if dry_run:
        return ("migrated", changed_rows, header_present, row_values)

    text = dump(data)
    if text.rstrip("\n") != dump(json.loads(text)).rstrip("\n"):
        return ("refused-noncanonical", changed_rows, header_present, row_values)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return ("migrated", changed_rows, header_present, row_values)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--season", help="limit to one season, e.g. 2026")
    args = ap.parse_args()

    stats = Counter()
    row_mix = Counter()
    sample = []
    for path in season_files(args.season):
        status, changed_rows, header_present, values = migrate(path, args.dry_run)
        stats[status] += 1
        row_mix[bool(values.get(True))] += 1
        if status == "migrated" and len(sample) < 5:
            sample.append(f"  {path.relative_to(ROOT)}  rows changed={changed_rows} "
                          f"header_removed={header_present} "
                          f"true={values.get(True, 0)} false={values.get(False, 0)}")
        if status == "refused-noncanonical":
            print(f"  REFUSED (not canonical JSON layout): {path.relative_to(ROOT)}",
                  file=sys.stderr)

    print(f"files: {sum(stats.values())}")
    for key in ("migrated", "clean", "refused-noncanonical"):
        if stats.get(key):
            print(f"  {key}: {stats[key]}")
    print(f"  files with at least one indoor row: {row_mix.get(True, 0)}")
    if sample:
        print("sample:")
        print("\n".join(sample))
    if args.dry_run:
        print("DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
