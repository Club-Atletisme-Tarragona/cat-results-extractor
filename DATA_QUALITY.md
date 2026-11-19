# Data quality status

Audited 2026-11-19 across **1,329 JSON files / 27,044 results** in
`seasons/<year>/json/`, seasons 2005-2026. `json/imported/` is excluded
(third-party processed files, intentionally not our extractor output).

Since 2026-11-19 **every season lives under `seasons/<year>/json/`** — the
current season included (`seasons/2026/`). There is no top-level `json/`
directory; a season is the calendar year of the event, resolved by
`season_paths.py` from the JSON's own `event_date`.

Re-run the audit at any time:

```bash
python3 -m unittest discover -s tests        # 46 tests: contract, goldens, units
python3 scripts/check_plausibility.py        # physically impossible values
python3 scripts/validate_performance.py      # performance vs DISCIPLINES.md format
```

## Verdict

| Seasons | Verdict |
|---|---|
| `seasons/2025`, `seasons/2026` (current) | **Valid and plausible.** Regenerated from source PDFs with current `extract_catt.py`. |
| `seasons/2017`–`2024` | **Valid and plausible.** Regenerated 2026-11-19 (mechanical formats + source re-extraction). |
| `seasons/2005`–`2016` | **Not yet.** Mechanical notation defects are fixed; the remaining defects need per-era re-parsers (below). |

## Contract checks — all green, every season

| Check | Result |
|---|---|
| Corrupt / unreadable JSON | 0 |
| Rows missing `athlete_name`, `performance` or `discipline` | 0 |
| Rows with an empty `discipline` | 0 |
| Files missing `event_date` / `event_src` | 0 |
| `internal_id` field present | every file |

Empty `athlete_dob` / `athlete_id` on pre-2012 sheets are legitimate: those
sheets do not print them (see AGENTS.md, "Legacy Empty Fields").

## What has been fixed

**2026-11-19 regeneration** (stale extractions, boundary/classification bugs):
`seasons/2017`–`2024` + `seasons/2025` — section-window overruns, HORARIO ghost
sections, combined-table misparses, master/veteran header gaps, age-graded
percentage columns, hurdle-height headers. Season 2025: 3,428 → 3,096 rows,
680 cross-discipline duplicates → 0.

**2026-11-19 mechanical sweep** (`scripts/repair_legacy_performance_formats.py`)
— 500 notation-only repairs across 181 files, all seasons:

| Count | Rule | Example |
|---:|---|---|
| 211 | sub-minute time under a `mm:ss.cc` discipline gets `0:` | `59.45` → `0:59.45` |
| 146 | minute-form with one decimal padded | `3:32.6` → `3:32.60` |
| 85 | `MM:SS` with the seconds dropped | `16:30` → `16:30.00` |
| 39 | one-decimal mark padded | `7.5` → `7.50` |
| 7 | minute-form value under a `ss.cc` discipline | `1:07.15` → `67.15` |
| 12 | `NULS` (Catalan "no mark") rows dropped | *row removed* |

Format issues 226 → 15; the script is idempotent and refuses to touch values
whose sub-minute form is physically impossible.

## What remains (documented, not hidden)

All of it is in `seasons/2005`–`2016`, produced by per-era parsers that predate
the current extraction code. The source PDFs are still downloadable from
`old.fcatletisme.cat`, so these are recoverable.

| Count | Defect | Needs |
|---:|---|---|
| **226** | Physically impossible values (e.g. a long-jump mark stored as a `60 METRES LLISOS` time in 2006 combined events) | per-era re-parsers, verified against the PDFs |
| **33** | Cross-discipline duplicate rows (same athlete + same mark under two disciplines, 2008–2024) | source-PDF check per row: **not resolvable by plausibility** (both copies are plausible), so nothing was guessed or deleted |
| 10 | Format mismatches: 6 misc, 3 veterans age/percentage column, 1 combined-table header stored as a discipline | targeted fixes |
| 1 | Unmapped discipline `60m tanques PC` (2017 infantile heat, no height in the header) | mapping rule |
| **38** | Exact-duplicate result rows exposed by the name cleanup: same athlete, same discipline, same mark twice in one file (combined-event files where the SUMARIO/total section repeats a sub-event result, e.g. `Silvia Gutierrez Comes` javelin 15.44 in `resulcatcombinades560512`). Previously invisible because the two rows differed only by a trailing series number (`JF 5` vs `5`) | row removal was NOT applied: two identical attempts are possible in throws, so this needs a per-file re-extraction decision, not a blind delete |
| 20 | `seasons/2008/json/resulcatclubsveterans21608.json`: the veterans parser stored the **percentage column** as the mark (`JOSE MARTIN ALVAREZ 200 metres llisos 80.48` where the PDF prints `24''90`; the same for `PEDRO VACAS` disc 69.23 and two of `JAVIER MARTIN ALVAREZ`'s shot attempts 22.16/36.06). The 6 relay rows of this file were already repaired with the real marks; the individual events were not touched | re-parse with a veterans-aware column map (`MARCA COEF % PUNTS`) |
| 2 | Names that cannot be cleaned without inventing data: `AHANOTU` (truncated by the PDF column, matched to 1391 by owner decision) and `ZAIRA AF` (only a given name survived the era parser) | per-source review |

### Relay compositions are no longer stored as one athlete

Six rows held a whole relay team in `athlete_name` — a fragment of the sheet's
dash-joined name column (`PERE PARDINES JOSE MARTIN` from the 2008 veterans
4x100, `LOPEZ BLANCO MATEO GARCIA` from 2010, `E. JOSE-J. GONZALEZ-A. LAGO-N.
PINYOL` from 2011). `extract_catt.py:split_relay_composition()` now splits such
a line into legs at the output boundary, and the six stored rows were rebuilt
from their source PDFs: **6 rows → 24 leg rows**, six of them resolving to club
athletes (Flores 4, Bardina 7, Pardines 71, Sanchis 205, Alex Lopez 227, Mateo
343). The two 2008 rows also had the percentage column as their mark
(`82.08`/`48.85` instead of `50.00`/`4:24.01`) and were corrected from the PDF.
The 2011 and one 2010 team print only initials; the owner identified them
(V.LOPEZ → Victor Lopez 322, J.BLANCO → Juan Blanco 328, J.M.MATEO → Josep
Maria Mateo 343, J.F.GARCIA → Jose Fco Garcia 5, E. JOSE → Edgar Jose 653,
J. GONZALEZ → Juan Gonzalez 1079, A. LAGO → Aleix Lago 660, N. PINYOL → Nil
Pinyol 714, L. MASCARELL → Laura Mascarell 646, M. VAZQUEZ → Mar Vazquez 642,
B. SANCHEZ → Berta Sanchez 643) and the leg names are stored in full.
`Carla Berenguel` has no record in either club list yet, so it stays unmapped.
The sheet's `Jose Fco Gracia` (2008) is a typo for Jose Fco. Garcia Navarrete
(5), handled as an owner override rather than by editing the source spelling.

### Stored names no longer carry sheet bookkeeping

`scripts/clean_athlete_names.py` removed the row prefix/suffix the legacy parsers
wrote into `athlete_name` (`1 258 (t) Francisco Javier Baz Vidal M-50` →
`Francisco Javier Baz Vidal`): **8,596 rows in 595 files**. Edge-only and
idempotent; a row is skipped when cleaning would stop it looking like a full
name. Applying it also unblocked **63 rows** that the noise had prevented from
matching the roster (all verified as spelling/truncation variants, no
cross-person merges).

## 10.000 metres marxa carries hours on purpose

`DISCIPLINES.md` row **id 49 `10.000 metres marxa`** declares `HH:mm:ss.cc`, and
that is correct: a 10 km walk legitimately passes 59 minutes (masters, women's
masters, beginners), which `mm:ss.cc` cannot express — `1:05:30.00` needs the
hour field. Sibling short events are consistent: `5K marxa (Ruta)` is
`mm:ss.cc`, `10K marxa (Ruta)` and `20 km marxa (Ruta)` are `HH:mm:ss`.

What was wrong was **our data**, which dropped the hour component. Fixed on
2026-11-19 by repair rule 7 and by `normalize_hhmmss_time()` in
`extract_catt.py`:

| before | after |
|---|---|
| `53:47.50` | `0:53:47.50` |
| `53:58` / `0:53:58` / `0:53:58.0` | `0:53:58.00` |
| `1:05:30` | `1:05:30.00` |

No database change is needed. Normalizing these values made one pre-existing
defect visible: `0:21:10.00` (Alicia Vázquez, 2019) is a 10 km walk in 21
minutes — impossible, so it now appears in the plausibility report for the
era-parser pass instead of hiding in an unparseable string.

## Rules of engagement for the remaining work

1. Never "fix" an implausible value by editing the number — re-extract from the
   source PDF or leave it visible. Guessing hides corruption.
2. Never dedupe on `(athlete, performance)` alone for combined/field events:
   AGENTS.md requires `(athlete, discipline, performance)` there.
3. After any data change: run the three commands at the top, then regenerate
   `seasons/<season>/discipline_mapping_report.md` and re-apply
   `scripts/add_internal_id.py` (`internal_id` is not written by the extractors).
