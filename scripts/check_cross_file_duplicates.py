#!/usr/bin/env python3
"""Cross-file duplicate detector for extracted results.

Issue #15: identical (athlete, discipline, performance) rows appearing in
different competition files may indicate an extraction bug (wrong section
captured) or simply genuine repetitions (same athlete competing in several
competitions and repeating the same mark — very common in Alçada, where kids
clear the same bar height, and plausible in Pes/Llargada and sprints).

This script scans json/*.json, groups results by
(athlete_name, discipline, performance) and reports every key found in more
than one distinct competition file (different event_src). It also cross-checks
each duplicate against the source PDF text (pdftotext -layout) when the PDF is
available in pdf_cache/**, so a human can confirm whether the mark really
appears in both source documents.

Usage:
    python3 scripts/check_cross_file_duplicates.py            # human report
    python3 scripts/check_cross_file_duplicates.py --pdf      # verify against PDFs
    python3 scripts/check_cross_file_duplicates.py --json     # machine-readable
    python3 scripts/check_cross_file_duplicates.py --dir seasons/2025-2026/json
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

REQUIRED_FIELDS = ("athlete_name", "discipline", "performance")


def load_results(json_dir):
    """Yield (filename, result) for every entry with the required fields."""
    for path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"WARNING: cannot read {path}: {exc}", file=sys.stderr)
            continue
        fname = os.path.basename(path)
        for result in data.get("results", []):
            if all(result.get(f) for f in REQUIRED_FIELDS):
                yield fname, result


def find_duplicates(json_dir):
    """Return {(athlete, discipline, performance): {filename: [result, ...]}}
    for keys present in more than one distinct file."""
    groups = defaultdict(lambda: defaultdict(list))
    for fname, result in load_results(json_dir):
        key = tuple(result[f] for f in REQUIRED_FIELDS)
        groups[key][fname].append(result)
    return {k: v for k, v in groups.items() if len(v) > 1}


def locate_pdf(event_src):
    """Find a cached PDF matching the event_src URL basename."""
    if not event_src:
        return None
    basename = os.path.basename(event_src.split("?")[0])
    for candidate in glob.glob(os.path.join("pdf_cache", "**", basename), recursive=True):
        return candidate
    return None


def pdf_contains_mark(pdf_path, athlete_name, performance):
    """True if the athlete name and the performance value appear in the PDF
    text (loose layout-independent check)."""
    perf_norm = performance.replace(",", ".")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                ["pdftotext", "-layout", pdf_path, os.path.join(tmp, "out.txt")],
                check=True, capture_output=True,
            )
            text = open(os.path.join(tmp, "out.txt"), encoding="utf-8", errors="replace").read()
        except (subprocess.CalledProcessError, OSError):
            return None
    lines_with_athlete = [ln for ln in text.splitlines() if athlete_name in ln]
    if not lines_with_athlete:
        return False
    for idx, ln in enumerate(lines_with_athlete):
        window = "\n".join(text.splitlines()[max(0, text.splitlines().index(ln)): text.splitlines().index(ln) + 6])
        if perf_norm in window:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="json", help="JSON directory to scan")
    parser.add_argument("--pdf", action="store_true", help="cross-check duplicates against source PDFs")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON report")
    args = parser.parse_args()

    dups = find_duplicates(args.dir)
    if args.json:
        report = {
            "duplicate_keys": len(dups),
            "affected_rows": sum(len(v) for v in dups.values()),
            "entries": [
                {"athlete_name": k[0], "discipline": k[1], "performance": k[2],
                 "files": sorted(files)}
                for k, files in sorted(dups.items())
            ],
        }
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    total_rows = sum(len(v) for v in dups.values())
    print(f"Cross-file duplicate keys: {len(dups)}  (affected rows: {total_rows})")
    if not dups:
        return

    by_discipline = defaultdict(int)
    for (athlete, discipline, _perf), files in dups.items():
        by_discipline[discipline] += 1
    print("By discipline:")
    for discipline, count in sorted(by_discipline.items(), key=lambda x: -x[1]):
        print(f"  {discipline}: {count}")
    print()

    for (athlete, discipline, perf), files in sorted(dups.items()):
        print(f"{athlete} | {discipline} | {perf}")
        for fname in sorted(files):
            src = None
            try:
                src = json.load(open(os.path.join(args.dir, fname))).get("event_src")
            except (OSError, ValueError):
                pass
            print(f"    {fname}" + (f"  <- {src}" if src else ""))
        if args.pdf:
            for fname in sorted(files):
                src = json.load(open(os.path.join(args.dir, fname))).get("event_src")
                pdf = locate_pdf(src)
                if pdf is None:
                    print(f"      [PDF] {fname}: source PDF not cached")
                    continue
                found = pdf_contains_mark(pdf, athlete, perf)
                verdict = {True: "FOUND in PDF", False: "NOT found in PDF", None: "unreadable"}[found]
                print(f"      [PDF] {fname}: {verdict} ({pdf})")
        print()


if __name__ == "__main__":
    main()