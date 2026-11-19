# Disciplines & performance format review — season 2025

Review of `seasons/2025/json/*.json` (102 files, 3428 results, 76 unique discipline
values) against `DISCIPLINES.md` (database dump, 134 discipline rows), covering:

1. discipline name membership,
2. performance format vs the DB `format` column,
3. data-quality issues surfaced by those checks (duplicates, implausible values, wind format).

## Resolution status (post-review, 2026-11-19)

- ✅ **P1 fixed**: `10 km marxa` → `10.000 metres marxa` (id 49) in mollet JSON + mapping table;
  REGINA GRAS deduped 3→1 (F55 section empty in PDF; overall+F45 were the same race).
- ✅ **P2 fixed**: 145 sub-minute times normalized to `0:SS.cc` in 57 files (this season + `json/`);
  `DISCIPLINES.md` row 103 updated to `2000 metres obstacles | mm:ss.cc`; extractor now emits
  `mm:ss.cc` for llisos ≥300 m / tanques-obstacles ≥400 m / marxa (`normalize_mmsscc_time`).
- ✅ **P3 diagnosed — all 10 worst files are STALE**: every committed duplicate was traced to
  `extract_catt.py` @ `d19d871` (2026-06-21 build). Re-extraction at HEAD yields **0 duplicate
  groups** on all 10 files (see "P3/P4 raw-PDF review" below), removes ~160 leak rows,
  recovers ~9 lost real results, and loses **0** correctly-labelled rows.
- ✅ **P4 diagnosed**: all 11 impossible values are misattached field-event marks or truncated
  `H:MM.SS` times; 9/10 vanish on HEAD re-extraction. **One live bug remains**: masters
  headers like `400m vallas (0,84) AL M55` are not recognized as section boundaries
  (Baz Vidal `1:17.59` → `17.59`).
- ⬜ Pending: regeneration of stale 2025 JSONs at HEAD + `update_disciplines.py` re-run.

## Summary

| Check | Result |
|---|---|
| Discipline names present in DISCIPLINES.md | 75/76 OK — **1 unmapped: `10 km marxa`** |
| Performance matches DB format | 3337/3428 OK — **91 format mismatches** (2 explainable groups) |
| Cross-discipline duplicates (same athlete + same performance under 2+ disciplines in one file) | **690 results in 54 files** |
| Standalone implausible performances | **12 results** (need source-PDF verification) |
| Wind values in canonical `+X.X` / `-X.X` form | 562 OK — **199 unsigned** (124 non-zero) |
| Non-numeric markers (DNS/DNF/DQ/RET) | none present |

## 1. Discipline names

75 of 76 unique `discipline` values match a `DISCIPLINES.md` row exactly.

### 1.1 Unmapped: `10 km marxa` (3 results)

`resultat-20251025-cat10000marxamastermollet.json` — raw discipline
`10.000m Marcha Mujeres` mapped to `10 km marxa`, which has no DB row.

- Closest DB rows: `10.000 metres marxa` (id 49) or `10K marxa (Ruta)` (id 77). Given the
  event is a track 10.000m marcha (not ruta), the mapping should be **`10.000 metres marxa`**.
- Bonus defect: the same athlete (REGINA GRAS CARDENAS) and the same performance
  (`53:47.50`) appear **3 times**, once per raw variant (`10.000m Marcha Mujeres`,
  `... Master F45`, `... Master F55`) — the overall + two category classifications of one
  single race. Deduplication kept all three.

## 2. Performance formats vs DB `format`

Every DB row declares one of `ss.cc`, `mm:ss.cc`, `HH:mm:ss`, `m.cm`, `p`.
91 of 3428 results do not match the declared format, in two groups:

### 2.1 Sub-minute times stored as `ss.cc` under `mm:ss.cc` disciplines (88 results)

| Discipline | `ss.cc` | `mm:ss.cc` | examples (`ss.cc`) |
|---|---:|---:|---|
| 300 metres llisos | 64 | 17 | `42.15`, `39.66`, `52.84` |
| 400 metres llisos | 20 | 37 | `49.96`, `58.58`, `54.31` |
| 400 metres tanques (0.914) | 3 | 2 | `56.25`, `57.93`, `59.85` |
| 400 metres tanques (0.84) | 1 | 3 | `57.25` |

All values are real, plausible performances — the issue is **representation**: within the
same discipline, sub-minute times are stored as `49.96` while over-minute times are stored
as `1:03.13`. Official timing writes sub-minute times without the minute part, so the data
is arguably correct and the DB `format` column is too strict; either way the two
representations coexist in the same discipline and downstream parsers must accept both.

### 2.2 `2000 m obstacles` stored as `mm:ss.cc` vs DB `HH:mm:ss` (3 results)

`7:36.59`, `8:28.52` (×2) — correct `mm:ss.cc` values for a 2000m steeplechase
(5–9 minutes). The DB row (id 103, `2000 m obstacles`, `HH:mm:ss`) is the outlier: every
sibling row (`1000/1500/3000 metres obstacles`) declares `mm:ss.cc`, and the row name
itself uses `m` instead of `metres`. The DB row is most likely wrong, not the data.

### 2.3 Formats that conform

- All field marks (`m.cm`): 2 decimals, e.g. `5.45`, `11.01` — OK.
- Combined-event points (`p`): plain integers (Tetratló, 3 results) — OK.
- All other track times — OK.

## 3. Cross-discipline duplicates (main data-quality issue)

**690 results in 54 files** carry the *same athlete + same performance value* under two or
more different disciplines in the same file. Identical marks to the centisecond/centimeter
under different implements/distances are extraction artifacts, not real performances.

Verified against source JSONs (spot checks):

- `resultat-20250215-controlfebrertarragona.json` — JULIA MUSTE SANTIAGO `8:16.31` appears
  under `2000 metres llisos` (raw `2.000m Mujeres AL`, correct) **and** `300 metres llisos`
  (raw `300m Mujeres`, impossible: 300m in 8+ minutes).
- `resultat-20250614-catsub12finalcastellar.json` — NOA PASCUAL PRATS `6.42` appears under
  `Pes (2 Kg)` (throw mark, correct) **and** `60 metres tanques (0.50)` (impossible time).
- `resultat-20250322-catsub12finalpcsabadell.json` — DANIEL LINARES ANTELO `10.26` appears
  under `60 metres tanques (0.50)` (correct) **and** `200 metres llisos` (impossible).

Root cause is consistent with the known section-boundary/summary-section extraction bug
(AGENTS.md: athletes leaking into an adjacent event section, e.g. via SUMARIO blocks):
one copy is attached to the correct discipline, the second copy to the section that
preceded or followed it.

Worst-affected files:

| results | file |
|---:|---|
| 84 | resultat-20250510-territorialpromociocambrils.json |
| 56 | resultat-20250215-territorialcombinadessub1214tarragona.json |
| 54 | resultat-20250412-territorialpromocioasco.json |
| 46 | resultat-20250518-territorialpromocioelvendrell.json |
| 34 | resultat-20250927-catpentatlollancamentsmasterlhospitalet.json |
| 32 | resultat-20250125-controlveloricattanquestarragona.json |
| 32 | resultat-20251129-previadelegacionsterritorialspromociotarragona.json |
| 26 | resultat-20250209-catllancamentssub1820serrahima.json |
| 26 | resultat-20250607-catsub12previavilanova.json |
| 24 | resultat-20250615-catsub14previagava.json |

(The remaining 44 affected files have 2–24 such results each.)

## 4. Standalone implausible performances (12 results)

Impossible values that are **not** part of a same-file duplicate pair — they need
verification against the source PDFs (`event_src` is populated in every file):

| discipline | performance | athlete | file |
|---|---|---|---|
| 60 metres tanques (0.84) | `5.09` | NORA MONTOLIO AMARO | resultat-20250202-catclubssub2pcsabadell.json |
| 60 metres tanques (0.91) | `6.12` | VICTOR JIMENEZ GARCIA | resultat-20250215-catsub18pcsabadell.json |
| 60 metres tanques (0.91) | `5.17` | IKER RODRIGUEZ BARRIOS | resultat-20250301-catsub16pcsabadell.json |
| 60 metres llisos | `5.15` | JULIA DIEZ BERTRAN | resultat-20250329-catcombinadessub12pcsabadell.json |
| 300 metres tanques (0.84) | `17.59` | FRANCISCO JAVIER BAZ VIDAL | resultat-20250518-territorialpromocioelvendrell.json |
| 300 metres tanques (0.762) | `11.47` | AINOA RODRIGUEZ MURILLO | resultat-20250518-territorialpromocioelvendrell.json |
| 220 metres tanques (0.762) | `8.77` | MARIA MARTIN CUADRADO | resultat-20250524-catclubsbsub14elprat.json |
| 300 metres tanques (0.762) | `9.15` | CLAUDIA BOTANCH RIUS | resultat-20250525-catclubsbsub16santacoloma.json |
| 300 metres tanques (0.762) | `11.97` | PAU ESTEVE HOSTALOT | resultat-20250629-catsub16finalsantceloni.json |
| 300 metres tanques (0.762) | `9.83` | DUINA BORREDA CERVELLO | resultat-20250629-catsub16finalsantceloni.json |

(A 300m hurdles race takes 40–70s at these ages; 9–18s is below world-record pace at any
distance. Cross-file duplicates — the same leaked value landing in a *different* file — are
a plausible explanation and were not scanned for here.)

## 5. Wind field format

- 562 values in canonical signed form (`+1.2` / `-0.8`) — OK.
- **199 unsigned values** (e.g. `0.1`, `1.7`, `2.2`) in 24 files; 124 of them non-zero.
  Concentrated in promoció/territorial files, e.g.
  `resultat-20250215-territorialcombinadessub1214tarragona.json` (38),
  `resultat-20250412-territorialpromocioasco.json` (34).
- 68 signed values exceed |2.0| m/s (above the `wind_limit` of the DB rows) — not a format
  error, but relevant if records/PBs are computed from this data (illegal-wind marks).

## 6. Clean checks

- No non-numeric performance markers (DNS/DNF/DQ/RET/N.P.) anywhere — validation is
  filtering them out as designed.
- `raw_discipline_name` is preserved on every result, enabling the mapping fixes above.

## 7. P3/P4 raw-PDF review (confirmed mechanisms)

All four review batches (researchers, PDFs cached in `/tmp/p3/`) agree on the verdicts:

| File | Committed | HEAD re-extract | Duplicates at HEAD |
|---|---|---|---|
| territorialpromociocambrils | 225 rows | 175 rows | 0 (50 leak rows removed, 0 true rows lost) |
| territorialcombinadessub1214tarragona | 264 rows | 214 rows | 0 (50 removed) |
| territorialpromocioasco | 168 rows | 135 rows | 0 (33 removed) |
| territorialpromocioelvendrell | 145 rows | 121 rows | 0 (27 removed) |
| catpentatlollancamentsmasterlhospitalet | 40 rows | 20 rows | 0 (combined-totals rows now correctly labelled) |
| previadelegacionsterritorialspromociotarragona | 201 rows | 185 rows | 0 |
| controlveloricattanquestarragona | 248 rows | 176 rows | 0 |
| catllancamentssub1820serrahima | 30 rows | 15 rows | 0 (HORARIO ghost section gone) |
| catsub12previavilanova | 57 rows | 44 rows | 0 (+2 real recovered, `12:23.68` marxa restored) |
| catsub14previagava | 55 rows | 45 rows | 0 (+2 real recovered) |

**Mechanisms** (all in the pre-`a6c2387` boundary code, dead at HEAD):
1. **Section boundary overrun** — an event spanning multiple pages whose repeated headers were
   deduped left a window running until an unrelated boundary, swallowing 2–8 following events
   and re-emitting their CATT rows under the opening section's label.
2. **HORARIO ghost section** — a schedule line (`17:30   Disc SUB18 (1,5kg) Homes   Final`)
   accepted as a section header, duplicating every CATT attempt in the file.
3. **Combined-totals table misparse** (pentathlon) — table cells emitted as individual results
   with disciplines taken from schedule lines or unrelated sections.
4. **Undetected headers** (`400m vallas ABS F`, `AL M55`) — page absorbed by previous section,
   `H:MM.SS` truncated by dropping the hour. **Still partially live**: the `AL M55` variant
   reproduces at HEAD.
5. **Neighbour-row marks** (P4) — athlete-block windows reading into the next competitor's
   field-attempt row, emitting a rival's mark as the CATT athlete's "time".

**Side defects observed (open, separate issues):**
- Truncated licence lines (`CAT-3787484-A…`) take `athlete_id` from the *next* athlete's line.
- Combined-events totals (pentathlon points) not emitted at HEAD (completeness gap).
- `Jabalina Vortex → Javelina (800 g)` and `Disc SUB18 (1,5kg) → Disc (2 Kg)` mappings in
  `update_disciplines.py` look questionable (unaudited).
- `event_name` empty in files with all-caps / "Cnt Territorial" headers (parse_header gap).

## Recommendations

1. **Fix the `10 km marxa` mapping** → `10.000 metres marxa` (id 49), and collapse the
   3 duplicate REGINA GRAS entries to one.
2. **Decide the sub-minute time representation** (`49.96` vs `0:49.96`): either normalize
   the 88 `ss.cc` values under `mm:ss.cc` disciplines to the DB format, or treat the DB
   `format` column as the display format and accept both shapes on import.
3. **Fix the DB row `2000 m obstacles`** (id 103): name should match its siblings
   (`2000 metres obstacles` is a separate id-59-style row; the two rows are near-duplicates)
   and the format should be `mm:ss.cc`.
4. **Deduplicate cross-discipline duplicates**: within a file, when the same athlete+performance
   appears under 2+ disciplines, keep the copy whose discipline makes the performance
   plausible (e.g. `8:16.31` belongs to 2000m, not 300m) and drop the rest. This removes
   ~345 spurious results (half of 690) and all the impossible times in sections 2/4 that
   are part of duplicate pairs.
5. **Verify the 12 standalone implausible values** against their source PDFs (`event_src`).
6. **Normalize unsigned wind values** to signed form (`0.1` → `+0.1`).
