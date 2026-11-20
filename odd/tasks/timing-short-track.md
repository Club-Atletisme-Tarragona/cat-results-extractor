# Feature: is_short_track + timing (contracte de migració)

## Specs

S1: `"is_short_track": true` per a les competicions de pista coberta (a partir de la font: pista coberta al PDF).

S2: `"timing": "electronic" | "manual"` per fila. Absent → electrònic. La fila mana sobre la capçalera.

S3: cronometratge manual si el PDF ho indica: els resultats ho mostren en curses sense centèsimes, només decimals i molts cops després del decimal hi figura un `-` (per exemple en 60 llisos `7.2-`).

## Tasks

T1 (S1-S3): extractor — `is_short_track` a nivell de fitxer (capçalera/nom/URL), `timing` per fila (nivell de fila sempre mana), tests unitaris.
T2 (S1-S3): backfill dels 1,329 JSONs ja emmagatzemats (era-parsers inclosos) amb el mateix detector, sense re-extraure.
T3 (S1-S3): goldens, AGENTS.md (contracte de sortida), verificació completa + CI.

## Log

L2 (2026-11-20): T1 fet — detect_short_track + timing_from_mark a extract_catt.py,
export natiu, 11 tests nous (tests/test_timing_contract.py), goldens regenerats.
T2 fet — scripts/backfill_timing_contract.py: 1,329 fitxers, 446 pista coberta /
883 aire lliure, 37,799 files electronic / 0 manual (l'extractor sempre ha
normalitzat les marques a 2 decimals; el format manual '7.2-' no apareix a cap
font escanejada 2005-2026 — es deteccionara quan surti). Idempotent.
T3 fet — AGENTS.md (seccio Export Contract), goldens, 75/75 tests.

L1 (2026-11-20): "Haurem de fer un canvi gran del contracte... afegir mes coses per determinar les marques si son manuals, que en general n'hi hauran poques i si son de pista coberta" + contracte citat a S1-S3.
