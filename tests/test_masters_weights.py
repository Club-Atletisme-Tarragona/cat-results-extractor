"""Unit tests for masters_weights.py (issue #30, spec S1).

The RFEA 2026 table is quoted verbatim in
`odd/tasks/masters-implement-weights.md` (S1). These tests pin every band for
both sexes, the DISCIPLINES.md heavy-hammer spellings, and the header parsing
that lets a category be established without guessing.

Run: python3 -m unittest tests.test_masters_weights -v
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from masters_weights import (  # noqa: E402
    AUTHORITY_NO_SPELLING,
    AUTHORITY_PRINTED,
    AUTHORITY_TABLE,
    AUTHORITY_UNPARSEABLE,
    AUTHORITY_UNRESOLVED,
    IMPLEMENT_WEIGHT_LABELS,
    RFEA_2026_WEIGHTS,
    age_on,
    band_for_age,
    decide_implement_label,
    expected_weight,
    heavy_hammer_label_for,
    heavy_hammer_label_from_header,
    implement_from_text,
    label_for_weight,
    parse_implement_label,
    parse_printed_weight,
    parse_sex_and_category,
    resolve_implement_weight,
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

    def test_uppercase_mas_abbreviation_is_male(self):
        # the sheets' own abbreviation: 'MAS.' / 'MASC.'
        self.assertEqual(parse_sex_and_category("Disc Vet. MAS. 50-54"), ("m", 50))
        self.assertEqual(parse_sex_and_category("Javelina VET. MASC. 60-64"), ("m", 60))
        # ... but the lowercase Catalan word is never read as a sex
        self.assertEqual(parse_sex_and_category("Pes mas 50-54"), (None, 50))

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


class TestDisciplinesVocabulary(unittest.TestCase):
    """S3 — every spelling these helpers can emit is in DISCIPLINES.md."""

    @staticmethod
    def _disciplines_names():
        names = set()
        text = (REPO_ROOT / "DISCIPLINES.md").read_text(encoding="utf-8")
        for line in text.splitlines():
            m = re.match(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|", line)
            if m and m.group(1) != "name":
                names.add(m.group(1))
        return names

    def test_every_label_is_a_disciplines_name(self):
        names = self._disciplines_names()
        self.assertIn("Martell pesat (9.08 Kg)", names)  # sanity: the file parsed
        for implement, labels in IMPLEMENT_WEIGHT_LABELS.items():
            for weight, label in labels.items():
                self.assertIn(label, names, f"{implement} {weight} kg")


class TestPrintedWeight(unittest.TestCase):
    """S8/S10 — read the weight the sheet printed, verbatim, from the header."""

    def test_kilograms(self):
        self.assertEqual(parse_printed_weight("PES Màster F-50 Femení          3 kg"),
                         (3.0, "ok"))
        self.assertEqual(parse_printed_weight("Peso (4kg) Mujeres PC Master F55"),
                         (4.0, "ok"))
        self.assertEqual(parse_printed_weight("Martell pesat (7,26 Kg) M70"),
                         (7.26, "ok"))
        self.assertEqual(parse_printed_weight("Pes MÀSTER M50-M55 (6kg)"),
                         (6.0, "ok"))

    def test_grams(self):
        self.assertEqual(parse_printed_weight("JAVELINA Màster F-50 Femení     500 g"),
                         (0.5, "ok"))
        self.assertEqual(parse_printed_weight("Javelina Júnior 700 g"), (0.7, "ok"))
        self.assertEqual(parse_printed_weight("Disc 800 grs"), (0.8, "ok"))

    def test_thousands_separator_weights(self):
        # '7.260' / '1.750' are the dataset's own spellings for 7.26 / 1.75 kg
        self.assertEqual(parse_printed_weight("Martell (7.260 Kg)"), (7.26, "ok"))
        self.assertEqual(parse_printed_weight("LLANÇAMENT DE DISC (1,750)"),
                         (1.75, "ok"))

    def test_bare_k_is_kilograms_in_a_throw_header(self):
        self.assertEqual(parse_printed_weight("Pes (3k) Fem. PC 50-54"), (3.0, "ok"))

    def test_no_weight_printed(self):
        self.assertEqual(parse_printed_weight("Javelina VET. Fem. 50-54"),
                         (None, "none"))
        self.assertEqual(parse_printed_weight("Martell Homes Master M65"),
                         (None, "none"))
        self.assertEqual(parse_printed_weight("Peso Vet. Hombres. PC MM50"),
                         (None, "none"))
        self.assertEqual(parse_printed_weight(""), (None, "none"))
        # '100 metres' is a distance word (6 letters), never a weight unit
        self.assertEqual(parse_printed_weight("100 metres llisos"), (None, "none"))

    def test_unparseable_unit_is_reported(self):
        self.assertEqual(parse_printed_weight("Pes 16 lb"), (None, "unparseable"))
        self.assertEqual(parse_printed_weight("Javelina 600 onzas"), (None, "unparseable"))

    def test_category_markers_are_not_read_as_units(self):
        # 'SF' is a category marker, not a weight: nothing is printed here
        self.assertEqual(parse_printed_weight("Martillo Pesado Mujeres 35-49 SF"),
                         (None, "none"))
        self.assertEqual(parse_printed_weight("Disc Vet. MAS. 50-54"), (None, "none"))


class TestWeightPrecedence(unittest.TestCase):
    """S8/S9/S10 — the printed result wins; the regulation is the fallback."""

    def test_printed_weight_beats_the_table_when_they_disagree(self):
        # f/50-59 javelina is 500 g in the table; this sheet printed 600 g
        self.assertEqual(expected_weight("f", 50, "javelina"), 0.5)
        self.assertEqual(resolve_implement_weight("javelina", "f", "50-59", 0.6),
                         (0.6, AUTHORITY_PRINTED))
        # f/50-59 pes is 3 kg in the table; this sheet printed 4 kg
        self.assertEqual(expected_weight("f", 50, "pes"), 3.0)
        self.assertEqual(resolve_implement_weight("pes", "f", "50-59", 4.0),
                         (4.0, AUTHORITY_PRINTED))

    def test_printed_weight_is_accepted_as_printed_text(self):
        self.assertEqual(resolve_implement_weight("javelina", "f", "50-59", "500 g"),
                         (0.5, AUTHORITY_PRINTED))
        self.assertEqual(resolve_implement_weight("javelina", "f", "50-59", "600 g"),
                         (0.6, AUTHORITY_PRINTED))

    def test_table_decides_when_no_weight_is_printed(self):
        self.assertEqual(resolve_implement_weight("pes", "m", "60-69", None),
                         (5.0, AUTHORITY_TABLE))
        self.assertEqual(resolve_implement_weight("javelina", "f", "50-59", ""),
                         (0.5, AUTHORITY_TABLE))
        self.assertEqual(resolve_implement_weight("martell_pesat", "m", "50-59", None),
                         (11.34, AUTHORITY_TABLE))

    def test_table_accepts_a_raw_age(self):
        self.assertEqual(resolve_implement_weight("pes", "m", 65, None),
                         (5.0, AUTHORITY_TABLE))

    def test_unresolvable_without_printed_weight_or_category(self):
        self.assertEqual(resolve_implement_weight("pes", None, None, None),
                         (None, AUTHORITY_UNRESOLVED))
        self.assertEqual(resolve_implement_weight("pes", "m", None, None),
                         (None, AUTHORITY_UNRESOLVED))
        self.assertEqual(resolve_implement_weight("pes", "m", "20-29", None),
                         (None, AUTHORITY_UNRESOLVED))
        self.assertEqual(resolve_implement_weight("shot", "m", "60-69", None),
                         (None, AUTHORITY_UNRESOLVED))

    def test_unparseable_printed_weight_is_never_silently_ignored(self):
        # do NOT fall back to the table: an unreadable printed weight is reported
        self.assertEqual(resolve_implement_weight("pes", "m", "60-69", "16 lb"),
                         (None, AUTHORITY_UNPARSEABLE))


class TestLabels(unittest.TestCase):
    """S3 — only DISCIPLINES.md spellings, never an invented one."""

    def test_every_regulation_weight_has_a_disciplines_spelling(self):
        for (sex, band), weights in RFEA_2026_WEIGHTS.items():
            for implement, weight in weights.items():
                label = label_for_weight(implement, weight)
                self.assertIsNotNone(label, (sex, band, implement, weight))
                self.assertEqual(parse_implement_label(label), (implement, weight))

    def test_printed_only_weights_are_spelled(self):
        self.assertEqual(label_for_weight("javelina", 0.5), "Javelina (500 g)")
        self.assertEqual(label_for_weight("pes", 3.0), "Pes (3 Kg)")
        self.assertEqual(label_for_weight("pes", 4.0), "Pes (4 Kg)")
        self.assertEqual(label_for_weight("disc", 1.75), "Disc (1,750)")
        self.assertEqual(label_for_weight("disc", 1.5), "Disc (1,5 Kg)")
        self.assertEqual(label_for_weight("disc", 0.75), "Disc (750 g)")
        self.assertEqual(label_for_weight("martell", 7.26), "Martell (7.260 Kg)")
        self.assertEqual(label_for_weight("martell_pesat", 11.34),
                         "Martell pesat (11.34 Kg)")

    def test_weight_without_a_spelling_is_reported(self):
        # no DISCIPLINES.md spelling exists for a 12 kg shot: never invent one
        self.assertIsNone(label_for_weight("pes", 12.0))
        self.assertIsNone(label_for_weight("pes", None))

    def test_implement_from_header_text(self):
        self.assertEqual(implement_from_text("JAVELINA Màster F-50 Femení 500 g"),
                         "javelina")
        self.assertEqual(implement_from_text("Pes VET. Fem. AL 50-54"), "pes")
        self.assertEqual(implement_from_text("Peso Vet. Hombres. AL"), "pes")
        self.assertEqual(implement_from_text("Disco M55 Vet. MAS."), "disc")
        self.assertEqual(implement_from_text("LLANÇAMENT DE MARTELL MASCULÍ"),
                         "martell")
        self.assertEqual(implement_from_text("Martillo Pesado Hombres 50-59 Master M50"),
                         "martell_pesat")
        self.assertIsNone(implement_from_text("Llargada Dones PC Master F55"))


class TestDecideImplementLabel(unittest.TestCase):
    """S10 — the raw header is the discriminator; the stored label never is."""

    def test_printed_weight_wins_over_the_table(self):
        self.assertEqual(
            decide_implement_label("JAVELINA Màster F-50 Femení                       500 g"),
            ("Javelina (500 g)", AUTHORITY_PRINTED, 0.5))
        self.assertEqual(
            decide_implement_label("PES Màster F-50 Femení                            3 kg"),
            ("Pes (3 Kg)", AUTHORITY_PRINTED, 3.0))

    def test_table_decides_when_the_header_prints_no_weight(self):
        self.assertEqual(decide_implement_label("Javelina VET. Fem. 50-54"),
                         ("Javelina (500 g)", AUTHORITY_TABLE, 0.5))
        self.assertEqual(decide_implement_label("Pes Homes PC Master M65"),
                         ("Pes (5 Kg)", AUTHORITY_TABLE, 5.0))
        self.assertEqual(decide_implement_label("Pes Dones PC Master F55"),
                         ("Pes (3 Kg)", AUTHORITY_TABLE, 3.0))

    def test_category_from_the_header_wins_over_the_dob(self):
        # the header prints M50, so the DOB band must not be consulted
        self.assertEqual(
            decide_implement_label("Pes Masculí Master M50", dob="01/01/1960",
                                   event_date="01/01/2025"),
            ("Pes (6 Kg)", AUTHORITY_TABLE, 6.0))

    def test_dob_is_the_fallback_when_the_header_prints_no_category(self):
        # 'Jabalina Vet. Hombres.' prints sex but no category: the row DOB
        # (1963-01-01, so 52 on 2015-06-07) puts it in m/50-59 -> 700 g
        self.assertEqual(
            decide_implement_label("Jabalina Vet. Hombres.", dob="01/01/1963",
                                   event_date="07/06/2015"),
            ("Javelina (700 g)", AUTHORITY_TABLE, 0.7))

    def test_unresolvable_rows_are_reported_not_guessed(self):
        self.assertEqual(decide_implement_label("Jabalina Vet. Hombres."),
                         (None, AUTHORITY_UNRESOLVED, None))

    def test_unparseable_header_weight_is_reported(self):
        self.assertEqual(decide_implement_label("Pes VET. Fem. 50-54 16 lb"),
                         (None, AUTHORITY_UNPARSEABLE, None))

    def test_non_implement_sections_are_not_touched(self):
        self.assertEqual(decide_implement_label("Llargada Dones PC Master F55"),
                         (None, None, None))

    def test_heavy_hammer_selected_from_the_header(self):
        # 'Martillo Pesado' is the heavy implement, and the table weights it
        self.assertEqual(decide_implement_label("Martillo Pesado Hombres 50-59 Master M50"),
                         ("Martell pesat (11.34 Kg)", AUTHORITY_TABLE, 11.34))
        self.assertEqual(decide_implement_label("Martillo Pesado Hombres 70-79 Master M75"),
                         ("Martell pesat (7.26 Kg)", AUTHORITY_TABLE, 7.26))

    def test_missing_spelling_is_reported(self):
        # 12 kg shot: no DISCIPLINES.md spelling, so the row must be reported
        self.assertEqual(decide_implement_label("Pes Màster M50 12 kg"),
                         (None, AUTHORITY_NO_SPELLING, 12.0))


if __name__ == "__main__":
    unittest.main()
