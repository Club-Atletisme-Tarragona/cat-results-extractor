# Rundeck import runbook

Operational plan for the night-time auto-import (`app:extractor:import-seasons`
in `clubatletismetarragona.dev`), from the extractor side.

The extractor's job ends at `seasons/<year>/json/`. Everything below assumes the
consumer reads those files from GitHub and validates them with
`ImportPayloadContractValidator`.

## What the extractor guarantees today

- **Contract**: `is_short_track` lives on **every result row** and never in the
  header — the validator rejects a header-level key as a hard error (incident
  2026-11-24). A header-level key used to block *every* season, not just the
  current one.
- **Coverage**: all 1,330 season files (2005–2026, 40,699 rows) already satisfy
  that contract, so **no historical season is blocked by the extractor**.
- **Provenance**: every file carries `event_src` (the competition PDF) and
  `event_name` (the sheet's own title), which the consumer stores per mark.

## Schedules

| Job | Cadence | Command | Why |
|---|---|---|---|
| `extractor-import-current` | weekly, after the FCAT results are published | `app:extractor:import-seasons --year=<current>` | the normal path: new competitions of the running season |
| `extractor-import-history` | weekly, **a different day** than the current-season job | `app:extractor:import-seasons --year=<older> --limit=<small>` | progressive backfill, one bounded slice per run |

Rules that make those two safe:

1. **One season per history run.** Season is derived from `event_date`, so a
   year is a self-contained unit. `--limit` keeps each run reviewable and stops
   a backlog from turning into an unbounded transaction.
2. **Never run both at the same time.** They share the import and the quarantine
   tables; a long history run delays or fails the current-season pass, which is
   the one with a deadline.
3. **Oldest-last is fine.** Because every file already satisfies the contract,
   the history order is a product decision, not a technical constraint. Walking
   backwards from the current season keeps the most consulted data fresh.

## Guards (learned the hard way, 2026-11-24)

- **Dry-run after any extractor change, before the scheduled real run.** A
  contract break makes every file fail identically; the weekly job would burn an
  attempt per file while nobody is watching.
- **Treat `--dry-run` output as weak evidence.** In dry-run the use case returns
  before `recordAttempt()` and neither logs the reason nor counts
  `rowsDiscarded`, so a completely broken pass still prints `filesProcessed` and
  nothing else alarming. Confirm `marksCreated > 0` on a file you expect to
  import rather than trusting a clean-looking summary.
- **Quarantine is permanent at `attempts >= 3`.** There is no command to reset
  attempts; recovery means clearing `extractor_import_quarantine` by hand, which
  is an owner decision. Pause the job (`app_extractor_import_seasons`) rather
  than letting it keep burning attempts while a defect is open.
- **Pause the job when the extractor contract changes in this repo**, and resume
  only after a green suite plus one dry-run against a real season.

## Pre-flight checklist for the weekly job

- [ ] The extractor's `main` is deployed to whatever the consumer fetches from
      (the season JSONs are read from GitHub `main`).
- [ ] A file from the new competition exists under `seasons/<year>/json/` with
      `is_short_track` on its rows and no header key.
- [ ] `--dry-run` on that season reports the expected `filesProcessed` and a
      non-zero `marksCreated`.
- [ ] `scripts/check_plausibility.py` has not increased.
- [ ] The quarantine table has no file sitting at `attempts >= 3` that the run
      is expected to import.

## Extractor-side health checks worth scheduling alongside

| Check | Command | Meaning |
|---|---|---|
| Dataset contract | `python3 -m unittest discover -s tests` | header/row contract, goldens |
| Plausibility | `python3 scripts/check_plausibility.py` | impossible marks (must not grow) |
| Dates | `python3 scripts/check_event_dates.py` | stored date vs printed header (0 open expected) |
| Wind | `python3 scripts/check_wind.py` | nulls the sheet actually prints (16 known, none actionable) |

## Backfill progress tracking

`seasons/<year>/json/` is the only dataset, one file per competition. Progress is
"files imported" per season, which the consumer already counts
(`filesProcessed` / `filesDeferred` / `filesQuarantined`). Nothing in the
extractor needs a per-season flag: a season is complete when every file in its
directory has been imported and none sits in quarantine.
