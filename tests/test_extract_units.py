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
    parse_veterans_clubs,
    parse_veterans_pentatlo,
    parse_duatlo_puntuacio,
    parse_nastic_prova,
    _find_catt_old_format,
    extract_name_from_line,
    is_excluded_athlete,
    split_relay_composition,
    is_team_entity,
    normalize_weight_units,
    masters_discipline_label,
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


class TestMastersImplementWeights(unittest.TestCase):
    """issue #30 / S4, S8-S10 — a masters implement section is emitted with
    the weight the sheet printed; the RFEA 2026 table is only the fallback for
    headers that print no weight. Non-masters sections are untouched."""

    def test_heavy_hammer_with_category_gets_weight(self):
        self.assertEqual(masters_discipline_label("Martell Pesat Masculí Master M75"),
                         "Martell pesat (7.26 Kg)")
        self.assertEqual(masters_discipline_label("Martell Pesat Homes Master M65"),
                         "Martell pesat (9.08 Kg)")
        self.assertEqual(masters_discipline_label("Martell Pesat VET. Fem. AL 40-44"),
                         "Martell pesat (9.08 Kg)")
        self.assertEqual(masters_discipline_label("Martell pesat (7,26 Kg) M70"),
                         "Martell pesat (7.26 Kg)")

    def test_header_without_category_is_unchanged(self):
        self.assertEqual(
            masters_discipline_label("LLANÇAMENT DE MARTELL PESAT FEMENI"),
            "LLANÇAMENT DE MARTELL PESAT FEMENI")
        self.assertEqual(masters_discipline_label("Martell Pesat"), "Martell Pesat")

    def test_plain_masters_implement_gets_the_table_weight(self):
        # table fallback (S9): no weight printed, sex + category are
        self.assertEqual(masters_discipline_label("Martell Homes Master M65"),
                         "Martell (5 Kg)")
        self.assertEqual(masters_discipline_label("Pes Dones PC Master F55"),
                         "Pes (3 Kg)")
        self.assertEqual(masters_discipline_label("Disco M55 Vet. MAS."),
                         "Disc (1,5 Kg)")

    def test_printed_weight_wins_over_the_table(self):
        # S8: this sheet printed 4 kg for a F55 shot, so 4 kg is stored even
        # though the regulation says 3 kg
        self.assertEqual(masters_discipline_label("Peso (4kg) Mujeres PC Master F55"),
                         "Pes (4 Kg)")
        self.assertEqual(masters_discipline_label("JAVELINA Màster F-50 Femení 500 g"),
                         "Javelina (500 g)")
        self.assertEqual(masters_discipline_label("PES Màster F-50 Femení 3 kg"),
                         "Pes (3 Kg)")

    def test_dob_resolves_a_header_without_category(self):
        # S1: category label first, then DOB + event_date
        self.assertEqual(
            masters_discipline_label("Jabalina Vet. Hombres.", dob="01/01/1963",
                                     event_date="07/06/2015"),
            "Javelina (700 g)")
        # no printed category and no DOB: nothing to decide from -> verbatim
        self.assertEqual(masters_discipline_label("Jabalina Vet. Hombres."),
                         "Jabalina Vet. Hombres.")

    def test_non_masters_output_is_unchanged(self):
        self.assertEqual(masters_discipline_label("Martell (6kg)"), "Martell (6 Kg)")
        self.assertEqual(masters_discipline_label("PES Absolut Femení  4 kg"),
                         "PES Absolut Femení  4 kg")
        self.assertEqual(masters_discipline_label("Llargada Dones PC Master F55"),
                         "Llargada Dones PC Master F55")


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

    def test_era_double_apostrophe_and_centisecond_quotes(self):
        # Fail-layout sheets (promovalls50414, trobada Cambrils) print
        # seconds as 10''06 / 10"65 and often a trailing wind/flag 'F'.
        # Without these, _promocio_worth_row_regex skips the row and the
        # era fallback exports an empty JSON (issue #26 fail layouts).
        self.assertEqual(_quote_to_decimal("10''06"), "10.06")
        self.assertEqual(_quote_to_decimal("10''00"), "10.00")
        self.assertEqual(_quote_to_decimal("10''00 F"), "10.00")
        self.assertEqual(_quote_to_decimal("9''64 F"), "9.64")
        self.assertEqual(_quote_to_decimal("11'51"), "11.51")
        self.assertEqual(_quote_to_decimal('10"65'), "10.65")
        self.assertEqual(_quote_to_decimal('9"59'), "9.59")
        # Clubs veterans MARCA column: 01:01,22 / 00:53,61 (MM:SS,cc).
        self.assertEqual(_quote_to_decimal("01:01,22"), "1:01.22")
        self.assertEqual(_quote_to_decimal("00:53,61"), "0:53.61")

    def test_era_quote_rows_with_flag_and_centiseconds(self):
        import textwrap
        text = textwrap.dedent("""
        60 m.ll. Benjamí Masculí
        Lloc Dorsal      Llicència Nom                             Any Club                        Marca
            2         391   CL 71732   Paredes Lario, Ruben           2005   C. A. Tarragona          10''00 F
            5         82    CL 71742   Rozas Bellido, Marc            2005   C. A. Tarragona          11'51
           2        48    EDGAR JOSE DIAZ                     2002   C. A. TARRAGONA       10"65
           1         4    ALMALÉ LERÍN, JAVIER                2000   C. A. TARRAGONA                  7"2
        """)
        rows = parse_promocio_series(text)
        by = {r["atleta_nom"]: r["marca"] for r in rows}
        self.assertEqual(by["Paredes Lario, Ruben"], "10.00")
        self.assertEqual(by["Rozas Bellido, Marc"], "11.51")
        self.assertEqual(by["EDGAR JOSE DIAZ"], "10.65")
        self.assertEqual(by["ALMALÉ LERÍN, JAVIER"], "7.20")

    def test_amposta_cursa_track_rows(self):
        # Amposta CURSA sheets: "CURSA 60 Llisos … 1ª sèrie" + multi-column
        # rows (NOM + COGNOMS split, club, year, TEMPS). Without these the
        # era fallback recovers 0 track rows (issue #26 Amposta family).
        import textwrap
        text = textwrap.dedent("""
               CURSA                           60 Llisos Benjamí masculí                          3ª sèrie

        LLOC   DORSAL              NOM I COGNOMS                                CLUB       ANY    LLICÈNCIA   TEMPS
          1     141     GUILLEM     FERRAN JIMENEZ                         CA TARRAGONA    2008                 9"5
          2     145     LLUC        SUBIROS BRASERO                        CA TARRAGONA    2007                 9"7
          3      40     ARITZ       FERNANDEZ TERRÓN                        UA MONTSIÀ     2007                10"1

               CURSA                          1000 m.ll. Benjamí masculí                    1a sèrie

        LLOC   DORSAL              NOM I COGNOMS                                CLUB       ANY    LLICÈNCIA   TEMPS
          1     145     LLUC       SUBIROS BRASERO                   CA TARRAGONA    2007               3'49"1
        """)
        rows = parse_promocio_series(text)
        by = {(r["atleta_nom"], r["prova"]): r["marca"] for r in rows}
        self.assertEqual(by[("GUILLEM FERRAN JIMENEZ", "60 Llisos Benjamí masculí")], "9.50")
        self.assertEqual(by[("LLUC SUBIROS BRASERO", "60 Llisos Benjamí masculí")], "9.70")
        self.assertEqual(by[("LLUC SUBIROS BRASERO", "1000 m.ll. Benjamí masculí")], "3:49.10")
        # UA Montsià is not CATT
        self.assertFalse(any("FERNANDEZ" in r["atleta_nom"] for r in rows))

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

    def test_veterans_clubs_marxa_header_starts_a_new_section(self):
        # Issue #31: a "5000 MARXA" header must start a new section. When it
        # does not, the race-walk rows inherit the previous section's
        # discipline and a 25:32.97 walk is stored as a 400 m hurdles mark.
        import textwrap
        text = textwrap.dedent("""
        400 METRES TANQUES MASCULÍ
        Sèrie Carrer Dorsal Llicència Nom Data Naix. Club Edat Categ. MARCA Ref. Percent. Posició PUNTS
         1      6      40    CT 9121      PARDINES GRAS, PERE       30/01/1965 CA Tarragona        51    M-50    01:08,80   58,24   84,6512      2        10
        5000 MARXA MASCULÍ
        Ordre Dorsal Llicència Nom Data Naix. Club Edat Categ. MARCA Ref. Percent. Posició PUNTS
          1     40   CT 15201       FLORES MONTES, FERNANDO       17/06/1969 CA Tarragona        47    M-45    25:32,97   1199,99   78,2788      2        10
        """)
        rows = parse_veterans_clubs(text)
        by_name = {r["atleta_nom"].upper(): (r["marca"], r["prova"]) for r in rows}
        self.assertIn("PARDINES GRAS PERE", by_name)
        self.assertIn("TANQUES", by_name["PARDINES GRAS PERE"][1].upper())
        self.assertIn("FLORES MONTES FERNANDO", by_name)
        marca, prova = by_name["FLORES MONTES FERNANDO"]
        self.assertEqual(marca, "25:32.97")
        self.assertIn("MARXA", prova.upper(),
                      f"race-walk row kept the previous section: {prova!r}")
        self.assertNotIn("TANQUES", prova.upper())

    def test_veterans_clubs_stores_marca_not_coef(self):
        # Clubs veterans sheets (2015/2016) print MARCA Ref Percent Pos PUNTS.
        # AGENTS.md: store MARCA only — never Ref/COEF/%. parse_promocio_series
        # skips these rows (anti-hang), so a dedicated path recovers track that
        # the stored JSON lost and drops height ghosts like Ref 2.15 as Alçada
        # (issue #26 fail layouts — veterans family).
        import textwrap
        text = textwrap.dedent("""
        100 METRES LLISOS MASCULÍ
        Sèrie Carrer Dorsal Llicència Nom Data Naix. Club Edat Categ. MARCA Ref. Percent. Posició PUNTS
         1      6      40    CL 22364   ARGILAGA SALVADO, JOSEP RAMON      23/10/1963 CA Tarragona        52     M-50   12,71   11,12   87,4902      3        9
        SALT D'ALÇADA MASCULÍ
         2     40    CL 12544   MARTIN ALVAREZ, JOSE MIGUEL   10/09/1972 CA Tarragona        43    M-40     1,70    2,15    79,0698      4           8
        """)
        self.assertEqual(parse_promocio_series(text), [])
        rows = parse_veterans_clubs(text)
        by_name = {(r["atleta_nom"].upper(), r["marca"], r["prova"]) for r in rows}
        self.assertIn(
            ("ARGILAGA SALVADO JOSEP RAMON", "12.71", "100 METRES LLISOS MASCULÍ"),
            by_name,
        )
        self.assertNotIn(
            ("ARGILAGA SALVADO JOSEP RAMON", "11.12", "100 METRES LLISOS MASCULÍ"),
            by_name,
        )
        martin = [r for r in rows if "MARTIN" in r["atleta_nom"].upper()]
        self.assertEqual([(r["marca"], r["prova"]) for r in martin],
                         [("1.70", "SALT D'ALÇADA MASCULÍ")])

    def test_veterans_clubs_skips_empty_marca_seg_ref(self):
        # When MARCA is blank the sheet leaves a wide gap before Seg/Ref
        # (e.g. "M-45               1180,53"). Capturing that later column
        # stores age-graded seconds as a 3000 m mark (issue #26).
        import textwrap
        text = textwrap.dedent("""
        3000 METRES MASCULÍ
        Sèrie Carrer Dorsal Llicència Nom Data Naix. Club Edat Categ. MARCA Ref. Percent. Posició PUNTS
        12     10    CL 16079       ORTEGA RIDAO, PEDRO         12/10/1977 CA Tarragona        36    M-35    09:36,13   452,26   78,4996      10        3
        12     10    CL 15201     FLORES MONTES, FERNANDO       17/06/1969 CA Tarragona        45    M-45               1180,53
        """)
        rows = parse_veterans_clubs(text)
        marks = [(r["atleta_nom"].upper(), r["marca"]) for r in rows]
        self.assertIn(("ORTEGA RIDAO PEDRO", "9:36.13"), marks)
        self.assertFalse(
            any(m == "1180.53" for _, m in marks),
            f"empty-MARCA Seg/Ref must not become a mark: {marks}",
        )

    def test_veterans_2013_marca_after_club(self):
        # 2013 clubs veterans: "Prova: 100 Mll Masculi" headers and MARCA
        # glued right after the club (no Edat/Categ between). Columns after
        # Marca are Seg / Porcentaje / Base — never store those (issue #26).
        import textwrap
        text = textwrap.dedent("""
        Prova: 100 Mll Masculi
        Pos Serie Dorsal    Licencia APELLIDO           NOMBRE             EDAT   FECHA DE NACIMIENTO       CLUB        Marca      Seg Porcentaje Base Puntos
         9    1     13     CT 17561 FORNIES CAMER       ANTONIO             46        31/12/1966       CA Tarragona 00:13,22      13,22 80,8623% 10,69      4
        Prova: Alçada Masculi
         6    1    13    CT 9121 PARDINES GRAS     PERE         48 30/01/1965  CA Tarragona   1,47
        Prova: Llargada Masculi
         3    1     13    CT 17487       SAEZ PEREZ            LUIS       64    01/03/1949   CA Tarragona                                                        69,3493% 5,84    10
        """)
        self.assertEqual(parse_promocio_series(text), [])
        rows = parse_veterans_clubs(text)
        by_name = {(r["atleta_nom"].upper(), r["marca"], r["prova"]) for r in rows}
        self.assertIn(
            ("FORNIES CAMER ANTONIO", "0:13.22", "100 Mll Masculi"),
            by_name,
        )
        self.assertNotIn(
            ("FORNIES CAMER ANTONIO", "13.22", "100 Mll Masculi"),
            by_name,
        )
        self.assertIn(
            ("PARDINES GRAS PERE", "1.47", "Alçada Masculi"),
            by_name,
        )
        # Blank MARCA + percentage must not become a mark
        saez = [r for r in rows if "SAEZ" in r["atleta_nom"].upper()]
        self.assertEqual(saez, [])

    def test_veterans_pentatlo_summary_marks_not_punts(self):
        # Veterans pentatló multi-column summary: after club, each sub-event
        # prints MARCA then Punts, then Total Punts. Store every sub-mark and
        # the total as "Pentatló"; never intermediate Punts (issue #26).
        import textwrap
        text = textwrap.dedent("""
        RESULTAT DEL CAMPIONAT DE CATALUNYA
        DE PENTATLÓ MASCULINA
        N.ORDEN      N.Llicencia    Cat.             Cognoms            Nom              CLUB                                   Total Punts
                                                                                             Llargada   Punts     Javelina   Punts       200 m.       Punts      Disc      Punts    1.500 m.   Punts
          2          CT‐19378      M‐45 MATEO SANZ             JOSEP MARIA     CA Tarragona              5,00       537     24,73       285       26,89         620       25,33       475   06:09,25      366    2.283
        RESULTATS DEL CAMPIONAT DE CATALUNYA
        DE PENTATLÓ FEMENINA
                                                                                             Tanques    Punts     Alçada     Punts        Pes         Punts     Llargada   Punts    800 m.     Punts
          1       CL‐25649      W‐35   CALATRAVA FERNANDEZ    DOLORES        CA Tarragona            23,65            87       1,18      350       6,32         306        4,19      401   03:10,54      281       1.425
        """)
        self.assertEqual(parse_promocio_series(text), [])
        self.assertEqual(parse_veterans_clubs(text), [])
        rows = parse_veterans_pentatlo(text)
        by = {(r["atleta_nom"].upper(), r["marca"], r["prova"]) for r in rows}
        self.assertIn(("MATEO SANZ JOSEP MARIA", "5.00", "Llargada"), by)
        self.assertIn(("MATEO SANZ JOSEP MARIA", "24.73", "Javelina"), by)
        self.assertIn(("MATEO SANZ JOSEP MARIA", "26.89", "200 metres llisos"), by)
        self.assertIn(("MATEO SANZ JOSEP MARIA", "25.33", "Disc"), by)
        self.assertIn(("MATEO SANZ JOSEP MARIA", "6:09.25", "1500 metres llisos"), by)
        self.assertIn(("MATEO SANZ JOSEP MARIA", "2283", "Pentatló"), by)
        # Intermediate Punts must never become marks
        self.assertFalse(any(r["marca"] in ("537", "285", "620", "475", "366") for r in rows))
        self.assertIn(("CALATRAVA FERNANDEZ DOLORES", "23.65", "Tanques"), by)
        self.assertIn(("CALATRAVA FERNANDEZ DOLORES", "1.18", "Alçada"), by)
        self.assertIn(("CALATRAVA FERNANDEZ DOLORES", "3:10.54", "800 metres llisos"), by)
        self.assertIn(("CALATRAVA FERNANDEZ DOLORES", "1425", "Pentatló"), by)
        self.assertFalse(any(r["marca"] == "1.425" for r in rows))

    def test_old_format_skip_labels_when_lookback_misses(self):
        # When lookback never assigns skip_labels (no useful name line above
        # the CATT anchor), collecting data lines still references it and
        # crashed with UnboundLocalError on clubs140615 (issue #26).
        lines = [
            "   12  40  CA Granollers",
            "   5  19  CA Tarragona  11.59",
            "   RESULTADOS",
            "   11.59",
        ]
        athletes = _find_catt_old_format(lines, 0, len(lines))
        self.assertEqual(len(athletes), 1)
        self.assertEqual(athletes[0]["position"], 5)
        # RESULTADOS is a skip label — not collected as a data line
        data_texts = [t.strip() for _, t in athletes[0]["data_lines"]]
        self.assertNotIn("RESULTADOS", data_texts)
        self.assertIn("11.59", data_texts)

    def test_duatlo_puntuacio_stores_total(self):
        # Duatló de llançaments sheets print attempt tables (already stored)
        # plus a PUNTUACIÓ ranking with the combined total. Store that total
        # as "Duatló"; never treat attempt decimals as the combined mark
        # (issue #26 fail layouts).
        import textwrap
        text = textwrap.dedent("""
        2a Duatló de llançaments
        Vic 28 de març de 2015
        MARTELL CADET-JUVENIL FEMENÍ (3)
        7 MONTSERRAT MONTAÑÉS ARBO   CL 71723       2001    C.A.TARRAGONA              27,94   31,36    X      31,17   31,36
        PUNTUACIÓ FEMENINA CATEGORIA 2
        6    ARIADNA MENOUAR TROTA             CT 23606       1999    LLEIDA U.A.                3138
        7    MONTSERRAT MONTAÑÉS ARBO          CL 71723       2001    C.A.TARRAGONA              3130
        8    JUDIT PALAZUELO ADROVER           CL 69223       2001    C.A.CANALETES              2919
        """)
        self.assertEqual(parse_promocio_series(text), [])
        self.assertEqual(parse_veterans_clubs(text), [])
        self.assertEqual(parse_veterans_pentatlo(text), [])
        rows = parse_duatlo_puntuacio(text)
        by = {(r["atleta_nom"].upper(), r["marca"], r["prova"]) for r in rows}
        self.assertEqual(
            by,
            {("MONTSERRAT MONTAÑÉS ARBO", "3130", "Duatló")},
        )
        # Attempt decimals from the Martell table must not become marks here
        self.assertFalse(any(r["marca"] in ("27.94", "31.36", "31.17") for r in rows))

    def test_nastic_prova_attempts_not_cg(self):
        # Nàstic control sheets use "Prova: MARTELL/PES …" headers and
        # surname-first CATT rows with attempt columns + trailing MARCA.
        # Store every valid attempt; never CG Tarragona; flip "SUR, GIVEN"
        # to given-surname; strip the trailing MARCA column (issue #26).
        import textwrap
        text = textwrap.dedent("""
        Prova:         MARTELL                   CADET JUVENIL FEMENÍ
          1      MONTAÑES ARBO, MONTSERRAT        CA Tarragona   01    CT 24566    38.21    X      39.12   38.83    X       X      39.12
          3      PASCUAL RIVERA, ANDREA           CG Tarragona   02    CL 77200    28.91   34.54   31.97   26.82   29.02    X      34.54
          9      PELICANO SANCHIS, MARINA         CA Tarragona   02    CL 78444    20.78   15.26   17.52     -       -       -     20.78
        Prova: PES           JÚNIOR ABSOLUT MASCULÍ
           1     FERREZ HERNANDEZ, ALVARO JOSE   CA Tarragona    98        CL 22781   9.12    X      X     9.36   9.10   9.18    9.36
           2     GAVALDÀ, POL                    CA Tarragona    98        TRÀMIT     7.14   8.28   8.08   7.97   8.08   7.83    8.28
        Prova: PES           ABSOLUT FEMENÍ ( 4 kg.)
           1     TIBAU SENDRA, MARINA           CA Tarragona    95        CT 20392    10.59   10.92   10.64   10.46   10.87   10.82   10.92
        """)
        self.assertEqual(parse_promocio_series(text), [])
        self.assertEqual(parse_veterans_clubs(text), [])
        rows = parse_nastic_prova(text)
        by = {(r["atleta_nom"].upper(), r["marca"], r["prova"]) for r in rows}
        self.assertIn(("MONTSERRAT MONTAÑES ARBO", "38.21", "Martell (4 Kg)"), by)
        self.assertIn(("MONTSERRAT MONTAÑES ARBO", "39.12", "Martell (4 Kg)"), by)
        self.assertIn(("MONTSERRAT MONTAÑES ARBO", "38.83", "Martell (4 Kg)"), by)
        # Trailing MARCA must not duplicate the best mark as an extra attempt
        mont = [r for r in rows if r["atleta_nom"].upper() == "MONTSERRAT MONTAÑES ARBO"
                and r["prova"].startswith("Martell")]
        self.assertEqual(len(mont), 3)
        # CG Tarragona never stored
        self.assertFalse(any("PASCUAL" in r["atleta_nom"].upper() for r in rows))
        self.assertIn(("MARINA PELICANO SANCHIS", "20.78", "Martell (4 Kg)"), by)
        self.assertIn(("ALVARO JOSE FERREZ HERNANDEZ", "9.36", "Pes (7.260 Kg)"), by)
        self.assertIn(("POL GAVALDÀ", "8.28", "Pes (7.260 Kg)"), by)
        self.assertIn(("MARINA TIBAU SENDRA", "10.92", "Pes (4 Kg)"), by)
        # Invalid attempts excluded
        self.assertFalse(any(r["marca"] in ("X", "-", "Nuls", "NULS") for r in rows))

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

    def test_era_catalan_elision_and_spaced_slash_dates(self):
        # Fail-layout sheets print "Valls, 5 d'abril de 2014" (Catalan
        # elision) and "Cambrils, 24 / 01 / 2015" (spaces around /). Without
        # these, era_year stays 0 and the empty-result fallback never runs
        # (issue #26 fail layouts → extract_fail / empty JSON).
        _, _, loc, data = parse_header(
            "CAMPIONAT TERRITORIAL\nValls, 5 d'abril de 2014\n")
        self.assertEqual(data, "05/04/2014")
        self.assertEqual(loc, "Valls")
        _, _, loc, data = parse_header(
            "CONTROL TERRITORIAL\nCambrils, 24 / 01 / 2015\n")
        self.assertEqual(data, "24/01/2015")
        self.assertEqual(loc, "Cambrils")

    def test_legacy_2014_promovalls_header_date(self):
        header = parse_header(self._text(
            "tests/fixtures/resulterritpromovalls50414.pdf"))
        self.assertEqual(header[3], "05/04/2014")
        self.assertEqual(header[2], "Valls")
        self.assertIn("CAMPIONAT", header[0].upper())

    def test_amposta_date_glued_in_title(self):
        # Amposta CURSA sheets glue a short date into the title line
        # ("… AMPOSTA 5-3-16", "… AMPOSTA 13-02-16"). Without these,
        # era_year stays 0 and the empty-result fallback never runs
        # (issue #26 fail layouts — Amposta family).
        from extract_catt import _header_year
        _, _, loc, data = parse_header(
            "III CONTROL TERRITORIAL - AMPOSTA 5-3-16\n")
        self.assertEqual(data, "05/03/2016")
        self.assertEqual(_header_year(data), 2016)
        self.assertEqual(loc.upper(), "AMPOSTA")
        _, _, loc, data = parse_header(
            "II CONTROL D'HIVERN - AMPOSTA 13-02-16\n")
        self.assertEqual(data, "13/02/2016")
        self.assertEqual(_header_year(data), 2016)
        self.assertEqual(loc.upper(), "AMPOSTA")

    def test_fcat_filename_date_unlocks_headerless_trobada(self):
        # resultrobadacatgui20416.pdf has no competition header — only
        # result tables. parse_header returns empty date → era_year=0 and
        # the empty-result fallback never runs even though parse_promocio
        # finds ~29 CATT rows. Trailing FCAT digits encode the meeting
        # date (20416 → 20/04/2016); prefer DDMyy over DMMYY when both
        # are calendar-valid (issue #26 fail layouts — trobada/catgui).
        from extract_catt import _date_from_fcat_filename, _header_year
        self.assertEqual(
            _date_from_fcat_filename("resultrobadacatgui20416.pdf"),
            "20/04/2016")
        self.assertEqual(
            _header_year(_date_from_fcat_filename("resultrobadacatgui20416")),
            2016)
        self.assertEqual(
            _date_from_fcat_filename("resultrobadatardorcambrils171112.pdf"),
            "17/11/2012")
        self.assertEqual(
            _date_from_fcat_filename("resulcontrolterritamposta50316.pdf"),
            "05/03/2016")


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


class TestCattOldFormatSkipLabels(unittest.TestCase):
    """_find_catt_old_format must not crash when lookback never binds skip_labels."""

    def test_skip_labels_bound_when_lookback_finds_no_name(self):
        # When every lookback line is skipped before skip_labels is assigned
        # (other-club rows / short lines), collecting data lines still needs
        # the label list — previously UnboundLocalError (issue #26 fail46).
        lines = [
            "   12  40  CA Granollers",
            "   5  19  CA Tarragona  11.59",
            "   RESULTADOS",
            "   11.59",
        ]
        athletes = _find_catt_old_format(lines, 0, len(lines))
        self.assertEqual(len(athletes), 1)
        self.assertEqual(athletes[0]["position"], 5)


if __name__ == "__main__":
    unittest.main()
