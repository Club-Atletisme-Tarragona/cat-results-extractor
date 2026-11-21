# Era field/combinades exact-dups (issue #26 slice)

Authorized: user chose "Dups de camp/combinades" after track exact-dups close (2026-11-21).
Parent: GitHub issue #26 — remaining front after track exact-dups (`558e71f2`).

## Specs

S1. "Dups de camp/combinades" — Exact duplicate groups `(athlete_name, discipline, performance)` on **field** rows (Pes/Disc/Martell/Javelina/Llargada/Alçada/Perxa/…) in seasons 2005–2016.
S2. Durable inventory: `reports/era_field_exact_dups.txt` (64 groups / 14 files at slice start).
S3. Exact `(name, discipline, performance)` duplicates on field rows are double extraction (series + summary reprint, or merge re-add) — **not** legitimate second attempts. Distinct attempt values stay. Collapse each exact group to a single stored row (keep first).
S4. Do not shrink unrelated rows; do not invent discipline from value; never write %/COEF as mark.
S5. After changes: `python3 -m unittest discover -s tests` green; `check_plausibility.py` must not increase above current baseline (**259** after track-dups; do not exceed **260**).
S6. Prefer `pdf_cache/<year>/` over network downloads when verifying against PDF.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2 | Confirm 64 field groups + root cause (PDF series+summary) | | done |
| T2 | S3,S4 | Collapse exact field dups keep-first in the 14 files | | done |
| T3 | S5 | Suite + plausibility ≤260; re-count field exact-dups = 0 | | done |

## Slice boundary

Parent branch `feat/issue-26-2016-tabular-deep` is past the ~400 authored-line review slice vs `origin/main`. Keep this slice data-only (collapse proven exact field dups); do not batch parser work here.

## Log

L1. User selected: Dups de camp/combinades (after track dups `558e71f2`).
L2. Inventory: 64 exact field groups / 14 files (`reports/era_field_exact_dups.txt`). Combinades (Silvia/Helena/Maria/Didac) show a mirrored second block (gap≈8–16); Cambrils/nastic show series+summary reprint (gap far). Near-gap clubs (Pinyol/Pradillo/Saez) are adjacent re-adds of the same mark. PDF spot-checks: each attempt value appears once per section; the second JSON copy comes from the reprinted summary/series block.
L3. Collapse keep-first across 14 files: −65 exact duplicate rows (combinades560512 32→16, cambrils20213 180→169, combinades30310515 98→91, combinadespc9100116 18→11, etc.). Distinct attempt values kept. Re-scan 2005–2016 field exact-dup groups = 0.
L4. Suite 113 OK; plausibility **259** (held). Field exact-dup groups = 0. Slice closed. Remaining #26 fronts: optional PR for the branch; veterans_marks_suspect era already ≤10 (CSV now only 2026 outliers).
