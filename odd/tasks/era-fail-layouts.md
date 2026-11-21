# Era fail layouts 2013–2016 (issue #26 slice)

Authorized: user chose "Fail layouts (~42)" after push of 2016 tabular deep (2026-11-21).
Parent: GitHub issue #26 — remaining front after 2016 tabular profund.

## Specs

S1. "46 fail layouts amb CATT": cada PDF un layout d'era per modelar; els 4 sospitosos d'undercount ja recuperats (valls80214, cnatterritvalls90515, nastic121215, territoamposta70516 / resulterritpromoamposta70516); ~42 restants.
S2. Source list recovered from `/tmp/fail46_real.txt` (46 paths under seasons/2013–2016/json/). Durable copy: `reports/fail46_era_layouts.txt`.
S3. `regen_season.py` semantics: HEAD < stored ⇒ keep; recovery via merge_era_fallback or dedicated parser, never silent shrink.
S4. Never write %/COEF as mark; never resolve discipline by value alone — section evidence only.
S5. After each batch: `python3 -m unittest discover -s tests` green; `check_plausibility.py` must not increase above current baseline (260 on this branch).
S6. Prefer `pdf_cache/<year>/` over network downloads.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2 | Reproduce remaining fails vs HEAD using pdf_cache | | done |
| T2 | S1 | Classify remaining by layout family; pick first ≤5 batch | | done |
| T3 | S3,S4,S6 | Parser/golden for quote marks + Catalan/spaced dates (family 1) | | done |
| T4 | S5 | Suite + merge 2014/2015 + plausibility ≤260 | | done |
| T5 | S1,S3 | Amposta CURSA layout (date-in-title `5-3-16`) + veterans/trobada | | pending |

## Log

L1. push i a pel seguent
L2. User selected: Fail layouts (~42)
L3. Push of feat/issue-26-2016-tabular-deep done (8b4a8623, 72966f5e). List found at /tmp/fail46_real.txt (46 files). track-catt.json fail=16 is current-season pipeline fails, not this list.
L4. Probe of 46: 9 HEAD-sparse, 36 extract_fail, 1 no_pdf (`resulcatjuvenilcombinadespc13140216.json.json` double-ext). Root cause for family 1 (promocio SÈRIE): `_quote_to_decimal` / trailing gate missed `10''06`, `10"65`, `11'51`, trailing `F`; `parse_header` missed `d'abril` elision, spaced `24 / 01 / 2015`, and all-caps `CAMPIONAT`/`CONTROL`.
L5. Fix GREEN: 4 focused tests + suite 102 OK. `parse_promocio` on promovalls50414: 29→37 rows.
L6. Merge apply 2014 (+188) / 2015 (+262); cambrils240115 203→280; promovalls50414 185→192; valls70215 129→143. Zero (name,perf,disc) dups. Plausibility held at **260**. Amposta sheets (`resulcontrolterritamposta50316`, `resulcontrolampposta130216`) are a different family: CURSA multi-column + date glued in title (`5-3-16`) → era_year=0, parse_promocio=0 — next batch.
