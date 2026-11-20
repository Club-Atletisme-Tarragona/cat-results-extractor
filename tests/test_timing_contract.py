"""Unit tests for the export contract fields (odd/tasks/timing-short-track.md).

Contract: "is_short_track": true for indoor (pista coberta) competitions and
"timing": "electronic" | "manual" per row, absent -> electronic. The row wins
over the header.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import (  # noqa: E402
    detect_short_track,
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
