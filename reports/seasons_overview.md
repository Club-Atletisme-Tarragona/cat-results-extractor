# Seasons overview

One JSON file per competition PDF. *Athletes* counts distinct `internal_id`s
plus distinct unmatched identities (grouped with the same display cleaning the
unknown-athlete report uses). An athlete matched in one file and unmatched in
another counts once per side, so the athlete column is a close upper bound.

| Season | Competitions | Results | Athletes | of which unmapped |
|---:|---:|---:|---:|---:|
| 2005 | 39 | 365 | 33 | 2 |
| 2006 | 37 | 441 | 33 | 2 |
| 2007 | 36 | 275 | 32 | 5 |
| 2008 | 34 | 355 | 38 | 8 |
| 2009 | 47 | 515 | 34 | 1 |
| 2010 | 50 | 610 | 57 | 7 |
| 2011 | 48 | 762 | 72 | 23 |
| 2012 | 30 | 704 | 66 | 16 |
| 2013 | 61 | 1158 | 109 | 30 |
| 2014 | 26 | 806 | 103 | 32 |
| 2015 | 75 | 1791 | 158 | 65 |
| 2016 | 106 | 2193 | 161 | 49 |
| 2017 | 46 | 1344 | 159 | 35 |
| 2018 | 69 | 3068 | 222 | 69 |
| 2019 | 70 | 3421 | 199 | 57 |
| 2020 | 38 | 1653 | 185 | 52 |
| 2021 | 85 | 3654 | 204 | 51 |
| 2022 | 69 | 2376 | 194 | 37 |
| 2023 | 78 | 2775 | 216 | 41 |
| 2024 | 74 | 2826 | 198 | 33 |
| 2025 | 102 | 3085 | 240 | 17 |
| 2026 | 109 | 3634 | 202 | 3 |
| **Total** | **1329** | **37811** | **2915** | **635** |

Seasons 2017-2024 were regenerated with the HEAD extractor on 2026-11-19/20
(`scripts/regen_season.py`, per-file logs in `reports/regen_*.log`): the old
extractions predated the all-attempts, relay-leg and masters gains and
undercounted ~2x. The reintroduced rows were name-cleaned right after.
Season 2016 keeps its era-parser output: HEAD cannot read its tabular format
(comma surnames) and the stored file misses that era's track events - a
separate format-support job.
