"""Unit tests for the documented extraction pitfalls (AGENTS.md).

Covers the pure helper functions whose behavior AGENTS.md pins down:
event classification priority, wind applicability, weight-unit
normalization, name-noise stripping, the X'YY"ZZ long-race time format,
header parsing on real PDF texts, and location normalization.

Run: python3 -m unittest tests.test_extract_units -v
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import (  # noqa: E402
    classify_event,
    extract_name_from_line,
    normalize_weight_units,
    parse_header,
    wind_applicable,
)
from scripts.process_2005 import parse_performance  # noqa: E402


class TestClassifyEventPriority(unittest.TestCase):
    """AGENTS.md — Event Classification Priority (first match wins):
    combined > relay > marcha > height > field > jump > track > unknown."""

    def test_combined_beats_everything(self):
        self.assertEqual(classify_event("Pentathlon Mujeres PC"), "combined")
        self.assertEqual(classify_event("Heptathlon Masculino"), "combined")
        self.assertEqual(classify_event("COMBINED_TABLE::Pentathlon"), "combined_table")

    def test_relay(self):
        self.assertEqual(classify_event("4x100m Releus Masculí"), "relay")
        self.assertEqual(classify_event("4x400 m Homes"), "relay")

    def test_marcha(self):
        self.assertEqual(classify_event("3000 metres marxa femenins"), "marcha")
        self.assertEqual(classify_event("5000m Marcha Masc."), "marcha")

    def test_height_before_field(self):
        self.assertEqual(classify_event("Alçada Mujeres"), "height")
        self.assertEqual(classify_event("Salt Alçada"), "height")
        self.assertEqual(classify_event("Salt amb Pértiga"), "height")

    def test_field_before_jump(self):
        self.assertEqual(classify_event("Llançament Disc"), "field")
        self.assertEqual(classify_event("Pes (2 Kg)"), "field")
        self.assertEqual(classify_event("Martell Masculí"), "field")

    def test_jump(self):
        self.assertEqual(classify_event("Llargada Femení"), "jump")
        self.assertEqual(classify_event("Triple Salt"), "jump")

    def test_track_variants(self):
        # abbreviated + full-word + Conersys gender nouns (AGENTS.md)
        self.assertEqual(classify_event("100m Homes"), "track")
        self.assertEqual(classify_event("100 metres llisos masculins"), "track")
        self.assertEqual(classify_event("300 metres tanques masculins"), "track")
        # NOTE: without a gender suffix ('300 metres tanques') classify_event
        # returns 'unknown' today — the metres patterns require a gender noun.
        self.assertEqual(classify_event("3.000m MASCULINO"), "track")
        self.assertEqual(classify_event("60 m Dones"), "track")

    def test_unknown(self):
        self.assertEqual(classify_event(""), "unknown")
        self.assertEqual(classify_event("RANDOM NOISE"), "unknown")


class TestWindApplicable(unittest.TestCase):
    """AGENTS.md — Wind Field: only flat sprints <=200 m, hurdles <=220 m,
    Llargada and Triple Salto carry wind."""

    def test_wind_applicable(self):
        for disc in ("60m", "100 metres llisos", "200m", "150m",
                     "60m tanques", "110m vallas", "220m tanques",
                     "Llargada", "Longitud", "Triple Salto"):
            with self.subTest(disc=disc):
                self.assertTrue(wind_applicable(disc))

    def test_wind_not_applicable(self):
        for disc in ("80m", "300m tanques", "400m", "800m", "1500m",
                     "4x100m", "Marxa", "3000 metres marxa", "Disc",
                     "Pes", "Martell", "Jabalina", "Alçada", "Perxa", ""):
            with self.subTest(disc=disc):
                self.assertFalse(wind_applicable(disc))


class TestNormalizeWeightUnits(unittest.TestCase):
    """kg casing is canonicalized to 'Kg'; grams stay lowercase."""

    def test_kg_normalized(self):
        self.assertEqual(normalize_weight_units("Martell (6kg)"), "Martell (6 Kg)")
        self.assertEqual(normalize_weight_units("Martell (6 Kg)"), "Martell (6 Kg)")
        self.assertEqual(normalize_weight_units("Disch (1KG)"), "Disch (1 Kg)")

    def test_grams_untouched(self):
        self.assertEqual(normalize_weight_units("Disc (800 g)"), "Disc (800 g)")
        self.assertEqual(normalize_weight_units("Jabalina (800g)"), "Jabalina (800g)")


class TestExtractNameFromLine(unittest.TestCase):
    """AGENTS.md — Name Cleaning: strip dates, percentages, truncated times,
    RT/DQ/~, MMT/MMP, trailing numbers."""

    def test_strips_dob(self):
        self.assertEqual(extract_name_from_line("PERE ORTEGA RIDAO 14/05/1985"),
                         "PERE ORTEGA RIDAO")

    def test_strips_percentage(self):
        self.assertEqual(extract_name_from_line("ANTONI CREUS 70,41%"),
                         "ANTONI CREUS")

    def test_strips_truncated_time(self):
        self.assertEqual(extract_name_from_line("MARC LOPEZ 3:07.…"), "MARC LOPEZ")

    def test_strips_rt_dq_tilde(self):
        self.assertEqual(extract_name_from_line("ANNA PUIG RT 12.55"), "ANNA PUIG")
        self.assertEqual(extract_name_from_line("ANNA PUIG DQ"), "ANNA PUIG")
        self.assertEqual(extract_name_from_line("ANNA PUIG ~"), "ANNA PUIG")

    def test_strips_mmt_mmp_and_trailing_digits(self):
        self.assertEqual(extract_name_from_line("JOAN MAS MMT"), "JOAN MAS")
        self.assertEqual(extract_name_from_line("JOAN MAS 7"), "JOAN MAS")

    def test_strips_leading_pos_dorsal(self):
        self.assertEqual(extract_name_from_line("3 49 (t) Pep Aldave Mas"),
                         "Pep Aldave Mas")


class TestParsePerformance2005(unittest.TestCase):
    """AGENTS.md — Long Race Time Format: X'YY"ZZ -> X:YY.ZZ; positions and
    birth years are not marks; special values pass through uppercase."""

    def test_long_race_quote_format(self):
        self.assertEqual(parse_performance("3'53\"86"), ("3:53.86", None))
        self.assertEqual(parse_performance("17'11\"94"), ("17:11.94", None))

    def test_sprint_quote_format(self):
        self.assertEqual(parse_performance('11"26'), ("11.26", None))

    def test_special_values(self):
        self.assertEqual(parse_performance("DNS"), ("DNS", None))
        self.assertEqual(parse_performance("N.P."), ("N.P.", None))

    def test_position_is_not_a_mark(self):
        self.assertEqual(parse_performance("5"), (None, None))

    def test_birth_year_rejected(self):
        marks, _ = parse_performance("1985")
        self.assertNotIn("1985", marks or [])


class TestParseHeaderOnRealPdfs(unittest.TestCase):
    """parse_header against real cached PDF texts (characterization).

    Note: the 2014/2015 season JSONs were produced by the legacy pipeline
    (pre-dating current parse_header); current behavior for those headers
    is pinned here so any change is a conscious decision.
    """

    @staticmethod
    def _text(pdf_rel):
        pdf = REPO_ROOT / pdf_rel
        return subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True, text=True, check=True,
        ).stdout

    def test_jornades_header_2026(self):
        header = parse_header(self._text(
            "tests/fixtures/resultat-20260322-controltorredembarra.pdf"))
        self.assertEqual(header, ("IX Jornades Atlètiques Torredembarra",
                                  "", "Torredembarra", "22/03/2026"))

    def test_legacy_2014_header_unparsed_by_current_code(self):
        header = parse_header(self._text(
            "pdf_cache/2014/resulterritpromovalls50414.pdf"))
        self.assertEqual(header, ("", "", "", ""))


class TestLocationNormalization(unittest.TestCase):
    """AGENTS.md — Location Normalization: Serrahima variants collapse to
    Barcelona-SE; record lines (RCAT/RCAM) are never venue evidence."""

    def test_selftest_passes(self):
        proc = subprocess.run(
            [sys.executable, "location_normalization.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_variants_normalize(self):
        import location_normalization as ln
        for variant in ("Serrahima", "BCN-SE", "Estadi Joan Serrahima",
                        "Estadio Joan Serrahima", "BCN SE"):
            with self.subTest(variant=variant):
                self.assertEqual(ln.normalize_location(variant), "Barcelona-SE")

    def test_record_line_is_not_venue_evidence(self):
        import location_normalization as ln
        text = ("RCAM     8.23   JEREMIAH OBRO IYAMU   CGTT   "
                "Serrahima-BCN   18/06/2022\n")
        self.assertIsNone(ln.classify_pdf_header(text))

    def test_ambiguous_barcelona_not_resolved(self):
        import location_normalization as ln
        self.assertEqual(ln.normalize_location("Barcelona"), "Barcelona")


if __name__ == "__main__":
    unittest.main()
