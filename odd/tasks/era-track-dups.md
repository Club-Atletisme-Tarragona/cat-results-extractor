# Era track exact-dups (issue #26 slice)

Authorized: user chose "Dups de pista primer (13)" after fail-layouts close (2026-11-21).
Parent: GitHub issue #26 — remaining front after 2016 tabular deep + fail-layouts.

## Specs

S1. "Dups de pista primer (13)" — Exact duplicate groups `(athlete_name, discipline, performance)` on **track/marcha** rows in seasons 2005–2016 (not field attempts).
S2. Durable inventory: `reports/era_track_exact_dups.txt` (13 groups / 4 files at slice start).
S3. Track/marcha exact duplicates are never legitimate (unlike throw/jump same-mark attempts). Collapse each group to a single stored row.
S4. Do not shrink unrelated rows; do not touch field exact-dups in this slice.
S5. Never write %/COEF as mark; never resolve discipline by value alone.
S6. After changes: `python3 -m unittest discover -s tests` green; `check_plausibility.py` must not increase above current baseline (**260** on this branch).
S7. Prefer `pdf_cache/<year>/` over network downloads when verifying against PDF.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2 | Confirm 13 track groups + root cause per file (PDF/JSON) | | done |
| T2 | S3,S4 | Collapse exact track/marcha dups in the 4 files | | done |
| T3 | S6 | Suite + plausibility ≤260; re-count track dups = 0 | | done |

## Slice boundary

Parent branch `feat/issue-26-2016-tabular-deep` is already past the ~400 authored-line review slice vs `origin/main`. Keep this slice small (data-only collapse of proven track exact-dups); do not batch field/combinades dups here.

## Log

L1. Mirar què queda de #26 → Suspects veterans / dups era → Dups de pista primer (13)
L2. Root cause: each mark appears once in PDF; JSON held a second identical row (double extraction; indices far apart). Never field attempts in this slice.
L3. Collapse keep-first: nastic281115 230→222 (−8), combi21609 27→24 (−3), 10000+reunio200316 2→1 (−1), veteranspc60316 51→50 (−1). Re-scan 2005–2016 track exact-dup groups = 0.
L4. Suite 113 OK; plausibility **259** (was 260; −1 from dropped dup row). Track exact-dup groups = 0. Slice closed. Remaining #26 fronts: 64 field/combinades exact-dups (separate slice; never blind-dedupe), optional PR.
