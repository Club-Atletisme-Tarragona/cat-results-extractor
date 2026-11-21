# Retire `athletes/` derived aggregates (closes issue #20)

Authorized: user decided `athletes/` JSONs are discarded — per-competition
extraction is mature enough and duplication risk outweighs the value.
Original request (verbatim): "Crec que els json de @athletes/ els descartarem,
podriem eliminar-los i tot, i tot el que els generaba, extraient la informació
per competició cada cop està més afinat i hi ha mes confiança en la qualitat de
les dades, i així evitarem duplicats, crec que podem tancar la #20 i esborrar el
relacionat." Confirmed with "si" on the deletion scope.

## Specs

S1. `athletes/` (881 tracked JSON files) is deleted from the repository.
S2. Every generator/post-processor that exists only to produce or maintain
    `athletes/` is deleted: `scripts/aggregate_athletes.py`,
    `scripts/add_internal_id_athletes.py`, `scripts/split_athlete_files.py`,
    `scripts/merge_athlete_files.py`, `scripts/fix_montanes_2010_rows.py`.
S3. Shared tooling keeps its `seasons/` behavior and loses only the
    `athletes/` branch: `scripts/fix_empty_event_fields.py`,
    `scripts/add_internal_id.py`, `Makefile` (`athletes` target + help line).
S4. Tests and docs stop requiring `athletes/`: remove
    `TestAthleteFileContract` and `TestAggregatorCharacterization` from
    `tests/test_data_contract.py`; remove the AGENTS.md "Legacy Empty Fields
    (athletes/)" section.
S5. `python3 -m unittest discover -s tests` stays green; plausibility must not
    increase above the branch baseline (**259**).
S6. Issue #20 is closed as discarded (the `athletes/` half no longer exists;
    season-level `event_date`/`event_src` repair stays available).

## Tasks

| ID | Specs | Route | Commit | Status |
|----|-------|-------|--------|--------|
| T1 | S1,S2 | Delete `athletes/` + athletes-only scripts | | done |
| T2 | S3 | Trim shared scripts + Makefile | | done |
| T3 | S4 | Trim tests + AGENTS.md | | done |
| T4 | S5,S6 | Suite green, plausibility ≤259, close #20 | | done |

## Log

L1. Crec que els json de @athletes/ els descartarem, podriem eliminar-los i tot, i tot el que els generaba, extraient la informació per competició cada cop està més afinat i hi ha mes confiança en la qualitat de les dades, i així evitarem duplicats, crec que podem tancar la #20 i esborrar el relacionat.
L2. si (scope confirmed: full plan, incl. athletes-only one-shots)
L3. Deleted 881 `athletes/*.json` + 5 athletes-only scripts (`aggregate_athletes`,
`add_internal_id_athletes`, `split_athlete_files`, `merge_athlete_files`,
`fix_montanes_2010_rows`). Trimmed `fix_empty_event_fields.py` (seasons-only, audit
reports `AUDIT seasons/`), `add_internal_id.py` (no `ATHLETES_DIR`, no
`load_athlete_variants`, no canonical-variant fallback), `Makefile` (`athletes` target
and help line), `tests/test_data_contract.py` (dropped `TestAthleteFileContract` +
`TestAggregatorCharacterization`; #20 test now asserts the season audit), and the
AGENTS.md "Legacy Empty Fields" section (now records the retirement).
L4. Verification: suite **104 OK** (was 113; −9 from the two deleted classes);
plausibility **259** (unchanged). Issue #20 closed as discarded: its `athletes/`
half no longer exists, and season-level `event_date`/`event_src` are 0 empty.
