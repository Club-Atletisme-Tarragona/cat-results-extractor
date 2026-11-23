# parse_header: reject non-meeting dates (issue #32)

Authorized: user said "si" to continuing with #32 after #28 closed.
Parent: GitHub issue #32 — root cause behind 8 of the 19 "keep stored" decisions
that closed #28.

## Specs

S1. `parse_header` must not accept as a meeting date any line that is:
    a birth date, an `RCAT`/`RCAM` record line, a season-best/`MMP` line, or a
    Conersys generation stamp (weekday present).
S2. The `D/M/YY` and 4-digit-slash fallbacks must only consider the **first
    plausible meeting header block**, not the first date hit anywhere in the
    first 30 lines. The current slash branch accepts any year 2000–2035, which
    is what lets a DOB through.
S3. A title carrying an explicit dotted date (`17.01.2026 - RESULTADOS`) is
    header evidence and must be preferred over a later unrelated date.
S4. Each pinned case below keeps its **stored** date; the fix must make
    `parse_header` agree with the stored value, so the audit's `KEEP_STORED`
    containment can be reduced.
S5. No regression for the families that already work: Catalan and Spanish month
    names, zero-padded and non-padded dates, era sheet headers, and the
    current-season RFEA/Conersys layouts.
S6. Verification: suite green; `scripts/check_plausibility.py` must not exceed
    **259**; `scripts/check_event_dates.py` must stay at **0 open**; one
    differential check because `parse_header` is shared by every extractor.

## Pinned cases (evidence read from the PDFs during #28)

| File | Stored (correct) | What parse_header preferred | The line actually is |
|---|---|---|---|
| `seasons/2026/json/resultat-20260117-gpmarxaelvendrell.json` | 17/01/2026 | 25/08/2007 | a DOB; the title reads `17.01.2026 - RESULTADOS` |
| `seasons/2016/json/resullliguetasub11bcn71115.json` | 07/11/2015 | 23/07/2009 | a DOB; header `Mar Bella, 7 de novembre de 2015` |
| `seasons/2009/json/resulcatcadetpc2122209.json` | 22/02/2009 | 26/02/2005 | an `RCAT` record line |
| `seasons/2005/json/resulcatabsolut.json` | 19/06/2005 | 08/06/2005 | season-best line; meeting 18–19 June |
| `seasons/2005/json/resulcatjuniorpc.json` | 27/02/2005 | 12/02/2005 | season-best line; meeting 26–27 Feb |
| `seasons/2005/json/resulcatjuvenilpc.json` | 27/02/2005 | 12/02/2005 | season-best line; meeting 26–27 Feb |
| `seasons/2008/json/resulcatcadetpc2324208.json` | 24/02/2008 | 20/01/2008 | season-best line; meeting 23–24 Feb |
| `seasons/2009/json/resulcatjuvenilpc2122209.json` | 22/02/2009 | 08/02/2009 | season-best line; meeting 21–22 Feb |

Sources: each JSON's `event_src`; cached copies under `pdf_cache/<season>/`.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2,S3 | RED tests pinning the eight cases from their real header text | | done — `tests/test_parse_header_dates.py`, 22 RED failures first |
| T2 | S1,S2,S3 | Reject non-meeting candidate lines; restrict the fallbacks | | done — `extract_catt.py` `_header_*` predicates + 5 ordered tiers |
| T3 | S4 | Reduce the audit's `KEEP_STORED` for the cases now covered by tests | | done — 19 → 11 entries, then 11 → 15 with the four ambiguous rows below |
| T4 | S5,S6 | Suite, plausibility, audit, differential; work-unit commit | | done — see Verification |

## What the fix surfaced (T4)

The eight pinned cases were the visible part. Making `parse_header` read the
meeting header instead of the first date-shaped line also exposed **20 stored
`event_date` values that the source PDFs contradict**, which the audit could not
see before: the old parser returned *no* date for those sheets
(`header_no_date` 113 of 1255 cached PDFs before, 54 after), so nothing was
compared and "0 open" was partly an artefact of the parser being blind.

Each row below was opened in the PDF. The header quoted is the title-block line
that carries the competition's venue and date; the correction is `event_date`
only, applied with `scripts/check_event_dates.py --apply`.

### (a) Stored date was an athlete's birth date — 13 rows

| File | Stored → new | Header line read from the PDF |
|---|---|---|
| `seasons/2017/json/resultat-2017011415-catcombinadespc.json` | 05/08/1993 → 15/01/2017 | `Sabadell (Pista Coberta de Catalunya), 14-15 enero 2017` |
| `seasons/2017/json/resultat-2017021819-catcombinadescadetpc.json` | 25/05/2002 → 19/02/2017 | `Sabadell (Pista Coberta de Catalunya), 18-19 febrero 2017` |
| `seasons/2017/json/resultat-2017021819-catcombinadesjuvenilpc.json` | 13/04/2000 → 18/02/2017 | `Sabadell (Pista Coberta de Catalunya), 18 febrero 2017` |
| `seasons/2017/json/resultat-20170225-catcombinadesinfantilpc.json` | 24/02/2004 → 25/02/2017 | `Sabadell (Pista Coberta de Catalunya), 25 febrero 2017` |
| `seasons/2017/json/resultat-2017052728-catcombinades.json` | 12/08/1988 → 28/05/2017 | `Barcelona-Estadi Joan Serrahima, 27-28 mayo 2017` |
| `seasons/2017/json/resultat-2017052728-catcombinadespromocio.json` | 06/05/2002 → 28/05/2017 | `Barcelona-Estadi Joan Serrahima, 27-28 mayo 2017` |
| `seasons/2018/json/resultat-2018011314-catcombinadespcsabadell.json` | 05/08/1993 → 14/01/2018 | `Sabadell (Pista Coberta de Catalunya), 13-14 enero 2018` |
| `seasons/2018/json/resultat-2018022425-catcombinadessub16pcsabadell.json` | 21/02/2003 → 25/02/2018 | `Sabadell (Pista Coberta de Catalunya), 24-25 febrero 2018` |
| `seasons/2018/json/resultat-2018052627-catcombinadesserrahima.json` | 05/08/1993 → 27/05/2018 | `Barcelona (Estadi Joan Serrahima), 26-27 mayo 2018` |
| `seasons/2019/json/resultat-2019022324-catcombinadessub16pcsabadell.json` | 27/04/2004 → 24/02/2019 | `Sabadell (Pista Coberta de Catalunya), 23-24 febrero 2019` |
| `seasons/2019/json/resultat-20190302-catsub14combinadespcsabadell.json` | 20/07/2006 → 02/03/2019 | `Sabadell (Pista Coberta de Catalunya), 2 marzo 2019` |
| `seasons/2019/json/resultat-2019042728-catcombinadesserrahima.json` | 05/08/1993 → 28/04/2019 | `Barcelona (Estadi Joan Serrahima), 27-28 abril 2019` |
| `seasons/2020/json/resultat-2020020809-catcombinadessub18pcsabadell.json` | 09/06/2003 → 09/02/2020 | `Sabadell (Pista Coberta de Catalunya), 8-9 febrero 2020` |

### (b) Stored date came from the filename, not the sheet — 7 rows

| File | Stored → new | Header line read from the PDF |
|---|---|---|
| `seasons/2006/json/resultarragona1-2405.json` | 2/4/2005 → 02/04/2006 | `Camp Clar, 1 i 2 d'abril de 2006` |
| `seasons/2006/json/resultarragona10111205.json` | 10/11/2005 → 11/12/2005 | `Camp Clar, 10 i 11 de desembre de 2005` |
| `seasons/2007/json/resulcatcombinadespc2021107.json` | 02/11/2007 → 21/01/2007 | `Vilafranca, 20 i 21 de gener de 2007` |
| `seasons/2010/json/resulcatcombijuvenilpc2021210.json` | 02/12/2010 → 21/02/2010 | `Vilafranca del Penedès, 20 i 21 de febrer de 2010` |
| `seasons/2012/json/resulcatveteranscombinades230612.json` | 23/06/2012 → 03/06/2012 | `CAMBRILS, 2 i 3 de juny de 2012` |
| `seasons/2014/json/resulcatveteranscombinadesal17180514.json` | 18/05/2014 → 18/06/2014 | `CAMBRILS, 17 i 18 de juny de 2014` |
| `seasons/2015/json/resulcnatterritcombinadescambrils230515.json` | 23/05/2015 → 03/05/2015 | `Cambrils, 2 i 3 de maig de 2015` |

### (c) Genuinely ambiguous two-day rows — 4 kept, not changed

Stored day is one of the days the sheet itself names, so the decision is "keep
stored" and lives in `KEEP_STORED` (`span-2-dies`), not in a code rule.

| File | Stored (kept) vs header | Why both are defensible |
|---|---|---|
| `seasons/2015/json/resulcombinadescambrils20121214.json` | 20/12/2014 vs 21/12/2014 | `Cambrils, 20 i 21 de desembre de 2014` — the sheet has no per-session dates, so either end of the range is supported. |
| `seasons/2017/json/resultat-20170114-controlabsolutpc.json` | 15/01/2017 vs 14/01/2017 | Title says `14 enero 2017`; 15 session lines say `15/01/2017 17:10`. |
| `seasons/2017/json/resultat-20170212-controlabsolutpcmati.json` | 10/02/2017 vs 12/02/2017 | Title says `12 febrero 2017`; sessions are dated on both 10/02 and 12/02. |
| `seasons/2018/json/resultat-20180211-controlpctardasabadell.json` | 07/02/2018 vs 11/02/2018 | Title says `11 febrero 2018`; sessions are dated on both 07/02 and 11/02. |

## Verification (T4)

| Check | Before | After |
|---|---|---|
| `python3 -m unittest discover -s tests` | 171 tests, OK | 188 tests, OK |
| `python3 scripts/check_plausibility.py` | 259 violations | 259 violations (ceiling 259) |
| `python3 scripts/check_event_dates.py` | 0 open, 19 kept — but 113/1255 cached sheets produced no date at all | 0 open, 15 kept, 54/1255 without a date |
| Differential, 5 required fixtures (base commit files in `mktemp -d` vs this tree) | — | byte-identical JSON, all 5 |

Differential fixtures: `tests/fixtures/resulcontrolvalls60216.pdf`,
`resultat-20260418-territorialpromociovalls.pdf`,
`resultat-20260502-controlvelocitatmaigtarragona.pdf`,
`resultat-2026050203-territorialcombinadestarragona.pdf`,
`resultat-20260426-cat10000marxamastergava.pdf` — same `event_date`, same rows,
same order.

Corpus-wide probe (all 1255 cached PDFs, before vs after): **0 dates lost**, 59
sheets gain the date they always had in the header, 18 sheets change day — 7 of
them are the pinned cases now agreeing with their stored value, the rest are the
20 corrections above (before the audit run) and the 4 kept rows.

## Log

L1. si (continue with #32 after #28)

L2. T1 RED: `tests/test_parse_header_dates.py` — 16 tests, 22 failures, each one
the pinned defect verbatim (DOB, `RCAT` record line, season-best line).

L3. T2: tier order is now 1) single-day month-name header, 2) dotted title date,
3) `DD/MM/YYYY`, 4) glued short date, 5) month-name *range* (closing day). Lines
carrying a record, a season best, a DOB column, a licence row, a hand-time row or
a Conersys stamp (weekday) are skipped, and the scan stops at the first result-
table header. The range is last on purpose: two-day sheets that print per-session
dates are filed under the first session (the stored convention), so a range is
only used when nothing more precise exists.

L4. T3: `KEEP_STORED` 19 → 11 (the eight pinned entries removed; the parser now
reads their headers itself), then 11 → 15 with the four `span-2-dies` rows in
(c). `tests/test_event_dates.py` pins that the eight stay out of the registry.

L5. T4: applying the 20 corrections changed `event_date` and nothing else —
`git diff -U0 -- seasons/` shows only `event_date` lines. The four (c) rows keep
their stored date and their registry entry.

