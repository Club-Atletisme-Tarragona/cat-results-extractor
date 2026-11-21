"""Data contract tests: validate every JSON in seasons/ (and legacy json/)
against the documented output contract (AGENTS.md).

These are regression guards over the whole dataset. They would have caught
issue #20 (327 rows with empty event_date, 5 with empty event_src) before
it shipped, and they catch any future extractor/aggregator change that
breaks the contract.

Two kinds of assertions:
- Hard invariants: things that must always hold (non-empty required fields,
  valid dates, provenance URLs, wind rules).
- Bounded known-legacy gaps: documented gaps that are legitimate for
  historical data (e.g. missing event_name in 215 old source files).
  They are pinned with a ceiling so they cannot grow silently.

Run: python3 -m unittest tests.test_data_contract -v
"""

import datetime
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import COMBINED_PATTERNS  # noqa: E402,F401  (re-exported use below)

DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
WIND_RE = re.compile(r"^[+-]?\d+\.\d{1,2}$")
RELAY_RE = re.compile(r"4\s*[xX]\s*\d+")
# Data-level combined-event notion (wider than extract_catt.COMBINED_PATTERNS,
# which requires a gender/category suffix and misses bare 'Triatló' rows).
# Covers both 'Pentathlon' and Catalan 'Pentatló' spellings (with/without h).
COMBINED_DISCIPLINE_RE = re.compile(
    r"pent(atl|athlon)|hept(atl|athlon)|dec(atl|athlon)|tri(atl|athlon)"
    r"|tetr(atl|athlon)|hex(atl|athlon)|combinad",
    re.IGNORECASE,
)

# Bounded known-legacy gaps: (description, ceiling). Ceilings must never grow.
KNOWN_LEGACY = {
    "source_files_empty_event_name": 215,
}


def source_files():
    """All source JSONs from seasons/<year>/json/ (excluding imported/).

    There is no top-level json/ directory: every season, current and past,
    lives under seasons/<year>/json/ (see season_paths.py).
    """
    files = set(glob.glob(str(REPO_ROOT / "seasons" / "*" / "json" / "*.json")))
    return sorted(f for f in files if f"{os.sep}imported{os.sep}" not in f)


def valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        datetime.datetime.strptime(value, "%d/%m/%Y")
        return True
    except ValueError:
        return False


class TestSourceFileContract(unittest.TestCase):
    """Event-level fields live at FILE level in seasons/ and json/ files."""

    def setUp(self):
        self.files = source_files()

    def test_dataset_present(self):
        # Sanity: the scan must actually find the dataset.
        self.assertGreater(len(self.files), 1000)

    def test_event_date_present_and_valid(self):
        bad = []
        for fp in self.files:
            data = json.load(open(fp, encoding="utf-8"))
            if not data.get("results"):
                continue
            date = (data.get("event_date") or "").strip()
            if not date or not valid_date(date):
                bad.append(fp)
        self.assertEqual(bad, [], f"source files with missing/invalid event_date: {bad[:5]}")

    def test_event_src_present_and_is_url(self):
        bad = []
        for fp in self.files:
            data = json.load(open(fp, encoding="utf-8"))
            if not data.get("results"):
                continue
            src = (data.get("event_src") or "").strip()
            if not src.startswith(("http://", "https://")):
                bad.append(fp)
        self.assertEqual(bad, [], f"source files with missing/invalid event_src: {bad[:5]}")

    def test_required_result_fields_non_empty(self):
        bad = []
        for fp in self.files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                for field in ("athlete_name", "performance", "discipline"):
                    if not (row.get(field) or "").strip():
                        bad.append(f"{fp}[{i}].{field}")
        self.assertEqual(bad, [], f"rows missing required fields: {bad[:5]}")

    def test_known_legacy_empty_event_name_does_not_grow(self):
        count = 0
        for fp in self.files:
            data = json.load(open(fp, encoding="utf-8"))
            if data.get("results") and not (data.get("event_name") or "").strip():
                count += 1
        ceiling = KNOWN_LEGACY["source_files_empty_event_name"]
        self.assertLessEqual(
            count, ceiling,
            f"empty event_name count grew: {count} > {ceiling}. "
            "If fixing legacy files, lower the ceiling in KNOWN_LEGACY.",
        )


class TestVeteransWorklistStaysHonest(unittest.TestCase):
    """A clean masters dataset must not leave a stale worklist on disk.

    The checker used to write `--csv` only when it found suspects, so a clean
    run left the previous run's rows in place and read as if they were open.
    """

    def test_clean_run_rewrites_the_worklist_header_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "suspects.csv")
            out.write_text(
                "file,event_name,athlete_name,discipline,performance,why,source\n"
                "stale,garbage,row,kept,from,a,previous run\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "scripts/check_veterans_marks.py", "--csv", str(out)],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1, f"stale worklist not cleared: {lines}")
            self.assertTrue(lines[0].startswith("file,event_name,"))


class TestIssue20FixStaysFixed(unittest.TestCase):
    """The issue #20 fixer must be a no-op on a healthy dataset.

    The `athletes/` aggregates were retired, so the fixer only maintains
    season JSONs; a healthy tree reports zero empty event_date/event_src.
    """

    def test_fixer_is_idempotent(self):
        proc = subprocess.run(
            [sys.executable, "scripts/fix_empty_event_fields.py", "--dry-run"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(
            "AUDIT seasons/: empty event_date=0, empty event_src=0",
            proc.stdout,
        )


if __name__ == "__main__":
    unittest.main()
