#!/usr/bin/env python3
"""Strip sheet bookkeeping out of `athlete_name` in the stored JSONs.

Legacy era parsers wrote the row's position, lane and category into the name
itself, so a stored result can read:

    1 258 (t) Francisco Javier Baz Vidal M-50
    119 Francisco Jose Iborra M-50 AB NP AB
    1 93 (t) Kilian Borreda Cervello q RCAM
    Carla Berenguel 4 Q

Those prefixes/suffixes are the sheet's bookkeeping, not part of the athlete's
name. This script removes them, conservatively:

* leading position/dorsal numbers and (t)/(q) round markers;
* trailing category, series, record and status tokens, plus trailing digits;
* an age code glued to a trailing number (M-50, F-45, M50).

It deliberately does NOT touch single-letter tokens in the middle of a name
(a middle initial such as "JOSE M GARCIA" is information, not noise). Names are
only ever shortened at the edges, and a row is left untouched when the result
would stop looking like a two-token name.

Nothing is deduplicated: when cleaning makes two rows identical the script
reports them and leaves the decision to a human, because combining attempts and
rounds is a domain rule (see AGENTS.md), not a formatting fix.

Usage:
    python3 scripts/clean_athlete_names.py            # dry run, default
    python3 scripts/clean_athlete_names.py --apply
    python3 scripts/clean_athlete_names.py --season 2018 --apply
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SEASONS_DIR = ROOT / "seasons"

# Markers the sheet prints around the position: round (t)/(q), foreign (e).
_ROUND_MARKER = re.compile(r"\((?:t|q|e|f)\)", re.IGNORECASE)
# A leading position/dorsal token: "1", "258", "1068", "51." (the sheet
# sometimes prints the dorsal with a trailing dot).
_LEADING_TOKEN = re.compile(r"^(?:\d{1,4}\.?|\((?:t|q|e|f)\))$", re.IGNORECASE)
# Age category glued to the name: M-50, F-45, M50, W-35
_AGE_CODE = re.compile(r"\b[MFW]-?\d{2,3}\b")
# Trailing tokens that are the sheet's business, never part of a name.
_TRAILING_NOISE = {
    # categories: benjamí/cadet/juvenil/junior/promesa/sènior/absolut
    "BM", "BF", "IM", "IF", "CM", "CF", "JM", "JF", "SM", "SF", "PM", "PF",
    "PBM", "PBF", "JNM", "JNF", "JVF", "LM", "LF", "AM", "AF", "AB",
    # series / qualifier / status markers
    "Q", "QB", "QN", "QC", "NP", "E", "DNS", "DNF", "DQ", "RET", "MMT", "MMF", "MMP",
    # medal text and regional record markers
    "DOR", "ARGENT", "BRONZE", "PLATA", "OR", "GOLD", "SILVER", "RCAM", "RCAT",
}


def clean_name(name: str) -> str:
    """Return the athlete's name with the sheet's bookkeeping removed."""
    text = " ".join(str(name or "").split())
    previous = None
    while previous != text:
        previous = text
        text = _ROUND_MARKER.sub(" ", text)
        text = _AGE_CODE.sub(" ", text)
        text = " ".join(text.split())
        # drop the leading run of position/dorsal numbers and markers, at most
        # two numbers (position, then dorsal) so a bare number-only prefix is
        # never eaten deeper into the name
        parts = text.split()
        dropped_numbers = 0
        while parts and dropped_numbers < 2:
            token = parts[0]
            if not _LEADING_TOKEN.match(token):
                break
            if token.replace(".", "").isdigit():
                dropped_numbers += 1
                if dropped_numbers > 2:
                    break
            parts.pop(0)
        text = " ".join(parts)
        # strip trailing noise tokens and stray numbers, one at a time
        while True:
            parts = text.split()
            if not parts:
                break
            last = parts[-1]
            bare = re.sub(r"[^A-Za-z0-9]", "", last).upper()
            # a trailing number, possibly decimal ("Ruth Prats Nadal 7.5")
            if re.fullmatch(r"\d+(?:[.,]\d+)?\.?", last) or bare in _TRAILING_NOISE:
                text = " ".join(parts[:-1])
                continue
            break
        text = " ".join(text.split())
    return text


def usable(cleaned: str, original: str) -> bool:
    """Reject a cleaning that stops looking like a person's full name."""
    tokens = cleaned.split()
    if len(tokens) < 2:
        return False
    if not tokens[0][0].isalpha():
        return False
    if len(cleaned) < 4 or len(cleaned) > len(original):
        return False
    return True


def iter_files(season=None):
    pattern = f"{season}/json/*.json" if season else "*/json/*.json"
    for path in sorted(SEASONS_DIR.glob(pattern)):
        yield path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--season", help="limit to one season (e.g. 2018)")
    args = ap.parse_args()

    changed_rows = 0
    changed_files = 0
    skipped = []
    samples = []
    collisions = []
    preexisting = []

    for path in iter_files(args.season):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"!! invalid JSON {path}: {exc}", file=sys.stderr)
            continue

        touched = False
        def key_of(result):
            return (result.get("athlete_name"), result.get("discipline"),
                    result.get("performance"))
        before_counts = Counter(key_of(r) for r in data.get("results", []))
        renamed = 0
        for r in data.get("results", []):
            original = r.get("athlete_name") or ""
            cleaned = clean_name(original)
            if cleaned == original:
                continue
            if not usable(cleaned, original):
                skipped.append((path, original, cleaned))
                continue
            r["athlete_name"] = cleaned
            touched = True
            renamed += 1
            changed_rows += 1
            if len(samples) < 12:
                samples.append((original, cleaned))

        # Cleaning must not silently merge two rows: report what it caused,
        # never deduplicate. Repeats that already existed are counted apart.
        after_counts = Counter(key_of(r) for r in data.get("results", []))
        for key, count in after_counts.items():
            if count > 1:
                if count > before_counts.get(key, 0):
                    collisions.append((path, key, count))
                else:
                    preexisting.append((path, key, count))

        if touched:
            changed_files += 1
            if args.apply:
                fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, indent=2, ensure_ascii=False)
                        fh.write("\n")
                    os.replace(tmp, path)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)

    print(f"rows to clean: {changed_rows} in {changed_files} files")
    if samples:
        print("\nsamples:")
        for original, cleaned in samples:
            print(f"  {original[:52]:54s} -> {cleaned}")
    if skipped:
        print(f"\nleft untouched (result would not be a full name): {len(skipped)}")
        for path, original, cleaned in skipped[:10]:
            print(f"  {path.relative_to(ROOT)} | {original!r} -> {cleaned!r}")
    if collisions:
        print(f"\nNEW repeats created by cleaning: {len(collisions)} groups (not deduplicated)")
        for path, key, count in collisions[:10]:
            print(f"  {path.relative_to(ROOT)} | {key} x{count}")
    else:
        print("\nno new repeats created by cleaning")
    if preexisting:
        print(f"pre-existing repeats left alone: {len(preexisting)} groups")
    print("\nAPPLIED" if args.apply else "\nDRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
