#!/usr/bin/env python3
"""Normalize sub-minute ss.cc performances to the mm:ss.cc DB format.

DISCIPLINES.md declares format `mm:ss.cc` for llisos >= 300m, tanques/
obstacles >= 400m, all marxa and 4x200+ relays, but the PDFs print
sub-minute times without the minute part (e.g. `49.96` for a 400m), and
older extractor runs stored them verbatim. This script re-prefixes those
values with `0:` so they match the DB `format` column.

Only touches results whose mapped `discipline` declares `mm:ss.cc` in
DISCIPLINES.md and whose `performance` matches `ss.cc` (1-2 digits, dot,
exactly 2 decimals). `raw_discipline_name` and everything else are left
untouched. Idempotent: `0:49.96` does not match `ss.cc` and is skipped.

Usage:
    python3 scripts/normalize_mmsscc_times.py --dry-run
    python3 scripts/normalize_mmsscc_times.py
"""

import argparse
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCIPLINES_MD = os.path.join(REPO, "DISCIPLINES.md")
TARGET_DIRS = [
    os.path.join(REPO, "seasons", "2025", "json"),
    os.path.join(REPO, "json"),  # current season; imported/ is excluded below
]

SS_CC = re.compile(r"^\d{1,2}\.\d{2}$")


def load_mmsscc_disciplines():
    """Return the set of discipline names whose DB format is mm:ss.cc."""
    discs = set()
    with open(DISCIPLINES_MD, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(?:ASC|DESC)\s*\|\s*([^|]+?)\s*\|", line)
            if m and m.group(1) != "name" and m.group(2).strip() == "mm:ss.cc":
                discs.add(m.group(1))
    return discs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mmsscc = load_mmsscc_disciplines()
    print(f"Disciplines with mm:ss.cc format: {len(mmsscc)}")

    total_files = total_changed = 0
    for target in TARGET_DIRS:
        if not os.path.isdir(target):
            continue
        for fn in sorted(os.listdir(target)):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(target, fn)
            rel = os.path.relpath(path, REPO)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            results = data.get("results", [])
            changed = []
            for r in results:
                if r.get("discipline") in mmsscc and SS_CC.match(str(r.get("performance", ""))):
                    r["performance"] = f"0:{r['performance']}"
                    changed.append(r)
            if not changed:
                continue
            total_files += 1
            total_changed += len(changed)
            print(f"{rel}: {len(changed)} values normalized")
            for r in changed[:3]:
                print(f"    {r['discipline']:35s} {r['performance']}  {r['athlete_name']}")
            if len(changed) > 3:
                print(f"    ... and {len(changed) - 3} more")
            if not args.dry_run:
                data["total_results"] = len(results)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, path)

    mode = "DRY RUN - no files written" if args.dry_run else "written"
    print(f"\n{total_changed} performances in {total_files} files ({mode})")


if __name__ == "__main__":
    main()
