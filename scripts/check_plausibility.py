#!/usr/bin/env python3
"""Plausibility check for performance values in result JSONs.

Complements scripts/validate_performance.py (format check) with a
physical-plausibility check: every track/marxa time must be at or above a
world-record-level floor for its distance, and a sub-minute ss.cc value
under a distance whose sub-minute time is impossible (600m+ llisos,
obstacles, marxa, long relays) is flagged as corrupt data regardless of
format.

Origin: the '0:45.57 for 800m' defect (2026-11) - a truncated 2:45.57 was
re-prefixed by a format normalizer that never asked whether a sub-minute
800m could exist. Format checks alone cannot catch corrupt-but-well-formed
values; this script is the missing gate.

Usage:
    python3 scripts/check_plausibility.py                     # json/ + seasons/*/json
    python3 scripts/check_plausibility.py --season 2025      # one season only
Exit code 1 when violations are found.
"""
import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Minimum plausible times in seconds (world-record-level floors; youth and
# masters are slower, so these are safe lower bounds).
DIST_FLOOR = {
    50: 5.6, 60: 6.4, 80: 7.5, 100: 9.6, 120: 11.0, 150: 13.5, 200: 19.2,
    220: 21.0, 300: 30.5, 330: 34.0, 400: 42.0, 500: 55.0, 600: 68.0,
    800: 95.0, 1000: 120.0, 1500: 195.0, 2000: 280.0, 3000: 440.0,
    5000: 750.0, 10000: 1560.0,
}
HURDLE_EXTRA = {60: 1.5, 80: 2.0, 100: 2.5, 110: 3.0, 200: 3.0, 300: 6.0, 400: 8.0, 330: 8.0}
SUB_MINUTE_OK = {300, 400, 500}  # llisos distances where sub-minute is possible

TRACK_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})?|\d{3,5}) metres (llisos|tanques|obstacles|marxa)")
RELAY_RE = re.compile(r"^(?:4x|3x)(\d{2,3})")
MARKERS = {"DNS", "DNF", "DQ", "RET", "N.P.", "NP", "RET.", "NM", "RT"}


def perf_seconds(p):
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})(?:\.\d{1,2})?", p)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.fullmatch(r"(\d{1,3}):(\d{2}\.\d{2})", p)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    if re.fullmatch(r"\d{1,2}\.\d{2}", p):
        return float(p)
    return None


def check_result(r):
    """Return a violation reason string or None."""
    disc = r.get("discipline", "")
    perf = str(r.get("performance", "")).strip()
    if not perf or perf in MARKERS:
        return None
    secs = perf_seconds(perf)
    if secs is None:
        return None  # not a time (marks/points handled by extraction ranges)

    m = TRACK_RE.match(disc)
    if m:
        dist, kind = int(m.group(1).replace(".", "")), m.group(2)
        floor = DIST_FLOOR.get(dist)
        if floor is not None and kind == "tanques":
            floor += HURDLE_EXTRA.get(dist, 0)
        if floor is not None and secs < floor:
            return f"time {perf}s below floor {floor:.0f}s for {dist}m {kind}"
        # sub-minute impossible: llisos 600m+, all marxa and obstacles
        sub_ok = kind == "llisos" and dist in SUB_MINUTE_OK
        if not sub_ok and dist >= 600 and secs < 60.0:
            return f"sub-minute time {perf}s impossible for {dist}m {kind}"
        return None

    m = RELAY_RE.match(disc)
    if m:
        legs = 4 if disc.startswith("4x") else 3
        total = int(m.group(1)) * legs
        # World-record-level floor (~10.5 m/s with running starts): 4x100 WR is
        # 36.84s. Normal club/youth teams (4x100 in 43-60s, 4x60 kids ~34s) all
        # pass; only physically impossible times flag.
        floor = total / 10.5
        if secs < floor:
            return f"relay time {perf}s implausibly fast for {total}m total"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season")
    args = ap.parse_args()

    if args.season:
        targets = sorted(glob.glob(os.path.join(REPO, "seasons", args.season, "json", "*.json")))
    else:
        targets = sorted(glob.glob(os.path.join(REPO, "json", "*.json"))) + \
                  sorted(glob.glob(os.path.join(REPO, "seasons", "*", "json", "*.json")))
    targets = [t for t in targets if os.sep + "imported" not in t]

    violations = 0
    checked = 0
    for path in targets:
        try:
            d = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        file_viol = []
        for r in d.get("results", []):
            checked += 1
            reason = check_result(r)
            if reason:
                file_viol.append(f"    {r.get('athlete_name', '?'):32s} {r.get('performance', '?'):>10s} "
                                 f"{r.get('discipline', '?'):32s} raw={str(r.get('raw_discipline_name', ''))[:40]} | {reason}")
        if file_viol:
            violations += len(file_viol)
            print(f"{os.path.relpath(path, REPO)}:")
            print("\n".join(file_viol[:12]))
            if len(file_viol) > 12:
                print(f"    ... and {len(file_viol) - 12} more in this file")

    print(f"\nchecked {checked} results in {len(targets)} files: {violations} plausibility violations")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
