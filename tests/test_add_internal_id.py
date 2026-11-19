"""Unit tests for the athlete-identity report grouping (AGENTS.md).

The unknown-athlete report groups rows per athlete because legacy era parsers
stored each row's position, lane and category inside athlete_name. These are
the exact strings found in reports/unknown_athletes.md.

Run: python3 -m unittest tests.test_add_internal_id -v
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.add_internal_id import display_identity, normalize  # noqa: E402


class TestDisplayIdentity(unittest.TestCase):
    """One athlete must collapse to one identity, whatever the sheet's noise."""

    def test_strips_position_dorsal_and_category(self):
        self.assertEqual(display_identity("1 56 (t) Kilian Borreda Cervello BM"),
                         "Kilian Borreda Cervello")

    def test_strips_series_and_record_markers(self):
        self.assertEqual(display_identity("1 93 (t) Kilian Borreda Cervello q RCAM"),
                         "Kilian Borreda Cervello")

    def test_strips_glued_date_and_age_code(self):
        self.assertEqual(display_identity("(t) Kilian Borreda Cervello 09/05/2013 AM 2"),
                         "Kilian Borreda Cervello")

    def test_strips_absolut_marker_chain(self):
        self.assertEqual(display_identity("119 Francisco Jose Iborra M-50 AB NP AB"),
                         "Francisco Jose Iborra")

    def test_strips_trailing_position_and_qualifier(self):
        self.assertEqual(display_identity("Carla Berenguel 4 Q"), "Carla Berenguel")

    def test_keeps_a_clean_name_untouched(self):
        self.assertEqual(display_identity("Erika Diez Plasencia"), "Erika Diez Plasencia")

    def test_variants_share_one_grouping_key(self):
        variants = [
            "1 56 (t) Kilian Borreda Cervello BM",
            "1 93 (t) Kilian Borreda Cervello q RCAM",
            "13 79 (t) Kilian Borreda Cervello",
            "KILIAN BORREDA CERVELLO",
        ]
        keys = {normalize(display_identity(v)) for v in variants}
        self.assertEqual(keys, {"KILIAN BORREDA CERVELLO"})

    def test_different_athletes_do_not_collapse(self):
        self.assertNotEqual(normalize(display_identity("1 56 (t) Kilian Borreda Cervello BM")),
                            normalize(display_identity("2 282 (t) Duina Borreda Cervello AF")))


if __name__ == "__main__":
    unittest.main()
