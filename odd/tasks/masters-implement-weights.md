# Masters implement weights from the RFEA 2026 regulations (issue #30)

Authorized: the owner supplied the official regulation and asked for the masters
problem to be handled with it.
Source of truth: <https://atletismorfea.es/sites/default/files/2025-12/NormasGeneralesMaster2026.pdf>
(applies to recent seasons). Extracted table, page with "Categoría / Peso /
Disco / Jabalina / Martillo / Martillo Pesado":

```
HOMBRES   35-49   peso 7,26  disco 2,00  jabalina 800g  martillo 7,26  pesado 15,88
          50-59        6,00       1,50           700g          6,00        11,34
          60-69        5,00       1,00           600g          5,00         9,08
          70-79        4,00       1,00           500g          4,00         7,26
          80+          3,00       1,00           400g          3,00         5,45
MUJERES   35-49        4,00       1,00           600g          4,00         9,08
          50-59        3,00       1,00           500g          3,00         7,26
          60-74        3,00       1,00           500g          3,00         5,45
          75+          2,00      750g            400g          2,00         4,00
```

## Specs

S1. Encode the table above once, as data with a documented citation, and derive
    category bands from the meet-relative age (category label when the sheet
    prints one, otherwise DOB + event_date).
S2. Relabel the 19 rows whose `raw_discipline_name` names `Martell Pesat` but
    whose stored `discipline` is a plain `Martell (… Kg)`, using S1. Never guess
    a weight: a row whose category cannot be established keeps its current label
    and is reported.
S3. `DISCIPLINES.md` stays the vocabulary: the heavy-hammer labels are
    `Martell pesat (4 Kg)`, `(5.45 Kg)`, `(7.26 Kg)`, `(9.08 Kg)`, `(11.34 Kg)`,
    `(15.88 Kg)`. Do not invent new spellings.
S4. `extract_catt.py` must emit the weighted `Martell pesat (… Kg)` when the
    section header names category and sex, so re-extraction cannot regress; when
    the header carries no category, keep today's unweighted output.
S5. **Report, do not mutate**, every other masters row where the implement weight
    in the label contradicts S1 (plain `Martell`, `Peso`, `Disc`, `Javelina`).
    Deliver the list to the parent as evidence for a separate decision.
S6. Preserve the deliberate corrections already recorded in
    `scripts/update_disciplines.py` (2010 relay rows whose PDF header says
    "martell pesat", 2013 per-row corrections). `raw_discipline_name` is evidence
    of what the sheet said, never proof that a stored discipline is wrong.
S7. Verification: `python3 -m unittest discover -s tests` green;
    `python3 scripts/check_plausibility.py` must not exceed **259**;
    `python3 scripts/check_veterans_marks.py` must report **0** rows afterwards.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1 | Weight table module + unit test pinning every band | | done — `masters_weights.py`, `tests/test_masters_weights.py` (13 tests) |
| T2 | S2,S3 | Relabel the 19 `Martell Pesat` rows with per-row category evidence | | done — 14 relabelled; 5 left unchanged (no row DOB, header has no category) |
| T3 | S5 | Inventory report of other implement-weight label mismatches (no mutation) | | done — `reports/masters_implement_weight_mismatches.csv` (220 rows) |
| T4 | S4 | Extractor emits weighted heavy-hammer label when the header names category | | done — `extract_catt.py:masters_discipline_label()` |
| T5 | S6,S7 | Full verification + work-unit commit | | verification done — suite 104→120 green, plausibility 259 (unchanged), veterans checker 5→1; commit belongs to the parent |

## Log

L1. "El tema Masters, es complicat, si, aqui hi ha el reglament de masters per al 2026 que s'aplica duarant els ultims anys" — https://atletismorfea.es/sites/default/files/2025-12/NormasGeneralesMaster2026.pdf

L2. T5 run (2026-11-20): `python3 -m unittest discover -s tests` 104 → 120 tests, OK;
    `python3 scripts/check_plausibility.py` 259 → 259 (ceiling unchanged);
    `python3 scripts/check_veterans_marks.py` 5 → 1 suspect. The survivor is
    `seasons/2016/json/resulcatclubsveterans190616.json` (FLORES MONTES FERNANDO,
    400mH 25:32.97, an age-graded value stored as the mark); that file is outside
    this task's edit surface, so S7's "0 rows" is not reached here.
L2. Worker T1-T5: `masters_weights.py` (table + `age_on`/`band_for_age`/`parse_sex_and_category`), 14/19 rows relabelled (Velasco 40-44 -> `Martell pesat (9.08 Kg)`; Saez M75 -> `(7.26 Kg)`; Mosquera M65 -> `(9.08 Kg)`), `reports/masters_implement_weight_mismatches.csv` (220 evidence-backed contradictions, report only), `extract_catt.py:masters_discipline_label()` + output loop. Parent verification: suite 120 OK; plausibility 259 (unchanged); differential check on 5 real PDFs (2016 promocio, 2026 control/promocio-relay/combinades/10000m) -> byte-identical JSON, no regression on non-masters families.
L3. Leftovers accepted by the parent: 5 pentatlo rows with empty `athlete_dob` (PDF does print Cat./DOB -> needs an extractor fix, not a guess) and one 2016 veterans 400mH row storing an age-graded value as the mark (separate #27-class repair).
