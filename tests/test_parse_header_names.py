#!/usr/bin/env python3
"""parse_header must return the SHEET'S competition title, verbatim (issue #23).

The second thing `parse_header` reads is the competition name, and it is stored
as `event_name`: it is written into the season JSON and it is venue evidence for
location normalisation, so it cannot be normalised, translated, title-cased or
decorated with the venue.

The old cascade matched keywords ("Campionat", "Jornada", "Control") anywhere in
the first 30 lines, which made it pick section labels of the RFEA/Conersys
sheets ("ACTA DEL CAMPEONATO") and miss every family whose title carries no
keyword ("Criterium Josep Campmany", "Trofeu Nadal", "Gran Premi de Marxa …").
210 season files ended with an empty `event_name` this way.

Behaviour under test (specs S1-S3 of odd/tasks/event-name-backfill.md):
  S1  the value is a header line copied verbatim — no normalisation, no venue.
  S2  only lines of the meeting header block (`_header_block`) are considered.
  S3  stamps (weekday), RCAT/RCAM/Rècord, season-best/MMP, DOB context,
      result-table headers and bare venue/date lines are never the title.

Every header block below is copied VERBATIM from the source PDF named in the
case (pdftotext -layout, leading whitespace preserved) and the expected title is
the line the sheet prints as its competition title.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import parse_header  # noqa: E402


def name(text):
    """The competition name `parse_header` reads out of a header."""
    return parse_header(text)[0]


# --- verbatim header blocks from the pinned PDFs --------------------------

# pdf_cache/2007/resulcampmany13607.pdf
# The title carries no "Campionat"/"Jornada"/"Control" keyword, so the old
# cascade returned nothing for this whole family.
CAMPMANY_2007 = """\
                                               Criterium Josep Campmany
                                 Estadi Joan Serrahima de Barcelona, 13 de juny de 2007



100 METRES LLISOS MASCULINS

Sèrie   Lloc   Carrer   Dorsal   Llicència   Nom i cognoms                 Any     Club                      Marca
"""

# pdf_cache/2017/resultat-20170311-gpmarxasantcugat.pdf
# "ACTA DEL CAMPEONATO" is the sheet's section label; it contains "Campeonato"
# and the old keyword cascade took it as the competition name. It is not.
GP_MARXA_SANT_CUGAT = """\
                          II Gran Premi de Marxa "Ciutat de Sant Cugat"

                           ZEM "LA GUINARDERA" Sant Cugat del Vallés, 11 marzo 2017




                                              ACTA DEL CAMPEONATO
"""

# pdf_cache/2005/resulcllancaments13205.pdf
# "4a. Jornada" is the round number, printed above the competition title.
LLANCAMENTS_2005 = """\
                                                    4a. Jornada
                                       CRITERIUM DE LLANÇAMENTS D'HIVERN
                             Estadi Joan Serrahima de Barcelona, 13 de febrer de 2005




                                     LLANÇAMENT DE MARTELL MASCULÍ
"""

# pdf_cache/2016/resulcontrolvalls60216.pdf
# "GENERAL!A1" is the PDF layout marker emitted above the header.
CONTROL_VALLS = """\
GENERAL!A1
                      CONTROL TERRITORIAL
                            Valls, 6 de febrer de 2016


   60 m.ll. Benjamí Masculí
  1a. Sèrie
   Lloc Dorsal Nom                                    Any Club                    Marca
"""

# pdf_cache/2024/resultat-20241215-trofeunadalcnrp.pdf
# Title, then the organising club, then a bare city, then two date lines.
TROFEU_NADAL_2024 = """\
                                                                         Trofeu Nadal
                                                                         CN Reus Ploms
                                                                             Reus
                                                                              15/12/2024
                               15/12/2024
                                                                 60m Hombres AL SM
                               10:40
                                                                       Final
"""

# pdf_cache/2011/resulmemorialjulioalvarez13711.pdf
# A two-column header: the title and the venue sit on the same physical line, so
# the extracted line mixes them. Writing that line as a name would smuggle the
# venue into `event_name`; the file is unresolvable instead (spec S4).
MEMORIAL_JULIO_ALVAREZ = """\
                                                             4t
                                                                                                                         13 DE JULIOL 2011
                                                         MEMORIAL                                                    ESTADI D'EL CONGOST
                                                       JULIO ALVAREZ                                                             MANRESA



                                              PROVA: MARTELL FEMENÍ                                                           HORA:    16:30
"""

# pdf_cache/2015/resulcontrolasco300515.pdf — the sheet never prints a title.
CLUB_ONLY_2015 = """\
                              CLUB ATLETISME ASCÓ- RIBERA D'EBRE




                                     Ascó, 30 Maig de 2015
"""


class TestVerbatimTitle(unittest.TestCase):
    def test_keywordless_title_is_found(self):
        self.assertEqual(name(CAMPMANY_2007), "Criterium Josep Campmany")

    def test_section_label_is_not_a_title(self):
        self.assertEqual(
            name(GP_MARXA_SANT_CUGAT),
            'II Gran Premi de Marxa "Ciutat de Sant Cugat"')

    def test_round_number_is_not_a_title(self):
        self.assertEqual(
            name(LLANCAMENTS_2005),
            "CRITERIUM DE LLANÇAMENTS D'HIVERN")

    def test_layout_marker_is_not_a_title(self):
        self.assertEqual(name(CONTROL_VALLS), "CONTROL TERRITORIAL")

    def test_title_beats_club_city_and_date_lines(self):
        self.assertEqual(name(TROFEU_NADAL_2024), "Trofeu Nadal")


class TestRejectedCandidates(unittest.TestCase):
    """S3: the lines that look like a title but are not one."""

    def test_generation_stamp(self):
        self.assertEqual(name(
            "miércoles, 29 de abril de 2026\n"
            "Trofeu Promoció 2026 (1ª jornada)\n"), "Trofeu Promoció 2026 (1ª jornada)")

    def test_record_line(self):
        self.assertEqual(name(
            "CAMPIONAT DE CATALUNYA CADET\n"
            "   RCAT     7,17   RAMON MONTEJANO   CATT   Serrahima-BCN   26/02/05\n"),
            "CAMPIONAT DE CATALUNYA CADET")

    def test_season_best_line(self):
        self.assertEqual(name(
            "CAMPIONAT DE CATALUNYA CADET\n"
            "Millor Marca Temporada: 7,25 Sergio Acera, 14/02/08\n"),
            "CAMPIONAT DE CATALUNYA CADET")

    def test_result_table_header(self):
        # The table header closes the header block, so it is never the title,
        # and a block made only of table furniture yields nothing at all.
        self.assertEqual(name(
            "Dorsal   POS   10km Marcha FEM. RUTA    Pais  F.Nac  Licència   Club   Marca\n"),
            "")
        self.assertEqual(name(
            "Trofeu Nadal\n"
            "Dorsal   POS   10km Marcha FEM. RUTA    Pais  F.Nac  Licència   Club   Marca\n"),
            "Trofeu Nadal")

    def test_bare_venue_line(self):
        self.assertEqual(name(
            "Estadi Municipal d'Atletisme de Sant Celoni\n"
            "II CRITERIUM VETERANS BAIX MONTSENY\n"),
            "II CRITERIUM VETERANS BAIX MONTSENY")

    def test_bare_city_and_date_line(self):
        self.assertEqual(name(
            "Cambrils, 09/02/08\n"
            "TERRITORIAL INFANTIL D'HIVERN 07-08\n"),
            "TERRITORIAL INFANTIL D'HIVERN 07-08")

    def test_merged_two_column_header_is_not_a_title(self):
        self.assertEqual(name(MEMORIAL_JULIO_ALVAREZ), "")

    def test_club_line_is_not_a_title(self):
        self.assertEqual(name(CLUB_ONLY_2015), "")

    def test_discipline_header_is_not_a_title(self):
        # A sheet that opens directly on an event has no competition title;
        # inventing one from the event would label a whole file with a discipline.
        self.assertEqual(name("80 m.ll. Infantil Masculí\n1a. Sèrie\n"), "")

    def test_parenthesised_session_label(self):
        self.assertEqual(name(
            "(Jornada de matí)\n"
            "CONTROL TERRITORIAL\n"), "CONTROL TERRITORIAL")


class TestVerbatimNotNormalised(unittest.TestCase):
    """S1: whatever the sheet prints is what gets stored."""

    def test_case_and_accents_are_preserved(self):
        self.assertEqual(
            name("          42è Ct Catalunya Clus de Marxa Masculí, Femení i Mixte\n"),
            "42è Ct Catalunya Clus de Marxa Masculí, Femení i Mixte")

    def test_typo_in_the_sheet_is_preserved(self):
        self.assertEqual(
            name("Camponat Catalunya Clubs Benjamí Masculí\n"),
            "Camponat Catalunya Clubs Benjamí Masculí")

    def test_trailing_round_suffix_is_preserved(self):
        self.assertEqual(
            name("CRITERIUM CAMPMANY (2a. Jornada)\n"),
            "CRITERIUM CAMPMANY (2a. Jornada)")

    def test_surrounding_whitespace_is_not_part_of_the_name(self):
        self.assertEqual(
            name("        TROFEU NEMESI PONSATI (1a. Jornada)        \n"),
            "TROFEU NEMESI PONSATI (1a. Jornada)")


class TestPinnedCasesAgainstCachedPdfs(unittest.TestCase):
    """Corroborate the inline blocks against the cached PDFs when present."""

    def _text(self, rel):
        return subprocess.run(
            ["pdftotext", "-layout", str(REPO_ROOT / rel), "-"],
            capture_output=True, text=True, check=True,
        ).stdout

    def test_cached_pdfs_agree(self):
        cache = [
            ("pdf_cache/2007/resulcampmany13607.pdf", "Criterium Josep Campmany"),
            ("pdf_cache/2017/resultat-20170311-gpmarxasantcugat.pdf",
             'II Gran Premi de Marxa "Ciutat de Sant Cugat"'),
            ("pdf_cache/2005/resulcllancaments13205.pdf",
             "CRITERIUM DE LLANÇAMENTS D'HIVERN"),
            ("pdf_cache/2016/resulcontrolvalls60216.pdf", "CONTROL TERRITORIAL"),
            ("pdf_cache/2024/resultat-20241215-trofeunadalcnrp.pdf", "Trofeu Nadal"),
            ("pdf_cache/2011/resulmemorialjulioalvarez13711.pdf", ""),
            ("pdf_cache/2015/resulcontrolasco300515.pdf", ""),
        ]
        for rel, expected in cache:
            with self.subTest(pdf=rel):
                if not (REPO_ROOT / rel).is_file():
                    self.skipTest(f"{rel} not cached")
                self.assertEqual(name(self._text(rel)), expected)


if __name__ == "__main__":
    unittest.main()
