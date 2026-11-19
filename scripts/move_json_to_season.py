#!/usr/bin/env python3
"""Move an extracted JSON into seasons/<season>/json/, printing its path.

The season is the calendar year of the JSON's own `event_date` (see
season_paths.py), so a PDF from December and one from January land in the
right folders and a new year needs no code or workflow change.

Used by `make extract`, `make extract/remote` and the extract-remote
GitHub workflow, which previously hard-coded a top-level `json/`:

    DEST=$(python3 scripts/move_json_to_season.py "$JSON")

Options:
    --dry-run   print the destination without moving anything
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import season_paths  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path", help="extracted JSON to file under seasons/<season>/json/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(args.json_path)
    if not os.path.isfile(src):
        sys.exit(f"not a file: {src}")

    import json
    try:
        with open(src, encoding="utf-8") as fh:
            event_date = json.load(fh).get("event_date", "")
    except (json.JSONDecodeError, OSError) as exc:
        sys.exit(f"cannot read {src}: {exc}")

    season = season_paths.season_of(event_date)
    dest_dir = season_paths.season_json_dir(season)
    dest = os.path.join(dest_dir, os.path.basename(src))

    if args.dry_run:
        print(dest)
        return

    os.makedirs(dest_dir, exist_ok=True)
    if os.path.abspath(dest) != src:
        shutil.move(src, dest)
    print(dest)


if __name__ == "__main__":
    main()
