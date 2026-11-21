# Era 2016 tabular deep parser (issue #26 slice)

Authorized: user chose "2016 tabular profund" for issue #26 (2026-11-21).
Parent: GitHub issue #26 — era-parser rework 2005–2016.

## Specs

S1. "2016 tabular profund (parser camps + pista al mateix PDF) — prioritat #1 de l'issue"
S2. "`parse_promocio_series()`: nou parser per al layout SÈRIE/LLOC/DORS/LLICENCIA/ATLETA/TEMPS (2013-2016)" — must also read field tables in the same PDF (Llargada multi-attempt, Alçada Marca, Pes/Disc attempts).
S3. "Ferran Jimenez 9\"6 present in the resulting JSON" — acceptance probe from issue #26.
S4. "NEVER output only the best result for salt (jump) or llançament (throw) events. Every valid attempt must be a separate result entry." (AGENTS.md) — Llargada/Pes/Disc: one row per valid attempt; X/`-`/nuls excluded.
S5. Alçada: store the sheet's Marca (best cleared height), not O/X cells; skip `nuls`. Matches stored era rows and section evidence.
S6. "Never write a %/COEF value as a mark" — not applicable to this sheet; keep guard.
S7. Comma marks (`1,30`, `3,99`) must normalize to dot decimals (`1.30`, `3.99`) at parse time so merge/dedup keys do not re-add the same attempt.
S8. Golden/unit coverage with real layout text (Valls 6/02/2016 family) before rewriting season JSON.

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S3,S4,S5,S7,S8 | inline RED unit tests for field+comma | pending | done (RED: 4 failures) |
| T2 | S7 | normalize comma marks in `_quote_to_decimal` + era merge keys | pending | done |
| T3 | S1,S2,S4,S5 | extend `parse_promocio_series` for field multi-attempt / Alçada Marca | pending | done |
| T4 | S1,S3 | re-extract `resulcontrolvalls60216` spot-check Ferran Jimenez + Disc attempts | pending | done |
| T5 | S8 | `python3 -m unittest discover -s tests` green; plausibility not increased | pending | done (97 OK; plausibility 220) |
| T6 | S1,S8 | hang-fix prefilter + mark floors; merge_era_fallback 2016 | | done |

## Log

L1. anem a fer la issue #26
L2. User selected: 2016 tabular profund
L3. Explore handoff: `_PROMOCIO_ROW_RE` is single-trailing-mark → cannot read Llargada/Pes attempt columns; Alçada Marca matched but left as `1,30`; merge keys use raw mark → PINYOL `1.30` + `1,30` dup in `seasons/2016/json/resulcontrolvalls60216.json`. PDF cached at `pdf_cache/2016/resulcontrolvalls60216.pdf`.
L4. Implemented: `_quote_to_decimal` comma→dot; `_parse_promocio_field_rows` for Llargada/Pes/Disc/Alçada Marca; `_is_catt_club` rejects CG Tarragona; merge keys normalize marks in `extract_catt.py` + `merge_era_fallback.py`.
L5. Spot-check Valls: Ferran Jimenez 9.60 manual; Montañes Disc 6 attempts; Pinyol Alçada 1.30 (no comma phantom). Stored JSON 226→205 (dropped CG leaks + comma dups). Suites: 10/10 promocio + 97/97 full. Plausibility 220 (unchanged).
L6. Slice closed for representative file. Remaining issue #26 fronts: ~42 fail layouts, 220 plausibility era, 110 dups, Antequera multi-category; apply field parser across other 2016 mixed sheets via merge_era_fallback.
L7. User: "commit i continua". Commit 8b4a8623 (Valls deep). merge_era_fallback hung on 5 veterans/combinades PDFs → `_promocio_worth_row_regex` prefilter; first apply raised plausibility 220→293 (height ghosts under track) → `_promocio_mark_plausible` floors; re-apply +149 rows across 4 files; plausibility back to 260 (HEAD baseline after Valls rewrite). Suite 99/99 OK.
L8. Commit hang-fix + merge recovery (this unit).
