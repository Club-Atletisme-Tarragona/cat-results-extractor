#!/usr/bin/env python3
"""Unit tests for the event-date audit (`scripts/check_event_dates.py`).

The audit used to compare `stored` and `header` as strings, so the same day
written `26/4/2006` (no zero padding) and `26/04/2006` was reported as a
mismatch. Issue #28 counted 15 such rows out of 55 and they buried the real
conflicts in the worklist. A date comparison must compare days, not spellings.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import check_event_dates  # noqa: E402


class TestDateComparison(unittest.TestCase):
    def test_unpadded_day_is_the_same_day(self):
        self.assertFalse(check_event_dates.dates_conflict("26/4/2006", "26/04/2006"))

    def test_unpadded_month_is_the_same_day(self):
        self.assertFalse(check_event_dates.dates_conflict("9/2/2008", "09/02/2008"))

    def test_identical_dates_do_not_conflict(self):
        self.assertFalse(check_event_dates.dates_conflict("14/02/2016", "14/02/2016"))

    def test_a_real_difference_still_conflicts(self):
        # glued leading zero in the filename: '20416' is 02/04, not 20/04
        self.assertTrue(check_event_dates.dates_conflict("20/4/2016", "02/04/2016"))

    def test_a_different_year_conflicts(self):
        self.assertTrue(check_event_dates.dates_conflict("07/04/2017", "07/04/2018"))

    def test_missing_stored_date_is_not_silently_ignored(self):
        # An empty stored date is a contract defect, but the audit only cares
        # about conflicts; the call site keeps its own `stored and` guard.
        self.assertTrue(check_event_dates.dates_conflict("", "02/04/2016"))

    def test_unparseable_values_conflict(self):
        self.assertTrue(check_event_dates.dates_conflict("not a date", "02/04/2016"))
        self.assertTrue(check_event_dates.dates_conflict("20/4/2016", "garbage"))


class TestParseDate(unittest.TestCase):
    def test_parses_padded_and_unpadded(self):
        import datetime

        self.assertEqual(check_event_dates.parse_date("26/4/2006"),
                         datetime.date(2006, 4, 26))
        self.assertEqual(check_event_dates.parse_date("26/04/2006"),
                         datetime.date(2006, 4, 26))

    def test_tolerates_surrounding_whitespace(self):
        import datetime

        self.assertEqual(check_event_dates.parse_date("  09/02/2008 "),
                         datetime.date(2008, 2, 9))

    def test_returns_none_for_junk(self):
        for value in (None, "", "  ", "32/01/2016", "01/13/2016", "not a date"):
            self.assertIsNone(check_event_dates.parse_date(value), value)


class TestCachedPdf(unittest.TestCase):
    """The audit must prefer pdf_cache/ over re-downloading every PDF."""

    def test_finds_the_cached_pdf_by_url_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "2016"
            cache.mkdir()
            pdf = cache / "event.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            found = check_event_dates.cached_pdf(
                "https://old.fcatletisme.cat/Pcoberta/2016/event.pdf", "2016",
                cache_root=Path(tmp))
            self.assertEqual(found, pdf)

    def test_handles_double_extension_cache_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "2016"
            cache.mkdir()
            pdf = cache / "combi.pdf.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            found = check_event_dates.cached_pdf(
                "https://old.fcatletisme.cat/Pcoberta/2016/combi.pdf.pdf", "2016",
                cache_root=Path(tmp))
            self.assertEqual(found, pdf)

    def test_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(check_event_dates.cached_pdf(
                "https://example.org/nope.pdf", "2016", cache_root=Path(tmp)))


class TestKeepStoredRegistry(unittest.TestCase):
    """A documented "keep stored" decision must not hide a future change.

    Each entry pins the exact stored/header pair it was decided on. If either
    side moves, the row becomes an open mismatch again instead of being
    silently swallowed by the registry.
    """

    KEPT_FILE = "seasons/2010/json/resulmitingveteransreus8510.json"

    def test_matching_entry_counts_as_kept(self):
        decision = check_event_dates.keep_decision(
            self.KEPT_FILE, "8/5/2010", "09/05/2010")
        self.assertIsNotNone(decision)
        self.assertIn("Reus", decision.evidence)

    def test_changed_stored_date_resurfaces_as_open(self):
        self.assertIsNone(check_event_dates.keep_decision(
            self.KEPT_FILE, "7/5/2010", "09/05/2010"))

    def test_changed_header_date_resurfaces_as_open(self):
        self.assertIsNone(check_event_dates.keep_decision(
            self.KEPT_FILE, "8/5/2010", "10/05/2010"))

    def test_unknown_file_has_no_decision(self):
        self.assertIsNone(check_event_dates.keep_decision(
            "seasons/2016/json/nope.json", "01/01/2016", "02/01/2016"))

    def test_covered_cases_are_not_kept_here(self):
        # issue #32: parse_header now reads these headers itself, so they must
        # not linger as decisions. A regression surfaces as an open mismatch.
        for rel in (
            "seasons/2005/json/resulcatabsolut.json",
            "seasons/2005/json/resulcatjuniorpc.json",
            "seasons/2005/json/resulcatjuvenilpc.json",
            "seasons/2008/json/resulcatcadetpc2324208.json",
            "seasons/2009/json/resulcatcadetpc2122209.json",
            "seasons/2009/json/resulcatjuvenilpc2122209.json",
            "seasons/2016/json/resullliguetasub11bcn71115.json",
            "seasons/2026/json/resultat-20260117-gpmarxaelvendrell.json",
        ):
            with self.subTest(path=rel):
                self.assertNotIn(rel, check_event_dates.KEEP_STORED)

    def test_every_entry_documents_its_evidence(self):
        for path, decision in check_event_dates.KEEP_STORED.items():
            self.assertTrue(decision.evidence.strip(), f"{path} has no evidence")
            self.assertIsNotNone(check_event_dates.parse_date(decision.stored), path)
            self.assertIsNotNone(check_event_dates.parse_date(decision.header), path)


if __name__ == "__main__":
    unittest.main()
