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

## Precedence rule (owner decision, L5)

**The printed result wins; the regulation is the fallback.**

S8. If the source sheet prints the implement weight (section header or row, e.g.
    `Martell (7,26 kg)`, `Pes 4 kg.`, `Javelina 800 g`), that weight is stored
    **even when it contradicts** the RFEA table. The sheet is the record of what
    was actually thrown.
S9. Only when the sheet prints no weight does the RFEA 2026 table decide it,
    from the printed category and sex (S1).
S10. The discriminator is `raw_discipline_name`, which stores the header text
    verbatim: it prints a weight or it does not. Never infer "the PDF printed
    it" from the stored label.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1 | Weight table module + unit test pinning every band | | done — `masters_weights.py`, `tests/test_masters_weights.py` (13 tests) |
| T2 | S2,S3 | Relabel the 19 `Martell Pesat` rows with per-row category evidence | | done — 14 relabelled; 5 left unchanged (no row DOB, header has no category) |
| T3 | S5 | Inventory report of other implement-weight label mismatches (no mutation) | | done — `reports/masters_implement_weight_mismatches.csv` (220 rows) |
| T4 | S4 | Extractor emits weighted heavy-hammer label when the header names category | | done — `extract_catt.py:masters_discipline_label()` |
| T5 | S6,S7 | Full verification + work-unit commit | | verification done — suite 104→120 green, plausibility 259 (unchanged), veterans checker 5→1; commit belongs to the parent |
| T6 | S8,S9,S10 | Precedence resolver in `masters_weights.py` (printed weight first, table as fallback), test-first | | done — `resolve_implement_weight()`, `decide_implement_label()`, `parse_printed_weight()`, `label_for_weight()`; 41 unit tests in `tests/test_masters_weights.py` |
| T7 | S8,S9,S10 | Apply the rule to the 220 report rows + regenerate the worklist | | done — 218 relabelled / 2 already correct / 0 left undecided; worklist regenerated: 34 rows `pending-apply`, 0 `unresolved` |
| T8 | S8,S9 | `extract_catt.py` prefers the printed weight, table only as fallback | | done — `masters_discipline_label(prova, dob, event_date)`; non-masters output unchanged |
| T9 | S7 | Verification: suite, plausibility 259, veterans 0, 5-PDF differential | | done — 152 OK; 259; 0; 5/5 fixtures byte-identical |

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
L4. Parent closed the leftovers with PDF evidence from `pdf_cache/2016/`:
`resulcatpentatlollancamentsveterans180916.pdf` prints `LLANÇAMENT DE MARTELL PESAT FEMENI`
with category per row -> PRADILLO GUTIERREZ MARISA `W-55` (rows 5.99/6.58 -> `Martell pesat (7.26 Kg)`)
and VELASCO MARTI ANA CRISTINA `W-40` (6.33/5.69/6.06 -> `Martell pesat (9.08 Kg)`), so the 5 rows
the worker reported as unresolvable are now relabelled from printed evidence, not a guess.
Also `resulcatclubsveterans190616.pdf`: FLORES MONTES FERNANDO's `25:32,97` sits under
`5000 MARXA MASCULÍ` but was stored as `400 METRES TANQUES MASCULÍ` (section leak) -> `5000 metres marxa`;
URBANO FLORES MARIA ANGELES printed no MARCA (only `Ref. 127,02`) -> entry dropped.
`check_veterans_marks.py` now always rewrites `--csv` (header only when clean) so a clean run cannot
leave a stale worklist; covered by `TestVeteransWorklistStaysHonest`.
Verification: suite **121 OK**; plausibility **259** (unchanged); veterans checker **0** suspects.
Remaining, tracked separately: the parser still needs to recognise `5000 MARXA` sections and to skip
empty-MARCA rows, so re-extraction cannot regress these two repairs.
L5. "si el resultat original indica el pes, mana el resultat original, quan no quedi clar, fem fallback al document" — owner precedence rule (S8-S10).
L6. T6 (worker): the rule lives in one place. `resolve_implement_weight(implement, sex,
    category_band, printed_weight) -> (kg, authority)`; authority is `printed` / `table` /
    `unparseable` / `unresolved`. An unparseable printed weight does NOT fall back to the
    table: substituting the regulation weight would overwrite what the sheet said it threw.
    `decide_implement_label(raw_discipline_name, dob, event_date)` is the single decision
    point (header category first, DOB + meet date as the S1 fallback) and returns the
    DISCIPLINES.md label plus the authority and the weight. Spellings live in
    `IMPLEMENT_WEIGHT_LABELS` and are pinned against `DISCIPLINES.md` by a test, so a
    weight with no official spelling is reported (`no-spelling`) instead of invented.
    Two narrow reading rules were added from the data, both tested: `MAS.`/`MASC.`
    (uppercase only, so the Catalan word `mas` is never a sex) and a bare `k` as
    kilograms inside a throw header (`Pes (3k) Fem. PC 50-54`). `lb`/`oz` are reported
    as `unparseable`; category markers such as `SF`/`MF40` are not read as units.
L7. T7 (worker): 220 inventory rows re-decided from `raw_discipline_name` only.
    **218 relabelled, 2 already correct, 0 undecided.** 38 rows decided by a printed
    weight (25 x `Pes (3 Kg)`, 11 x `Javelina (500 g)`, 2 x `Pes (4 Kg)` — the last two
    are `Peso (4kg) Mujeres PC Master F55`, where the print matches the stored label);
    182 decided by the table (pes 3/5/6 kg, javelina 500/600/700 g, disc 1/1,5 kg,
    martell 3/4/5 kg, and 2 heavy-hammer rows from `Martillo Pesado … M50/M75`).
    Only `discipline` changed per row; each file was written through a sibling temp file
    and `os.replace()`, and the writer asserts that no other field differs. No spelling was
    missing from `DISCIPLINES.md`. None of the 20 files carries an entry in
    `scripts/update_disciplines.py` (checked programmatically against every filename-keyed
    map in that file), and the 2013 per-row corrections live in other files; per-row
    corrections are also re-checked in the worklist generator.
L8. T7 worklist (`reports/masters_implement_weight_mismatches.csv`, regenerated):
    **34 rows `pending-apply` in 9 groups, 0 `unresolved`.** `pending-apply` = the rule
    decides the label but the row was outside the 220-row inventory this unit was
    authorised to change, so applying it is a follow-up decision:
    `resulcatveterans100612` (6 `LLANÇAMENT DE JAVELINA FEMENÍ (500 g.)` -> `Javelina (500 g)`;
    5 `… JAVELINA MASCULÍ (600 g.)` -> `Javelina (600 g)`; 6 `… PES FEMENÍ (3 KG)` -> `Pes (3 Kg)`),
    `resulcatveteranspc190212` (6 `LLANÇAMENT DE PES (3 KG.) FEMENÍ` -> `Pes (3 Kg)`),
    `resulcatveterans120616` (4 `Javelina Vet. MAS. 60-64` -> `Javelina (600 g)`),
    `resulcatveterans70615` (4 `Disc Vet. MAS. 50-54` -> `Disc (1,5 Kg)`),
    `resulcnatterritcombinadescambrils230515` (1 `Disc Màster 1,5 kg` -> `Disc (1,5 Kg)`),
    `resultat-20250927-…lhospitalet` (2 `Martillo Pesado Mujeres 35-49 MF40/SF` ->
    `Martell pesat (9.08 Kg)`). The three 2012 groups and the two `Martillo Pesado` rows
    were missed by the T3 scan: it required a category/DOB before it could compute an
    expected weight, while the printed weight alone decides those rows.
L9. T7 non-worklist class: 292 masters rows print no weight, the header names no category
    and the row stores no `athlete_dob` (`LLANÇAMENT DE PES MASCULÍ` in 2006-2016 era sheets,
    the `resulcatpentatloveterans*` tables). Nothing about the weight can be decided from the
    stored data — the PDFs carry a per-row category/birth-year column that the era parsers do
    not store (the same gap L3/L4 recorded). Not listed row by row: there is no weight
    evidence to apply, and the fix is an extractor one (read the per-row category column).
    The worklist generator re-applies the `scripts/update_disciplines.py` correction test
    (whitespace-collapsed raw prefix, accents stripped on the athlete), which excludes 13
    further rows that carry a documented correction — e.g. MONTSE GUINOVART's
    `DISC Cadet Femení 800 g` row, whose stored `4x100` is right because the mark is the
    relay's `58.36`, not a discus throw.
L10. T8: `masters_discipline_label(prova, dob=None, event_date=None)` now composes the
    weighted DISCIPLINES.md label for every masters implement section (printed weight first,
    then table from header category, then DOB + meet date) and leaves everything else
    verbatim. `is_masters_section()` gates it, so age-group sheets are untouched. On the 16
    repaired files whose PDFs are cached, a previous-vs-new extractor diff changes 256 rows
    and every one is a masters implement row gaining its official weighted label
    (`Disc VET. Fem. 50-54` -> `Disc (1 Kg)`, `Javelina Vet. MAS. 65-69` -> `Javelina (600 g)`,
    `Martell Homes Master M65` -> `Martell (5 Kg)`, `Disco (1,5 Kg) Hombres Master M50` ->
    `Disc (1,5 Kg)`, …). Re-extraction reproduces 237/259 stored masters implement rows; the
    22 misses are 10 `pending-apply` rows (the extractor already emits the rule's label) and 12
    2014 shot rows whose only difference is a comma in the athlete name (era-parser drift).
L11. T9 verification (worker, 2026-11-21): `python3 -m unittest discover -s tests` 121 -> **152
    OK**; `python3 scripts/check_plausibility.py` **259** (unchanged);
    `python3 scripts/check_veterans_marks.py` **0** suspects. Differential vs `HEAD` on the five
    named fixtures: byte-identical JSON, all five
    (`resulcontrolvalls60216`, `resultat-20260418-territorialpromociovalls`,
    `resultat-20260502-controlvelocitatmaigtarragona`,
    `resultat-2026050203-territorialcombinadestarragona`,
    `resultat-20260426-cat10000marxamastergava`). No git command was run.
L6. Precedence implemented (worker T6-T9 + parent): `masters_weights.py` gained
`parse_printed_weight` / `resolve_implement_weight` (`printed` > `table` > `unresolved`, an unparseable
print never falls back) and `decide_implement_label`; `extract_catt.py` now prefers the printed weight.
218 of the 220 inventory rows relabelled (38 by print, 182 by table, 2 already correct); the parent then
applied the 34 `pending-apply` rows the worker left for scope (2012 veterans javelina `(500 g.)` printed vs
stored 600 g; 2025 `Martillo Pesado Mujeres 35-49` -> `Martell pesat (9.08 Kg)`), so the worklist is fully
applied (status `applied`, 0 pending, 0 unresolved).
Verification: suite **152 OK**; plausibility **259**; veterans checker **0**; 5-fixture differential on
`extract_catt.py` byte-identical; season diff touches only `discipline` (0 non-discipline lines).
Remaining and out of scope: 292 masters rows carry no weight evidence at all (no print, no header category,
no stored DOB) — needs per-row category extraction in the era parsers, not a guess.
