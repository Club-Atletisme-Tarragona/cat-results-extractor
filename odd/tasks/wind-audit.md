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

## Log

L1. si (attack wind: #21 + #25)
L2. Measured: #21 wind half = 0 rows; #25 naive = 7,170 null wind-applicable rows, of which 4,245 indoor-ish and 6,261 jumps/combined.

L3. Built `scripts/check_wind.py` + `tests/test_check_wind.py` (38 unit tests on real
    header/wind-line snippets). Full pass over 22 seasons / 1,330 JSON files / 1,330
    PDFs: **2m45s**, idempotent (byte-identical CSV on a repeated run), no write
    outside `reports/` (and `pdf_cache/`, where 76 PDFs that were missing got
    downloaded; the rest of the sources were already cached).

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
