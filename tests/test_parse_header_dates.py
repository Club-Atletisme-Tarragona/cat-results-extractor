#!/usr/bin/env python3
"""parse_header must read the MEETING date, not the first date-like line (issue #32).

`parse_header` finds the meeting date for every extractor, and the season is
derived from it, so a wrong day files a whole competition under the wrong year.
Its `D/M/YY` fallback used to take the first slash date anywhere in the first 30
lines and the 4-digit branch accepted any year 2000-2035, which is how a birth
date, an `RCAT`/`RCAM` record line or a season-best (`MMP`) line beat the header.

Each header block below is copied VERBATIM from the source PDF named in the
case (pdftotext -layout, leading whitespace preserved) and the expected date is
the one already stored in the season JSON, verified against the sheet during
issue #28. The expectation is never adjusted to fit the code.

Industry-relevant behaviour under test (specs S1-S3):
  S1  birth dates, RCAT/RCAM record lines, season-best/MMP lines and Conersys
      generation stamps (weekday present) are never meeting dates.
  S2  the fallbacks only consider the first plausible meeting header block.
  S3  a dotted title date ("17.01.2026 - RESULTADOS") is header evidence and
      wins over a later unrelated date.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract_catt import parse_header  # noqa: E402


# --- verbatim header blocks from the pinned PDFs --------------------------

# seasons/2026/json/resultat-20260117-gpmarxaelvendrell.json
# https://fcatletisme.cat/wp-content/uploads/2026/01/resultat-20260117-gpmarxaelvendrell.pdf
# The title carries the date as 17.01.2026; the first slash date on the page is
# the winner's birth date (25/8/2007) in the results table.
GP_MARXA_VENDRELL = """\
                                     GRAN PREMI DE MARXA DEL VENDRELL
                                          17.01.2026 - RESULTADOS
Dorsal   POS   10km Marcha FEM. RUTA             Pais    F.Nac             Licència                     Club             Marca
   128    1    GINA TORRES AUBERNI               ESP     25/8/2007   CAT-3694533-A-N-s      L'Hospitalet At.           48:00
   130    2    ERIKA LOCKLEY                     GBR    06/12/1992   2750066                                           48:19
   117    3    DANIELA GAITAN PRATS              ESP     14/3/2010   CAT-3701650-A-N-s      CA Igualada                51:14
"""

# seasons/2016/json/resullliguetasub11bcn71115.json
# The header reads "Barcelona (Mar Bella), 7 de novembre de 2015"; the first
# slash date is a birth date in the table ("23/07/09").
LLIGUETA_SUB11 = """\
                    3a. LLIGUETA ATLÈTICA DE BARCELONA SUB-11
                      Barcelona (Mar Bella), 7 de novembre de 2015

                           60 m.ll. PRE-BENJAMI MASCULI

SERIE LLOC MARCA DORSAL         NOM      COGNOMS                 ANY      LLICÈNCIA         CLUB

 1     1   11''4     477    HUGO         FERNÁNDEZ CANO        08-03-2009 0           BARCELONA AT.
 1     2   11''8     633    POL          LOBO BERTRAN           23/07/09 0            SANT JUST
 1     3   12''1    7103    IVÁN         SARDELLLI CALVO       27-09-2009 0            BARCELONA AT.
"""

# seasons/2009/json/resulcatcadetpc2122209.json — the fallback used to take the
# record date "26/02/05" from the "Rècord de Catalunya" line.
CADET_PC_2009 = """\
                                                               14è. CAMPIONAT DE CATALUNYA CADET EN PISTA COBERTA
                                                                            Vilafranca del Penedès, 21 i 22 de febrer de 2009

                                    60 METRES LLISOS CADET MASCULINS
                                                                                                      Passen a la final
Rècord de Catalunya: 7,17 Ramon Montejano, 26/02/05                                                      per llocs (F) 2
Rècord dels Campionats: 7,24 Ramon Montejano 2005                                                       per temps (f) 2
Millor Marca Temporada: 7,25 Sergio Acera, 14/02/08
1a. Semifinal

 LLOC     CARRER      DORSAL       LLIC.    NOM                                    ANY     CLUB                            MARCA
"""

# seasons/2005/json/resulcatabsolut.json — season-best line "08/06/05" used to
# win over the "Manresa, 18 i 19 de juny de 2005" header.
ABSOLUT_2005 = """\
                      CAMPIONAT DE CATALUNYA ABSOLUT A L'AIRE LLIURE
                                                Manresa, 18 i 19 de juny de 2005

                                   100 METRES LLISOS MASCULINS
                                                                                                            Passen a la final
Rècord de Catalunya: 10,28 Jordi Mayoral, 10/07/96                                                             per llocs (F) 2
Rècord dels Campionats: 10,46 José Illan 1999                                                                 per temps (f) 2
Millor Marca Temporada: 10,57 Jordi Mayoral, 08/06/05
1a. Semifinal                                                                                                          Vent:      -2,8
"""

# seasons/2005/json/resulcatjuniorpc.json
JUNIOR_PC_2005 = """\
                        CAMPIONAT DE CATALUNYA JUNIOR EN PISTA COBERTA
                                                 Vilafranca, 26 i 27 de febrer de 2005

                                    60 METRES LLISOS MASCULINS
                                                                                              Passen a la final
Rècord de Catalunya: 6"75 Josep Carbonell, 10/02/76                                              per llocs (F) 3
Rècord dels Campionats: 6"88 José Illan 1996                                                       per temps (f) 2
Millor Marca Temporada: 7"21 Roger Carulla12/02/05
1a. Semifinal
"""

# seasons/2005/json/resulcatjuvenilpc.json
JUVENIL_PC_2005 = """\
                        CAMPIONAT DE CATALUNYA JUVENIL EN PISTA COBERTA
                                                    Vilafranca, 26 i 27 de febrer de 2005

                                    60 METRES LLISOS MASCULINS
                                                                                                  Passen a la final
Rècord de Catalunya: 6,97 Marc Luque 09/03/86                                                        per llocs (F) 3
Rècord dels Campionats: 7,10 Francesc Recasens 1999                                                 per temps (f) 2
Millor marca temporada: 7,10 Marc Altes, 12/02/05
1a. Semifinal
"""

# seasons/2008/json/resulcatcadetpc2324208.json
CADET_PC_2008 = """\
                                           13è. CAMPIONAT DE CATALUNYA
                                              CADET EN PISTA COBERTA
                                       Vilafranca del Penedès, 23 i 24 de febrer de 2008

                               60 METRES LLISOS CADET MASCULINS
                                                                                                 Passen a la final
Rècord de Catalunya: 7,17 Ramon Montejano, 26/02/05                                                 per llocs (F) 2
Rècord dels Campionats: 7,24 Ramon Montejano 2005                                                  per temps (f) 2
Millor Marca Temporada: 7,36 Nelson de la Puente, 20/01/2008
1a. Semifinal

 LLOC     CARRER      DORSAL       LLIC.    NOM                                 ANY CLUB                              MARCA
"""

# seasons/2009/json/resulcatjuvenilpc2122209.json
JUVENIL_PC_2009 = """\
                                                                           24è. Campionat de Catalunya Juvenil en Pista Coberta
                                                                                Vilafranca del Penedès, 21 i 22 de febrer de 2009

                                    60 METRES LLISOS JUVENIL MASCULINS
                                                                                                    Passen a la final
Rècord de Catalunya: 6,97 Marc Luque-Eduard Viles 09/03/86-15/03/08                                    per llocs (F) 2
Rècord dels Campionats: 7,03 Eduard Viles, 2008                                                       per temps (f) 2
Millor Marca Temporada: 7,12 Adria Burriel, 08/02/2009
1a. Semifinal

 LLOC     CARRER      DORSAL        LLIC.     NOM                              ANY      CLUB                             MARCA
"""


PINNED_CASES = [
    ("GP Marxa del Vendrell (2026)", GP_MARXA_VENDRELL, "17/01/2026",
     "seasons/2026/json/resultat-20260117-gpmarxaelvendrell.json"),
    ("Lligueta Sub-11 BCN (2016)", LLIGUETA_SUB11, "07/11/2015",
     "seasons/2016/json/resullliguetasub11bcn71115.json"),
    ("Cadet PC 21-220209", CADET_PC_2009, "22/02/2009",
     "seasons/2009/json/resulcatcadetpc2122209.json"),
    ("Absolut 2005", ABSOLUT_2005, "19/06/2005",
     "seasons/2005/json/resulcatabsolut.json"),
    ("Junior PC 2005", JUNIOR_PC_2005, "27/02/2005",
     "seasons/2005/json/resulcatjuniorpc.json"),
    ("Juvenil PC 2005", JUVENIL_PC_2005, "27/02/2005",
     "seasons/2005/json/resulcatjuvenilpc.json"),
    ("Cadet PC 23-240208", CADET_PC_2008, "24/02/2008",
     "seasons/2008/json/resulcatcadetpc2324208.json"),
    ("Juvenil PC 21-220209", JUVENIL_PC_2009, "22/02/2009",
     "seasons/2009/json/resulcatjuvenilpc2122209.json"),
]


class TestPinnedMeetingDates(unittest.TestCase):
    """The eight pinned cases: stored (verified) date must be what parse_header reads."""

    def test_all_pinned_cases(self):
        for name, text, expected, _ in PINNED_CASES:
            with self.subTest(case=name):
                self.assertEqual(parse_header(text)[3], expected)

    def test_pinned_cases_match_the_stored_json(self):
        # The expectation is the stored value, not a value invented here.
        import json
        for name, _, expected, rel in PINNED_CASES:
            with self.subTest(case=name):
                stored = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))
                self.assertEqual(stored["event_date"], expected)


class TestNonMeetingLinesAreNotDates(unittest.TestCase):
    """S1: non-meeting date lines never become the meeting date."""

    def test_rcat_record_line_is_skipped(self):
        # "Rècord de Catalunya: 10,66 POL RETAMAL ... 01/06/2016"
        header = parse_header(
            "Campionat Catalunya Sub18\n"
            "Barcelona (Estadi Joan Serrahima), 2-3 junio 2018\n"
            "   RCAT       10.66   POL RETAMAL AVILA   SCOZA   Serrahima-BCN   01/06/2016\n"
            "   RCAM       10.99   MARC ALTES                 NRPT    Castellar   29/05/2005\n")
        self.assertEqual(header[3], "03/06/2018")

    def test_season_best_line_is_skipped(self):
        # "Millor Marca Temporada: 7,36 Nelson de la Puente, 20/01/2008"
        header = parse_header(
            "CAMPIONAT DE CATALUNYA CADET EN PISTA COBERTA\n"
            "Vilafranca del Penedès, 23 i 24 de febrer de 2008\n"
            "Millor Marca Temporada: 7,36 Nelson de la Puente, 20/01/2008\n")
        self.assertEqual(header[3], "24/02/2008")

    def test_conersys_generation_stamp_is_skipped(self):
        # The stamp carries a weekday and the print date, not the meeting date.
        header = parse_header(
            "Campionat de Catalunya de 10.000m marxa Màster\n"
            "Estadi Municipal “La Bóbila”\n"
            "Gavà\n"
            "26/04/2026\n"
            "Gestión de Resultados por Conersys Sports Solutions "
            "miércoles, 29 de abril de 2026 12:04:01\n")
        self.assertEqual(header[3], "26/04/2026")

    def test_generation_stamp_alone_yields_no_date(self):
        header = parse_header(
            "CONTROL TERRITORIAL\n"
            "Gestión de Resultados por Conersys Sports Solutions "
            "miércoles, 29 de abril de 2026\n")
        self.assertEqual(header[3], "")

    def test_birth_date_row_is_skipped(self):
        # A results row: licence + birth date, no meeting header above it.
        header = parse_header(
            "GRAN PREMI DE MARXA DEL VENDRELL\n"
            "Dorsal   POS   Pais    F.Nac      Licència      Club        Marca\n"
            "   128    1    ESP     25/8/2007  CAT-3694533-A  L'Hospitalet 48:00\n")
        self.assertEqual(header[3], "")


class TestDottedTitleDate(unittest.TestCase):
    """S3: a dotted title date is header evidence and outranks later dates."""

    def test_dotted_title_date_wins(self):
        header = parse_header(
            "GRAN PREMI DE MARXA DEL VENDRELL\n"
            "17.01.2026 - RESULTADOS\n"
            "Dorsal POS Pais F.Nac Licència Club Marca\n"
            "128 1 ESP 25/8/2007 CAT-3694533-A L'Hospitalet 48:00\n")
        self.assertEqual(header[3], "17/01/2026")

    def test_dotted_title_date_with_city_line(self):
        header = parse_header(
            "CONTROL DE MARXA\n"
            "El Vendrell, 17.01.2026 - RESULTADOS\n")
        self.assertEqual(header[3], "17/01/2026")


class TestHeaderFamiliesStillWork(unittest.TestCase):
    """S5: no regression for the families that already worked."""

    def test_catalan_month_name_with_venue_parentheses(self):
        _, _, loc, date = parse_header(
            "3a. LLIGUETA ATLÈTICA DE BARCELONA SUB-11\n"
            "Barcelona (Mar Bella), 7 de novembre de 2015\n")
        self.assertEqual(date, "07/11/2015")
        self.assertEqual(loc, "Barcelona (Mar Bella)")

    def test_spanish_month_name_span_uses_the_closing_day(self):
        # Era sheets print one range and nothing more precise; the stored
        # convention (verified during #28) is the closing day.
        _, _, loc, date = parse_header(
            "CAMPIONAT DE CATALUNYA CADET EN PISTA COBERTA\n"
            "Vilafranca del Penedès, 21 i 22 de febrer de 2009\n")
        self.assertEqual(date, "22/02/2009")
        self.assertEqual(loc, "Vilafranca del Penedès")

    def test_single_day_header_still_wins(self):
        _, _, loc, date = parse_header(
            "CONTROL TERRITORIAL\nCambrils, 24 / 01 / 2015\n")
        self.assertEqual(date, "24/01/2015")
        self.assertEqual(loc, "Cambrils")

    def test_catalan_elision(self):
        _, _, loc, date = parse_header(
            "CAMPIONAT TERRITORIAL\nValls, 5 d'abril de 2014\n")
        self.assertEqual(date, "05/04/2014")
        self.assertEqual(loc, "Valls")

    def test_date_on_its_own_line(self):
        _, _, _, date = parse_header(
            "Control Velocitat Maig\n"
            "Pista de Atletismo de Camp Clar\n"
            "Tarragona\n"
            "02/05/2026\n")
        self.assertEqual(date, "02/05/2026")

    def test_session_date_line_survives_a_multi_day_header(self):
        # Two-day sheets print a date in the header range AND per-session
        # dates. The dataset files such a meeting under the first session
        # (verified stored values), so the session date must still win over
        # the ambiguous range.
        header = parse_header(
            "Campionat Catalunya Sub18\n"
            "Barcelona (Estadi Joan Serrahima), 2-3 junio 2018\n"
            "   RCAT    10.66   POL RETAMAL AVILA   SCOZA   Serrahima-BCN   01/06/2016\n"
            "   Semifinal 1 02/06/2018      11:25   Viento: -1.1\n")
        self.assertEqual(header[3], "02/06/2018")


class TestPinnedCasesAgainstCachedPdfs(unittest.TestCase):
    """Corroborate the inline blocks against the cached PDFs when present.

    The cache is a local work directory, so these skip on a bare checkout; the
    inline blocks above are the hermetic version of the same assertions.
    """

    def _text(self, rel):
        return subprocess.run(
            ["pdftotext", "-layout", str(REPO_ROOT / rel), "-"],
            capture_output=True, text=True, check=True,
        ).stdout

    def test_cached_pdfs_agree(self):
        cache = [
            ("pdf_cache/2016/resullliguetasub11bcn71115.pdf", "07/11/2015"),
            ("pdf_cache/2009/resulcatcadetpc2122209.pdf", "22/02/2009"),
            ("pdf_cache/2005/resulcatabsolut.pdf", "19/06/2005"),
            ("pdf_cache/2005/resulcatjuniorpc.pdf", "27/02/2005"),
            ("pdf_cache/2005/resulcatjuvenilpc.pdf", "27/02/2005"),
            ("pdf_cache/2008/resulcatcadetpc2324208.pdf", "24/02/2008"),
            ("pdf_cache/2009/resulcatjuvenilpc2122209.pdf", "22/02/2009"),
        ]
        for rel, expected in cache:
            with self.subTest(pdf=rel):
                if not (REPO_ROOT / rel).is_file():
                    self.skipTest(f"{rel} not cached")
                self.assertEqual(parse_header(self._text(rel))[3], expected)


if __name__ == "__main__":
    unittest.main()
