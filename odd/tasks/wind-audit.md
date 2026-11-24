# Wind: measure before touching (issue #25)

Authorized: user said "si" to attacking wind (#21 + #25 together) after #23 closed.
Parent: GitHub issue #25 — results in wind-applicable outdoor events exported with
`wind: null` though the source PDF records it.

## What is already true (measured now)

- **#21's wind half is resolved**: `wind_applicable(discipline)` against every row in
  `seasons/*/json/` gives **0** rows with a non-null `wind` on an event where wind does
  not apply (throws, long distance, relays).
- **#25 is large and unmeasured from the PDF side.** A naive count says **7,170** rows
  in wind-applicable events with `wind: null`, but that number mixes three very
  different things:
  - **4,245** rows involve 60 m / indoor-style disciplines, of which **1,412** sit in
    files marked `is_short_track: true` (legitimately no wind) and **2,833** sit in
    files **not** marked indoor — some of those files are indoor meets whose
    `is_short_track` contract flag is wrong, not a wind bug.
  - **6,261 "other"** rows, dominated by `Llargada` (2,644) and `Triple` — many are
    combined-event attempts, where the sheet does not print a per-attempt wind.
  - A small remainder in genuine sprint/hurdle/jump sections.

So the work cannot start with data edits: it needs a PDF-side denominator.

## Specs

S1. Build `scripts/check_wind.py`: for a given season or file set, reopen the source
    PDF (`pdf_cache/` first, `event_src` only when missing) and decide, **per row**,
    whether the sheet actually prints a wind value for that athlete's mark:
    - sprint/hurdle rows: the `Vent:`/`Viento:` header of that series, or a wind column,
    - jump rows: the wind line under the attempts,
    - absent/blank/`Nul`/`-`: no wind on the sheet.
S2. Classify every currently-null wind-applicable row into exactly one of:
    `pdf-has-wind` (the real defect), `pdf-no-wind` (legitimate), `indoor`
    (file is a pista coberta meet), `combined-event` (no per-attempt wind printed),
    `no-pdf` (cache miss and dead URL).
S3. The script **never writes data**. It emits
    `reports/wind_audit.csv` + a per-family summary. Deciding what to fix is a later
    slice, based on the real `pdf-has-wind` count and families.
S4. Also report the `is_short_track` contract check: files whose disciplines or header
    say pista coberta while `is_short_track` is not `true`, and the reverse. That is a
    distinct defect with its own fix, but it is what makes the wind numbers readable.
S5. Verification: `python3 -m unittest discover -s tests` green;
    `scripts/check_plausibility.py` unchanged at **259**; the script is idempotent and
    reported as a dry run.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1 | PDF-side wind extraction per row (series header + jump wind line) | | done |
| T2 | S2 | Classify every null wind-applicable row; emit the CSV + summary | | done |
| T3 | S4 | `is_short_track` contract report | | done |
| T4 | S5 | Verification + report the real defect size by family | | done |
| T5 | S4 | Fix `is_short_track` for the 21 `flag-false-but-indoor` files | | done |
| T6 | S2→S5 | Re-run the audit on the fixed flags; decide the contradiction set | | done, 125 rows need a decision |
| T7 | S1 | Repair the `pdf-has-wind` rows from the sheet, per row | | done, 332 rows |

## Log

L1. si (attack wind: #21 + #25)
L2. Measured: #21 wind half = 0 rows; #25 naive = 7,170 null wind-applicable rows, of which 4,245 indoor-ish and 6,261 jumps/combined.

L3. Built `scripts/check_wind.py` + `tests/test_check_wind.py` (38 unit tests on real
    header/wind-line snippets). Full pass over 22 seasons / 1,330 JSON files / 1,330
    PDFs: **2m45s**, idempotent (byte-identical CSV on a repeated run), no write
    outside `reports/` (and `pdf_cache/`, where 76 PDFs that were missing got
    downloaded; the rest of the sources were already cached).

L4. Repair slice, in the dictated order. `is_short_track` fixed for the 21
    `flag-false-but-indoor` files (that field only), audit re-run: same
    measurement, contract report cleared.
L5. Step 2 found the contradiction the order was meant to expose: 125
    wind-bearing rows in 5 now-indoor Cambrils combined-event files. Declined
    pending an owner decision, never guessed.
L6. Repaired the remaining `pdf-has-wind` rows: 332 written, 15 skipped on a
    status mark, 1 declined as a stored-data defect, 27 `unmatched` untouched.

## Results (T1-T4)

### The denominator, measured from the sheets

10,506 rows in `seasons/*/json/` (never `imported/`) have a wind-applicable
discipline and `wind: null`. Every one of them was classified from its source PDF:

| class | rows | what it means |
|-------|------|---------------|
| `pdf-has-wind` | **473** | the sheet prints a wind for that athlete's mark — **the real defect** |
| `pdf-no-wind` | 5,586 | the sheet prints no wind for that mark (legitimate) |
| `indoor` | 3,657 | pista coberta: wind is never measured (3,336 already flagged `is_short_track: true`, 321 not) |
| `combined-event` | 763 | combined-event section: no per-attempt wind printed |
| `unmatched` | 27 | line not located / mark not found — listed in the CSV, never guessed |
| `no-pdf` | 0 | every source PDF is now in `pdf_cache` |

By family (`pdf-has-wind` / rows):

| family | rows | pdf-has-wind | pdf-no-wind | indoor | combined | unmatched |
|--------|------|--------------|-------------|--------|----------|-----------|
| sprint | 3,590 | 110 | 2,111 | 1,126 | 242 | 1 |
| hurdles | 1,499 | 141 | 607 | 622 | 129 | 0 |
| long jump | 4,765 | 213 | 2,640 | 1,494 | 392 | 26 |
| triple | 652 | 9 | 228 | 415 | 0 | 0 |

**The 7,170 figure from L2** (rows in files not flagged indoor) resolves as:
`pdf-no-wind` 5,586 · `combined-event` 763 · **`pdf-has-wind` 473** ·
`indoor` 321 · `unmatched` 27. So the defect is **6.6% of the naive count**, not
all of it.

### Where the defect is

By season: 2005 17, 2006 18, 2007 6, 2008 29, 2009 49, 2010 18, 2011 32, 2012 12,
2013 53, 2014 44, 2015 41, 2016 71, 2017 2, 2018 8, 2019 9, 2020 1, 2021 8, 2022 4,
2023 13, 2024 6, 2025 25, 2026 7. The era parsers (2005-2016) hold 390 of 473;
the modern FCAT scraper is largely correct.

By evidence kind: `series-header` 232, `attempt-wind` 222, `row-column` 19.
97 of the 473 are a literal 0.0 (`.0` is a recorded wind, not "no wind");
19 sit on a status mark (`Ret.`/`NP`), so the repair slice is ~454 rows.

By file (top of the worklist; the full list is in `reports/wind_audit.csv`):

| rows | file |
|------|------|
| 38 | `seasons/2016/json/resulcontrolcombinadescambrils19201215.json` |
| 24 | `seasons/2008/json/resulcombicambrils231207.json` |
| 22 | `seasons/2014/json/resulcombinadeshiverncambrils21221213.json` |
| 21 | `seasons/2013/json/resulcnatterritcombinadeshiverntgna22231212.json` |
| 20 | `seasons/2015/json/resulcombinadescambrils20121214.json` |
| 19 | `seasons/2016/json/resulterritcombinadescambrils300410516.json` |
| 16 | `seasons/2009/json/resulcat28609.json` |
| 16 | `seasons/2011/json/resulcatveterans12611.json` |
| 15 | `seasons/2025/json/resultat-20250215-controlfebrertarragona.json` |
| 12 | `seasons/2005/json/resulccombinades12605.json` |
| 12 | `seasons/2014/json/resulcombinadescambrils29300314.json` |
| 11 | `seasons/2010/json/resulcatveterans27610.json` |
| 10 | `seasons/2015/json/resulcontrolcambrils240115.json` |

100 files in total; the top 12 hold 48%. **125 of the 473** sit in files whose
header or disciplines say pista coberta while `is_short_track` is false: fix that
flag first, or the repair would add an indoor wind.

### `is_short_track` contract (S4)

`reports/short_track_contract.csv` — 22 files:

- **21 `flag-false-but-indoor`**: 12 proven by the PDF header ("DE PISTA COBERTA"
  combined championships 2006-2016, plus `resulcatclubsveteranspcp250114`), 9 by
  the disciplines (2025 Sabadell `...pc...` meets: every section marked `PC`, none
  marked `AL`).
- **0 `flag-true-but-outdoor`**: no file claims indoor without evidence.
- 1 `unverified-no-pdf`: `2026/resultat-20260621-catsub1823girona` (URL 404s).

The signal is "some section is marked `PC` and no section is marked `AL`", not a
share threshold: a mixed meeting (e.g.
`2025/resultat-20250215-territorialcombinadessub1214tarragona`, which prints
`60m S14 Hombres AL` next to `60m S12 Hombres PC`) runs part of the day outdoors
and is not an indoor meet.

### Verification (S5)

- `python3 -m unittest discover -s tests` → **246 tests OK** (208 before, +38 new).
- `python3 scripts/check_plausibility.py` → **259**, unchanged.
- The audit is a dry run and never writes data: `seasons/` untouched, only
  `reports/*.csv` written (plus `pdf_cache/` for missing PDFs).
- Repeated run on the same seasons → byte-identical CSV.

### Reuse

`check_wind.py` imports `wind_applicable`, `extract_text` and `detect_short_track`
from `extract_catt.py`. `wind_applicable` is the single source of truth for which
rows to audit; `extract_text` is the only text path (`pdftotext -layout`, never
pdfplumber). **No helper needed to become public.** The jump wind helpers
(`extract_jump_wind`, `extract_all_attempts_from_name_line`) are extraction
heuristics that return only the best-mark wind and require a club line; the audit
needs per-attempt alignment with its own evidence string, so it keeps that logic
local rather than bending an extractor helper into a measuring tool.

### What could not be decided (27 rows, in the CSV as `unmatched`)

- `no-attempts` (17) / `attempt-not-found` (6): the mark is not inside the
  athlete's block — 10 of them are **stored data defects** (see risks), the rest
  are layouts where the attempts are not printed next to the name.
- `wind-line-misaligned` (2, `2007 ORIOL PAISANO AGUSTI Llargada 5.31`, `2013
  ALICIA VAZQUEZ DOMINGO Llargada 4.59`): a wind line exists but no value sits
  under that attempt column.
- `athlete line not found` (2): `2008 IBORRA MARTINEZ FRANCISCO JOSE` (the sheet
  prints `IBORRA MARTINEZ, FRANCISCO`, a different tokenisation).
- 3 of the 27 carry a status mark (`NP`/`N.P.`).

### Open risks found but not fixed (out of scope)

- **Impossible long jumps in the data**: `PAREDES LARIO RUBEN` stored as
  `Llargada 20.49 / 20.88 / 22.24 / 23.18 / 24.56 / 25.55 / 26.02 / 26.83`,
  `ARIZA CASABON DANIEL Llargada 64.96`, `HERNAN FERRAN JIMENEZ Llargada 18.92`
  (raw name `Longitud SUB8`). These are extraction defects of their own era
  parsers; they are why some rows cannot be matched to a sheet line.
- **The `discipline` field sometimes carries a section header plus a mark**:
  `"SALT DE LLARGADA BENJAMÍ FEMENÍ 23,18"`, `"SALT DE LLARGADA FEMENÍ 2.4"`.
- Sheets print `VENT : - 0,0`; the audit keeps it as `-0.0` rather than
  normalising a value it must not change.
- 60 m flat is a legitimately wind-applicable outdoor distance (youth meets run it
  outdoors with no wind header); those rows land in `pdf-no-wind`, which is why
  the 60 m share of the naive count is not all defect.

## Repair slice (T5-T7)

Order was the point: the `is_short_track` contract first, so that a wind is never
written into a row whose own file says pista coberta.

### T5 — `is_short_track` for the 21 contract files (flag only)

All 21 `flag-false-but-indoor` files in `reports/short_track_contract.csv` now
carry `"is_short_track": true`. 12 are proven by the PDF header
(`DE PISTA COBERTA` combined championships 2006-2016, plus
`resulcatclubsveteranspcp250114`), 9 by the disciplines (2025 Sabadell `...pc...`
meets: every section marked `PC`, none marked `AL`). The 22nd row of the report
(`2026/resultat-20260621-catsub1823girona`, URL 404s) is left alone - unverified.

`git diff -U0 -- seasons/` at that point: 21 removed `"is_short_track": false`,
21 added `"is_short_track": true`. Nothing else.

### T6 — re-audit after the flag fix, and the contradiction it exposes

`reports/short_track_contract.csv` clears to the single `unverified-no-pdf` row:
every file now agrees with its own evidence. `reports/wind_audit.csv` is
**byte-identical** to the pre-fix run (473 `pdf-has-wind`), because the audit
classifies from the sheet and the sheet does print those winds - there is even a
test pinning that order (`test_printed_wind_beats_indoor`: a value printed by an
indoor sheet is still a printed value).

So the 125 rows do not reclassify; they are the contradiction to decide:

| rows | file | the sheet prints |
|------|------|------------------|
| 38 | `2016/resulcontrolcombinadescambrils19201215` | `VENT : -0,9` per series |
| 24 | `2008/resulcombicambrils231207` | per-series `VENT` + jump wind lines |
| 22 | `2014/resulcombinadeshiverncambrils21221213` | per-series `VENT` |
| 21 | `2013/resulcnatterritcombinadeshiverntgna22231212` | per-series `VENT` |
| 20 | `2015/resulcombinadescambrils20121214` | per-series `VENT` |

All five are the December Cambrils combined championships headed
`CAMPIONAT TERRITORIAL DE PROVES COMBINADES / DE PISTA COBERTA`, and all five
print a wind for the sprint/hurdle series (values like `+1.7`, `-0.9`, `+0.1`;
48 of the 125 are a literal `0.0`). Two readings fit and the sheet alone does not
choose: either the meet ran outdoors despite the title, or the timing software
prints its wind field indoors too. **These 125 rows are not repaired.** Storing
an indoor wind contradicts the `is_short_track` contract that was just asserted;
discarding a printed measurement without evidence would also be a guess. Owner
decision needed: (a) keep them indoor and null, and treat the printed wind as
template noise; or (b) if the meet was outdoor, revert the flag for that file and
re-run the repair for its rows.

### T7 — the repair (332 rows, 92 files)

Only the remaining `pdf-has-wind` rows were written, each with the value
`reports/wind_audit.csv` already recorded for it (`wind_on_sheet`, located by the
audit's own tested evidence: series header, attempt wind line, row column).

- **repaired: 332** rows in 92 files - long jump 196, sprint 68, hurdles 59,
  triple 9. 43 of them are a zero wind.
- **skipped, status mark: 15** - the mark is `NP`/`Ret.`/`RET.`, so there is no
  mark to attach a wind to: `2006 BERNAT ROCAMORA CHAPARRO` 200 m `RET.`;
  `2014 DÍDAC ALONSO DEL CAMPO` 100m TQ `Ret.`; `2016 JOSEP MARIA MATEO SANZ`
  100m TQ `Ret`; `2018 Aina Tomas Virgili` / `Cristina Reyes Alcantara` 60m TQ
  `NP`; `2019 Ruth Martinez Rosillo` 220m valles `NP`; `2023 Carla Borras
  Verges` + `tapiro CF 4` 60m/80m valles/100m `NP` (4); `2023 Enzo Mate Gras`
  150m `NP`; `2024 Ferran` + `Marius Badia Riera` 220m valles `NP`.
- **declined, 1**: `2016 PRADILLO GUTIERREZ MARISA Llargada 2.30` - the stored
  mark is not a mark (her sheet MARCA is 3,14 and her attempts are 3,05-3,14);
  the audit aligned it to the `VENTS` table where `2,30` is her 6th wind. A
  stored-data defect, not a wind one.
- **declined, 125**: the contradiction set above.
- **unmatched: 27 rows, unchanged** - listed in `reports/wind_audit.csv`, still
  never guessed.

Conventions, checked against what the dataset already did rather than invented:

- spelling is `sign + one decimal`; zero is stored as `+0.0`, the spelling 994
  existing rows already use, so `-0.0` and `+0,00` land there too (a signed zero
  is the same measurement). 5 rows were printing `-0.0`, 4 were `+0.00`.
- the two decisions this slice added are pinned by tests in
  `tests/test_check_wind.py` (`TestWindSpelling`): zero-wind spelling and the
  status-mark skip. `format_wind()` lives in `check_wind.py` and only
  normalises spelling - it never invents a value and refuses anything out of the
  measuring range. The audit itself stays read-only.

### Verification

- `python3 -m unittest discover -s tests` → **252 tests OK** (246 before, +6).
- `scripts/check_plausibility.py` → **259**, unchanged (the ceiling).
- `scripts/check_wind.py`, class counts after T6 and after T7:

  | class | before | after T6 | after T7 |
  |-------|--------|----------|----------|
  | `pdf-has-wind` | 473 | 473 | **141** |
  | `pdf-no-wind` | 5,586 | 5,586 | 5,586 |
  | `indoor` | 3,657 | 3,657 | 3,657 |
  | `combined-event` | 763 | 763 | 763 |
  | `unmatched` | 27 | 27 | 27 |
  | rows audited | 10,506 | 10,506 | 10,174 |

  The 141 left are exactly the accounted remainder: 125 contradiction + 15 status
  + 1 declined. Nothing else moved class.
- `git diff -U0 -- seasons/`: 332 `"wind": null` → value, 21 `"is_short_track"`
  false → true, and nothing else. Every written value matches `[+-]d.d`.
- Per file, the JSON is byte-identical apart from the changed `wind` values
  (structurally asserted: same keys, same row count, no other field touched;
  written through a sibling temp file + `os.replace()`).
- `#21`'s invariant holds after the repair: **0** rows carry a wind on a
  discipline `wind_applicable()` rejects; rows with a wind went 6,578 → 6,910.
- `reports/wind_audit.csv` now lists the 10,174 rows still null; the pre-repair
  measurement (10,506 rows, 473 `pdf-has-wind`) is the committed version at
  `657c4d29`.

### Risks found in this slice (not fixed)

- **Team-shaped athlete names under individual disciplines**: `tapiro CF 4` and
  `tapiro SF 4` are stored as athletes in `2023/resultat-20230415-...cambrils`
  under `60m`/`80m valles`/`100m`. They only surfaced because their marks are
  `NP`, so they were skipped, but the rows exist.
- **2-decimal and unsigned wind values already in the dataset** (`1.61`, `1.48`,
  `0.0`, `1.6`, …): ~500 pre-existing values do not follow the `sign + one
  decimal` contract. They were not written by this slice and were left alone;
  normalising them is a separate, mechanical slice if the loader cares.
- **The VENTS-table layout** (a second table below the marks table, one line per
  athlete) is what defeated the audit for the `PRADILLO` row; a future audit
  revision could look the wind up in that table by athlete instead of by column.
L7. Parent decision on the 125 rows the repair slice stopped at (the December Cambrils
combined championships). Evidence read from all five PDFs: every one contains **only
`60 METRES LLISOS` and `60 METRES TANQUES`** — no 100 m anywhere — and each is titled
`… PROVES COMBINADES / DE PISTA COBERTA`. So they are indoor pentathlons, `is_short_track:
true` is right, and the per-series `VENT : -0,9` is the timing template printing a field
that does not apply indoors (48 of the 125 are a literal `0.0`, which fits a placeholder).
**Rule adopted: indoor beats a printed wind.** `check_wind.decide()` now classifies a row
as `indoor` when the file is indoor or the row's own section says `PC`, and notes
`printed-wind-not-applicable` instead of promoting it to a defect. `test_printed_wind_beats_indoor`
was replaced by `test_indoor_beats_printed_wind` for the same reason. The 125 rows keep
`wind: null`; their sheets' VENT column is not a measurement.
