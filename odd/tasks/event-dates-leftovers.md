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
| T1 | S1 | Fix the audit: compare parsed dates, not strings (kills 15 false rows) | | done |
| T2 | S1 | Re-run the audit; reconcile the worklist against today's data | | done |
| T3 | S2 | Resolve class A (span-2-dies) with per-session evidence | | done |
| T4 | S3,S4 | Resolve class B (genuine conflicts) with header evidence | | done |
| T5 | S5 | Move any file whose corrected date crosses a year | | done |
| T6 | S6,S7 | Verification + work-unit commit; report kept-stored decisions | | done (commit left to the parent) |

## Result (2026-11-22)

| Metric | Before | After |
|--------|--------|-------|
| `date_mismatch` (open) | 55 (15 formatting-only) | **0** |
| documented keep-stored | 0 | **19** (`reports/event_date_manual_review.csv`) |
| `download_fail` | 21 | 4 (2025/2026 URLs dead; none is a mismatch) |
| test suite | 153 tests OK | 171 tests OK |
| `scripts/check_plausibility.py` | 259 | 259 (ceiling 259) |

T1 fix: `check_event_dates.parse_date()` / `dates_conflict()` compare
`datetime.date` values, so `26/4/2006` and `26/04/2006` are one day. The audit
also reads `pdf_cache/<season>/` (1255 cache hits vs 75 live downloads) and
writes through a sibling temp file + `os.replace()`.

S7 needs the worklist to be a to-do list, so "keep stored" decisions live in
`KEEP_STORED` in `scripts/check_event_dates.py`, each pinned to the exact
stored/header pair it was decided on. If either date moves the row stops
matching and resurfaces as an open mismatch; a stale decision cannot hide a
regression. The audit renders them into `reports/event_date_manual_review.csv`
with its evidence.

### A. Dates corrected (23 files, header is the meeting header)

| File | Stored | New | Evidence (header text read from the PDF) |
|------|--------|-----|------------------------------------------|
| 2007/resulcatjuvenil2007.json | 20/07/2007 | 17/06/2007 | `Estadi Municipal Josep Molins de Sabadell, 17 de juny de 2007`; single-day sheet, no session dates. The stored 20/07 has no support in the file. |
| 2008/resulcontrolcd-jvpc26108.json | 26/10/2008 | 26/01/2008 | `Vilafranca del Penedès, 26 de gener de 2008`; filename `26108` = 26/01/08 — October came from misreading `01`. |
| 2010/resulcambrils16110.json | 16/11/2010 | 16/01/2010 | `Cambrils 16/01/10`. |
| 2011/resulcnatterritsub13equips29111.json | 29/11/2011 | 29/01/2011 | `Cambrils 29/01/11`. |
| 2012/resulcontrolprimaveracambrils230612.json | 23/06/2012 | 03/06/2012 | `Cambrils 02 i 03/06/12` on every page. Stored 23/06 is outside the printed span; the sheet has no per-session split, so the closing day (dataset convention for multi-day sheets) is used. |
| 2013/resulcatcadetpc30313.json | 30/3/2013 | 03/03/2013 | `Sabadell, 3 marzo 2013`; filename `30313` is the glued `03/03/13`. |
| 2013/resulcatinfantilpcprevia20313.json | 20/3/2013 | 02/03/2013 | `Sabadell, 2 marzo 2013`; filename `20313` = `02/03/13`. |
| 2013/resulcatjunior120613.json | 12/06/2013 | 02/06/2013 | `Estadi Municipal d'Igualada, 1-2 junio 2013`; session dates show CA Tarragona on 01/06 (Torrademe 13.90, Guinovart 1.46, Tibau 9.25) and 02/06 (Guinovart 5.03, Montañes 32.42). Stored 12/06 is outside the span; closing day kept and registered (see B). |
| 2013/resulcontrolbenaleinfelprat10613.json | 10/6/2013 | 01/06/2013 | `El Prat de Llobregat, 1 de juny de 2013`. |
| 2013/resulcontrolcadetpc20213.json | 20/2/2013 | 02/02/2013 | `Sabadell, 2 febrero 2013`. |
| 2013/resulcontroljuvjunpc20213.json | 20/2/2013 | 02/02/2013 | `Sabadell, 2 febrero 2013`. |
| 2013/resulterritinfantilcambrils20213.json | 20/2/2013 | 02/02/2013 | `Cambrils, 02 / 02 / 2013`. |
| 2015/resulcatjuvenilpc10315.json | 10/3/2015 | 01/03/2015 | `Sabadell (Pista Coberta de Catalunya), 1 marzo 2015`. |
| 2015/resulccampmany10715.json | 10/7/2015 | 01/07/2015 | `Barcelona (Estadi Joan Serrahima), 1 julio 2015`. |
| 2015/resulccampmany30615.json | 30/6/2015 | 03/06/2015 | `Barcelona (Estadi Joan Serrahima), 3 junio 2015`. |
| 2015/resulcllancaments10215.json | 10/2/2015 | 01/02/2015 | `Barcelona (Estadi Joan Serrahima), 1 febrero 2015`. |
| 2015/resulcontrolabspc10215.json | 10/2/2015 | 01/02/2015 | `Sabadell (Pista Coberta de Catalunya), 1 febrero 2015`. |
| 2015/resultpromociomataro31015.json | 31/01/2015 | 03/10/2015 | `3a. Jornada Trofeu Promoció / Mataró, 3 d'octubre de 2015`; filename `31015` = 3/10/15. |
| 2016/resulcatclubsalevial20416.json | 20/4/2016 | 02/04/2016 | `El Prat de Llobregat, 2 abril 2016`; filename `20416` = `02/04/16`. |
| 2016/resulcatclubsbenjamial30416.json | 30/4/2016 | 03/04/2016 | `El Prat de Llobregat, 3 abril 2016`; filename `30416` = `03/04/16`. |
| 2016/resulcatclubscadetal30416.json | 30/4/2016 | 03/04/2016 | `El Prat de Llobregat, 3 abril 2016`. |
| 2016/resultrofeucalsmarxa30116.json | 30/11/2016 | 03/01/2016 | `XXII Trofeu Marxa Rossend Cals / Barcelona-SE, 3 enero 2016`; filename `30116` = 3/01/16. |
| 2017/resultat-20170407-gpmarxasantcugat.json | 07/04/2017 | 07/04/2018 | `III Gran Premi de Marxa "Ciutat de Sant Cugat" / ZEM "LA GUINARDERA" Sant Cugat del Vallés, 7 abril 2018`, plus `Final 07/04/2018 11:45`. Moved to `seasons/2018/json/` (S5); the 2017 season keeps the `II Gran Premi` of 11/03/2017, so this is not a duplicate. |

### B. Kept stored (18 files + the corrected junior sheet)

| File | Stored | Audit header | Why the stored date stands |
|------|--------|--------------|----------------------------|
| 2005/resulcatabsolut.json | 19/06/2005 | 08/06/2005 | `Manresa, 18 i 19 de juny de 2005` — the meeting spans two days and stored is the closing one. The audit date is `Millor Marca Temporada: 10,57 Jordi Mayoral, 08/06/05`, a season best, not the header. |
| 2005/resulcatjuniorpc.json | 27/02/2005 | 12/02/2005 | `Vilafranca, 26 i 27 de febrer de 2005`; audit date from `Millor Marca Temporada: 7"21 Roger Carulla12/02/05`. |
| 2005/resulcatjuvenilpc.json | 27/02/2005 | 12/02/2005 | `Vilafranca, 26 i 27 de febrer de 2005`; audit date from `Millor marca temporada: 7,10 Marc Altes, 12/02/05`. |
| 2008/resulcatcadetpc2324208.json | 24/02/2008 | 20/01/2008 | `Vilafranca del Penedès, 23 i 24 de febrer de 2008`; audit date from `Millor Marca Temporada: 7,36 Nelson de la Puente, 20/01/2008`. |
| 2009/resulcatcadetpc2122209.json | 22/02/2009 | 26/02/2005 | `Vilafranca del Penedès, 21 i 22 de febrer de 2009`; audit date is the record line `Rècord de Catalunya: 7,17 Ramon Montejano, 26/02/05` (S4). |
| 2009/resulcatjuvenilpc2122209.json | 22/02/2009 | 08/02/2009 | `Vilafranca del Penedès, 21 i 22 de febrer de 2009`; audit date from `Millor Marca Temporada: 7,12 Adria Burriel, 08/02/2009`. |
| 2010/resulmitingveteransreus8510.json | 8/5/2010 | 09/05/2010 | `3r Meeting "Ciutat de Reus" d'atletisme Veterà / 8 de maig de 2010` — the stored date. The audit read the garbled `9:0109/05/2010` line (print time + date), not the header (S4). |
| 2013/resulcatcombinadespromocio25260513.json | 26/05/2013 | 25/05/2013 | `Barcelona (Serrahima), 25-26 mayo 2013`; `Serie 1` dates show CA Tarragona on both days, so the file cannot carry one day alone — closing day kept (S2). |
| 2013/resulcontrolprimaveracambrils18190513.json | 19/05/2013 | 18/05/2013 | Section headers read both `Cambrils, 18 / 05 / 2013` and `Cambrils, 19 / 05 / 2013`, with CA Tarragona on both (Targa 1'39"34 on 19/05) — closing day kept (S2). |
| 2013/resulcatjunior120613.json | 02/06/2013 | 01/06/2013 | Same multi-day sheet as in A: both sessions have CA Tarragona results, so the corrected closing day is registered instead of oscillating to the first session on every audit. |
| 2015/resulcatcombinades30310515.json | 31/05/2015 | 30/05/2015 | `Barcelona-SE, 30-31 mayo 2015`; `Serie 1 30/05/2015` and `Serie 1 31/05/2015` both carry CA Tarragona — closing day kept (S2). |
| 2015/resulcatcombinadesjuvenilpc21220215.json | 22/02/2015 | 21/02/2015 | `Sabadell (Pista Coberta de Catalunya), 21-22 febrero 2015`; Jan Sans Riola competes on 21/02 (60m) and 22/02 (day-2 events) — closing day kept. |
| 2015/resulcontrolcambrils16170515.json | 17/05/2015 | 16/05/2015 | Section headers read both `Cambrils, 16 / 05 / 2015` and `Cambrils, 17 / 05 / 2015`, with CA Tarragona on both — closing day kept (S2). |
| 2016/resulcatcadetcombinadescpc20210216.json | 21/02/2016 | 20/02/2016 | `Sabadell (Pista Coberta de Catalunya), 20-21 febrero 2016`; hexathlon acta runs over both days — closing day kept. |
| 2016/resulcatjuniorcombinadespc13140216.json | 14/02/2016 | 13/02/2016 | `Sabadell (Pista Coberta de Catalunya), 13-14 febrero 2016`; Jan Sans Riola on both days — closing day kept. |
| 2016/resulcatjuniorcombinadespc13140216.json.json | 14/02/2016 | 13/02/2016 | Same sheet as above (duplicate output file). |
| 2016/resulcatjuvenilcombinadespc13140216.json.json | 14/02/2016 | 13/02/2016 | `… 13-14 febrero 2016`; Mireia Lopez Urbano competes on 14/02 — closing day kept. |
| 2016/resullliguetasub11bcn71115.json | 07/11/2015 | 23/07/2009 | `3a. Lligueta Atlètica de Barcelona Sub-11 / Barcelona (Mar Bella), 7 de novembre de 2015` — the stored date. The audit date is a birth date in the table (`POL LOBO BERTRAN 23/07/09`) (S4). |
| 2026/resultat-20260117-gpmarxaelvendrell.json | 17/01/2026 | 25/08/2007 | Title reads `GRAN PREMI DE MARXA DEL VENDRELL / 17.01.2026 - RESULTADOS` — the stored date. The audit date is a birth date (`GINA TORRES AUBERNI 25/8/2007`) (S4). |

### C. Formatting-only rows (unchanged, no longer reported) — 15 files

`resulcontrolploms26406` (26/4/2006), `resulpromoterritinfantilcambrils9208`
(9/2/2008), `resulreus2509` (2/5/2009), `resultarragona16509` (16/5/2009),
`resul-lligacat-tarragona15510` (15/5/2010), `resulcontrolprimaveracambrils25410`
(25/4/2010), `resulcatrelleus30411` and `resulcnatterritpromoamposta30411`
(30/4/2011), `resulcnatterritpromovalls2411` (2/4/2011), `resultrobadacambrils60413`
(6/4/2013), `resulterritpromovalls50414` (5/4/2014), `resulcontrolcep71114`
(7/11/2014), `resulcnatlocalcambrils80516` (8/5/2016),
`resulcontrolterritamposta50316` (5/3/2016), `resulterritpromoamposta70516`
(7/5/2016). Reason: same day as the header, written without zero padding. The
contract accepts `D/M/YYYY`, so the dates were left as they are (no data gain in
rewriting them, and 15 extra diffs would only blur the review).

### Not in scope / observed while working

- `parse_header` (extract_catt.py, outside this task's surfaces) accepts a
  season-best / record / birth date when the meeting header does not match its
  month-name pattern: the 2-digit fallback `D/M/YY` takes the first hit in the
  first 30 lines, and the 4-digit slash branch accepts any year 2000-2035, so a
  DOB like `25/8/2007` wins over a title like `17.01.2026 - RESULTADOS`. That is
  the root cause of 8 of the 19 kept rows and would be worth its own issue.
- 4 files fail to download (2025/2026 FCAT URLs dead) and 113 have no header
  date; both groups are unchanged by this task.
- `reports/event_date_manual_review.csv` used to be hand-maintained and carried
  stale rows for already-fixed files. It is now generated by the audit from
  `KEEP_STORED`.

## Log

L1. si (continue with #28 after #31)
L2. Audit re-run: 55 mismatches -> 15 formatting-only, 40 genuine (glued-leading-zero family dominant).
L3. T1: `parse_date()`/`dates_conflict()` + pdf_cache-first audit; 18 new unit tests (red then green).
L4. T2 re-run: 41 rows (40 + `resulcontrolcd-jvpc26108`, previously a download failure), 1255 cache hits, 4 download fails.
L5. T3/T4: 23 dates corrected from the printed header, 18 kept with evidence; `resulcatjunior120613` corrected to its closing day and registered as a multi-day keep.
L6. T5: `resultat-20170407-gpmarxasantcugat.json` is the 2018 edition (`III Gran Premi`), date 07/04/2018, moved to `seasons/2018/json/`.
L7. T6: final audit 0 open / 19 documented; suite 171 OK; plausibility 259 (ceiling 259).

