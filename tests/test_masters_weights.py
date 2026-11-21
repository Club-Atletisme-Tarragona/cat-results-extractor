"""Unit tests for masters_weights.py (issue #30, spec S1).

The RFEA 2026 table is quoted verbatim in
`odd/tasks/masters-implement-weights.md` (S1). These tests pin every band for
both sexes, the DISCIPLINES.md heavy-hammer spellings, and the header parsing
that lets a category be established without guessing.

Run: python3 -m unittest tests.test_masters_weights -v
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from masters_weights import (  # noqa: E402
    RFEA_2026_WEIGHTS,
    age_on,
    band_for_age,
    expected_weight,
    heavy_hammer_label_for,
    heavy_hammer_label_from_header,
    parse_implement_label,
    parse_sex_and_category,
)


class TestRegulationTable(unittest.TestCase):
    """Every band of the RFEA 2026 table, both sexes (S1)."""

    def test_men_bands(self):
        self.assertEqual(RFEA_2026_WEIGHTS[("m", "35-49")],
                         {"pes": 7.26, "disc": 2.00, "javelina": 0.800,
                          "martell": 7.26, "martell_pesat": 15.88})
        self.assertEqual(RFEA_2026_WEIGHTS[("m", "50-59")],
                         {"pes": 6.00, "disc": 1.50, "javelina": 0.700,
                          "martell": 6.00, "martell_pesat": 11.34})
        self.assertEqual(RFEA_2026_WEIGHTS[("m", "60-69")],
                         {"pes": 5.00, "disc": 1.00, "javelina": 0.600,
                          "martell": 5.00, "martell_pesat": 9.08})
        self.assertEqual(RFEA_2026_WEIGHTS[("m", "70-79")],
                         {"pes": 4.00, "disc": 1.00, "javelina": 0.500,
                          "martell": 4.00, "martell_pesat": 7.26})
        self.assertEqual(RFEA_2026_WEIGHTS[("m", "80+")],
                         {"pes": 3.00, "disc": 1.00, "javelina": 0.400,
                          "martell": 3.00, "martell_pesat": 5.45})

    def test_women_bands(self):
        self.assertEqual(RFEA_2026_WEIGHTS[("f", "35-49")],
                         {"pes": 4.00, "disc": 1.00, "javelina": 0.600,
                          "martell": 4.00, "martell_pesat": 9.08})
        self.assertEqual(RFEA_2026_WEIGHTS[("f", "50-59")],
                         {"pes": 3.00, "disc": 1.00, "javelina": 0.500,
                          "martell": 3.00, "martell_pesat": 7.26})
        self.assertEqual(RFEA_2026_WEIGHTS[("f", "60-74")],
                         {"pes": 3.00, "disc": 1.00, "javelina": 0.500,
                          "martell": 3.00, "martell_pesat": 5.45})
        self.assertEqual(RFEA_2026_WEIGHTS[("f", "75+")],
                         {"pes": 2.00, "disc": 0.75, "javelina": 0.400,
                          "martell": 2.00, "martell_pesat": 4.00})

    def test_every_band_is_boundary_addressable(self):
        men = {35: "35-49", 49: "35-49", 50: "50-59", 59: "50-59",
               60: "60-69", 69: "60-69", 70: "70-79", 79: "70-79",
               80: "80+", 95: "80+"}
        women = {35: "35-49", 49: "35-49", 50: "50-59", 59: "50-59",
                 60: "60-74", 74: "60-74", 75: "75+", 90: "75+"}
        for age, band in men.items():
            self.assertEqual(band_for_age("m", age), band, age)
            self.assertEqual(expected_weight("m", age, "martell_pesat"),
                             RFEA_2026_WEIGHTS[("m", band)]["martell_pesat"])
        for age, band in women.items():
            self.assertEqual(band_for_age("f", age), band, age)
            self.assertEqual(expected_weight("f", age, "martell_pesat"),
                             RFEA_2026_WEIGHTS[("f", band)]["martell_pesat"])

    def test_below_masters_has_no_weight(self):
        self.assertIsNone(band_for_age("m", 34))
        self.assertIsNone(band_for_age("f", 20))
        self.assertIsNone(expected_weight("m", None, "martell_pesat"))

    def test_heavy_hammer_labels_are_disciplines_spellings(self):
        self.assertEqual(heavy_hammer_label_for("m", 40), "Martell pesat (15.88 Kg)")
        self.assertEqual(heavy_hammer_label_for("m", 55), "Martell pesat (11.34 Kg)")
        self.assertEqual(heavy_hammer_label_for("m", 65), "Martell pesat (9.08 Kg)")
        self.assertEqual(heavy_hammer_label_for("m", 75), "Martell pesat (7.26 Kg)")
        self.assertEqual(heavy_hammer_label_for("m", 85), "Martell pesat (5.45 Kg)")
        self.assertEqual(heavy_hammer_label_for("f", 40), "Martell pesat (9.08 Kg)")
        self.assertEqual(heavy_hammer_label_for("f", 55), "Martell pesat (7.26 Kg)")
        self.assertEqual(heavy_hammer_label_for("f", 65), "Martell pesat (5.45 Kg)")
        self.assertEqual(heavy_hammer_label_for("f", 80), "Martell pesat (4 Kg)")


class TestCategoryEvidence(unittest.TestCase):
    def test_age_on_meet_day(self):
        self.assertEqual(age_on("15/01/1974", "12/06/2016"), 42)
        self.assertEqual(age_on("1/3/1949", "08/06/2025"), 76)
        self.assertEqual(age_on("7/9/1956", "05/07/2026"), 69)
        self.assertEqual(age_on("7/9/1956", "26/09/2026"), 70)

    def test_age_on_missing_dates_is_none(self):
        self.assertIsNone(age_on("", "18/09/2016"))
        self.assertIsNone(age_on("15/01/1974", ""))
        self.assertIsNone(age_on("not a date", "12/06/2016"))

    def test_header_category_and_sex(self):
        self.assertEqual(parse_sex_and_category("Martell Pesat Masculí Master M75"),
                         ("m", 75))
        self.assertEqual(parse_sex_and_category("Martell Pesat Homes Master M65"),
                         ("m", 65))
        self.assertEqual(parse_sex_and_category("Martell Pesat VET. Fem. AL 40-44"),
                         ("f", 40))
        self.assertEqual(parse_sex_and_category("Martell pesat (7,26 Kg) M70"),
                         ("m", 70))
        self.assertEqual(parse_sex_and_category("Martell Pesat Dones Master F55"),
                         ("f", 55))

    def test_header_without_category_is_unknown(self):
        self.assertEqual(parse_sex_and_category("LLANÇAMENT DE MARTELL PESAT FEMENI"),
                         ("f", None))
        self.assertEqual(parse_sex_and_category("Martell Pesat"), (None, None))
        self.assertEqual(parse_sex_and_category("Martell Homes Master M65"),
                         ("m", 65))

    def test_heavy_hammer_header_labels(self):
        self.assertEqual(
            heavy_hammer_label_from_header("Martell Pesat Masculí Master M75"),
            "Martell pesat (7.26 Kg)")
        self.assertEqual(
            heavy_hammer_label_from_header("Martell Pesat Homes Master M65"),
            "Martell pesat (9.08 Kg)")
        self.assertEqual(
            heavy_hammer_label_from_header("Martell Pesat VET. Fem. AL 40-44"),
            "Martell pesat (9.08 Kg)")

    def test_header_without_category_or_without_heavy_marker(self):
        # no category: keep today's unweighted output (S4)
        self.assertIsNone(
            heavy_hammer_label_from_header("LLANÇAMENT DE MARTELL PESAT FEMENI"))
        self.assertIsNone(heavy_hammer_label_from_header("Martell Pesat"))
        # plain hammer is not the heavy implement
        self.assertIsNone(
            heavy_hammer_label_from_header("Martell Homes Master M65"))


class TestStoredLabels(unittest.TestCase):
    def test_label_weights(self):
        self.assertEqual(parse_implement_label("Martell (7.260 Kg)"), ("martell", 7.26))
        self.assertEqual(parse_implement_label("Pes (7.260 Kg)"), ("pes", 7.26))
        self.assertEqual(parse_implement_label("Disc (1,750)"), ("disc", 1.75))
        self.assertEqual(parse_implement_label("Disc (1,5 Kg)"), ("disc", 1.5))
        self.assertEqual(parse_implement_label("Javelina (800 g)"), ("javelina", 0.8))
        self.assertEqual(parse_implement_label("Martell pesat (9.08 Kg)"),
                         ("martell_pesat", 9.08))

    def test_unweighted_or_unknown_labels(self):
        self.assertIsNone(parse_implement_label("Martell"))
        self.assertIsNone(parse_implement_label("Llargada"))
        self.assertIsNone(parse_implement_label(""))


if __name__ == "__main__":
    unittest.main()
