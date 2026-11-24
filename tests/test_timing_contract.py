"""Unit tests for the export contract fields (odd/tasks/timing-short-track.md).

Contract: `is_short_track` on every ROW (a property of the mark; the consumer
rejects it at header level) and "timing": "electronic" | "manual" per row,
absent -> electronic. The row wins over the header.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import (  # noqa: E402
    detect_short_track,
    row_short_track,
    timing_from_mark,
)


class TestDetectShortTrack(unittest.TestCase):
    """The competition-level flag, from header text, event name or URL."""

    def test_event_name_catalan_spanish(self):
        self.assertTrue(detect_short_track(
            "Campionat de Catalunya Pista Coberta - Sabadell"))
        self.assertTrue(detect_short_track(
            "Cto. de Catalunya en Pista Cubierta"))

    def test_url_paths(self):
        self.assertTrue(detect_short_track(
            "http://old.fcatletisme.cat/Pcoberta/pcoberta2005/resulcontrolpc15105.pdf"))
        self.assertTrue(detect_short_track(
            "https://www.rfeacontent.es/resultados/2026/short_track/st_x.pdf"))
        self.assertFalse(detect_short_track(
            "https://fcatletisme.cat/wp-content/uploads/2026/07/resultat-20260712-catclubssub20lleida.pdf"))

    def test_filename_pc_tokens(self):
        # 'pc' in the stem is how era files were named (resulcontrolpc15105)
        self.assertTrue(detect_short_track(
            "resulcontrolpc15105.pdf", url=""))
        # but a substring inside a word must not match (e.g. 'spec', 'opc')
        self.assertFalse(detect_short_track("resulspec15105.pdf", url=""))

    def test_outdoor_is_false(self):
        self.assertFalse(detect_short_track(
            "Control Absolut - Estadi Joan Serrahima, Barcelona",
            url="http://old.fcatletisme.cat/Pairelliure/pairelliure2005/x.pdf"))


class TestTimingFromMark(unittest.TestCase):
    """timing per row, from the stored mark. The row wins over the header.

    Manual timekeeping shows as times without centiseconds, and the sheets
    often trail a '-' after the decimal ('7.2-').
    """

    def test_absent_means_electronic(self):
        self.assertEqual(timing_from_mark(""), "electronic")
        self.assertEqual(timing_from_mark(None), "electronic")

    def test_electronic_formats(self):
        for mark in ("7.19", "6.89", "1:55.10", "4:24.01", "0:53:47.50",
                     "2:10,66", "9''74"):
            self.assertEqual(timing_from_mark(mark), "electronic", mark)

    def test_manual_one_decimal(self):
        self.assertEqual(timing_from_mark("7.2"), "manual")
        self.assertEqual(timing_from_mark("7,2"), "manual")
        self.assertEqual(timing_from_mark("1:55.1"), "manual")

    def test_manual_trailing_dash(self):
        self.assertEqual(timing_from_mark("7.2-"), "manual")
        self.assertEqual(timing_from_mark("25.5-"), "manual")

    def test_no_decimal_seconds_is_manual(self):
        # a whole-second time cannot come from an electronic timer
        self.assertEqual(timing_from_mark("7"), "manual")

    def test_era_quote_format_is_manual(self):
        # '11"6' = 11 s 6 tenths: the sprint hand-time of the era sheets
        # (resulcontrolcgt240514.pdf, promocio 2014). One decimal = manual;
        # the long-race X'YY"ZZ form carries centiseconds and stays electronic.
        self.assertEqual(timing_from_mark('11"6'), "manual")
        self.assertEqual(timing_from_mark('12"5-'), "manual")
        self.assertEqual(timing_from_mark('3\u201953"86'), "electronic")
        self.assertEqual(timing_from_mark("3'53\"86"), "electronic")

    def test_field_marks_and_points_are_not_timing(self):
        # lengths, heights and points carry no timing semantics
        for mark in ("5.90", "1.95", "49.51", "3458", "13.26", "X", "DNS", "NP"):
            self.assertEqual(timing_from_mark(mark), "electronic", mark)

    def test_row_wins_over_header(self):
        # contract: 'la fila mana sobre la capçalera' - an electronic-looking
        # header (indoor electronic meet) still yields manual when the row
        # shows a hand time. Covered via the export rule in test_golden.
        pass


if __name__ == "__main__":
    unittest.main()

class TestRowShortTrack(unittest.TestCase):
    """The flag belongs to the mark, so a mixed meet can carry both values.

    A sheet that prints `60m S14 Hombres AL` beside `60m S12 Hombres PC` is not
    indoor: the file-level flag cannot describe both, which is why the export
    contract puts the value on each row.
    """

    def test_section_pc_is_indoor_even_in_an_outdoor_file(self):
        self.assertIs(row_short_track("60m S12 Hombres PC", False), True)

    def test_section_al_is_outdoor_even_in_an_indoor_file(self):
        self.assertIs(row_short_track("60m S14 Hombres AL", True), False)

    def test_aire_lliure_spelled_out(self):
        self.assertIs(row_short_track("Llargada Aire Lliure", True), False)

    def test_no_section_marker_falls_back_to_the_file(self):
        self.assertIs(row_short_track("100 metres llisos", True), True)
        self.assertIs(row_short_track("100 metres llisos", False), False)

    def test_no_substring_false_positive(self):
        # 'AL' inside a word is not the outdoor marker
        self.assertIs(row_short_track("Llançament de javelina", True), True)
