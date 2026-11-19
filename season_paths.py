#!/usr/bin/env python3
"""Single source of truth for season-scoped data paths.

Every extractor output lives in `seasons/<season>/json/`. There is no
top-level `json/` directory: the 2026 season was the last one kept there
and was migrated to `seasons/2026/json/` on 2026-11-19, so seasons are
uniform for every year, past and future.

A "season" is the calendar year of the event (matching seasons/2005 ..
seasons/2025, which hold the events that took place in that year), not an
academic year. Two helpers keep that rule in one place:

    season_of("14/3/2026")     -> "2026"   (from an event date)
    current_season()           -> "2026"   (today, or $CATT_SEASON)

`CATT_SEASON` lets an operator or a workflow pin the target season
explicitly; it is only a fallback for data whose date is unknown.

Usage:
    from season_paths import season_of, current_season, season_json_dir
"""

import datetime
import os
import re

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SEASONS_DIR = os.path.join(REPO_ROOT, "seasons")

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def season_of(date_str, fallback=None):
    """Season (year string) for an event date written DD/MM/YYYY or YYYY-MM-DD.

    Returns `fallback` (default: current_season()) when the date is missing
    or unparseable, so callers never crash on legacy sheets.
    """
    if date_str:
        text = str(date_str).strip()
        m = _DATE_RE.fullmatch(text) or _DATE_RE.search(text)
        if m:
            year = int(m.group(3))
            if year < 100:  # two-digit year: 06 -> 2006
                year += 2000 if year < 70 else 1900
            if 1990 <= year <= 2100:
                return str(year)
        m = _ISO_RE.fullmatch(text) or _ISO_RE.search(text)
        if m:
            year = int(m.group(1))
            if 1990 <= year <= 2100:
                return str(year)
    return fallback if fallback is not None else current_season()


def current_season():
    """Season to use when no event date is available.

    `$CATT_SEASON` overrides; otherwise the calendar year of today. A pin is
    only needed for unusual backfills - normal runs derive the season from
    the event date itself.
    """
    pinned = os.environ.get("CATT_SEASON", "").strip()
    if pinned:
        if not re.fullmatch(r"\d{4}", pinned):
            raise ValueError(f"CATT_SEASON must be a 4-digit year, got {pinned!r}")
        return pinned
    return str(datetime.date.today().year)


def season_json_dir(season=None, root=None):
    """Absolute path of seasons/<season>/json (not created)."""
    return os.path.join(root or SEASONS_DIR, season or current_season(), "json")


def season_imported_dir(season=None, root=None):
    """Absolute path of seasons/<season>/json/imported (the "already
    imported into the CATT system" marker, per season)."""
    return os.path.join(season_json_dir(season, root), "imported")


def known_seasons(root=None):
    """Season labels that already have a json/ directory, sorted."""
    root = root or SEASONS_DIR
    if not os.path.isdir(root):
        return []
    return sorted(
        name for name in os.listdir(root)
        if re.fullmatch(r"\d{4}", name) and os.path.isdir(os.path.join(root, name, "json"))
    )


if __name__ == "__main__":  # tiny self-test
    assert season_of("14/3/2026") == "2026"
    assert season_of("01/12/05") == "2005"
    assert season_of("2026-03-14") == "2026"
    assert season_of("") == current_season()
    assert season_of(None, fallback="2019") == "2019"
    assert season_json_dir("2026").endswith(os.path.join("seasons", "2026", "json"))
    print("season_of('14/3/2026') =", season_of("14/3/2026"))
    print("current_season()       =", current_season())
    print("known seasons          =", ", ".join(known_seasons()))
    print("ok")
