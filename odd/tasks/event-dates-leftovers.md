# Event dates: leftover mismatches vs PDF headers (issue #28)

Authorized: user said "si" to continuing with #28 after #31.
Parent: GitHub issue #28 — leftovers after the rule-level fix `c757a48`
(175 dates corrected by rule: 126 zero-padding, 49 filename-misread months).

## Specs

S1. Worklist: `reports/event_date_manual_review.csv` (37 lines at the time of
    writing), produced by `scripts/check_event_dates.py`.
S2. Class A — "span-2-dies": stored and header dates differ by 1–3 days inside
    the same month/year because the meeting ran over several days. Resolve by
    reading which day CA Tarragona's events actually took place. When the sheet
    genuinely spans both days with no per-session date, **keep the stored date**
    and record why — never flip a coin.
S3. Class B — "revisio-manual": the dates genuinely disagree. Each needs the
    PDF open; a header date wins **only** when it is the meeting header.
S4. Never take a date from a Conersys generation stamp (weekday present), a
    record line (`RCAT`/`RCAM`), or a birth date. `parse_header` already skips
    them; manual edits must too.
S5. A corrected date that crosses a year boundary moves the file with
    `scripts/move_json_to_season.py`, then `scripts/update_disciplines.py` and
    `scripts/add_internal_id.py` re-run as the pipeline requires.
S6. Every change states its evidence: the header text read from the PDF, which
    of the two dates it supports, and why the other one is rejected.
S7. Verification: suite green; `scripts/check_plausibility.py` must not exceed
    **259**; the audit re-runs to a **shrinking** worklist (every remaining row
    must be a documented "keep stored" decision, not an open question).

### Audit findings (2026-11-22, `scripts/check_event_dates.py`)

1330 files: `date_mismatch=55`, `header_no_date=113`, `download_fail=21`.
Of the 55, **15 are formatting noise** (`26/4/2006` vs `26/04/2006` — same day,
the audit compares strings) and **40 are genuine**.

Dominant family in the 40: a **glued leading zero** in the DDMMYY filename is
read as a two-digit day (`resulcatclubsalevial20416` → stored 20/4/2016,
header 02/04/2016; same for `30416`, `20213`, `13140216`). The header is
authoritative there and the filename encoding confirms it.

Suspicious headers that must NOT be trusted blindly (year far from the file's):
`resulcatcadetpc2122209` (header 26/02/**2005**), `resullliguetasub11bcn71115`
(header 23/07/**2009**), `resultat-20260117-gpmarxaelvendrell` (header
25/08/**2007**), `resultpromociomataro31015`, `resultrofeucalsmarxa30116`.
Read the PDF; if the line is a record/stamp line, keep the stored date and say so.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1 | Fix the audit: compare parsed dates, not strings (kills 15 false rows) | | pending |
| T2 | S1 | Re-run the audit; reconcile the worklist against today's data | | pending |
| T3 | S2 | Resolve class A (span-2-dies) with per-session evidence | | pending |
| T4 | S3,S4 | Resolve class B (genuine conflicts) with header evidence | | pending |
| T5 | S5 | Move any file whose corrected date crosses a year | | pending |
| T6 | S6,S7 | Verification + work-unit commit; report kept-stored decisions | | pending |

## Log

L1. si (continue with #28 after #31)
L2. Audit re-run: 55 mismatches -> 15 formatting-only, 40 genuine (glued-leading-zero family dominant).
