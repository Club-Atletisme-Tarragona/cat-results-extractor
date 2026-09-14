"""Data contract tests: validate every JSON in seasons/, json/ and athletes/
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
    """All source JSONs from seasons/ and json/ (excluding json/imported/)."""
    files = set(glob.glob(str(REPO_ROOT / "seasons/*/**/*.json"), recursive=True))
    files |= set(glob.glob(str(REPO_ROOT / "json/*.json")))
    files |= set(glob.glob(str(REPO_ROOT / "json/**/*.json"), recursive=True))
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


class TestAthleteFileContract(unittest.TestCase):
    """Event fields live per ROW in athletes/ files (aggregated output)."""

    @classmethod
    def setUpClass(cls):
        # Only per-athlete files: skip aggregator artifacts (index.json,
        # _report.json, internal_id_report.json).
        skip = {"index.json", "_report.json", "internal_id_report.json"}
        cls.athlete_files = sorted(
            p for p in glob.glob(str(REPO_ROOT / "athletes/*.json"))
            if Path(p).name not in skip
        )

    def test_athletes_present(self):
        self.assertGreater(len(self.athlete_files), 500)

    def test_row_event_date_present_and_valid(self):
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                date = (row.get("event_date") or "").strip()
                if not date or not valid_date(date):
                    bad.append(f"{fp}[{i}] {date!r}")
        self.assertEqual(bad, [], f"rows with missing/invalid event_date: {bad[:5]}")

    def test_row_event_src_present_and_is_url(self):
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                src = (row.get("event_src") or "").strip()
                if not src.startswith(("http://", "https://")):
                    bad.append(f"{fp}[{i}] {src!r}")
        self.assertEqual(bad, [], f"rows with missing/invalid event_src: {bad[:5]}")

    def test_required_row_fields_non_empty(self):
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                for field in ("athlete_name", "performance", "discipline"):
                    if not (row.get(field) or "").strip():
                        bad.append(f"{fp}[{i}].{field}")
        self.assertEqual(bad, [], f"rows missing required fields: {bad[:5]}")

    def test_wind_format(self):
        """wind is null or a signed decimal like +1.2 / -0.8 / 1.4."""
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                wind = row.get("wind")
                if wind is not None and not WIND_RE.match(str(wind)):
                    bad.append(f"{fp}[{i}] wind={wind!r}")
        self.assertEqual(bad, [], f"rows with malformed wind: {bad[:5]}")

    def test_no_wind_on_relays(self):
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                if row.get("wind") is not None and RELAY_RE.search(row.get("discipline", "")):
                    bad.append(f"{fp}[{i}] {row.get('discipline')}")
        self.assertEqual(bad, [], f"relay rows carrying wind: {bad[:5]}")

    def test_integer_performances_only_for_combined_events(self):
        """Pure integers <=3 digits are positions, not marks — except
        combined-event points (AGENTS.md: Position numbers are NOT
        performances)."""
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            for i, row in enumerate(data.get("results", [])):
                perf = (row.get("performance") or "").strip()
                disc = (row.get("discipline") or "").strip()
                if perf.isdigit() and len(perf) <= 3 and not COMBINED_DISCIPLINE_RE.search(disc):
                    bad.append(f"{fp}[{i}] {disc}={perf}")
        self.assertEqual(bad, [], f"position-like performances outside combined events: {bad[:5]}")

    def test_total_results_matches_list(self):
        bad = []
        for fp in self.athlete_files:
            data = json.load(open(fp, encoding="utf-8"))
            if data.get("total_results") != len(data.get("results", [])):
                bad.append(fp)
        self.assertEqual(bad, [], f"total_results mismatch: {bad[:5]}")


class TestIssue20FixStaysFixed(unittest.TestCase):
    """The issue #20 fixer must be a no-op on a healthy dataset."""

    def test_fixer_is_idempotent(self):
        proc = subprocess.run(
            [sys.executable, "scripts/fix_empty_event_fields.py", "--dry-run"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("filled 0 event_date, 0 event_src", proc.stdout)


class TestAggregatorCharacterization(unittest.TestCase):
    """Pin the current end-to-end aggregation behavior for one athlete.

    If this test fails after an intentional change to merge/dedup rules,
    update the expected numbers after reviewing the diff — they are the
    characterization baseline (stored athletes/ files were built by older
    pipeline versions and may legitimately differ).
    """

    ATHLETE = "PEP ALDAVE MAS"

    def test_aggregation_reproducible_and_dated(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "scripts/aggregate_athletes.py",
                 "--athlete", self.ATHLETE, "--output-dir", tmp],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = Path(tmp, "pep-aldave-mas.json")
            self.assertTrue(out.exists(), "aggregator did not write the athlete file")
            data = json.load(open(out, encoding="utf-8"))
            self.assertEqual(len(data["results"]), 104)
            empty_dates = [r for r in data["results"] if not r.get("event_date")]
            empty_srcs = [r for r in data["results"] if not r.get("event_src")]
            self.assertEqual(empty_dates, [])
            self.assertEqual(empty_srcs, [])


if __name__ == "__main__":
    unittest.main()
