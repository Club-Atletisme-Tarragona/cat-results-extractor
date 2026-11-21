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
    _quote_to_decimal,
    parse_promocio_series,
    extract_name_from_line,
    is_excluded_athlete,
    split_relay_composition,
    is_team_entity,
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


class TestPromocioSeriesFormat(unittest.TestCase):
    """The promocio 2013-2016 layout: SÈRIE/LLOC/DORS/LLICENCIA/ATLETA/NAIX/
    ENTITAT/TEMPS with hand-time quote marks (11"6). The current extractor
    reads zero rows from these PDFs (issue #26, resulcontrolcgt240514 /
    resultrofeunastic70315 lost all their sprint series).
    """

    def test_quote_time_to_decimal(self):
        self.assertEqual(_quote_to_decimal('11"6'), "11.60")
        self.assertEqual(_quote_to_decimal('9"8'), "9.80")
        self.assertEqual(_quote_to_decimal("2'03\"1"), "2:03.10")

    def test_row_extraction(self):
        import textwrap
        text = textwrap.dedent("""
        RESULTATS 100 METRES LLISOS CADET - ABSOLUT MASCULÍ
                                                                            V= -0.6
        SÈRIE LLOC DORS LLICENCIA    ATLETA              NAIX CATG        ENTITAT       TEMPS
         1    1 625 CL 22279 Milla Guasch, Adolf                     98     JVM     CA Tarragona           11"6
         1    2 630 CL 69630 Jimenez Ramos, Josep                    99     CM      CA Tarragona           12"2
         1    3 624 CL 22880 Munoz Vazquez, Jesus                    97     JVM     CN Reus Ploms          12"2
        """)
        rows = parse_promocio_series(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["atleta_nom"], "Milla Guasch, Adolf")
        self.assertEqual(rows[0]["marca"], "11.60")
        self.assertEqual(rows[0]["prova"], "100 METRES LLISOS CADET - ABSOLUT MASCULÍ")
        self.assertEqual(rows[0]["vent"], "-0.6")
        self.assertEqual(rows[1]["atleta_licencia"], "CL 69630")

    def test_non_catt_rows_dropped(self):
        # Jimenez Ramos (CN Reus Ploms) must not appear: the dataset is CATT-only
        import textwrap
        text = textwrap.dedent("""
        RESULTATS 100 METRES LLISOS CADET - ABSOLUT MASCULÍ
        SÈRIE LLOC DORS LLICENCIA    ATLETA              NAIX CATG        ENTITAT       TEMPS
         1    2 630 CL 69630 Jimenez Ramos, Josep                    99     CM      CN Reus Ploms          12"2
        """)
        self.assertEqual(parse_promocio_series(text), [])

    def test_cg_tarragona_is_not_catt(self):
        # CG Tarragona shares the city name; AGENTS.md: NEVER include it.
        import textwrap
        text = textwrap.dedent("""
        60 m.ll. Benjamí Masculí
        Lloc  Dorsal Nom                              Any Club                 Temps
            1         386   Carla Rodríguez Martínez      2008   CG Tarragona          10"3
            2         141   Ferran Jimenez, Guillem           2008   CA Tarragona         9"6
        Alçada Infantil Femení
        Lloc Dorsal Nom                         Any Club                    1,05 1,10 1,15 1,20 Marca
         4    248   Gil Nuez, Laia               2004 CG Tarragona          O     XO    XO   XXO XXX                            1,20
        """)
        rows = parse_promocio_series(text)
        names = [r["atleta_nom"] for r in rows]
        self.assertEqual(names, ["Ferran Jimenez, Guillem"])
        self.assertNotIn("Gil Nuez, Laia", names)

    def test_catt_only_at_output_boundary(self):
        import textwrap
        text = textwrap.dedent("""
        RESULTATS 80 METRES LLISOS INFANTIL MASCULÍ
        Sèrie   Lloc Dorsal   Llicència       Atleta                      Naix     Entitat                 Temps
        1         1   112 CL 71714        Lago Garbajosa, Aleix            02    CA Tarragona              11"0
        1         2    14 tramit          Susoko Damba, Ismael             02    CA Torredembarra          11"1
        """)
        rows = parse_promocio_series(text)
        self.assertEqual([r["atleta_nom"] for r in rows], ["Lago Garbajosa, Aleix"])

    def test_comma_decimal_normalized(self):
        # Era sheets print field marks with a comma; merge keys must see dots
        # or the fallback re-adds the same attempt as a phantom (issue #26).
        self.assertEqual(_quote_to_decimal("1,30"), "1.30")
        self.assertEqual(_quote_to_decimal("11,95"), "11.95")
        self.assertEqual(_quote_to_decimal("3,99"), "3.99")

    def test_alcada_marca_only_skips_nuls(self):
        import textwrap
        text = textwrap.dedent("""
        Alçada Infantil Masculí
        Lloc Dorsal Nom                         Any Club                    1,10 1,15 1,20 1,25 1,30 1,33 1,36 1,39 1,42 Marca
          3   114   Pinyol Mateu, Nil           2003 CA Tarragona           O     O     O    XXO O       XXX                    1,30
          5   104   Aixala Guiu, Pol            2004 CA Tarragona           O     XXX                                           1,10
              115   Bartolome Vazquez, Oscar    2004 CA Tarragona           XXX                                                 nuls
        """)
        rows = parse_promocio_series(text)
        by_name = {r["atleta_nom"]: r for r in rows}
        self.assertEqual(by_name["Pinyol Mateu, Nil"]["marca"], "1.30")
        self.assertEqual(by_name["Aixala Guiu, Pol"]["marca"], "1.10")
        self.assertNotIn("Bartolome Vazquez, Oscar", by_name)
        self.assertEqual(len(rows), 2)

    def test_llargada_emits_each_valid_attempt(self):
        import textwrap
        text = textwrap.dedent("""
        Llargada Aleví Masculí
        Lloc Dorsal Nom                             Any Club                      1      2      3     4   5   6   Marca
         3    161   Paredes Lario, Ruben            2005   CA Tarragona          3,99   3,86   3,99                3,99
        19   122   Virgili Garrigos, Oriol         2006   CA Tarragona           X     2,92    X                  2,92
         4    290   Pau Valdepeñas Valderrama       2005   CE Penedès            3,85   3,79   3,88                3,88
        """)
        rows = parse_promocio_series(text)
        paredes = [r["marca"] for r in rows if r["atleta_nom"] == "Paredes Lario, Ruben"]
        virgili = [r["marca"] for r in rows if r["atleta_nom"] == "Virgili Garrigos, Oriol"]
        # unique valid attempts; trailing Marca column is not a second row when
        # it equals an attempt already taken
        self.assertEqual(sorted(paredes), ["3.86", "3.99"])
        self.assertEqual(virgili, ["2.92"])
        self.assertTrue(all(r["prova"] == "Llargada Aleví Masculí" for r in rows))
        self.assertFalse(any("Penedès" in (r["atleta_nom"] + r.get("prova", ""))
                             for r in rows if "Valdepeñas" in r["atleta_nom"]))
        self.assertEqual(len([r for r in rows if "Valdepeñas" in r["atleta_nom"]]), 0)

    def test_pes_and_disc_all_attempts(self):
        import textwrap
        text = textwrap.dedent("""
        Pes Cadet Femení                            3 Kg
        Lloc Dorsal Nom                              Any Club                     1       2      3      4      5      6     Marca
          1   165   Montañes Arbo, Montserrat       2001   CA Tarragona          11,95 11,43 11,22 10,88 11,23 11,13        11,95
        Disc Cadet Femení                           800 gr.
        Lloc Dorsal Nom                              Any Club                  1       2       3       4       5       6      Marca
          1   165   Montañes Arbo, Montserrat       2001   CA Tarragona       22,66   28,46    8,74   28,61   29,71   30,48   30,48
        """)
        rows = parse_promocio_series(text)
        pes = [r["marca"] for r in rows if r["prova"].startswith("Pes")]
        disc = [r["marca"] for r in rows if r["prova"].startswith("Disc")]
        self.assertEqual(pes, ["11.95", "11.43", "11.22", "10.88", "11.23", "11.13"])
        self.assertEqual(disc, ["22.66", "28.46", "8.74", "28.61", "29.71", "30.48"])

    def test_track_ferran_jimenez_still_recovered(self):
        import textwrap
        text = textwrap.dedent("""
        60 m.ll. Benjamí Masculí
        Lloc  Dorsal Nom                              Any Club                 Temps
            1         141   Ferran Jimenez, Guillem           2008   CA Tarragona         9"6
            2         145   Subiros Brasero, Lluc             2007   CA Tarragona         9"8
        """)
        rows = parse_promocio_series(text)
        ferran = [r for r in rows if r["atleta_nom"] == "Ferran Jimenez, Guillem"]
        self.assertEqual(len(ferran), 1)
        self.assertEqual(ferran[0]["marca"], "9.60")
        self.assertTrue(ferran[0]["manual"])

    def test_veterans_multicolumn_does_not_hang(self):
        # Masters sheets print MARCA COEF % PUNTS after the club. Feeding those
        # lines to _PROMOCIO_ROW_RE backtracks for seconds (issue #26 merge hang).
        import textwrap
        import time
        # 60 m (not 100): 6"8 is a real hand time there; under 100 m the
        # mark-floor filter correctly drops it as implausible.
        text = textwrap.dedent("""
        60 m.ll. Màster Masculí
        LLOC CARRER DORSAL LLIC. NOM ANY CLUB MARCA COEF % PUNTS
         1      6      40    CL 22364   ARGILAGA SALVADO, JOSEP RAMON      23/10/1963 CA Tarragona        52     M-50   12,71   11,12   87,4902
         1     52      CL 22783    JAN SANS RIOLA                   1998   C.A. TARRAGONA          6"8       868
        """)
        t0 = time.perf_counter()
        rows = parse_promocio_series(text)
        self.assertLess(time.perf_counter() - t0, 1.0)
        # Masters multi-decimal row is skipped; C.A. + quote time is kept
        self.assertEqual(
            [(r["atleta_nom"], r["marca"]) for r in rows],
            [("JAN SANS RIOLA", "6.80")],
        )

    def test_rejects_height_ghost_under_track(self):
        # Combined-event sheets leak Alçada (1.xx) into a hurdles/track
        # section; those must not become sprint/hurdle marks (issue #26).
        # Columns need 2+ spaces — the row regex requires them.
        import textwrap
        text = textwrap.dedent("""
        60 metres tanques (0.76)
        Lloc Dorsal Nom                              Any Club                 Temps
         1         48 CL-12544 MARIA ALVAREZ AUNOS                    1972   CA Tarragona          1.46
         2         50 CL 25467 ALBERT GENE FERNANDEZ                  1999   CA Tarragona         10"7
        600 m.ll. Aleví Masculí
        Lloc Dorsal Nom                              Any Club                 Temps
         1         12   BONNIN OBACH, DAVID                           2004   CA Tarragona          3.62
         2        141   Ferran Jimenez, Guillem                       2008   CA Tarragona       2'15"9
        LLANÇAMENT DE PES Cadet
        Lloc Dorsal Nom                              Any Club                   Marca
         1         48   JOSE MIGUEL MARTIN                            1972   CA Tarragona          1.59
         2        165   Montanes Arbo, Montserrat                     2001   CA Tarragona         11.95
        """)
        rows = parse_promocio_series(text)
        by = {(r["atleta_nom"], r["marca"]) for r in rows}
        self.assertNotIn(("MARIA ALVAREZ AUNOS", "1.46"), by)
        self.assertNotIn(("BONNIN OBACH, DAVID", "3.62"), by)
        self.assertNotIn(("JOSE MIGUEL MARTIN", "1.59"), by)
        # Legitimate marks kept
        kept = {r["marca"] for r in rows}
        self.assertIn("10.70", kept)   # 10"7 hurdles
        self.assertIn("2:15.90", kept)  # 600m
        self.assertIn("11.95", kept)    # real shot


class TestRelayComposition(unittest.TestCase):
    """A relay team printed as one dash-joined string is several athletes.

    Veterans and old promote sheets list the whole team in the name column.
    Storing that as one athlete is what produced the phantom "PERE PARDINES
    JOSE MARTIN" (a fragment of a 4x100 line) in the 2008 veterans file.
    """

    def test_splits_full_name_composition(self):
        self.assertEqual(
            split_relay_composition(
                "Alex Lopez- Fernando Flores- Pere Pardines- Jose Martin"),
            ["Alex Lopez", "Fernando Flores", "Pere Pardines", "Jose Martin"])

    def test_splits_initials_composition(self):
        self.assertEqual(
            split_relay_composition("V.LOPEZ-J.BLANCO-J.M.MATEO-J.F.GARCIA"),
            ["V.LOPEZ", "J.BLANCO", "J.M.MATEO", "J.F.GARCIA"])

    def test_keeps_two_leg_names_together(self):
        # a hyphen is legitimate in a name; two legs are not a team
        self.assertEqual(split_relay_composition("Carla BORRAS VERGES-TAPIRO"), [])
        self.assertEqual(split_relay_composition("Segolene-josephine Deconinck Urbano"), [])

    def test_keeps_compound_surnames_together(self):
        self.assertEqual(split_relay_composition("Clara ORTIZ DE LANDAZURI ONTOSO"), [])

    def test_plain_name_is_not_a_composition(self):
        self.assertEqual(split_relay_composition("Hugo Jules SAIZ SANTOLARIA"), [])
        self.assertEqual(split_relay_composition(""), [])


class TestExcludedGuestAthletes(unittest.TestCase):
    """Guest athletes in RFEA club competitions are not ours to claim.

    The sheet registers them with CA Tarragona for that meeting only; the
    owner confirmed the result belongs to the athlete and their own club, so
    excluded_athletes.csv removes them from the dataset (see AGENTS.md).
    """

    def test_known_guest_is_excluded(self):
        self.assertTrue(is_excluded_athlete("EDMAR SUBIRÓS ARVEZ"))
        self.assertTrue(is_excluded_athlete("SAID DAMOUH GALLEGO"))

    def test_matching_ignores_order_case_and_accents(self):
        for spelling in ("Subirós Arvez, Edmar", "edmar subiros arvez",
                         "EDMAR  SUBIRÓS   ARVEZ"):
            self.assertTrue(is_excluded_athlete(spelling), spelling)

    def test_club_athletes_are_not_excluded(self):
        # a real member and a same-surname member: only the full guest name matches
        self.assertFalse(is_excluded_athlete("ADRIA SERRES PARDINES"))
        self.assertFalse(is_excluded_athlete("LLUC SUBIROS BRASERO"))

    def test_empty_name_never_matches(self):
        self.assertFalse(is_excluded_athlete(""))
        self.assertFalse(is_excluded_athlete(None))

    def test_team_labels_still_filtered(self):
        self.assertTrue(is_team_entity("CA Tarragona B"))
        self.assertFalse(is_team_entity("EDMAR SUBIRÓS ARVEZ"))


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
            "tests/fixtures/resulterritpromovalls50414.pdf"))
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
