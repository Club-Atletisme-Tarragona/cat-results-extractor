"""Unit tests for the wind audit (scripts/check_wind.py, issue #25).

The audit measures, per stored row, whether the source sheet prints a wind
value for that athlete's mark. These tests pin the decision logic on real
header/line snippets copied out of the PDFs, not on I/O: if a snippet stops
being recognised, the audit's denominator is wrong.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_wind import (  # noqa: E402
    Sheet,
    classify_family,
    decide,
    format_wind,
    is_event_title,
    is_status_mark,
    parse_wind_header,
    wind_tokens,
)


def row(name, discipline, performance, raw=""):
    return {
        "athlete_name": name,
        "discipline": discipline,
        "performance": performance,
        "raw_discipline_name": raw,
    }


INDOOR_HEADER = "Pista coberta de Catalunya"


class TestWindHeader(unittest.TestCase):
    """`Vent:` / `Viento:` headers, with a value, blank, or Nul."""

    def test_era_layout_glued_value(self):
        # 2009-era FCAT series header (resulcampmany10609.pdf)
        h = parse_wind_header(
            "                                                                                      "
            "VENT:+1,1")
        self.assertIsNotNone(h)
        self.assertEqual(h.value, "+1.1")

    def test_2005_space_padded_value(self):
        # 2005-era (resulcatabsolut.pdf): full-width padding after the label
        h = parse_wind_header("1a. Semifinal                       "
                              "                                    Vent:      -5,6")
        self.assertEqual(h.value, "-5.6")

    def test_rfea_final_header(self):
        h = parse_wind_header("                     Final A 27/04/2024       12:00   "
                              "Viento: +2.8")
        self.assertEqual(h.value, "+2.8")

    def test_blank_header_is_present_but_empty(self):
        # Hand-timed promocio finals print the label with no value
        h = parse_wind_header("                     Final A 20/01/2024       9:40    "
                              "Viento:")
        self.assertIsNotNone(h)
        self.assertIsNone(h.value)

    def test_null_forms(self):
        for line in (
            "2a. Semifinal                                    Vent:        Nul",
            "VENT: Nul",
            "Viento: Nulo",
            "Viento: -",
        ):
            h = parse_wind_header(line)
            self.assertIsNotNone(h, line)
            self.assertIsNone(h.value, line)

    def test_nul_on_the_athlete_row(self):
        # resultponsati10705.pdf: the null marker sits on the data row
        h = parse_wind_header(
            " 1     4   CL-15436   BERNAT ROCAMORA CHAPARRO      89   "
            "CA TARRAGONA        23,83   VENT: Nul")
        self.assertIsNone(h.value)
        self.assertIn("VENT: Nul", h.text)

    def test_column_header_is_not_a_header(self):
        # Conersys SUMARIO column caption, no label/value pair
        self.assertIsNone(parse_wind_header(
            "                                   Serie       Calle      Rank"
            "          Resultado Viento"))

    def test_ordinary_line_is_not_a_header(self):
        self.assertIsNone(parse_wind_header("AEA Ventallo"))
        self.assertIsNone(parse_wind_header("  1   5  103  CT-10661  PUIGTIO"))


class TestWindTokens(unittest.TestCase):
    """Signed decimals are wind; unsigned 2-decimal marks are not."""

    def test_jump_wind_line(self):
        toks = wind_tokens(
            "                      AA Catalunya                         "
            "          CT20636    +2.7   +2.0                     +1.4"
            "              +2.7")
        self.assertEqual([t.value for t in toks], ["+2.7", "+2.0", "+1.4", "+2.7"])

    def test_2005_pure_numeric_wind_line(self):
        toks = wind_tokens("       1                                    "
                           "                    +1,2      +1,7   +0,6   +1,0")
        self.assertEqual([t.value for t in toks], ["+1.2", "+1.7", "+0.6", "+1.0"])

    def test_marks_are_not_wind(self):
        self.assertEqual(wind_tokens(
            "  1        372     CT-7728 GENER BOADAS, JOSEP MARIA       80   "
            "PLAYAS CASTELLON                7,17      7,12   7,40"), [])

    def test_per_row_wind_column(self):
        # Conersys: wind is a trailing column on the athlete's row
        toks = wind_tokens(
            "                                     AACB                         "
            "         1          4           1                 13.03      -1.3")
        self.assertEqual([t.value for t in toks], ["-1.3"])

    def test_dob_is_not_wind(self):
        self.assertEqual(wind_tokens("  1    2 Pau Aragones Camacho   09/02/1998"), [])


class TestFamily(unittest.TestCase):
    def test_families(self):
        self.assertEqual(classify_family("60 metres llisos"), "sprint")
        self.assertEqual(classify_family("200 metres llisos"), "sprint")
        self.assertEqual(classify_family("100 metres tanques (0.84)"), "hurdles")
        self.assertEqual(classify_family("110m vallas (1,00) MASC. AL"), "hurdles")
        self.assertEqual(classify_family("Llargada"), "long jump")
        self.assertEqual(classify_family("Longitud S12 MASC. AL"), "long jump")
        self.assertEqual(classify_family("Triple"), "triple")
        self.assertEqual(classify_family("Triple Salt FEM. PC"), "triple")
        self.assertEqual(classify_family("Alçada"), "other")
        self.assertEqual(classify_family(""), "other")

    def test_titles(self):
        self.assertTrue(is_event_title("SALT DE LLARGADA MASCULÍ"))
        self.assertTrue(is_event_title("   Llargada Aleví Masculí"))
        self.assertTrue(is_event_title("60 metres llisos"))
        self.assertFalse(is_event_title(
            "    1    479   Peralta Ruiz, Mubarek           2005   CG Tarragona"
            "           X     4,10   4,16                4,16"))
        self.assertFalse(is_event_title(
            " 1       1       4      212      CT15483 PROS GUASCH, RUBEN"
            "                05/03/1990 MEDILAST LLEIDA                 10,57"))


SERIES_SHEET = """
100 METRES LLISOS MASCULINS

Sèrie   Lloc   Carrer   Dorsal   Llicència   Nom i cognoms       Any     Club       Marca

                                                                        VENT:+1,1

 1       1       4      212      CT15483 PROS GUASCH, RUBEN                05/03/1990 MEDILAST LLEIDA     10,57

 1       2       5      194      CT11051 ALJARILLA FERNANDEZ, ALVARO       02/06/1984 FC BARCELONA        10,78

                       ffffff                                     VENT: Nul

 2       1       4      210      CT13592 BALLESTIN GONZALEZ, CARLOS        17/08/1989 TF CAJACANARIAS     11,05
"""

JUMP_SHEET = """
                                                       SALT DE LLARGADA MASCULÍ
   RCAT                                   6.91   JORDI Y. MATSUOKA

           Pto Dor Nombre                                           F de Nac     1     2        3       4       5       6       Marca
                    Club                                               Lic
              Final 16/06/2013        10:30

            1       2 Pau Aragones Camacho                         09/02/1998   6.22   6.07         X       X   3.64        X     6.22   8
                      AA Catalunya                                   CT20636    +2.7   +2.0                     +1.4              +2.7
            2      97 (t) Newnit Tort Ripoll                       07/10/1998   5.59   5.86    5.81     5.65    5.98    5.87      5.98   7
                      FC Barcelona                                   CL59512    +2.6   +1.5    +0.6     +2.1    +2.6    +1.3      +2.6
"""

JUMP_NO_WIND_SHEET = """
   Llargada Aleví Masculí
   Lloc Dorsal Nom                             Any Club                      1      2      3     4   5   6   Marca
    1    479   Peralta Ruiz, Mubarek           2005   CG Tarragona           X     4,10   4,16                4,16
    3    161   Paredes Lario, Ruben            2005   CA Tarragona          3,99   3,86   3,99                3,99
"""

COMBINED_SHEET = """
                                                       Pentatló Absolut Masculí
           Pto Dor Nombre                                           F de Nac     1     2        3
                    Club                                               Lic
            1       2 Pau Aragones Camacho                         09/02/1998
                      CA Tarragona                                   CT20636
   Llargada
    1    2 Pau Aragones Camacho                         09/02/1998   6.22   6.07         X
"""


class TestTrackDecision(unittest.TestCase):
    """Sprint/hurdle rows take the wind of their own series header."""

    def test_series_with_wind(self):
        sheet = Sheet(SERIES_SHEET)
        d = decide(sheet, row("PROS GUASCH, RUBEN", "100 metres llisos", "10.57"))
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+1.1")
        self.assertIn("VENT:+1,1", d.evidence)

    def test_second_series_resets_to_nul(self):
        sheet = Sheet(SERIES_SHEET)
        d = decide(sheet,
                   row("BALLESTIN GONZALEZ, CARLOS", "100 metres llisos", "11.05"))
        self.assertEqual(d.cls, "pdf-no-wind")
        self.assertIsNone(d.wind)
        self.assertIn("Nul", d.evidence)

    def test_null_wind_is_not_exported_as_zero(self):
        # "VENT: Nul" must never become '+0.0' (process_2005.parse_wind did)
        sheet = Sheet("        VENT: Nul\n   1  212  CT15483 PROS GUASCH, RUBEN  10,57")
        d = decide(sheet, row("PROS GUASCH, RUBEN", "100 metres llisos", "10.57"))
        self.assertIsNone(d.wind)


class TestJumpDecision(unittest.TestCase):
    """Jump rows take the wind printed under their own attempt."""

    def test_attempt_wind_aligned(self):
        sheet = Sheet(JUMP_SHEET)
        d = decide(sheet, row("PAU ARAGONES CAMACHO", "Llargada", "6.22"))
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+2.7")

    def test_other_attempt_of_the_same_athlete(self):
        sheet = Sheet(JUMP_SHEET)
        d = decide(sheet, row("PAU ARAGONES CAMACHO", "Llargada", "3.64"))
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+1.4")

    def test_no_wind_line_in_section(self):
        sheet = Sheet(JUMP_NO_WIND_SHEET)
        d = decide(sheet, row("PAREDES LARIO, RUBEN", "Llargada", "3.99"))
        self.assertEqual(d.cls, "pdf-no-wind")
        self.assertIsNone(d.wind)

    def test_triple_uses_the_same_rule(self):
        sheet = Sheet(JUMP_SHEET)
        d = decide(sheet, row("NEWNIT TORT RIPOLL", "Triple", "5.98"))
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+2.6")


# 2009-era layout (resulcontrolfacvac4709.pdf): the per-attempt winds sit on a
# bare line below the attempts and positive values carry no '+' sign.
UNSIGNED_WIND_SHEET = """
 2     CT-17650 ARIADNA RAMOS GANDIA           1994 CA IGUALADA         X      5,05     X      5,15    4,91    5,09    5,15
                                                                                1.3             0.0     1.0     1.2     0.0
 3     CL-55941 MONTSE GUINOVART PEDESCOLL     1994 CA TARRAGONA        X       X      4,63    4,91    5,05     X      5,05
                                                                                        0.6    -1.7     0.0             0.0
"""


class TestUnsignedWindLine(unittest.TestCase):
    """Positive winds printed without '+' are still winds, one per attempt."""

    def test_each_attempt_gets_its_own_value(self):
        sheet = Sheet(UNSIGNED_WIND_SHEET)
        got = {}
        for mark in ("4.63", "4.91", "5.05"):
            got[mark] = decide(sheet,
                               row("MONTSE GUINOVART PEDESCOLL", "Llargada", mark))
        self.assertEqual(got["4.63"].wind, "+0.6")
        self.assertEqual(got["4.91"].wind, "-1.7")
        self.assertEqual(got["5.05"].wind, "+0.0")
        self.assertTrue(all(d.cls == "pdf-has-wind" for d in got.values()))

    def test_unsigned_two_decimal_marks_are_not_a_wind_line(self):
        from check_wind import wind_line_tokens
        self.assertEqual(wind_line_tokens("     4,63    4,91    5,05    5,05"), [])


# 2025 Conersys layout (resultat-20250608-catmasterllela.pdf): the winds sit on
# the club+licence line, unsigned except the last, with a lone '+' wind for the
# Resultado column on its own line above.
CLUB_LINE_WIND_SHEET = """
                                                      Llargada Masculí Master M75
              Nombre                                              Fecha Nac.
Puesto Dorsal Club                              Club                 Licencia
                                                                                   1         2          3         4       5      6      Resultado

              FRANCISCO GRIÑANT ALMAGRO                            4/8/1947       2.70      2.84       2.94      2.89     2.79   2.74        2.94
  1     184                                    CATT
                                                                                                                                          +0.0
              CA Tarragona                                           CT18394       1.2        1.0       0.0        0.4     2.4   -2.9
"""


class TestClubLineWind(unittest.TestCase):
    """Winds printed on the club+licence line (RFEA layout), unsigned."""

    def _wind(self, perf):
        sheet = Sheet(CLUB_LINE_WIND_SHEET)
        return decide(sheet, row("FRANCISCO GRIÑANT ALMAGRO", "Llargada", perf))

    def test_first_attempt(self):
        d = self._wind("2.70")
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+1.2")

    def test_best_attempt(self):
        d = self._wind("2.94")
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "+0.0")

    def test_negative_last_attempt(self):
        d = self._wind("2.74")
        self.assertEqual(d.cls, "pdf-has-wind")
        self.assertEqual(d.wind, "-2.9")


class TestClassPrecedence(unittest.TestCase):
    def test_no_pdf(self):
        d = decide(None, row("X Y", "Llargada", "5.00"))
        self.assertEqual(d.cls, "no-pdf")

    def test_indoor_beats_no_wind(self):
        sheet = Sheet(INDOOR_HEADER + "\n" + SERIES_SHEET)
        d = decide(sheet, row("BALLESTIN GONZALEZ, CARLOS", "60 metres llisos", "11.05"),
                   indoor=True)
        self.assertEqual(d.cls, "indoor")

    def test_indoor_beats_printed_wind(self):
        # A pista coberta meet does not measure wind, so a VENT column there is
        # the timing template printing its field, not a measurement. Decision
        # taken on the five December Cambrils combined championships: titled
        # DE PISTA COBERTA, every section 60 m / 60 m hurdles, no 100 m, yet
        # each series prints `VENT : -0,9`. Storing it would contradict the
        # indoor contract the same file declares.
        sheet = Sheet(INDOOR_HEADER + "\n" + SERIES_SHEET)
        d = decide(sheet, row("PROS GUASCH, RUBEN", "60 metres llisos", "10.57"),
                   indoor=True)
        self.assertEqual(d.cls, "indoor")
        self.assertIn("printed-wind-not-applicable", d.note)

    def test_combined_event(self):
        sheet = Sheet(COMBINED_SHEET)
        d = decide(sheet, row("PAU ARAGONES CAMACHO", "Llargada", "6.22"))
        self.assertEqual(d.cls, "combined-event")

    def test_unmatched_is_reported_not_guessed(self):
        sheet = Sheet(JUMP_NO_WIND_SHEET)
        d = decide(sheet, row("NOBODY HERE AT ALL", "Llargada", "3.99"))
        self.assertEqual(d.cls, "unmatched")


class TestPerfLookup(unittest.TestCase):
    """Locating a stored mark on the sheet (era hand-time spellings)."""

    def test_hand_time_and_comma_forms(self):
        from check_wind import _perf_in_line
        self.assertTrue(_perf_in_line('1 377 CL 18223 ROBERT ROMANI SUAREZ 1986 '
                                      'C.A. TARRAGONA 7"0 799', '7.00'))
        self.assertTrue(_perf_in_line('  5  12,50  X', '12.50'))
        self.assertTrue(_perf_in_line('  X  11.6-', '11.60'))
        self.assertFalse(_perf_in_line('  5   7.05', '7.00'))

    def test_status_marks_are_not_marks(self):
        from check_wind import is_status_mark
        self.assertTrue(is_status_mark('Ret.'))
        self.assertTrue(is_status_mark('NP'))
        self.assertTrue(is_status_mark('DQ'))
        self.assertFalse(is_status_mark('7.00'))


class TestWindSpelling(unittest.TestCase):
    """The spelling a repair writes: the dataset's, not the sheet's.

    The value always comes from the sheet; only its spelling is normalised, so
    the tests pin the spelling conventions that already exist in
    ``seasons/*/json/`` instead of inventing new ones.
    """

    def test_keeps_a_signed_value(self):
        self.assertEqual(format_wind("+1.2"), "+1.2")
        self.assertEqual(format_wind("-0.8"), "-0.8")

    def test_adds_the_missing_sign(self):
        self.assertEqual(format_wind("1.2"), "+1.2")
        self.assertEqual(format_wind("1,2"), "+1.2")

    def test_zero_follows_the_existing_convention(self):
        # 994 rows already store a zero wind as '+0.0'; a signed zero is the
        # same measurement (0 m/s), so it gets the same spelling.
        self.assertEqual(format_wind("0.0"), "+0.0")
        self.assertEqual(format_wind("+0.0"), "+0.0")
        self.assertEqual(format_wind("-0.0"), "+0.0")
        self.assertEqual(format_wind("- 0,0"), "+0.0")

    def test_one_decimal(self):
        self.assertEqual(format_wind("+0.00"), "+0.0")
        self.assertEqual(format_wind("-1.46"), "-1.5")
        self.assertEqual(format_wind("+2,55"), "+2.6")

    def test_refuses_a_mark_and_a_blank(self):
        # a wind above the measuring range is an attempt, not a wind
        self.assertIsNone(format_wind("12.30"))
        self.assertIsNone(format_wind("+64.96"))
        self.assertIsNone(format_wind(""))
        self.assertIsNone(format_wind(None))
        self.assertIsNone(format_wind("nul"))

    def test_status_mark_has_no_wind_to_attach(self):
        for mark in ("NP", "N.P.", "Ret.", "DQ", "DNS", "DNF", "-"):
            self.assertTrue(is_status_mark(mark), mark)
        for mark in ("7.00", "4,63", "-0.0"):
            self.assertFalse(is_status_mark(mark), mark)


class TestIndoorSignals(unittest.TestCase):
    """S4: what makes a file (or a row) an indoor one."""

    def test_disciplines_indoor_needs_no_aire_lliure_marker(self):
        from check_wind import disciplines_say_indoor
        self.assertTrue(disciplines_say_indoor([
            {"raw_discipline_name": "60m MASC. PC"},
            {"raw_discipline_name": "Llargada Masculí"},
        ]))
        self.assertFalse(disciplines_say_indoor([
            {"raw_discipline_name": "60m S14 Hombres AL"},
            {"raw_discipline_name": "60m S12 Hombres PC"},
        ]))
        self.assertFalse(disciplines_say_indoor([
            {"raw_discipline_name": "Altura Mujeres"},
        ]))

    def test_row_level_pista_coberta(self):
        from check_wind import row_says_indoor
        self.assertTrue(row_says_indoor({"raw_discipline_name": "60m S12 Hombres PC"}))
        self.assertFalse(row_says_indoor({"raw_discipline_name": "60m S14 Hombres AL"}))


class TestSheetAttribution(unittest.TestCase):
    """The context is per line and cannot leak across events or pages."""

    def test_context_resets_on_a_new_event_title(self):
        text = ("                       VENT:+1,1\n"
                "   1  212  CT15483 PROS GUASCH, RUBEN        10,57\n"
                "\n"
                "                        SALT DE LLARGADA MASCULÍ\n"
                "   1  212  CT15483 PROS GUASCH, RUBEN        10,57\n")
        sheet = Sheet(text)
        self.assertEqual(sheet.track_wind_at(1)[0], "+1.1")
        self.assertIsNone(sheet.track_wind_at(4)[0])

    def test_context_resets_on_a_page_break(self):
        text = ("                       VENT:+1,1\n"
                "\x0c\n"
                "   1  212  CT15483 PROS GUASCH, RUBEN        10,57\n")
        sheet = Sheet(text)
        self.assertIsNone(sheet.track_wind_at(2)[0])


if __name__ == "__main__":
    unittest.main()
