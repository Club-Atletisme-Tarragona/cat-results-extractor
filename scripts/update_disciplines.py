#!/usr/bin/env python3
"""Update `discipline` values in season JSON files to the official DISCIPLINES.md names.

The original raw value is always preserved in a new `raw_discipline_name` field
(inserted right after `discipline`) so doubtful mappings can be manually reviewed.

Mapping engine (for 2005-era data, categories: cadet=Sub16, juvenil=Sub18,
junior=Sub20, promesa=Sub23, absolut=open/senior):

  - Category context is resolved in this order:
      1. explicit suffix in the raw discipline name (CADET/JUVENIL/JUNIOR/PROMESA)
      2. per-file category hint (event_name or FILE_CATEGORY table below)
      3. un-suffixed events in open meets use the absolut spec
         (verified against the source PDFs: separate "JUNIOR" sections exist
          where juniors compete with junior implements)
      4. per-athlete overrides (ABSJUN_OVERRIDES) for mixed absolut+junior meets
         (resolved from the birth-year "ANY" column of the source PDF)

  - Heights/weights follow the FCA "Proves autoritzades" tables
    (https://fcatletisme.cat/wp-content/uploads/provesautoritzadespc2019.pdf
     https://fcatletisme.cat/wp-content/uploads/provesautoritzadesal2019.pdf);
    these specs are stable for the 2005 era.

Usage:
    python3 scripts/update_disciplines.py --season 2005 --dry-run
    python3 scripts/update_disciplines.py --season 2005
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DISCIPLINES_MD = REPO_ROOT / "DISCIPLINES.md"

# ---------------------------------------------------------------------------
# Official discipline names (parsed from DISCIPLINES.md `name` column)
# ---------------------------------------------------------------------------

def load_official_names() -> set:
    names = set()
    for line in DISCIPLINES_MD.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|", line)
        if m and m.group(1) != "name":
            names.add(m.group(1))
    return names

OFFICIAL_NAMES = load_official_names()

# Canonical casing for implement-weight units in official discipline names.
# The disciplines table uses mixed case for kilograms ("Martell (6 Kg)") and
# lowercase for grams ("Disc (800 g)"); raw PDF names vary freely
# ("Martillo (6kg)"), so force kg -> Kg on every mapped name.
def normalize_weight_units(name: str) -> str:
    return re.sub(r"\((\d+(?:[.,]\d+)?)\s*[kK][gG]\)",
                  lambda m: f"({m.group(1)} Kg)", name)

# Approved names not (yet) present in DISCIPLINES.md; the user will add them.
# Juvenil/cadet boys ran 100m hurdles (0.914) in this era before switching to 110mh.
# Note: "Martell (6 kg)" was here when DISCIPLINES.md lacked the row; the official
# "Martell (6 Kg)" (id 176) now covers it, so it must NOT be re-added lowercase.
# The Javelina gram-weight entries were dropped once DISCIPLINES.md carried the
# spaced official names (ids 25/39/91/98/99/164, e.g. "Javelina (500 g)"); the
# unspaced forms must NOT be re-added here.
APPROVED_PENDING = {
    "100 metres tanques (0.91)",   # cadet/juvenil boys 100mh (0.914) in this era
    "60 metres tanques (0.50)",    # aleví (Sub-12) 60mh
    "Pes (2 Kg)",                  # aleví (Sub-12) both genders / infantil (Sub-14) women
    "Disc (600 g)",                # aleví (Sub-12) discus
    "Martell (2 Kg)",              # aleví (Sub-12) hammer
}

# ---------------------------------------------------------------------------
# Category model
# ---------------------------------------------------------------------------

CATEGORY_ORDER = ("cadet", "juvenil", "junior", "promesa", "absolut")

# FCA specs: men's / women's implement weights by category
PES_M = {"cadet": "Pes (4 Kg)", "juvenil": "Pes (5 Kg)", "junior": "Pes (6 Kg)",
         "promesa": "Pes (7.260 Kg)", "absolut": "Pes (7.260 Kg)"}
PES_F = {"cadet": "Pes (3 Kg)", "juvenil": "Pes (3 Kg)", "junior": "Pes (4 Kg)",
         "promesa": "Pes (4 Kg)", "absolut": "Pes (4 Kg)"}
DISC_M = {"cadet": "Disc (1 Kg)", "juvenil": "Disc (1,5 Kg)", "junior": "Disc (1,750)",
          "promesa": "Disc (2 Kg)", "absolut": "Disc (2 Kg)"}
DISC_F = {"cadet": "Disc (800 g)", "juvenil": "Disc (1 Kg)", "junior": "Disc (1 Kg)",
          "promesa": "Disc (1 Kg)", "absolut": "Disc (1 Kg)"}
# Sub-12 (aleví) and Sub-14 (infantil) specs per the FCA artefact tables
PES_M.update({"alevi": "Pes (2 Kg)", "infantil": "Pes (3 Kg)"})
PES_F.update({"alevi": "Pes (2 Kg)", "infantil": "Pes (2 Kg)"})
# Veterans (WMA): M40-49 / W35-49 = senior implements; >=50 per WMA
PES_M.update({"vet50": "Pes (6 Kg)"})
PES_F.update({"vet50": "Pes (3 Kg)"})
DISC_M.update({"vet50": "Disc (1,5 Kg)", "infantil": "Disc (800 g)", "alevi": "Disc (600 g)"})
DISC_F.update({"infantil": "Disc (800 g)", "alevi": "Disc (600 g)"})
DISC_F.update({"vet50": "Disc (1 Kg)"})
MARTELL_M = {"cadet": "Martell (4 Kg)", "juvenil": "Martell (5 Kg)", "junior": "Martell (6 Kg)",
             "promesa": "Martell (7.260 Kg)", "absolut": "Martell (7.260 Kg)"}
MARTELL_F = {"cadet": "Martell (3 Kg)", "juvenil": "Martell (3 Kg)", "junior": "Martell (4 Kg)",
             "promesa": "Martell (4 Kg)", "absolut": "Martell (4 Kg)"}
MARTELL_M.update({"infantil": "Martell (3 Kg)", "alevi": "Martell (2 Kg)"})
MARTELL_F.update({"alevi": "Martell (2 Kg)"})
MARTELL_F.update({"infantil": "Martell (3 Kg)"})
JAVELINA_M = {"cadet": "Javelina (600 g)", "juvenil": "Javelina (700 g)",
              "junior": "Javelina (800 g)", "promesa": "Javelina (800 g)",
              "absolut": "Javelina (800 g)", "infantil": "Javelina (500 g)",
              "alevi": "Javelina (500 g)"}
JAVELINA_F = {"cadet": "Javelina (500 g)", "juvenil": "Javelina (500 g)",
              "junior": "Javelina (600 g)", "promesa": "Javelina (600 g)",
              "absolut": "Javelina (600 g)", "infantil": "Javelina (400 g)",
              "alevi": "Javelina (400 g)"}
JAVELINA_M.update({"vet50": "Javelina (700 g)"})
JAVELINA_F.update({"vet50": "Javelina (500 g)"})

# Hurdle heights by (distance, gender, category) -> official 60/100/110/400 tanques name
def tanques_name(distance: int, gender: str, cat: str) -> str:
    d = int(distance)
    if d == 80:
        # single official row: 80 metres tanques (0.84)
        return "80 metres tanques (0.84)"
    if d == 60:
        if cat == "alevi":
            # Sub-12: 0.50 m (row pending in DISCIPLINES.md)
            return "60 metres tanques (0.50)"
        if cat == "infantil":
            # Sub-14: 0.84 m
            return "60 metres tanques (0.84)"
        if gender == "f":
            # women: cadet/juvenil 0.762 -> (0.76); junior+ 0.84
            return "60 metres tanques (0.76)" if cat in ("cadet", "juvenil") else "60 metres tanques (0.84)"
        # men: cadet/juvenil 0.914 -> (0.91); junior 0.991 -> (0.99); promesa/abs 1.067
        if cat in ("cadet", "juvenil"):
            return "60 metres tanques (0.91)"
        return "60 metres tanques (0.99)" if cat == "junior" else "60 metres tanques (1.067)"
    if d == 100:
        if gender == "f":
            # women: cadet/juvenil 0.762; junior+ 0.84
            return "100 metres tanques (0.762)" if cat in ("cadet", "juvenil") else "100 metres tanques (0.84)"
        # men's 100mh: cadet/juvenil (0.914) or absolut (0.91 per FCA Sub23+)
        return "100 metres tanques (0.91)"
    if d == 110:
        # men only: cadet/juvenil 0.914 -> (0.91); junior 0.991 -> (0.99); promesa/abs 1.067
        if cat in ("cadet", "juvenil"):
            return "110 metres tanques (0.91)"
        return "110 metres tanques (0.99)" if cat == "junior" else "110 metres tanques (1.067)"
    if d == 220:
        # Sub-14 (infantil) 220mh: 0.762
        return "220 metres tanques (0.762)"
    if d == 300:
        # women's 300mh: Sub16 0.762, Sub18+ 0.84 (men run 400mh)
        if gender == "f":
            return "300 metres tanques (0.762)" if cat in ("cadet", "juvenil") else "300 metres tanques (0.84)"
        # men's 300mh: Sub16-Sub18 (0,762/0,84 per FCA)
        return "300 metres tanques (0.762)" if cat in ("cadet", "juvenil") else "300 metres tanques (0.84)"
    if d == 330:
        return "330 metres tanques (S16)"
    if d == 400:
        if gender == "f":
            return "400 metres tanques (0.762)"
        # men: juvenil 0.84; junior/promesa/abs 0.914
        return "400 metres tanques (0.84)" if cat == "juvenil" else "400 metres tanques (0.914)"
    return None

OBSTACLES_NAMES = {"1000": "1000 metres obstacles", "1500": "1500 metres obstacles",
                   "2000": "2000 m obstacles", "3000": "3000 metres obstacles"}

# Per-file category fallback (used when the raw name carries no category suffix).
# "open" means: un-suffixed events use the absolut spec (verified in source PDFs).
FILE_CATEGORY = {
    "resulcatcombicadetpc.json": "cadet",
    "resulcatcombijuvenilpc.json": "juvenil",
    "resulcatcombipromesapc.json": "promesa",
    "resulcatcombinadespc2006.json": "absolut",
    # event_name truncated ('CAMPIONAT DE CATALUNYA'); PDF is the cadet-juvenil
    # combined championship PC
    "resulcatcombicd-jvpc1617208.json": "juvenil",
}

# Per-athlete overrides for the mixed ABSOLUT-JUNIOR PC combined championship
# (resulcatcombiabsjunpc.pdf): implements depend on the athlete's category,
# resolved from the birth-year ("ANY") column of the source PDF:
#   FERRAN TORTOSA PRADILLO (1986) -> junior
#   ADRIA SERRES PARDINES (1983), PERE PARDINES GRAS (1965) -> absolut
ABSJUN_OVERRIDES = {
    ("FERRAN TORTOSA PRADILLO", "60 METRES TANQUES MASCULINS"): "60 metres tanques (0.99)",
    ("FERRAN TORTOSA PRADILLO", "LLANÇAMENT DE PES MASCULÍ"): "Pes (6 Kg)",
    ("ADRIA SERRES PARDINES", "60 METRES TANQUES MASCULINS"): "60 metres tanques (1.067)",
    ("ADRIA SERRES PARDINES", "LLANÇAMENT DE PES MASCULÍ"): "Pes (7.260 Kg)",
    ("PERE PARDINES GRAS", "60 METRES TANQUES MASCULINS"): "60 metres tanques (1.067)",
    ("PERE PARDINES GRAS", "LLANÇAMENT DE PES MASCULÍ"): "Pes (7.260 Kg)",
}

# Per-athlete context for files whose raw names carry neither gender nor category
# (combined-event championships organised in per-category PDF sections; resolved
# from the section each CATT athlete competes in and the birth-year "ANY" column).
# Keys are accent-stripped uppercase substrings of the athlete name.
FILE_ATHLETE_CONTEXT = {
    # Territorial combined championship AL (2006-04): decatlo/hexatlo
    "resultarragona1-2405.json": {
        "MARTIN ALVAREZ": ("m", "absolut"),
        "SERRES PARDINES": ("m", "absolut"),
        "RIOS MESEGUER": ("m", "absolut"),
        "RIOS MESSEGUER": ("m", "absolut"),
        "BENITEZ LAZCANO": ("m", "juvenil"),
        "AGUIRRE": ("m", "juvenil"),
        "MALLA": ("f", "cadet"),
    },
    # Territorial combined championship PC (2005-12): heptatlo/pentatlo/tetratlo
    "resultarragona10111205.json": {
        "MARTIN ALVAREZ": ("m", "absolut"),
        "SERRES PARDINES": ("m", "absolut"),
        "RIOS MESEGUER": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "BENITEZ LAZCANO": ("m", "juvenil"),
        "ORIOL": ("m", "juvenil"),
        "MARCO CAZCARRA": ("m", "juvenil"),
        "SOLE": ("f", "absolut"),
        "MALLA": ("f", "cadet"),
    },
    # Territorial combined championship AL (2006-05): decatlo/hexatlo
    "resulcatcombinades13-14506.json": {
        "RIOS MESEGUER": ("m", "absolut"),
        "RIOS MESSEGUER": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "BENITEZ LAZCANO": ("m", "juvenil"),
        "ORIOL": ("m", "juvenil"),
        "SOLE": ("f", "absolut"),
        "MALLA": ("f", "cadet"),
    },
    # Catalan juvenil championship AL (2006-06): gender varies per section
    "resulcatjuvenil25606.json": {
        "ROCAMORA": ("m", "juvenil"),
        "VERGARA": ("m", "juvenil"),
        "ORIOL": ("m", "juvenil"),
        "BENITEZ LAZCANO": ("m", "juvenil"),
        "MALLA": ("f", "juvenil"),
    },
    # Territorial combined championship PC (2006-12, 'CAMPIONAT TERRITORIAL ... HIVERN'):
    # PDF tables self-label implements (ABSOLUT 7,260 kg / JUNIOR 6 kg); Agusti Oriol
    # (born 89) competes with junior implements, Anna Solé (born 88) is junior women.
    "resulcombihiverntarragona23241206.json": {
        "MARTIN": ("m", "absolut"),
        "SERRES PARDINES": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "ORIOL": ("m", "junior"),
        "SOLE": ("f", "junior"),
        "MALLA": ("f", "juvenil"),
    },
    # Territorial combined championship AL (2007-03): same implement tables
    # (Pes Júnior 6 kg / Disc Júnior 1,750 kg / Javelina Júnior 700 g for Oriol)
    "resulcombireus25307.json": {
        "RIOS MESEGUER": ("m", "absolut"),
        "ORIOL": ("m", "junior"),
        "SOLE": ("f", "absolut"),
        "MALLA": ("f", "juvenil"),
    },
    # Catalan combined championship AL (2007-05): Oriol in DECATLÓ JUNIOR MASCULÍ
    "resulcatcombi6507.json": {
        "ORIOL": ("m", "junior"),
        "MALLA": ("f", "juvenil"),
    },
    # Catalan combined championship PC cadet-juvenil (2007-10): Beatriu = juvenil women
    "resulcatcombinadescadjuvpc2728107.json": {
        "MALLA": ("f", "juvenil"),
    },
    # Catalan combined championship PC (2007-01): Oriol in the JUNIOR section
    "resulcatcombinadespc2021107.json": {
        "ORIOL": ("m", "junior"),
    },
    # Veterans championship AL (2007): veteran specs coincide with standard rows
    # M35≡absolut (1.067 / 0.914 / 800g), M40 110t≡(0.99), M55 javelina≡700g (junior)
    "resulcatveterans16607.json": {
        "IBORRA": ("m", "absolut"),
        "PARDINES GRAS": ("m", "junior"),
        "FLORES": ("m", "absolut"),
        "SERRES CASAMITJANA": ("m", "junior"),
    },
    # Clubs veterans championship (2007-06): VACAS M45 disc 2kg, SERRES M55 javelina 700g
    "resulcatclubsveterans9607.json": {
        "VACAS": ("m", "absolut"),
        "SERRES CASAMITJANA": ("m", "junior"),
    },
    # Territorial combined championship PC (2007-12): Oriol junior implements,
    # Anna Solé absolut women (competing up), Beatriu juvenil women
    "resulcombicambrils231207.json": {
        "MARTIN": ("m", "absolut"),
        "SERRES PARDINES": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "IBORRA": ("m", "absolut"),
        "ORIOL": ("m", "junior"),
        "SOLE": ("f", "absolut"),
        "MALLA": ("f", "juvenil"),
    },
    # Territorial combined championship AL (2008-04): Beatriu absolut women
    # (competing up), Marc Díaz (born 93) juvenil octathlon
    "resulcombicambrils56408.json": {
        "MALLA": ("f", "absolut"),
        "DIAZ": ("m", "juvenil"),
    },
    # Catalan cadet championship (2008)
    "resulcatcadet21608.json": {
        "DIAZ": ("m", "cadet"),
        "TORTAJADA": ("f", "cadet"),
    },
    # Veterans championship AL (2008-06): Flores M35, Iborra M40
    "resulcatveterans15608.json": {
        "FLORES": ("m", "absolut"),
        "IBORRA": ("m", "junior"),
    },
    # Clubs veterans (2008-05): Martin M40 pes 7.260, Vacas M45 disc 2kg, Flores M35
    "resulcatclubsveterans21608.json": {
        "MARTIN": ("m", "absolut"),
        "VACAS": ("m", "absolut"),
        "FLORES": ("m", "absolut"),
    },
    # Master meeting (2008): javelina implement labelled 800g for all in the PDF
    "resulmasterreus3508.json": {
        "PARDINES": ("m", "absolut"),
        "SAEZ": ("m", "absolut"),
    },
    # Veterans combined championship PC (2008-02): Martin M35, Pardines M40
    # (M35 60t 1.067 = absolut spec; M40 60t 0.991 = junior spec)
    "resulcatveteranscombipc2208.json": {
        "MARTIN": ("m", "absolut"),
        "PARDINES GRAS": ("m", "junior"),
    },
    # Territorial combined championship PC (2008-12): absolut men + Oriol/Rocamora
    # junior (6kg), Beatriu in the cadet women's 600m pentathlon (3kg), Díaz juvenil
    "resulcombinadescambrils20211208.json": {
        "MARTIN": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "MELLAKHI": ("m", "absolut"),
        "ROMANI": ("m", "absolut"),
        "ORIOL": ("m", "junior"),
        "ROCAMORA": ("m", "junior"),
        "MALLA": ("f", "cadet"),
        "GUINOVART": ("f", "cadet"),
        "TORRADEM": ("f", "cadet"),
        "DIAZ": ("m", "juvenil"),
    },
    # Catalan juvenil championship (2009-06)
    "resulcatjuvenil14609.json": {
        "DIAZ": ("m", "juvenil"),
        "TORTAJADA": ("f", "juvenil"),
    },
    # Clubs veterans Lleida (2009-06): SERRES M55 javelina 700g;
    # IBORRA M41 / DOMINGO M43 / others M35-M45 = absolut-equivalent implements
    "resulcatclubs7609.json": {
        "IBORRA": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "SAEZ PEREZ": ("m", "absolut"),
        "DOMINGO": ("m", "absolut"),
        "SRRES CASMITJANA": ("m", "vet50"),
    },
    # Veterans meeting (2009-05): Ros M40 disc 2kg
    "resulmeetingcat23509.json": {
        "ROS": ("m", "absolut"),
    },
    # Territorial combined championship PC (2009-12): abs men, Díaz juvenil,
    # Torrademé cadet women
    "resulcombinadescambrils19201209.json": {
        "ROMANI": ("m", "absolut"),
        "TORTOSA": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "DIAZ": ("m", "juvenil"),
        "TORRADEM": ("f", "cadet"),
    },
    # Territorial combined championship AL (2010-04): abs decathlon men,
    # Díaz juvenil, aleví athletes (Sub-12: pes 2kg / 60mh 0.50)
    "resulcombinadescambrils2425410.json": {
        "ORIOL": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "DIAZ": ("m", "juvenil"),
        "LOPEZ URBANO": ("f", "alevi"),
        "VAZQUEZ": ("f", "alevi"),
        "MORENO PACHECHO": ("m", "alevi"),
    },
    # Masters decathlon championship (2011): veterans use senior implements
    "catveteransdecatlo1617411.json": {
        "PARDINES GRAS": ("m", "absolut"),
    },
    # Clubs veterans (2011): Ariza M35 pes 7.260, Vazquez M40 disc 2kg
    "resulcatclubsveterans4611.json": {
        "ARIZA": ("m", "absolut"),
        "VAZQUEZ": ("m", "absolut"),
    },
    # Veterans championship (2011-06): Pinyol W45 pes 4kg
    "resulcatveterans12611.json": {
        "PINYOL": ("f", "absolut"),
    },
    # Veterans meeting (2011-07): Pinyol W45 pes 4kg
    "resulmeetingveteranslloret22511.json": {
        "PINYOL": ("f", "absolut"),
    },
    # Territorial combined championship AL (2011-04): promesa men (abs),
    # Solé promesa women (abs), Gutiérrez juvenil women, López aleví
    "resulcnatterritcombinades1617411.json": {
        "ROMANI": ("m", "absolut"),
        "TORTOSA": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "SOLE": ("f", "absolut"),
        "GUTIERREZ": ("f", "juvenil"),
        "LOPEZ URBANO": ("f", "alevi"),
    },
    # Territorial combined championship PC (2010-12): all-category meet with
    # per-implement tables (ABSOLUT 7,260 / JÚNIOR 6 / JUVENIL 5 / CADET 4)
    "resulterritcombinadescambrils18191210.json": {
        "ROMANI": ("m", "absolut"),
        "TORTOSA": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "ARIZA": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "GARGALLO": ("m", "absolut"),
        "SOLE": ("f", "absolut"),
        "GUTIERREZ": ("f", "juvenil"),
        "TORRADEM": ("f", "cadet"),
        "ALVAREZ": ("f", "cadet"),
        "ESPARZA": ("f", "cadet"),
    },
    # Masters decathlon championship (2012): senior implements
    "resulcatveteranscombinades230612.json": {
        "PARDINES GRAS": ("m", "absolut"),
    },
    # Territorial combined championship AL (2012-04): veterans Pardines/Mateo
    # (110mh 0.991), Romani absolut; women absolut/juvenil per PDF tables,
    # aleví girls (60mh 0.50)
    "resulcnattarragonacombinades310310412.json": {
        "PARDINES GRAS": ("m", "junior"),
        "MATEO SANZ": ("m", "junior"),
        "ROMANI": ("m", "absolut"),
        "SOLE": ("f", "absolut"),
        "ESPARZA": ("f", "juvenil"),
        "ALVAREZ": ("f", "juvenil"),
        "DOMINGO CIURANA": ("f", "alevi"),
        "MASCARELL": ("f", "alevi"),
        "PARDINES VILALTA": ("f", "alevi"),
        "SANCHEZ RUIZ": ("f", "alevi"),
        # aleví/infantil athletes (birth years from the PDF): aleví 60mh 0.50,
        # infantil 60mh 0.84; pes aleví 2kg, infantil boys 3kg / girls 2kg
        "MARIA FALCO": ("f", "alevi"),
        "MONTANES": ("f", "alevi"),
        "CARLA BERENGUEL": ("f", "alevi"),
        "SIRA BO": ("f", "alevi"),
        "MARTA ROS": ("f", "alevi"),
        "LAIA DOMINGO": ("f", "alevi"),
        "MASCARELL": ("f", "alevi"),
        "PARDINES VILALTA": ("f", "alevi"),
        "SANCHEZ RUIZ": ("f", "alevi"),
        "MAR VAZQUEZ": ("f", "alevi"),
        "ALICIA VAZQUEZ": ("f", "infantil"),
        "TARGA": ("f", "infantil"),
        "NEREA LAGO": ("f", "infantil"),
        "PARERA": ("m", "infantil"),
        "TEXIER": ("m", "infantil"),
        "EDGAR JOSE": ("m", "alevi"),
    },
    # Masters decathlon (2013): senior implements
    "resulcatveteranscombinades18190513.json": {
        "FORNIES": ("m", "absolut"),
        "MATEO SANZ": ("m", "absolut"),
    },
    # Masters decathlon AL (2014): senior implements
    "resulcatveteranscombinadesal17180514.json": {
        "MATEO SANZ": ("m", "absolut"),
    },
    # Campionat de Sabadell (2014): senior men
    "resulcnatsabadell121014.json": {
        "SANS RIOLA": ("m", "absolut"),
        "TAMARIT": ("m", "absolut"),
    },
    # Territorial combined AL (2014-03): birth-year categories from the PDF
    # (1999-2000 cadet, 2002 aleví)
    "resulcombinadescambrils29300314.json": {
        "ALONSO DEL CAMPO": ("m", "cadet"),
        "PARERA": ("m", "cadet"),
        "OCHOA": ("m", "cadet"),
        "ALDAVE": ("m", "alevi"),
    },
    # Territorial combined aleví (2014-05)
    "resulcombinadescambrilsalevi180514.json": {
        "NIL PINYOL": ("m", "alevi"),
    },
    # Territorial combined AL (2014-03): pes tables per category (masc: abs
    # 7,260 / juv 5 / cadet 4 / inf 2; fem: abs 4 / juv 3 / cadet 3 / inf 2)
    "resulcombinadescambrils29300314.json": {
        "MATEO SANZ": ("m", "absolut"),
        "JAN SANS": ("m", "juvenil"),
        "ADOLF MILLA": ("m", "juvenil"),
        "ANDREA LOPEZ": ("f", "juvenil"),
        "ALONSO DEL CAMPO": ("m", "cadet"),
        "PARERA": ("m", "cadet"),
        "OCHOA": ("m", "cadet"),
        "ALICIA VAZQUEZ": ("f", "cadet"),
        "MIREIA LOPE": ("f", "cadet"),
        "NEREA LAGO": ("f", "cadet"),
        "ALEIX LAGO": ("m", "infantil"),
        "PEP ALDAVE": ("m", "infantil"),
        "ROVIRA": ("f", "infantil"),
        "SIRA BO": ("f", "infantil"),
        "SANCHEZ RUIZ": ("f", "infantil"),
        "GEMMA PARERA": ("f", "infantil"),
        "FALCÓ": ("f", "infantil"),
        "LAURINE MARIMON": ("f", "alevi"),
        "CLAUDIA MIR": ("f", "alevi"),
        "DE LAS HERAS": ("f", "alevi"),
        "NIL PINYOL": ("m", "alevi"),
        "AIXALA": ("m", "alevi"),
        "BARTOLOME": ("m", "alevi"),
    },
    # Territorial combined PC (2013-12): masc abs 7,260 (Martín/Mateo veterans,
    # Díez 1992, Álvarez 1994 per PDF), juvenil 5kg (Milla/Sans 1998),
    # cadet 4kg (2000-born); fem junior 4kg, cadet 3kg
    "resulcombinadeshiverncambrils21221213.json": {
        "DIEZ SANCHEZ": ("m", "absolut"),
        "ALVAREZ AUNOS": ("m", "absolut"),
        "ROMANI": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "MATEO SANZ": ("m", "absolut"),
        "ADOLF MILLA": ("m", "juvenil"),
        "JAN SANS": ("m", "juvenil"),
        "PARERA": ("m", "cadet"),
        "JOSEP MILLA": ("m", "cadet"),
        "OCHOA": ("m", "cadet"),
        "GUTIERREZ": ("f", "junior"),
        "TORRADEM": ("f", "junior"),
        "TIBAU": ("f", "junior"),
        "TORTAJADA": ("f", "junior"),
        "ALICIA VAZQUEZ": ("f", "cadet"),
        "MIREIA LOPE": ("f", "cadet"),
        "NEREA LAGO": ("f", "cadet"),
        "PEP ALDAVE": ("m", "infantil"),
        "EDGAR JOSE": ("m", "infantil"),
        "GRAN BADIA": ("m", "infantil"),
        "BONDIA": ("m", "infantil"),
        "MARIO SANCHEZ": ("m", "infantil"),
        "MAR VAZQUEZ": ("f", "infantil"),
        "FALCO": ("f", "infantil"),
        "INES DELGADO": ("f", "infantil"),
        "GEMMA PARERA": ("f", "infantil"),
        "MASCARELL": ("f", "infantil"),
        "BERTA PARDINES": ("f", "infantil"),
    },
        "AINA TOMÀS": ("f", "infantil"),
        "ALBA TORRES": ("f", "infantil"),
        "BERTA POMES": ("f", "infantil"),
        "CLÀUDIA BARBENS": ("f", "infantil"),
        "CRISTINA REYES": ("f", "infantil"),
        "EGOITZ PEDROL": ("m", "infantil"),
        "ERIKA DÍEZ": ("f", "infantil"),
        "GERARD FERRÁNDIZ": ("m", "infantil"),
        "ISAAC GUZMAN": ("m", "infantil"),
        "JANA TORRES": ("f", "infantil"),
        "JULIA SUAREZ": ("f", "infantil"),
        "LAIA ALDAVE": ("f", "infantil"),
        "LARA HERRERA": ("f", "infantil"),
        "LAURA SANTOS": ("f", "infantil"),
        "MARTINA POMES": ("f", "infantil"),
        "NATALIA SÁNCHEZ": ("f", "infantil"),
        "OLIVIA NOLLA": ("f", "infantil"),
        "POL MASCARELL": ("m", "infantil"),
        "RUBÉN PAREDES": ("m", "infantil"),
        "DE LAS HERAS": ("f", "infantil"),
    # Control (2013-06): Montañes juvenil disc 1kg
    "resulcontrolvic130613.json": {
        "MONTANES": ("f", "juvenil"),
    },
    # Combined promoció (2013-05): Adolf cadet decathlon, Alicia cadet hexathlon
    "resulcatcombinadespromocio25260513.json": {
        "ADOLF MILLA": ("m", "cadet"),
        "ALICIA VAZQUEZ": ("f", "cadet"),
    },
    # 2015 combined championships (broad contexts; marks are 60/100mh times)
    "resulcnatterritcombinadespalafrugell9100515.json": {
        "MIREIA LOPE": ("f", "cadet"),
        "MIREIA LÓPEZ": ("f", "cadet"),
    },
    "resulcatcombinades30310515.json": {
        "HELENA": ("f", "absolut"),
        "ALICIA VAZQUEZ": ("f", "juvenil"),
        "MIREIA LOPE": ("f", "cadet"),
        "MIREIA LÓPEZ": ("f", "cadet"),
        "MARIMON": ("f", "alevi"),
        "LIANA": ("f", "alevi"),
        "MARTINA POMES": ("f", "alevi"),
        "GERARD PARERA": ("m", "cadet"),
        "JAVIER ALMALE": ("m", "cadet"),
    },
    "resulcatcombinadescadetpc780315.json": {
        "MIREIA LOPE": ("f", "cadet"),
        "MIREIA LÓPEZ": ("f", "cadet"),
    },
    # Territorial combined PC (2014-12): birth-year bands 2014-15
    "resulcombinadescambrils20121214.json": {
        "MATEO SANZ": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "ROMANI": ("m", "absolut"),
        "DIEZ": ("m", "absolut"),
        "RIOS": ("m", "junior"),
        "HELENA": ("f", "junior"),
        "SANS": ("m", "juvenil"),
        "ALICIA VAZQUEZ": ("f", "juvenil"),
        "MILLA": ("m", "cadet"),
        "PARERA": ("m", "cadet"),
        "MIREIA LOPE": ("f", "cadet"),
        "NEREA LAGO": ("f", "cadet"),
        "BUSCAIL": ("f", "cadet"),
        "LIAN SOLÉ": ("f", "cadet"),
        "SILVIA": ("f", "cadet"),
        "MARIO SANCHEZ": ("m", "infantil"),
        "GRAN BADIA": ("m", "infantil"),
        "EDGAR JOSE": ("m", "infantil"),
        "BERTA": ("f", "infantil"),
        "GEMMA PARERA": ("f", "infantil"),
        "FALCÓ": ("f", "infantil"),
        "MAR VÁZQUEZ": ("f", "infantil"),
        "MAR V": ("f", "infantil"),
        "BERENGUEL": ("f", "infantil"),
        "HUGO BERENGUEL": ("m", "infantil"),
        "NIL PINYOL": ("m", "infantil"),
        "PEP ALDAVE": ("m", "infantil"),
        "SIRA BO": ("f", "infantil"),
        "JOSEP MILLA": ("m", "cadet"),
        "JAVIER ALMALE": ("m", "cadet"),
        "SERGI RALITA": ("m", "cadet"),
        "ALIX": ("m", "infantil"),
        "ROBERT ROMANI": ("m", "absolut"),
        "ALVARO DÍEZ": ("m", "absolut"),
        "ALVARO DIEZ": ("m", "absolut"),
        "GERARD PARERA": ("m", "cadet"),
        "MIREIA LÓPEZ": ("f", "cadet"),
        "HELENA RÍOS": ("f", "junior"),
        "ALICIA VAZQUEZ DOMINGO": ("f", "juvenil"),
        "MARIA BUSCAIL": ("f", "cadet"),
        "MARIA LIAN": ("f", "cadet"),
        "BERNAT VERDÚ": ("m", "infantil"),
        "ALEXANDRE GRAN": ("m", "infantil"),
        "MARIA FALCÓ": ("f", "infantil"),
        "BERTA SÁNCHEZ": ("f", "infantil"),
        "GEMMA PARERA BODI": ("f", "infantil"),
        "CARLA BERENGUEL": ("f", "infantil"),
        "MAR VÁZQUEZ DOMINGO": ("f", "infantil"),
        "INES DELGADO": ("f", "infantil"),
    },
    # Territorial combined PC (2015-12): masc cadet 4kg, fem 3kg group
    "resulcontrolcombinadescambrils19201215.json": {
        "MATEO SANZ": ("m", "vet50"),
        "PARDINES GRAS": ("m", "absolut"),
        "ROMANI": ("m", "absolut"),
        "VERDÚ": ("m", "cadet"),
        "EDGAR JOSÉ": ("m", "cadet"),
        "GERARD PARERA": ("m", "cadet"),
        "JAN SANS": ("m", "cadet"),
        "JAVIER ALMALE": ("m", "cadet"),
        "LUCAS FARIÑA": ("m", "cadet"),
        "MARIO SÁNCHEZ": ("m", "cadet"),
        "ÁLVAREZ AUÑOS": ("m", "absolut"),
        "GUTIERREZ": ("f", "juvenil"),
        "TORRADEM": ("f", "juvenil"),
        "MIREIA LÓPEZ": ("f", "juvenil"),
        "ALICIA VAZQUEZ": ("f", "juvenil"),
        "FALCÓ": ("f", "juvenil"),
        "BUSCAIL": ("f", "juvenil"),
        "SIRA BO": ("f", "juvenil"),
        "MASCARELL": ("f", "juvenil"),
        "DELGADO": ("f", "juvenil"),
        "MARIMON": ("f", "juvenil"),
        "LIANA": ("f", "juvenil"),
        "MAR VÁZQUEZ": ("f", "juvenil"),
        "GEMMA PARERA": ("f", "juvenil"),
        "BERTA": ("f", "juvenil"),
        "CARRASCO": ("f", "juvenil"),
        "ARIADNA ALONSO": ("f", "juvenil"),
        "INIESTA": ("f", "juvenil"),
        "CARLA BERENGUEL": ("f", "juvenil"),
        "NIL PINYOL": ("m", "infantil"),
        "POL AIXALA": ("m", "infantil"),
        "ORIOL ALDAVE": ("m", "infantil"),
        "OSCAR BARTOLOME": ("m", "infantil"),
        "NIL AIXALÀ": ("m", "infantil"),
        "ALBERT GENÉ": ("m", "cadet"),
        "JOAN ANDREU": ("m", "cadet"),
        "BLANCA TORTAJADA": ("f", "absolut"),
        "MARINA TIBAU": ("f", "junior"),
        "BERTA PRADOS": ("f", "juvenil"),
        "DE LAS HERAS": ("f", "juvenil"),
        "ERIKA DÍEZ": ("f", "infantil"),
        "ALBA TORRES": ("f", "infantil"),
        "JANA TORRES": ("f", "infantil"),
        "JULIA SUAREZ": ("f", "infantil"),
        "LAIA ALDAVE": ("f", "infantil"),
        "LARA HERRERA": ("f", "infantil"),
        "LAURA SANTOS": ("f", "infantil"),
        "OLIVIA NOLLA": ("f", "infantil"),
    },
    # Territorial combined PC (2016-04): masc juv 5kg / cadet 4kg; fem juv 3kg
    "resulterritcombinadescambrils300410516.json": {
        "MATEO SANZ": ("m", "vet50"),
        "ALBERT ORTEGA": ("m", "juvenil"),
        "DÍDAC ALONSO": ("m", "juvenil"),
        "DIEZ SANCHEZ": ("m", "juvenil"),
        "JUAN CARLOS HERRERA": ("m", "juvenil"),
        "ALEIX LAGO": ("m", "cadet"),
        "BERNAT VERDÚ": ("m", "cadet"),
        "EDGAR JOSÉ": ("m", "cadet"),
        "LUCAS FARIÑA": ("m", "cadet"),
        "ALICIA VÁZQUEZ": ("f", "juvenil"),
        "MARIA ALVAREZ": ("f", "juvenil"),
        "MARIA BUSCAIL": ("f", "juvenil"),
        "SIRA BO": ("f", "cadet"),
        "INES DELGADO": ("f", "cadet"),
        "LAURA MASCARELL": ("f", "cadet"),
        "MARIA FONS": ("f", "cadet"),
        "MARIA FALCO": ("f", "cadet"),
        "LAURINE MARIMON": ("f", "cadet"),
        "LUCÍA MAYOLAS": ("f", "cadet"),
        "ANDREA CARRASCO": ("f", "cadet"),
        "ARIADNA ALONSO": ("f", "cadet"),
        "AINA TOMÀS": ("f", "infantil"),
        "ALBA TORRES": ("f", "infantil"),
        "BERTA POMES": ("f", "infantil"),
        "CLÀUDIA BARBENS": ("f", "infantil"),
        "CRISTINA REYES": ("f", "infantil"),
        "EGOITZ PEDROL": ("m", "infantil"),
        "ERIKA DÍEZ": ("f", "infantil"),
        "GERARD FERRÁNDIZ": ("m", "infantil"),
        "ISAAC GUZMAN": ("m", "infantil"),
        "JANA TORRES": ("f", "infantil"),
        "JULIA SUAREZ": ("f", "infantil"),
        "LAIA ALDAVE": ("f", "infantil"),
        "LARA HERRERA": ("f", "infantil"),
        "LAURA SANTOS": ("f", "infantil"),
        "MARTINA POMES": ("f", "infantil"),
        "NATALIA SÁNCHEZ": ("f", "infantil"),
        "OLIVIA NOLLA": ("f", "infantil"),
        "POL MASCARELL": ("m", "infantil"),
        "RUBÉN PAREDES": ("m", "infantil"),
        "DE LAS HERAS": ("f", "infantil"),
        "NIL PINYOL": ("m", "infantil"),
        "OSCAR BARTOLOME": ("m", "infantil"),
    },

        "AINA TOMÀS": ("f", "infantil"),

        "ALBA TORRES": ("f", "infantil"),

        "BERTA POMES": ("f", "infantil"),

        "CLÀUDIA BARBENS": ("f", "infantil"),

        "CRISTINA REYES": ("f", "infantil"),

        "EGOITZ PEDROL": ("m", "infantil"),

        "ERIKA DÍEZ": ("f", "infantil"),

        "GERARD FERRÁNDIZ": ("m", "infantil"),

        "ISAAC GUZMAN": ("m", "infantil"),

        "JANA TORRES": ("f", "infantil"),

        "JULIA SUAREZ": ("f", "infantil"),

        "LAIA ALDAVE": ("f", "infantil"),

        "LARA HERRERA": ("f", "infantil"),

        "LAURA SANTOS": ("f", "infantil"),

        "MARTINA POMES": ("f", "infantil"),

        "NATALIA SÁNCHEZ": ("f", "infantil"),

        "OLIVIA NOLLA": ("f", "infantil"),

        "POL MASCARELL": ("m", "infantil"),

        "RUBÉN PAREDES": ("m", "infantil"),

        "DE LAS HERAS": ("f", "infantil"),

    # Territorial combined AL/PC (2015-05): birth-year bands 2015
    "resulcnatterritcombinadescambrils230515.json": {
        "MARTÍN": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "ÁLVAREZ": ("m", "absolut"),
        "ALVAREZ": ("m", "absolut"),
        "ROMANI": ("m", "absolut"),
        "RÍOS": ("m", "junior"),
        "RIOS": ("m", "junior"),
        "ALICIA VÁZQUEZ": ("f", "juvenil"),
        "ALICIA VAZQUEZ": ("f", "juvenil"),
        "PARERA": ("m", "cadet"),
        "JAVIER ALMALE": ("m", "cadet"),
        "BUSCAIL": ("f", "cadet"),
        "PARDINES": ("m", "vet50"),
        "FALCÓ": ("f", "alevi"),
        "AIXALA": ("m", "alevi"),
        "ALDAVE": ("m", "alevi"),
        "LIANA": ("f", "alevi"),
        "MARIMON": ("f", "alevi"),
        "MASCARELL": ("m", "alevi"),
        "MARTIN 2004": ("m", "alevi"),
        "BERENGUEL": ("m", "infantil"),
        "NIL PINYOL": ("m", "infantil"),
        "BERTA": ("f", "infantil"),
        "DELGADO": ("f", "infantil"),
        "VERDÚ": ("m", "infantil"),
        "ARIADNA SUÁREZ": ("f", "infantil"),
        "POMES": ("f", "infantil"),
        "DE LAS HERAS": ("f", "alevi"),
        "EMMA RONDELAERE": ("f", "alevi"),
        "ISAAC GUZMÁN": ("m", "infantil"),
        "MARC ROZAS": ("m", "infantil"),
        "MARINA MIR": ("f", "infantil"),
        "NATALIA SÁNCHEZ": ("f", "infantil"),
        "ORIOL ALDAVE": ("m", "infantil"),
        "POL AIXALA": ("m", "alevi"),
        "POL MASCARELL": ("m", "infantil"),
        "RUBÉN PAREDES": ("m", "infantil"),
        "UNAISA GUIJARRO": ("f", "infantil"),
        "ZAIRA BUENO": ("f", "infantil"),
    },
    # Territorial combined championship PC (2012-12): all-category meet
    # (ABSOLUT 7,260 / MÀSTER 7,260 M40-45 / JÚNIOR 6 / JUVENIL 5 / CADET 4)
    "resulcnatterritcombinadeshiverntgna22231212.json": {
        "ROMANI": ("m", "absolut"),
        "MARTIN": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "MATEO SANZ": ("m", "absolut"),
        "ADOLF MILLA": ("m", "cadet"),
        "ALUJA": ("m", "cadet"),
        "TEXIER": ("m", "infantil"),
        "SOLE": ("f", "absolut"),
        "ESPARZA": ("f", "juvenil"),
        "HELENA RIOS": ("f", "juvenil"),
        "ALVAREZ": ("f", "juvenil"),
        "ALICIA VAZQUEZ": ("f", "cadet"),
        "ANDREA LOPEZ": ("f", "cadet"),
        "BERNAL": ("f", "cadet"),
        "TARGA": ("f", "infantil"),
        "MIREIA LOPE": ("f", "infantil"),
        "DELGADO": ("f", "infantil"),
        "PLANAS": ("f", "infantil"),
        "NEREA LAGO": ("f", "infantil"),
        "SIRA BO": ("f", "alevi"),
        "MONTANES": ("f", "alevi"),
        "LUNA": ("m", "cadet"),
        "PARERA": ("m", "infantil"),
        "PAU NOLLA": ("m", "alevi"),
        "JOSEP MILLA": ("m", "infantil"),
    },
    # Masters pentathlon championship (2012-09): senior implements
    "resulcatpentatloveterans150912.json": {
        "MATEO SANZ": ("m", "absolut"),
    },
    # Territorial combined championship PC (2011-12): veterans compete absolut
    "resulcnatterritcombinades17181211.json": {
        "ROMANI": ("m", "absolut"),
        "TORTOSA": ("m", "absolut"),
        "RIOS": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "MATEO SANZ": ("m", "absolut"),
        "SOLE": ("f", "absolut"),
        "TORRADEM": ("f", "cadet"),
        "ALVAREZ": ("f", "cadet"),
        "ESPARZA": ("f", "cadet"),
    },
    # Territorial combined championship AL (2009-04): absolut decathlon men
    # (Mellakhi/Tortosa/Pardines), Díaz juvenil, Guinovart/Torrademé cadet women
    "resulterritcombitarragona2526409.json": {
        "MELLAKHI": ("m", "absolut"),
        "TORTOSA": ("m", "absolut"),
        "PARDINES GRAS": ("m", "absolut"),
        "DIAZ": ("m", "juvenil"),
        "GUINOVART": ("f", "cadet"),
        "TORRADEM": ("f", "cadet"),
    },
}

# Per-athlete official names for combined-event totals ("CLASSIFICACIÓ PROVES
# COMBINADES"): combined event depends on venue (PC vs AL), gender and category.
FILE_ATHLETE_COMBINED = {
    # PC championship: men heptatlo, women pentatlo (all absolut)
    "resulcatcombinadespc2006.json": {
        "SERRES PARDINES": "Heptatlo",
        "RIOS MESEGUER": "Heptatlo",
        "SOLE": "Pentatló",
    },
    # PC championship (2007-01): absolut men heptatlo
    "resulcatcombinadespc2021107.json": {
        "RIOS MESEGUER": "Heptatlo",
        "MARTIN": "Heptatlo",
    },
    # PC cadet-juvenil championship (2007-10): juvenil women pentatlo
    "resulcatcombinadescadjuvpc2728107.json": {
        "MALLA": "Pentatló (S18)",
    },
    # AL championship (2008-05): Oriol junior decatlo
    "resulcatcombinades34508.json": {
        "ORIOL": "Decatló (sub20)",
    },
    # PC championship (2008-01): Rios promesa heptatlo, Oriol junior heptatlo
    "resulcatcombinadespc1213108.json": {
        "RIOS MESEGUER": "Heptatlo",
        "ORIOL": "Heptatló (S20)",
    },
    # AL championship (2009-05): Rios promesa decatlo, Díaz juvenil decatlo
    "resulcatcombinades910509.json": {
        "RIOS MESSEGUER": "Decatló (Abs)",
        "DIAZ": "Decatló (S18)",
    },
    # Control combinades (2010-06): Rios promesa decatlo
    "resulcontrolcombinades1920610.json": {
        "RIOS MESEGUER": "Decatló (Abs)",
        "RIOS MESSEGUER": "Decatló (Abs)",
    },
    # Veterans combined championship (2011): decatlo with senior implements
    # (no veterans row in DISCIPLINES.md; closest official name)
    "resulcatveteranscombinades20211.json": {
        "MARTIN": "Decatló (Abs)",
    },
    # Masters PC combined championship (2012): heptatlo
    "resulcatveteranscombinadespc190212.json": {
        "MATEO SANZ": "Heptatlo",
    },
    # AL championship: men decatlo (abs/juvenil), women heptatlo (abs) / hexatlo (cadet)
    "resulcatcombinades13-14506.json": {
        "RIOS MESEGUER": "Decatló (Abs)",
        "RIOS MESSEGUER": "Decatló (Abs)",
        "PARDINES GRAS": "Decatló (Abs)",
        "BENITEZ LAZCANO": "Decatló (S18)",
        "ORIOL": "Decatló (S18)",
        "SOLE": "Heptatlo",
        "MALLA": "Hexatló",
    },
}

# Suspect entries identified by cross-checking the source PDFs: the extractor
# mislabelled several combined-event sub-events (marks stored under a shifted
# event name) or mangled performances. Disciplines are renamed mechanically;
# these rows need re-extraction before DB import.
SUSPECT_ENTRIES = {
    "2006": {
        "resultarragona1-2405.json": [
            ("(several)", "100 METRES LLISOS", "5.91/5.26/6.19/6.09/5.58", "values are Llargada marks; real 100m times (11.69-12.79) missing"),
            ("SERRES/RIOS/MARTIN", "LLANÇAMENT DE PES", "1.76/1.70/1.67", "values are Alçada marks"),
            ("SERRES/RIOS", "LLANÇAMENT DE DISC", "3.60/2.30", "values are Perxa marks"),
            ("SERRES/RIOS", "1.500 METRES LLISOS", "44.51/44.80", "mangled 1500m times (PDF 4:44.51/4:44.80)"),
            ("BEATRIU MALLA", "100 METRES TANQUES", "1.39", "value is the Alçada mark; real 100mh 17.76 missing"),
            ("BEATRIU MALLA", "LLANÇAMENT DE PES", "4.23/4.22/4.05", "values are Llargada marks"),
        ],
        "resultarragona10111205.json": [
            ("abs masc athletes", "60 METRES TANQUES", "2.40/2.70/2.20", "values are Perxa marks"),
            ("juven masc athletes", "60 METRES TANQUES", "3.10/2.70/2.80", "values are Llargada marks"),
            ("ANNA SOLÉ/BEATRIU", "60 METRES TANQUES", "1.54/1.39", "values are Alçada marks"),
            ("abs masc athletes", "LLANÇAMENT DE PES", "1.75/1.72/1.69/1.60/1.63", "values are Alçada marks"),
            ("ANNA SOLÉ", "LLANÇAMENT DE PES", "4.95/4.97/4.92", "values are Llargada marks"),
            ("BEATRIU MALLA", "LLANÇAMENT DE PES", "4.38/4.16", "values are Llargada marks"),
            ("ANNA SOLÉ", "800 METRES LLISOS", "43.37", "mangled 800m time (PDF 2:43.37)"),
            ("BEATRIU MALLA", "600 METRES LLISOS", "51.53", "implausible 600m; sub-event to verify in PDF"),
            ("BERNAT ROCAMORA", "LLOC LLIC. ATLETA...", "7.53/23.64", "broken header-row extraction"),
        ],
        "resulcatcombinades13-14506.json": [],
        "resulcatcombinadespc2006.json": [],
        "resulcatjuvenil25606.json": [
            ("IVAN BENITEZ", "10000 METRES MARXA", "6.23", "value is a Llargada mark"),
            ("BEATRIU MALLA", "5000 METRES MARXA", "1.42", "value is the Alçada mark"),
        ],
        "resulmeetingmataro10706.json": [
            ("ESTHER ARAGONES", "Prova: Llançament de Javelina...", "2.18", "entry is her 800m (PDF 2.18.49); javelina event was masculine, no CATT athlete"),
        ],
        "resulcatveteranspc2006.json": [
            ("FLORES LOPEZ PARDINES GARCIA", "LLANÇAMENT DE PES MASCULÍ", "1:58.55", "garbled row: concatenated names + a track time"),
        ],
    },
    "2007": {
        "resulcombireus25307.json": [
            ("RIOS/ORIOL", "100 METRES LLISOS", "5.59/5.75", "values are Llargada marks; real 100m times (11.80/12.19) missing"),
            ("RIOS", "Pes Júnior", "1.72", "value is the Alçada mark"),
            ("ORIOL", "Disc Júnior", "2.80", "value is the Perxa mark"),
            ("ORIOL/RIOS", "1.500 METRES LLISOS", "3.08/44.15", "mangled 1500m times (PDF 5:03.08/5:44.15)"),
            ("ANNA SOLÉ", "100 METRES TANQUES", "1.61", "value is the Alçada mark; real 100mh 17.87 missing"),
            ("ANNA SOLÉ", "200 METRES LLISOS", "4.73", "value is a Llargada mark"),
            ("ANNA SOLÉ", "800 METRES LLISOS", "21.42", "implausible 800m; sub-event to verify in PDF"),
            ("BEATRIU MALLA", "100 METRES TANQUES", "1.34", "value is the Alçada mark"),
            ("BEATRIU MALLA", "LLANÇAMENT DE PES", "4.17", "value is a Llargada mark"),
        ],
        "resulcombihiverntarragona23241206.json": [
            ("masc athletes", "60 METRES TANQUES", "2.80/2.30/2.30", "values are Perxa marks"),
            ("ANNA/BEATRIU", "60 METRES TANQUES", "1.53/1.35", "values are Alçada marks"),
            ("ORIOL/MARTIN/PARDINES", "LLANÇAMENT DE PES", "1.62/1.59/1.59", "values are Alçada marks"),
            ("ANNA SOLÉ", "LLANÇAMENT DE PES", "4.83/4.89", "values are Llargada marks"),
        ],
        "resulcatcombi6507.json": [
            ("ORIOL", "100 METRES LLISOS", "4.91", "value is a Llargada mark; real 100m 12.40 missing"),
            ("ORIOL", "LLANÇAMENT DE PES", "1.60", "value is the Alçada mark"),
            ("BEATRIU MALLA", "100 METRES TANQUES", "1.41", "value is the Alçada mark"),
            ("BEATRIU MALLA", "LLANÇAMENT DE PES", "4.65/3.36", "values are Llargada marks"),
        ],
        "resulcatcombinadespc2021107.json": [
            ("DIDAC RIOS", "LLANÇAMENT DE PES MASCULÍ", "5.40", "value not consistent with pes attempts (9.09/9.10)"),
        ],
        "resulcatclubsveterans9607.json": [
            ("FLORES", "3000 METRES LLISOS", "1:05.59", "value is his 400m time"),
            ("PARDINES GRAS", "3000 METRES LLISOS", "1.68", "value is the Alçada mark"),
            ("IBORRA", "3000 METRES LLISOS", "8.15", "value inconsistent; multi-event row misread"),
            ("GARCIA NAVARRETE", "100 METRES LLISOS", "70.60", "value inconsistent; relay row misread"),
            ("SERRES CASAMITJANA", "LLANÇAMENT DE JAVELINA", "70.05", "value inconsistent (javelina best 28.72)"),
            ("VACAS", "LLANÇAMENT DE DISC", "69.23", "value inconsistent (disc best 30.20)"),
        ],
        "resulinauguraciobarbera21407.json": [
            ("FAROUK MELLAKHI", "Prova Disc F", "11.62/11.50", "marks are his 100m times; disc femenina event had no CATT athlete"),
        ],
        "resulveteranserrahima12507.json": [
            ("BARDINA/ORTEGA/RODRIGUEZ", "ALÇADA FEMENINA", "2.11/2.06/2.06", "male athletes with implausible marks; row attribution to verify in PDF"),
        ],
    },
    "2008": {
        "resulcombicambrils231207.json": [
            ("ORIOL/IBORRA/MARTIN", "60 METRES TANQUES", "3.10/2.90/2.00", "values are Perxa marks"),
            ("ANNA/BEATRIU", "60 METRES TANQUES", "1.50/1.35", "values are Alçada marks"),
            ("masc athletes", "LLANÇAMENT DE PES", "1.65/1.65/1.62/1.59/1.20", "values are Alçada marks"),
            ("ANNA SOLÉ", "LLANÇAMENT DE PES", "4.95/4.89", "values are Llargada marks"),
            ("BEATRIU MALLA", "LLANÇAMENT DE PES", "4.35/4.16/4.10", "values are Llargada marks"),
        ],
        "resulcombicambrils56408.json": [
            ("BEATRIU MALLA", "100 METRES TANQUES", "1.36", "value is the Alçada mark; real 100mh 17\"6 missing"),
            ("MARC JOSÉ DÍAZ", "100 METRES TANQUES", "2.30", "value is the Perxa mark; real 110mh 13.5 missing"),
            ("MARC JOSÉ DÍAZ", "LLANÇAMENT DE PES", "1.47", "value is the Alçada mark"),
        ],
        "resulcatclubsveterans21608.json": [
            ("JAVIER MARTIN", "LLANÇAMENT DE PES", "22.16/36.06", "values are his Disc/Javelina marks (multi-event row)"),
            ("PEDRO VACAS", "LLANÇAMENT DE DISC", "69.23/42.29", "values are another event's mark + percentage (disc best 29.28)"),
            ("AMADEU SERRES", "LLANÇAMENT DE JAVELINA", "68.66/38.04", "values are another event's mark + percentage (javelina best 26.12)"),
            ("FLORES", "400 METRES TANQUES", "76.93", "value is a percentage score, not a time"),
            ("PERE PARDINES JOSE MARTIN / BARDINA-SANCHIS", "LLANÇAMENT DE JAVELINA", "82.08/66.00/48.85/74.02", "relay rows (4x100 50\"00, 4x400 4'24\"01) with percentage values; disciplines corrected to 4x100/4x400"),
        ],
        "resulcatclubsbpc20108.json": [
            ("FLORES", "400 METRES TANQUES", "76.93", "value is a percentage score, not a time"),
        ],
    },
    "2009": {
        "resulcombinadescambrils20211208.json": [
            ("masc athletes", "60 METRES TANQUES", "3.30/2.80/2.40/2.20/2.20", "values are Perxa marks"),
            ("BEATRIU", "60 METRES TANQUES", "1.29", "value is the Alçada mark"),
            ("masc athletes", "LLANÇAMENT DE PES", "1.65/1.62/1.59/1.50/1.44", "values are Alçada marks"),
            ("BEATRIU", "LLANÇAMENT DE PES", "4.08/4.10", "values are Llargada marks"),
        ],
        "resultarragona16509.json": [
            ("(5 rows)", "DISC 2 0", "13.68-15.27", "values are 100m/110mh race times; club-scoring table misread as event title; disciplines corrected"),
            ("GUINOVART", "DISC Cadet Femení 800 g", "58.36", "row is the 4x100 SUB-18 relay (58\"36); discipline corrected"),
        ],
        "resulcontrolcombi21609.json": [
            ("RIOS", "LLOC LLIC header", "9 values", "decathlon row split into header-labelled entries; events re-attributed by standard order (100m/llargada/pes/alçada/400/110t/disc/perxa/javelina)"),
        ],
        "resulmeetingcat23509.json": [
            ("SÁEZ/ROS/BARBERÁN/GARCÍA", "Prova: ... (various)", "several", "extraction garbled: license numbers (17487/16437/15829) and percentages (71.66/75.45) as performances; rows duplicated under 'Per marca' and 'Per Percentatge' variants"),
        ],
        "resulcatclubs7609.json": [
            ("DOMINGO", "DISC MASCULÍ", "71.97", "value is a percentage (disc best 19.89); 27.64 is another event's mark"),
            ("SRRES CASMITJANA", "JAVELINA MASCULÍ", "67.27/34.95", "percentage + inconsistent mark (javelina best 23.51)"),
            ("IBORRA MARTIN PARDINES FLO / ROS SANCHIS GARCIA DOMINGO", "JAVELINA MASCULÍ", "10.26/48.76/12.19/48.85/39.16/69.79/70.00", "4x100 relay rows (totals 48.76/48.85) with leg times/percentages; disciplines corrected to 4x100"),
        ],
        "resulterritcombitarragona2526409.json": [
            ("MELLAKHI/TORTOSA/PARDINES", "Pes Júnior / Disc Júnior", "1.62/2.70/2.00/2.00", "values are Alçada (1.62) and Perxa (2.00-2.70) marks"),
            ("GUINOVART/TORRADEM", "100 METRES TANQUES", "1.30/1.27", "values are Alçada marks"),
            ("DIAZ", "LLANÇAMENT DE PES / DE DISC", "1.50/2.40", "values are Alçada (1.50) and Perxa (2.40) marks"),
        ],
    },
    "2010": {
        "resulcombinadescambrils19201209.json": [
            ("masc athletes", "60 METRES TANQUES", "3.30/2.90/2.50/2.20/2.00/2.40", "values are Perxa marks"),
            ("TORRADEM", "60 METRES TANQUES", "1.26", "value is the Alçada mark"),
            ("masc athletes", "LLANÇAMENT DE PES", "1.65/1.62/1.59/1.51/1.50", "values are Alçada marks"),
        ],
        "resulcombinadescambrils2425410.json": [
            ("DIAZ", "LLANÇAMENT DE PES", "1.51", "value is the Alçada mark"),
            ("DIAZ/ORIOL/RIOS", "110 METRES TANQUES", "see report", "genuine marks (Díaz juvenil 0.914; Oriol/Ríos absolut 1.067)"),
        ],
        "resultrofeucloendalloret171010.json": [
            ("ARIZA", "LLANÇAMENT DE PES MASCULI", "43.34", "value is a percentage (real pes 9.97)"),
        ],
        "resultrofeuaperturasabadell25410.json": [
            ("MATEO SANZ", "Llançament de DISC", "4.78", "mark is his Llargada (PDF row labelled LLARGADA); discipline corrected"),
        ],
        "resulcatveterans27610.json": [
            ("LOPEZ BLANCO MATEO GARCIA", "MARTELL PESAT 50+", "4:29.07", "relay row (4x400 time); discipline corrected to 4x400"),
        ],
    },
}

# Per-athlete explicit overrides where the implement weight does not match any
# standard category spec (e.g. veterans: M55 javelina = 700 g).
FILE_ATHLETE_OVERRIDES = {
    "resulcatveterans16607.json": {
        "SERRES CASAMITJANA": {"LLANÇAMENT DE JAVELINA": "Javelina (700 g)"},  # M-55
    },
    "resulcatclubsveterans9607.json": {
        "SERRES CASAMITJANA": {"LLANÇAMENT DE JAVELINA": "Javelina (700 g)"},  # M-55
    },
    "resulcatveterans15608.json": {
        "SAEZ": {"LLANÇAMENT DE JAVELINA": "Javelina (700 g)"},  # M-55
    },
    "resulcatclubsveterans21608.json": {
        "AMADEU SERRES": {"LLANÇAMENT DE JAVELINA": "Javelina (700 g)"},  # M-55
        # concatenated relay rows mislabelled as javelina (verified: 50"00 / 4'24"01)
        "PERE PARDINES JOSE MARTIN": {"LLANÇAMENT DE JAVELINA": "4x100"},
        "JOAN BARDINA JAUME SANCHIS": {"LLANÇAMENT DE JAVELINA": "4x400"},
    },
    "resulcat28609.json": {
        "SAEZ": {"LLANÇAMENT DE JAVELINA MASCULÍ": "Javelina (600 g)"},  # M-60 in 2009
        # relay quartet row mislabelled as martell pesat (verified: 48.61 = 4x100)
        "MARTIN PARDINES IBORRA": {"LLANÇAMENT DE MARTELL PESAT MASCULÍ": "4x100"},
    },
    "resulcatclubs7609.json": {
        # concatenated relay rows mislabelled as javelina (verified 48.76/48.85 totals)
        "IBORRA MARTIN PARDINES": {"JAVELINA MASCULÍ": "4x100"},
        "ROS SANCHIS GARCIA": {"JAVELINA MASCULÍ": "4x100"},
    },
    "resulmitingveteransreus8510.json": {
        "SAEZ": {"PROVA JAVELINA M.": "Javelina (600 g)"},  # M-60 in 2010
    },
    "resulcatveterans27610.json": {
        "SAEZ": {"LLANÇAMENT DE JAVELINA MASCULÍ 50+": "Javelina (600 g)"},  # M-60 in 2010
        # relay pair row mislabelled as martell pesat (verified: 4:29.07 = 4x400)
        "LOPEZ BLANCO": {"LLANÇAMENT DE MARTELL PESAT MASCULÍ 50+": "4x400"},
    },
    "resultrofeuaperturasabadell25410.json": {
        # the 4.78 mark is Mateo Sanz's Llargada (PDF row labelled LLARGADA);
        # the discus event label is an extractor mislabel
        "MATEO SANZ": {"LLANÇAMENT DE DISC": "Llargada"},
    },
}

# Row-level overrides for mislabelled extractions verified in the source PDFs:
# (file, athlete-substring, raw-discipline-exact, performance-exact) -> official name
FILE_ROW_OVERRIDES = {
    "resulcnatterritvalls90515.json": [
        # pdfplumber: Hailu's row used as false header; events from mark ranges
        ("BÒ CALAF", "PTO", "12.62", "60 metres llisos"),
        ("SUBIROS BRASERO", "PTO", "10.62", "60 metres llisos"),
        ("FERRÁNDIZ GINER", "PTO", "10.85", "60 metres llisos"),
        ("SUBIROS BRASERO", "PTO", "10.31", "60 metres llisos"),
        ("VICENTE NAVARRETE", "PTO", "11.11", "60 metres llisos"),
        ("LAS HERAS", "PTO", "11.33", "60 metres llisos"),
        ("AIXALÀ GUIU", "PTO", "10.06", "60 metres llisos"),
        ("MASCARELL JULIÁN", "PTO", "10.73", "60 metres llisos"),
        ("ROZAS BELLIDO", "PTO", "11.87", "60 metres llisos"),
        ("GUZMÁN VELASCO", "PTO", "10.27", "60 metres llisos"),
        ("ALDAVE FORÈS", "PTO", "11.44", "60 metres llisos"),
        ("MARIMÓN FERNÁNDEZ", "PTO", "9.78", "60 metres llisos"),
        ("ALDAVE MAS", "PTO", "10.26", "60 metres llisos"),
        ("BUENO UBEDA", "PTO", "10.78", "60 metres llisos"),
        ("LAS HERAS", "PTO", "9.56", "60 metres llisos"),
        ("MIR CASELLAS", "PTO", "11.03", "60 metres llisos"),
        ("SUAREZ PIZA", "PTO", "11.36", "60 metres llisos"),
        ("SANCHEZ ALVAREZ", "PTO", "9.76", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "10.40", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "9.52", "60 metres llisos"),
        ("LAS HERAS", "PTO", "9.54", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "9.61", "60 metres llisos"),
        ("VERDÚ GÓMEZ", "PTO", "21.55", "150 metres llisos"),
        ("PINYOL MATEU", "PTO", "24.58", "150 metres llisos"),
        ("VERDÚ GÓMEZ", "PTO", "21.17", "150 metres llisos"),
        ("MOHAMED MAMAN", "PTO", "23.60", "150 metres llisos"),
        ("JAN SANS", "PTO", "23.68", "150 metres llisos"),
        ("TOMAS CORDERO", "PTO", "23.94", "150 metres llisos"),
        ("ALMALÉ LERÍN", "PTO", "25.28", "150 metres llisos"),
        ("AIXALÀ GUIU", "PTO", "1.59", "Alçada"),
        ("GUZMÁN VELASCO", "PTO", "2.15", "Llargada"),
        ("MASCARELL JULIÁN", "PTO", "2.20", "Llargada"),
        ("MARIMÓN FERNÁNDEZ", "PTO", "2.08", "Llargada"),
        ("SANCHEZ ALVAREZ", "PTO", "2.09", "Llargada"),
        ("ALDAVE MAS", "PTO", "2.09", "Llargada"),
        ("GUIJARRO ESTEBAN", "PTO", "2.19", "Llargada"),
        ("SAFONT BALAGUER", "PTO", "3.15", "Llargada"),
        ("SOLÉ BARBA", "PTO", "3.57", "Llargada"),
        ("BÒ CALAF", "PTO", "3.30", "Llargada"),
        ("BUSCAIL BRIANSÓ", "PTO", "3.35", "Llargada"),
        ("SUBIROS BRASERO", "PTO", "25.94", "150 metres llisos"),
        ("SUBIROS BRASERO", "PTO", "26.25", "150 metres llisos"),
        ("SUBIROS BRASERO", "PTO", "28.03", "150 metres llisos"),
        ("FERRÁNDIZ GINER", "PTO", "13.90", "60 metres llisos"),
        ("FERRÁNDIZ GINER", "PTO", "10.94", "60 metres llisos"),
        ("BÒ CALAF", "PTO", "4.59", "Llargada"),
        ("BÒ CALAF", "PTO", "4.24", "Llargada"),
        ("BÒ CALAF", "PTO", "7.56", "Llargada"),
        ("VICENTE NAVARRETE", "PTO", "8.65", "60 metres llisos"),
        ("VICENTE NAVARRETE", "PTO", "3.87", "Llargada"),
        ("VICENTE NAVARRETE", "PTO", "6.93", "Llargada"),
        ("LAS HERAS", "PTO", "4.78", "Llargada"),
        ("LAS HERAS", "PTO", "7.14", "Llargada"),
        ("LAS HERAS", "PTO", "8.62", "60 metres llisos"),
        ("AIXALÀ GUIU", "PTO", "24.74", "150 metres llisos"),
        ("AIXALÀ GUIU", "PTO", "22.13", "150 metres llisos"),
        ("AIXALÀ GUIU", "PTO", "21.45", "150 metres llisos"),
        ("ALDAVE FORÈS", "PTO", "21.11", "150 metres llisos"),
        ("ALDAVE FORÈS", "PTO", "20.60", "150 metres llisos"),
        ("PAREDES LARIO", "PTO", "20.31", "150 metres llisos"),
        ("GUZMÁN VELASCO", "PTO", "11.59", "60 metres llisos"),
        ("ROZAS BELLIDO", "PTO", "8.65", "60 metres llisos"),
        ("ROZAS BELLIDO", "PTO", "9.27", "60 metres llisos"),
        ("ALDAVE MAS", "PTO", "13.67", "60 metres llisos"),
        ("LAS HERAS", "PTO", "12.38", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "11.70", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "12.01", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "12.80", "60 metres llisos"),
        ("SANCHEZ ALVAREZ", "PTO", "8.50", "60 metres llisos"),
        ("SANCHEZ ALVAREZ", "PTO", "11.95", "60 metres llisos"),
        ("SANCHEZ ALVAREZ", "PTO", "9.66", "60 metres llisos"),
        ("MIR CASELLAS", "PTO", "11.28", "60 metres llisos"),
        ("MIR CASELLAS", "PTO", "9.90", "60 metres llisos"),
        ("MIR CASELLAS", "PTO", "11.90", "60 metres llisos"),
        ("POMES CABELLO", "PTO", "11.76", "60 metres llisos"),
        ("SUAREZ PIZA", "PTO", "10.70", "60 metres llisos"),
        ("SUAREZ PIZA", "PTO", "10.62", "60 metres llisos"),
    ],
    "resultarragona16509.json": [
        # 'DISC 1 2' / 'DISC 2 0' are club-scoring tables; the rows under them
        # are 100 m.ll. races (and one 110 m.t. Juvenil race)
        ("INGLES", "DISC 2 0", "13.68", "100 metres llisos"),
        ("TORRADEM", "DISC 2 0", "13.90", "100 metres llisos"),
        ("GUINOVART", "DISC 2 0", "14.22", "100 metres llisos"),
        ("TORRADEM", "DISC 2 0", "14.08", "100 metres llisos"),
        ("DIAZ", "DISC 2 0", "15.27", "110 metres tanques (0.91)"),
        # the row is the 4x100 SUB-18 femení relay (58"36)
        ("GUINOVART", "DISC CADET FEMENÍ 800 G", "58.36", "4x100"),
    ],
    "resulcontrolcombi21609.json": [
        # Rios's decathlon row was split into 9 entries carrying the table
        # header as discipline; events recovered by the standard decathlon order
        ("RIOS", "LLOC", "12.02", "100 metres llisos"),
        ("RIOS", "LLOC", "5.70", "Llargada"),
        ("RIOS", "LLOC", "9.29", "Pes (7.260 Kg)"),
        ("RIOS", "LLOC", "1.65", "Alçada"),
        ("RIOS", "LLOC", "53.84", "400 metres llisos"),
        ("RIOS", "LLOC", "19.31", "110 metres tanques (1.067)"),
        ("RIOS", "LLOC", "21.74", "Disc (2 Kg)"),
        ("RIOS", "LLOC", "3.10", "Perxa"),
        ("RIOS", "LLOC", "27.36", "Javelina (800 g)"),
    ],
    "resulcatclubsalevi130512.json": [
        # garbled multi-event rows (same raw title for 4 different events);
        # events verified in the PDF ("60m FEM.", "600m FEM.", "2.000m FEM")
        ("BERENGUEL", "10 70 (T) VICTOR PESO KEYER", "9.67", "60 metres llisos"),
        ("JOVE", "10 70 (T) VICTOR PESO KEYER", "14.36", "600 metres llisos"),
        ("BO CALAF", "10 70 (T) VICTOR PESO KEYER", "45.71", "2000 metres llisos"),
        ("DOMINGO CIURANA", "10 70 (T) VICTOR PESO KEYER", "12.88", "60 metres tanques (0.50)"),
    ],
    "resulcatcombinadespromocio25260513.json": [
        # garbled duplicate rows (same marks as the properly-named entries);
        # Adolf = cadet decathlon, Alicia = cadet hexathlon, Mireia/Marta = aleví
        ("ADOLF MILLA", "PTO", "12.25", "100 metres llisos"),
        ("ADOLF MILLA", "PTO", "5.21", "Llargada"),
        ("ADOLF MILLA", "PTO", "10.62", "Pes (4 Kg)"),
        ("ADOLF MILLA", "PTO", "16.80", "100 metres tanques (0.91)"),
        ("ALICIA VAZQUEZ", "PTO", "18.37", "60 metres tanques (0.76)"),
        ("ALICIA VAZQUEZ", "PTO", "6.44", "Javelina (500 g)"),
        ("MIREIA LOPEZ", "PTO", "14.08", "80 metres tanques (0.84)"),
        ("MIREIA LOPEZ", "PTO", "8.39", "Pes (2 Kg)"),
        ("MIREIA LOPEZ", "PTO", "4.67", "Llargada"),
        ("MIREIA LOPEZ", "PTO", "11.25", "80 metres llisos"),
        ("MARTA TARGA", "PTO", "14.65", "80 metres tanques (0.84)"),
        ("MARTA TARGA", "PTO", "7.68", "Pes (2 Kg)"),
        ("MARTA TARGA", "PTO", "4.38", "Llargada"),
        ("MARTA TARGA", "PTO", "11.25", "80 metres llisos"),
        ("ALICIA VAZQUEZ", "PTO", "4.81", "Llargada"),
    ],
    "resulcatveteranspentatlo140913.json": [
        # masters pentathlon: llargada, javelina (700g M45), 200m, disc (2kg), 1500m
        ("MATEO SANZ", "LLARGADA PUNTS JAVELINA", "5.00", "Llargada"),
        ("MATEO SANZ", "LLARGADA PUNTS JAVELINA", "24.73", "Javelina (700 g)"),
        ("MATEO SANZ", "LLARGADA PUNTS JAVELINA", "26.89", "200 metres llisos"),
        ("MATEO SANZ", "LLARGADA PUNTS JAVELINA", "25.33", "Disc (2 Kg)"),
        ("FORNIES", "LLARGADA PUNTS JAVELINA", "4.55", "Llargada"),
        ("FORNIES", "LLARGADA PUNTS JAVELINA", "28.58", "Javelina (700 g)"),
        ("FORNIES", "LLARGADA PUNTS JAVELINA", "27.75", "200 metres llisos"),
        ("FORNIES", "LLARGADA PUNTS JAVELINA", "20.50", "Disc (2 Kg)"),
    ],
    "resulcatveteranspentatlollancaments140913.json": [
        # masters throws pentathlon (W50 Pinyol): martell 3kg, pes 3kg, disc 1kg,
        # javelina 500g, martell pesat
        ("PINYOL", "MARTELL PUNTS PES", "14.64", "Martell (3 Kg)"),
        ("PINYOL", "MARTELL PUNTS PES", "6.33", "Pes (3 Kg)"),
        ("PINYOL", "MARTELL PUNTS PES", "11.56", "Disc (1 Kg)"),
        ("PINYOL", "MARTELL PUNTS PES", "12.91", "Javelina (500 g)"),
        ("PINYOL", "MARTELL PUNTS PES", "4.84", "Martell pesat (15.88 Kg)"),
    ],
    "resultrobadaandorra180513.json": [
        ("LLUIS SAEZ", "CLASSIFICACIÓ LLARGADA", "3.67", "Llargada"),
        ("LLUIS SAEZ", "CLASSIFICACIÓ LLARGADA", "3.89", "Llargada"),
        ("LLUIS SAEZ", "CLASSIFICACIÓ LLARGADA", "3.46", "Llargada"),
        ("LLUIS SAEZ", "CLASSIFICACIÓ LLARGADA", "3.87", "Llargada"),
        ("LLUIS SAEZ", "CLASSIFICACIÓ LLARGADA", "3.81", "Llargada"),
    ],
    "resulterritsub13equipscambrils210112.json": [
        # the mark is Parera's 60m llisos time (PDF race row 10"12); the raw
        # discipline is a scoring-table fragment
        ("PARERA", "PES 4 5 3 0 0", "10.12", "60 metres llisos"),
        # the mark is Mireia's 60mh infantil time (PDF series "A" 12"42); the
        # raw discipline is the combined-event scoring header
        ("LOPEZ URBANO", "LLOC", "12.42", "60 metres tanques (0.84)"),
        # Pardines (M40-45 veteran): 60mh 0.991 (pes stays 7.260 = absolut)
        ("PARDINES GRAS", "60 METRES TANQUES", "10.77", "60 metres tanques (0.99)"),
    ],
}

# Per-file raw-discipline decisions (verified in source PDFs where noted)
FILE_DISCIPLINE_MAP = {
    "resulcatcombicadetpc.json": {
        # 4-event combined total (60 m.t., Pes, Llargada, 60 m.ll. -> Tetratló)
        "CLASSIFICACIÓ CADET FEMENÍ": "Tetratló",
    },
    "resulcjjp7505.json": {
        # athletes Rafael Vaquer (1985), Juan Velasco (1984) -> men -> 7.260 kg
        "LLANÇAMENT DE MARTELL PROMESA": "Martell (7.260 Kg)",
    },
    "resulmeetingmataro10706.json": {
        # verified: the only CATT entry is E. Aragones' 800m (2.18.49); the
        # javelina event was "Categoria: Masculina" with no CATT athlete
        "PROVA: LLANÇAMENT DE JAVELINA / LANZAMIENTO DE JABALINA": "800 metres llisos",
    },
    "resulcatcombialeinfcad67609.json": {
        # classificació table columns: 100 m.t., Alçada, Pes, Llargada, Javelina,
        # 100 m.ll. -> 6-event cadet women's combined
        "CLASSIFICACIÓ CADET FEMENINA": "Hexatló",
    },
    "resulinauguraciobarbera21407.json": {
        # verified: the CATT rows (license 081/SG/FAA07, marks 11.62/11.50) are
        # F. Mellakhi's 100m; the disc femenina event had no CATT athlete
        "PROVA DISC F": "100 metres llisos",
    },
}

CAT_TOKENS = {"CADET": "cadet", "JUVENIL": "juvenil", "JUNIOR": "junior", "PROMESA": "promesa",
              "ALEVÍ": "alevi", "ALEVI": "alevi", "INFANTIL": "infantil", "BENJAMÍ": "benjami",
              "BENJAMI": "benjami", "PREBENJAMÍ": "prebenjami", "PREBENJAMI": "prebenjami",
              "S10": "alevi", "S12": "alevi", "S14": "infantil", "S16": "cadet",
              "S18": "juvenil", "S20": "junior", "S23": "promesa",
              "SUB12": "alevi", "SUB14": "infantil", "SUB16": "cadet",
              "SUB18": "juvenil", "SUB20": "junior", "SUB23": "promesa"}

def norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().upper())

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", strip_accents((name or "").strip().upper()))

def athlete_context(filename: str, athlete_name: str):
    """Return (gender, category) from the per-athlete context table, or (None, None)."""
    ctx = FILE_ATHLETE_CONTEXT.get(filename)
    if not ctx:
        return None, None
    up = norm_name(athlete_name)
    for key, value in ctx.items():
        if strip_accents(key) in up:
            return value
    return None, None

def gender_of(raw_upper: str):
    if re.search(r"\bMASCUL[IÍ](N[OAS]|NS|O|A)?\b", raw_upper):
        return "m"
    if re.search(r"\bFEMEN[IÍ](N[AS]|NS|A|SES|SE)?\b", raw_upper):
        return "f"
    # glued abbreviations ("fem.Absolut", "masc.Junior", "Vet. MAS.")
    if re.search(r"\bMASC\b|\bMAS\b|\bMASCUÍ\b", raw_upper):
        return "m"
    if re.search(r"\bFEM\b", raw_upper):
        return "f"
    if re.search(r"\bHOMES\b|\bHOMBRES\b", raw_upper):
        return "m"
    if re.search(r"\bDONES\b|\bMUJERES\b", raw_upper):
        return "f"
    # single-letter tokens ("PES F", "JAVELINA M.")
    if re.search(r"\bM\b", raw_upper):
        return "m"
    if re.search(r"\bF\b", raw_upper):
        return "f"
    return None

def category_from_raw(raw_upper: str):
    up = strip_accents(raw_upper)
    for token, cat in CAT_TOKENS.items():
        if strip_accents(token) in up:
            return cat
    return None

def category_from_event(event_name: str):
    up = (event_name or "").upper()
    for token, cat in CAT_TOKENS.items():
        if token in up:
            return cat
    return "open"  # absolyt/open implement (verified for un-suffixed sections)

def resolve_file_category(event_name: str, filename: str):
    if filename in FILE_CATEGORY:
        return FILE_CATEGORY[filename]
    return category_from_event(event_name)

# ---------------------------------------------------------------------------
# Mapping rules
# ---------------------------------------------------------------------------


def normalize_2026_raw(raw: str) -> str:
    """Rewrite 2026-era extractor discipline names (Spanish event words, dotted
    thousands, category suffixes like U10M/S14F/AL/PC/Master M55) into the
    engine-friendly Catalan form. Safe for older raws: only rewrites tokens
    that never appear in pre-2026 raw names."""
    s = raw.strip()
    # dotted thousands before 'm': 1.000m -> 1000m
    s = re.sub(r"(\d)\.(\d{3})\s*m\b", r"\1\2 m", s)
    # Spanish event words -> Catalan
    repl = [
        (r"\bSalto con P[ée]rtiga\b", "Perxa"),
        (r"\bTriple Salto\b", "Triple"),
        (r"\bTriple salt\b", "Triple"),
        (r"\bP[ée]rtiga\b", "Perxa"),
        (r"\bLongitud\b", "Llargada"),
        (r"\bAltura\b", "Alçada"),
        (r"\bMartillo\b", "Martell"),
        (r"\bJabalina\b", "Javelina"),
        (r"\bDisco\b", "Disc"),
        (r"\bPeso\b", "Pes"),
        (r"\bMarcha\b", "Marxa"),
        (r"\bvallas\b", "tanques"),
        (r"\bObst\.", "obstacles"),
        (r"(\d{3,4})\s*m\s+obst", r"\1 metres obst"),
        (r"\bRelleu\b", "Relleus"),
        (r"\bTriatl[oó]n\b|\bTriatlon\b", "Triatló"),
        (r"\bPentathl[oó]n\b", "Pentatló"),
        (r"\bTetrathl[oó]n\b", "Tetratló"),
        (r"\bHeptathl[oó]n\b", "Heptatló"),
        (r"\bPentathl[oó]n?\b", "Pentatló"),
        (r"\bFemeninses\b", "Femenins"),
        (r"\bMascuins\b", "Masculins"),
        (r"\bMascui\b", "Masculí"),
        (r"\bfemeni\b", "femení"),
        (r"\bmasculi\b", "masculí"),
        (r"\bMujeres\b", "Femení"),
        (r"\bHombres\b", "Masculí"),
        (r"\bsin R[ií]a\b", ""),
        (r"\ben pista\b", ""),
        (r"\bpista\b", ""),
        (r"\(C\)", ""),
        (r"\bJUV/CAD\b|\bJUV-\b|\bCAD\b", ""),
        (r"\bINF-VET\.?\b", ""),
        (r"\bVET\.?\b|\bVet\.?\b", ""),




        (r"\bAL\b|\bPC\b|\bCF\b|\bIF\b|\bIM\b|\bCM\b|\bLM\b|\bLF\b|\bSM\b|\bBM\b|\bAF\b|\bAM\b", ""),


    ]
    for pat, rep in repl:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\s+", " ", s).strip(" .,-")
    return s

def map_discipline(raw: str, event_name: str, filename: str, athlete_name: str = None):
    """Return (official_name or None, note or None)."""
    raw = normalize_2026_raw(raw)
    up = norm(raw)
    ctx_gender, ctx_category = athlete_context(filename, athlete_name)

    # Combined-event totals: per-athlete decision (venue + gender + category)
    if up in ("CLASSIFICACIÓ PROVES COMBINADES", "CLASSIFICACIONS PROVES COMBINADES"):
        table = FILE_ATHLETE_COMBINED.get(filename, {})
        up_name = norm_name(athlete_name)
        for key, official in table.items():
            if strip_accents(key) in up_name:
                return official, "combined-event total (category from PDF section)"
        return None, "combined total without per-athlete decision"

    # Per-athlete explicit overrides (veteran implements, etc.)
    overrides = FILE_ATHLETE_OVERRIDES.get(filename, {})
    if overrides and athlete_name:
        up_name = norm_name(athlete_name)
        for key, mapping in overrides.items():
            if strip_accents(key) in up_name and up in mapping:
                return mapping[up], "per-athlete override (PDF-verified age class)"

    # Straight per-file decisions first
    file_map = FILE_DISCIPLINE_MAP.get(filename, {})
    if up in file_map:
        return file_map[up], "verified in source PDF"

    # Per-athlete overrides (mixed absolut-junior combined championship)
    if filename == "resulcatcombiabsjunpc.json" and up in {
        "60 METRES TANQUES MASCULINS", "LLANÇAMENT DE PES MASCULÍ"}:
        return "NEEDS_ATHLETE", None  # handled by caller

    # Junk prefixes used by some PDFs ("PROVA:", "RESULTATS", "HH:MM   ")
    up = re.sub(r"^(?:PROVA:?|RESULTATS)\s+", "", up)
    up = re.sub(r"^\d{1,2}:\d{2}\s+", "", up)

    # Flat (llisos)
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{3,5})\s+METRES LLISOS\b", up)
    if m:
        dist = int(m.group(1).replace(".", ""))
        return f"{dist} metres llisos", None
    # Abbreviated flat: "100 M.LL. MASCULÍ" (veterans clubs format)
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{3,5})\s*M\.?\s*LL\.?\b", up)
    if m and not re.search(r"\b(TANQU|OBST|MARXA|MARCHA)\b", up):
        dist = int(m.group(1).replace(".", ""))
        return f"{dist} metres llisos", None

    # Marató / Mitja Marató race walk — MUST be checked BEFORE the
    # running-marathon rule below (issue #12): raw names like
    # "Maratón Marcha Hombres" normalize to "... MARXA ..." and would
    # otherwise be captured by the bare ^MARAT[OÓ]N? rule as "Marato"
    # (running marathon) instead of the race-walk (Ruta) rows.
    # The half distance also carries a Spanish official alias (DISCIPLINES.md id 96
    # "Medio maratón Marcha"), so MEDIO MARATÓ joins the half rule: "Medio maratón
    # Marcha Masc" would otherwise fall through to the full-marathon rule below and
    # map to id 92 (Marató Marxa (Ruta)).
    if re.search(r"(?:MITJA|MEDIO) MARATÓ.*MARXA|MARXA.*(?:MITJA|MEDIO) MARATÓ", up):
        return "Mitja Marató Marxa (Ruta)", None
    if re.search(r"MARATÓ.*MARXA|MARXA.*MARATÓ", up):
        return "Marató Marxa (Ruta)", None

    # Marató / Mitja Marató (running)
    if re.match(r"^MITJA MARAT[OÓ]\b", up):
        return "Mitja Marato", None
    if re.match(r"^MARAT[OÓ]N?\b|^MARATÓ\b", up):
        return "Marato", None

    # Marxa (race walk) — before the bare-'m' rule ("2.000m Marxa MASC.")
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{3,5}(?:\.\d{3})?)\s*(?:M\.?|METRES)?\s*MARXA\b", up)
    if m:
        dist = int(m.group(1).replace(".", ""))
        table = {1000: "1000 metres marxa", 2000: "2000 metres marxa", 3000: "3000 metres marxa",
                 5000: "5000 metres marxa", 10000: "10 km marxa"}
        return table.get(dist), (None if dist in table else "unknown marxa distance")

    # "X METRES <cat/gender>" without LLISOS (e.g. "3000 METRES MASCULÍ")
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{3,5})\s+METRES\b", up)
    if m and not re.search(r"\b(TANQUES|OBSTACLES|MARXA|MARCHA|LLISOS|MT)\b", up):
        dist = int(m.group(1).replace(".", ""))
        return f"{dist} metres llisos", None

    # "2KM Aleví Femení" / "5 km Marcha sub-16 Hombres" km-distance form.
    # RFEA road-walk championships use the km form: per issue #12 these map
    # to the (Ruta) rows in DISCIPLINES.md. 1000/2000 km-forms keep the
    # track names (no ruta rows exist for those distances).
    m = re.match(r"^(\d{1,2})\s*KM\b", up)
    if m:
        dist = int(m.group(1)) * 1000
        table = {1000: "1000 metres marxa", 2000: "2000 metres marxa",
                 3000: "3 km marxa", 5000: "5K marxa (Ruta)", 10000: "10K marxa (Ruta)"}
        return table.get(dist), (None if dist in table else "unknown km distance")

    # Bare-'m' distance names ("1.500 m juvenil a absolut masculí", "60m FEM. AL")
    # But NOT if the raw mentions 'tanques' (e.g. "110m tanques (1,067) S23 MASC. AL")
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{3,5})\s*[mM](?=[A-ZÀ-Ú\s]|$)", up)
    if m and not re.search(r"\bTANQUES\b|\bVALLAS\b|\bMV\b|\dMT\b|\bOBSTACLES\b|\bMARXA\b", up):
        dist = int(m.group(1).replace(".", ""))
        return f"{dist} metres llisos", None

    # "CURSA 220 m. tanques IF" / "CURSA 1000 m. llisos Benjamí femení"
    m = re.match(r"^CURSA\s+(\d{1,2}(?:\.\d{3})?|\d{1,4})\s*[mM]\.?\s*(LLISOS|TANQUES|MV)?\b", up)
    if m:
        gender = gender_of(up) or ctx_gender
        cat = ctx_category or resolve_file_category(event_name, filename)
        if cat == "open":
            cat = "absolut"
        if m.group(2) and m.group(2).upper().startswith("TAN"):
            name = tanques_name(int(m.group(1).split(".")[0].lstrip("0") or "0"), gender or "m", cat if cat != "open" else "absolut")
            if name and name in OFFICIAL_NAMES | APPROVED_PENDING:
                return name, "CURSA meeting form"
            return None, f"CURSA tanques unresolved ({name})"
        dist = int(m.group(1).replace(".", ""))
        return f"{dist} metres llisos", "CURSA meeting form"

    # Hurdles (tanques): "X METRES TANQUES" form
    # "TANQUES LLARGUES" = long hurdles (400m); veterans M40 height 0.914
    if re.match(r"^TANQUES LLARGUES\b", up):
        return "400 metres tanques (0.914)", None
    m = re.match(r"^(\d{2,3})\s+METRES TANQUES\b", up)
    # Also match "Xm tanques" and "Xm vallas" forms
    if not m:
        m = re.match(r"^(\d{2,3})\s*[mM][tT]\b", up)  # '300mt (0,84)'
    if not m:
        m = re.match(r"^(\d{2,3})\s*[mM]\s+(?:TANQUES|VALLAS)\b", up)
    if m:
        # single official row regardless of gender/category
        if int(m.group(1)) == 80:
            return "80 metres tanques (0.84)", None
        # explicit height stated in the raw name (e.g. veterans "(1,00 m.)"):
        # pick the official row for this distance whose height is nearest
        mh = re.search(r"\(([\d.,]+)\s*M?", up)
        if mh:
            height = float(mh.group(1).replace(",", ".").rstrip("."))
            candidates = []
            for name in OFFICIAL_NAMES:
                mp = re.match(rf"^{m.group(1)} metres tanques \(([\d.]+)\)$", name)
                if mp:
                    candidates.append((abs(float(mp.group(1)) - height), name))
            if candidates:
                return min(candidates)[1], "explicit height in raw name (nearest official row)"
        gender = gender_of(up) or ctx_gender
        # 100mv is a women's event, 110mv a men's event: gender is derivable
        if gender is None and int(m.group(1)) == 100:
            gender = "f"
        elif gender is None and int(m.group(1)) == 110:
            gender = "m"
        cat = ctx_category or category_from_raw(up) or resolve_file_category(event_name, filename)
        if gender is None or cat is None:
            return None, "tanques without gender/category"
        if cat == "open":
            cat = "absolut"
        name = tanques_name(int(m.group(1)), gender, cat)
        return (name, None) if name else (None, f"no tanques rule for {m.group(1)}m {gender} {cat}")

    # Obstacles
    m = re.match(r"^(\d{1,2}(?:\.\d{3})?|\d{4})\s+METRES OBSTACLES\b", up)
    if m:
        dist = str(int(m.group(1).replace(".", "")))
        return OBSTACLES_NAMES.get(dist), (None if dist in OBSTACLES_NAMES else "unknown obstacle distance")

    # Jumps (full names, abbreviations and bare event words)
    if re.match(r"^SALT D'ALÇADA\b", up) or re.match(r"^(?:SALT )?ALÇADA\b", up) or re.match(r"^ALTURA\b", up):
        return "Alçada", None
    if re.match(r"^SALT (?:DE )?LLARGADA\b", up) or re.match(r"^SALT DE LARGADA\b", up) or re.match(r"^LLARGADA(FEM)?\b", up) or re.match(r"^LONGITUD\b", up):
        return "Llargada", None
    if re.match(r"^SALT (AMB |DE )?PERXA\b", up) or re.match(r"^(PERXA|PÉRTIGA|PERTIGA)\b", up) or re.search(r"\bPERXA\b|\bPÉRTIGA\b|\bPERTIGA\b", up):
        return "Perxa", None
    if re.match(r"^SALT DE TRIPLE\b|^TRIPLE SALT(O)?\b|^TRIPLE\b", up):
        return "Triple", None

    # Throws
    m = re.match(r"^LLANÇAMENT (?:DE|DEL) (PES|PESO|DISCO?|MAR(?:TELL|TILLO)(?:O)?|JAVELINA|JABALINA|JAVELOT)\b", up)
    if m:
        implement = m.group(1)
        gender = gender_of(up) or ctx_gender
        cat = ctx_category or category_from_raw(up) or resolve_file_category(event_name, filename)
        if cat == "open":
            cat = "absolut"
        if gender is None:
            # masters age range: "MÀSTER M50 (6kg)" / "MÀSTER M50-M55 (7,260kg)"
            m50 = re.search(r"\b([MWF])(\d\d)\b", up)
            if m50:
                gender = "m" if m50.group(1) == "M" else "f"
                lo_age = int(m50.group(2))
                cat = "vet50" if lo_age >= 50 else "absolut"
            else:
                # Sub-age suffix: "Pes SUB12M" / "Javelina S10F"
                sub_g = re.search(r"\b(?:S(?:UB)?|U)?(\d+)([MF])\b", up)
                if sub_g:
                    gender = sub_g.group(2).lower()
        if gender is None:
            # category-only raw names (e.g. "MARTELL PROMESA") are resolved in FILE_DISCIPLINE_MAP
            return None, f"{implement.lower()} without gender"
        table = {(("pes"), "m"): PES_M, ("pes", "f"): PES_F,
                 ("disc", "m"): DISC_M, ("disc", "f"): DISC_F,
                 ("martell", "m"): MARTELL_M, ("martell", "f"): MARTELL_F,
                 ("javelina", "m"): JAVELINA_M, ("javelina", "f"): JAVELINA_F}[({"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina"}.get(implement.lower(), implement.lower()), gender)]
        name = table.get(cat)
        if name is None:
            return None, f"no {implement.lower()} spec for {gender}/{cat}"
        if name not in OFFICIAL_NAMES | APPROVED_PENDING:
            return None, f"mapped value '{name}' not present in DISCIPLINES.md"
        return name, None

    # Self-specified implements (raw name contains the weight, e.g.
    # 'Pes Absolut 7,260 kg' or 'Javelina Júnior 700 g'): map directly by weight
    m = re.search(r"\b(PES|PESO|DISCO?|MAR(?:TELL|TILLO)(?:O)?|JAVELINA|JABALINA|JAVELOT)\b[^\d]{0,40}?(\d+(?:[.,]\d+)?)\s*(KG|GR\.?|G)\b", up)
    if m:
        implement = {"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina", "martillo": "martell", "martello": "martell", "martello": "martell"}.get(m.group(1).lower(), m.group(1).lower())
        weight = m.group(2).replace(" ", "")
        if re.match(r"^[\d]+[,\.](00)?$", weight):
            weight = weight.split(",")[0].split(".")[0]
        unit = "KG" if m.group(3).startswith("K") else "G"
        table = {
            "pes": {"7,260": "Pes (7.260 Kg)", "6": "Pes (6 Kg)", "5": "Pes (5 Kg)",
                    "4": "Pes (4 Kg)", "3": "Pes (3 Kg)", "2": "Pes (2 Kg)"},
                "disc": {"2": "Disc (2 Kg)", "1,750": "Disc (1,750)", "1,5": "Disc (1,5 Kg)",
                         "1": "Disc (1 Kg)", "0,8": "Disc (800 g)", "800": "Disc (800 g)",
                         "0,6": "Disc (600 g)", "600": "Disc (600 g)"},
                "martell": {"7,260": "Martell (7.260 Kg)", "6": "Martell (6 Kg)", "5": "Martell (5 Kg)",
                            "4": "Martell (4 Kg)", "3": "Martell (3 Kg)", "2": "Martell (2 Kg)",
                            "15,88": "Martell pesat (15.88 Kg)", "9,08": "Martell pesat (9.08 Kg)",
                            "7,26": "Martell pesat (7.260 Kg)"},
                "javelina": {"800": "Javelina (800 g)", "700": "Javelina (700 g)",
                             "600": "Javelina (600 g)", "500": "Javelina (500 g)", "400": "Javelina (400 g)", "300": "Javelina (300 g)"},
            }[implement]
        if weight not in table and unit == "KG":
            if implement == "pes" and weight == "7":
                weight = "7,260"
            elif "," in weight:
                weight = weight.replace(",", ".")
        name = table.get(weight)
        if name is None:
            return None, f"unrecognised {implement} weight '{weight} {unit}'"
        if name not in OFFICIAL_NAMES | APPROVED_PENDING:
            return None, f"mapped value '{name}' not present in DISCIPLINES.md"
        return name, "implement weight stated in raw name"

    # Bare implement names with no context: in 2016+ the extractor lost the
    # category context for combinades meets. Default to absolut for senior
    # athletes in championship-level meets.
    m = re.match(r"^(?:LLANÇAMENT (?:DE|DEL) )?(PES|PESO|DISCO?|MAR(?:TELL|TILLO)(?:O)?|JAVELINA|JABALINA|JAVELOT)\b", up)
    has_ctx = gender_of(up) or category_from_raw(up)
    if m and (has_ctx or filename.startswith("resulcontrolcombinades") or filename.startswith("resulterritcombinades")
              or filename.startswith("resulcontrolterrit") or filename.startswith("resulcnatterritcombinades")
              or filename.startswith("resulcatcombinades") or filename.startswith("resulcontrolvalls")
              or filename.startswith("resulmitingveterans")):
        implement = {"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina", "martillo": "martell", "martello": "martell"}.get(m.group(1).lower(), m.group(1).lower())
        gender = gender_of(up) or ctx_gender
        cat = ctx_category or "absolut"
        if cat == "open":
            cat = "absolut"
        if gender is None:
            gender = "m"  # control combinades are mostly male
        table = {("pes", "m"): PES_M, ("pes", "f"): PES_F,
                 ("disc", "m"): DISC_M, ("disc", "f"): DISC_F,
                 ("martell", "m"): MARTELL_M, ("martell", "f"): MARTELL_F,
                 ("javelina", "m"): JAVELINA_M, ("javelina", "f"): JAVELINA_F}[(implement, gender)]
        name = table.get(cat)
        if name and name in OFFICIAL_NAMES | APPROVED_PENDING:
            return name, "control combinades default (context lost)"

    # Turbo jav / Vortex javelina (Sub-10/12): 'Jabalina Vortex S10M' → Javelina (300 g)
    if re.search(r"\bVORTEX\b", up):
        gender = gender_of(up)
        if gender is None:
            gm = re.search(r"\bS10([MF])\b", up)
            if gm:
                gender = gm.group(1).lower()
        if gender is None:
            gender = "m"
        return "Javelina Vortex", "Vortex turbo jav"

    # Bare implement names (e.g. "Disc Femení") + masters age ranges
    m = re.match(r"^(PES|PESO|DISCO?|MAR(?:TELL|TILLO)(?:O)?|JAVELINA|JABALINA|JAVELOT)\b", up)
    if m:
        implement = {"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina", "martillo": "martell", "martello": "martell", "martello": "martell"}.get(m.group(1).lower(), m.group(1).lower())
        gender = gender_of(up) or ctx_gender
        cat = ctx_category or category_from_raw(up) or resolve_file_category(event_name, filename)
        if cat == "open":
            cat = "absolut"
        if gender is None:
            mvm = re.search(r"\b([MWF])?(\d\d)[-\u2013]([MWF])?(\d\d)\b", up)
            if mvm:
                gender = "m" if (mvm.group(1) or "M") == "M" else "f"
                lo_age = int(mvm.group(2))
                cat = "vet50" if lo_age >= 50 else "absolut"
            m50 = re.search(r"\b([MWF])(\d\d)\b", up)
            if m50:
                gender = "m" if m50.group(1) == "M" else "f"
                lo_age = int(m50.group(2))
                cat = "vet50" if lo_age >= 50 else "absolut"
        if gender is None:
            # Sub-age suffix: "Pes SUB12M" / "Javelina S10F"
            sub_g = re.search(r"\b(?:S(?:UB)?|U)?(\d+)([MF])\b", up)
            if sub_g:
                gender = sub_g.group(2).lower()
            if gender is None:
                return None, f"{implement.lower()} without gender"
        table = {("pes", "m"): PES_M, ("pes", "f"): PES_F,
                 ("disc", "m"): DISC_M, ("disc", "f"): DISC_F,
                 ("martell", "m"): MARTELL_M, ("martell", "f"): MARTELL_F,
                 ("javelina", "m"): JAVELINA_M, ("javelina", "f"): JAVELINA_F}[({"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina"}.get(implement.lower(), implement.lower()), gender)]
        name = table.get(cat)
        if name is None:
            return None, f"no {implement.lower()} spec for {gender}/{cat}"
        if name not in OFFICIAL_NAMES | APPROVED_PENDING:
            return None, f"mapped value '{name}' not present in DISCIPLINES.md"
        return name, None
    # Combined-event names stated directly
    m = re.match(r"^(TETRATL[ÓO]N?|PENTATL[ÓO]N?|HEXATL[ÓO]N?|HEPTATL[ÓO]N?|OCTATL[ÓO]N?|DECATL[ÓO]N?|TRIATL[ÓO]N?)\b", up)
    if m:
        table = {"TETRATLÓ": "Tetratló", "PENTATLÓ": "Pentatló", "HEXATLÓ": "Hexatló",
                 "HEPTATLÓ": "Heptatlo", "HEPTATLO": "Heptatlo", "OCTATLÓ": "Octatló",
                 "DECATLÓ": "Decatló (Abs)", "TRIATLÓ": "Triatló", "TRIATLON": "Triatló",
                 "PENTATLON": "Pentatló", "HEPTATLON": "Heptatlo", "DECATLON": "Decatló (Abs)",
                 "TETRATLON": "Tetratló"}
        key = strip_accents(m.group(1))
        stripped = {strip_accents(k): v for k, v in table.items()}
        name = stripped.get(key)
        if name:
            return name, None

    # Veterans age-class implements ("Pes VET. Fem. AL 50-54", "Javelina Vet.
    # MAS. 60-64", "Disc VET. Fem. 45-49", "60m MASC. PC 35-39"): WMA specs.
    vm = re.search(r"\b(35-39|40-44|45-49|50-54|55-59|60-64|65-69|70-74|75-79|80\+|F-\d\d|M-\d\d|\d\d\+)\b", up)
    vgender = re.search(r"\b([MF])(\d\d)\b", up)
    # "Pes MÀSTER M50-M55 (6kg)" / "Pes MÀSTER M40-M45 (7,260kg)" form
    mvm = re.match(r"^(?:LLANÇAMENT (?:DE|DEL) )?(PES|PESO|DISCO?|MAR(?:TELL|TILLO)(?:O)?|JAVELINA|JABALINA|JAVELOT)\b[^\d]*(\d\d)[-–](\d\d)", up)
    if mvm:
        implement = {"disco": "disc", "peso": "pes", "jabalina": "javelina", "javelot": "javelina", "martillo": "martell", "martello": "martell", "martello": "martell"}.get(mvm.group(1).lower(), mvm.group(1).lower())
        lo_age = int(mvm.group(3))
        gender = gender_of(up)
        if gender is None:
            # infer from M/W prefix in the age range
            prefix = re.search(r"\b([MW])\d\d\b", up)
            gender = "m" if (prefix and prefix.group(1) == "M") else ("f" if prefix else "m")
        vet_cat = "vet50" if lo_age >= 50 else "absolut"
        table = {("pes", "m"): PES_M, ("pes", "f"): PES_F,
                 ("disc", "m"): DISC_M, ("disc", "f"): DISC_F,
                 ("martell", "m"): MARTELL_M, ("martell", "f"): MARTELL_F,
                 ("javelina", "m"): JAVELINA_M, ("javelina", "f"): JAVELINA_F}[(implement, gender)]
        name = table.get(vet_cat)
        if name and name in OFFICIAL_NAMES | APPROVED_PENDING:
            return name, f"masters age range {lo_age}-{mvm.group(4)}"
        # fall through if the spec isn't found
    if vm:
        band = vm.group(1)
        try:
            lo = int(band.split("-")[0].lstrip("FM"))
        except ValueError:
            lo = 50
        vet_cat = "vet50" if lo >= 50 else "absolut"
        # route through the normal implement logic with the veteran category
        m2 = re.match(r"^(?:LLANÇAMENT (?:DE|DEL) )?(PES|DISCO?|MARTELL(?:O|ILLO)?|JAVELINA)\b", up)
        if m2:
            implement = {"disco": "disc"}.get(m2.group(1).lower(), m2.group(1).lower())
            gender = (vgender.group(1).lower() if vgender else None) or gender_of(up)
            if gender is None:
                return None, f"{implement.lower()} vet without gender"
            table = {("pes", "m"): PES_M, ("pes", "f"): PES_F,
                     ("disc", "m"): DISC_M, ("disc", "f"): DISC_F,
                     ("martell", "m"): MARTELL_M, ("martell", "f"): MARTELL_F,
                     ("javelina", "m"): JAVELINA_M, ("javelina", "f"): JAVELINA_F}[(implement, gender)]
            name = table.get(vet_cat)
            if name is None:
                return None, f"no {implement.lower()} spec for {gender}/{vet_cat}"
            if name not in OFFICIAL_NAMES | APPROVED_PENDING:
                return None, f"mapped value '{name}' not present in DISCIPLINES.md"
            return name, f"veteran age class {band}"

    # Pilota (benjamí)
    if re.search(r"\bPILOTA\b", up):
        return "Pilota", None

    # Relays
    m = re.search(r"(\d)\s*[xX×]\s*(\d{2,3})(?!\d)", up)
    if m:
        rel = f"{m.group(1)}x{int(m.group(2))}"
        table = {"4x60": "4x60", "4x80": "4x80", "4x100": "4x100", "4x200": "4x200", "4x300": "4x300",
                 "4x400": "4x400", "3x600": "3x600"}
        return table.get(rel), (None if rel in table else f"unknown relay {rel}")

    return None, "no rule matched"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_file(path: Path, dry_run: bool):
    data = json.loads(path.read_text(encoding="utf-8"))
    event_name = data.get("event_name", "")
    results = data.get("results", [])
    mapping_counts = Counter()
    review = []
    changed = 0

    for r in results:
        # on re-runs the official name is already applied; map from the raw source
        raw = r.get("raw_discipline_name") or r.get("discipline", "")
        if not raw:
            review.append({"athlete": r.get("athlete_name"), "raw": raw, "reason": "empty discipline"})
            continue
        up = norm(raw)
        official, note = None, None
        for (akey, rraw, perf, oname) in FILE_ROW_OVERRIDES.get(path.name, []):
            if akey in norm_name(r.get("athlete_name", "")) and up.startswith(norm(rraw)) and (r.get("performance") or "").strip() == perf:
                official, note = oname, "row-level override (PDF-verified mislabelled table)"
                break
        if official is None:
            official, note = map_discipline(raw, event_name, path.name, r.get("athlete_name"))

        if official == "NEEDS_ATHLETE":
            official = ABSJUN_OVERRIDES.get((r.get("athlete_name", ""), raw))
            note = "per-athlete category from PDF birth-year column (absolut-junior combined)"
        if official is not None:
            # defensive: guarantee canonical unit casing regardless of table/override path
            official = normalize_weight_units(official)
        if official is None:
            review.append({"athlete": r.get("athlete_name"), "raw": raw, "reason": note})
            if not dry_run and "raw_discipline_name" not in r:
                rebuilt = {}
                for k, v in r.items():
                    rebuilt[k] = v
                    if k == "discipline":
                        rebuilt["raw_discipline_name"] = raw
                r.clear()
                r.update(rebuilt)
                changed += 1
            continue

        if official not in OFFICIAL_NAMES | APPROVED_PENDING:
            review.append({"athlete": r.get("athlete_name"), "raw": raw,
                           "reason": f"'{official}' not in DISCIPLINES.md"})
            continue

        mapping_counts[(raw, official)] += 1
        if r.get("raw_discipline_name") != raw or r.get("discipline") != official:
            changed += 1
        if not dry_run:
            # rebuild dict to place raw_discipline_name right after discipline
            rebuilt = {}
            for k, v in r.items():
                rebuilt[k] = official if k == "discipline" else v
                if k == "discipline":
                    rebuilt["raw_discipline_name"] = raw
            r.clear()
            r.update(rebuilt)

    if not dry_run and changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(results), mapping_counts, review, changed

def write_report(season: str, files: int, total: int, counts: Counter, review: list,
                 out: Path = None, label: str = None):
    """Write the mapping report.

    season: season key; also selects the season-only suspect table. Pass None for
            non-season targets, so no season suspect table leaks into their report.
    label:  report title. Defaults to "season <season>". --json-dir runs pass the
            real target ("json", "json/imported") so the header cannot claim a
            season that was never processed.
    """
    if out is None:
        out = REPO_ROOT / "seasons" / season / "discipline_mapping_report.md"
    title = label if label is not None else f"season {season}"
    lines = [
        f"# Discipline mapping report — {title}", "",
        "Original raw values preserved in `raw_discipline_name` (inserted after `discipline`).",
        "Heights/weights follow the FCA *Proves autoritzades* tables (stable for the 2005 era: "
        "cadet=Sub16, juvenil=Sub18, junior=Sub20, promesa=Sub23). Un-suffixed events in open "
        "meets use the absolut spec (verified against the source PDFs). Mixed absolut-junior",
        "combined events resolved per athlete from the PDF birth-year column.", "",
        f"- files: {files}", f"- results: {total}", f"- mapped: {sum(counts.values())}",
        f"- review (left unchanged): {len(review)}", "",
        "| count | raw discipline | official discipline |", "|---:|---|---|",
    ]
    for (raw, official), cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0])):
        lines.append(f"| {cnt} | `{raw}` | `{official}` |")
    lines += [""]
    suspects = SUSPECT_ENTRIES.get(season, {}) if season else {}
    if suspects:
        lines += ["## Suspect entries (re-extraction recommended before DB import)", "",
                  "Marks stored under a shifted event name, or mangled performances,", 
                  "identified by cross-checking the source PDFs. Disciplines were renamed", 
                  "mechanically; the underlying rows are unreliable.", "",
                  "| file | athlete(s) | raw discipline | performance | note |", "|---|---|---|---|---|"]
        for fname, items in sorted(suspects.items()):
            for athlete, raw, perf, note in items:
                lines.append(f"| {fname} | {athlete} | `{raw}` | {perf} | {note} |")
    if review:
        lines += ["", "## Review (discipline left unchanged)", "",
                  "| file | athlete | raw | reason |", "|---|---|---|---|"]
        for item in review:
            lines.append(f"| {item['file']} | {item['athlete']} | `{item['raw']}` | {item['reason']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2005")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json-dir", help="process json/<dir> files instead of seasons/<season>")
    args = ap.parse_args()

    if args.json_dir:
        json_dir = REPO_ROOT / args.json_dir
        files = sorted(json_dir.glob("*.json"))
    else:
        json_dir = REPO_ROOT / "seasons" / args.season / "json"
        files = sorted(json_dir.glob("*.json"))
    if not files:
        sys.exit(f"no JSON files under {json_dir}")

    total = mapped = 0
    all_counts = Counter()
    all_review = []
    for f in files:
        n, counts, review, _ = process_file(f, args.dry_run)
        total += n
        mapped += sum(counts.values())
        all_counts.update(counts)
        for item in review:
            item["file"] = f.name
        all_review.extend(review)

    target_label = args.json_dir if args.json_dir else f"season {args.season}"
    print(f"{target_label}: {len(files)} files, {total} results")
    print(f"mapped: {mapped}, review: {len(all_review)}")
    print("\n=== mapping (raw -> official) ===")
    for (raw, official), cnt in sorted(all_counts.items(), key=lambda kv: (-kv[1], kv[0][0])):
        print(f"{cnt:5d}  {raw!r:60s} -> {official!r}")
    if all_review:
        print("\n=== REVIEW (discipline left unchanged) ===")
        for item in all_review:
            print(f"{item['file']}: {item['athlete']!r} raw={item['raw']!r} reason={item['reason']}")
    else:
        print("\nno review items — all results mapped")

    if not args.dry_run and all_review:
        print("\nNOTE: review items were left unchanged; re-run after fixing rules.")
    if not args.dry_run:
        report_path = None
        if args.json_dir:
            # json/ re-maps get their own report, never the season one
            report_path = REPO_ROOT / args.json_dir / "discipline_mapping_report.md"
        report = write_report(None if args.json_dir else args.season,
                              len(files), total, all_counts, all_review,
                              out=report_path, label=target_label)
        print(f"\nreport: {report}")

if __name__ == "__main__":
    main()
