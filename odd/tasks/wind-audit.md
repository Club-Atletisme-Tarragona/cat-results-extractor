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
| T1 | S1 | PDF-side wind extraction per row (series header + jump wind line) | | pending |
| T2 | S2 | Classify every null wind-applicable row; emit the CSV + summary | | pending |
| T3 | S4 | `is_short_track` contract report | | pending |
| T4 | S5 | Verification + report the real defect size by family | | pending |

## Log

L1. si (attack wind: #21 + #25)
L2. Measured: #21 wind half = 0 rows; #25 naive = 7,170 null wind-applicable rows, of which 4,245 indoor-ish and 6,261 jumps/combined.
