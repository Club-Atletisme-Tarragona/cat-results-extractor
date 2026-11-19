# Data quality status

Audited 2026-11-19 across **1,329 JSON files / 27,044 results** in
`seasons/*/json/` plus the current season in `json/`. `json/imported/` is
excluded (third-party processed files, intentionally not our extractor output).

Re-run the audit at any time:

```bash
python3 -m unittest discover -s tests        # 46 tests: contract, goldens, units
python3 scripts/check_plausibility.py        # physically impossible values
python3 scripts/validate_performance.py      # performance vs DISCIPLINES.md format
```

## Verdict

| Seasons | Verdict |
|---|---|
| `seasons/2025`, `json/` (current) | **Valid and plausible.** Regenerated from source PDFs with current `extract_catt.py`. |
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
| **225** | Physically impossible values (e.g. a long-jump mark stored as a `60 METRES LLISOS` time in 2006 combined events) | per-era re-parsers, verified against the PDFs |
| **33** | Cross-discipline duplicate rows (same athlete + same mark under two disciplines, 2008–2024) | source-PDF check per row: **not resolvable by plausibility** (both copies are plausible), so nothing was guessed or deleted |
| 15 | Format mismatches: 6 quote-format marcha (`12'41''`), 5 misc, 3 veterans age/percentage column, 1 combined-table header stored as a discipline | targeted fixes |
| 1 | Unmapped discipline `60m tanques PC` (2017 infantile heat, no height in the header) | mapping rule |

## Open item on the database side

`DISCIPLINES.md` row **id 49 `10.000 metres marxa`** declares `HH:mm:ss.cc`,
but a 10,000 m walk takes 45–60 minutes and is naturally written `mm:ss.cc`
like every sibling marxa row (`5K marxa (Ruta)`, `20 km marxa`…). Until that row
is corrected, `validate_performance.py` keeps reporting the few 10,000 m marxa
values that reach the JSONs. Same class as the `2000 m obstacles` fix.

## Rules of engagement for the remaining work

1. Never "fix" an implausible value by editing the number — re-extract from the
   source PDF or leave it visible. Guessing hides corruption.
2. Never dedupe on `(athlete, performance)` alone for combined/field events:
   AGENTS.md requires `(athlete, discipline, performance)` there.
3. After any data change: run the three commands at the top, then regenerate
   `seasons/<season>/discipline_mapping_report.md` and re-apply
   `scripts/add_internal_id.py` (`internal_id` is not written by the extractors).
