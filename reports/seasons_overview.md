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
| 2010 | 50 | 603 | 57 | 7 |
| 2011 | 48 | 755 | 72 | 23 |
| 2012 | 30 | 700 | 66 | 16 |
| 2013 | 61 | 1291 | 131 | 47 |
| 2014 | 26 | 1177 | 196 | 112 |
| 2015 | 75 | 2594 | 296 | 194 |
| 2016 | 105 | 2787 | 266 | 147 |
| 2017 | 46 | 1344 | 159 | 35 |
| 2018 | 69 | 3068 | 222 | 69 |
| 2019 | 70 | 3421 | 199 | 57 |
| 2020 | 38 | 1653 | 185 | 52 |
| 2021 | 85 | 3654 | 204 | 51 |
| 2022 | 69 | 2376 | 194 | 37 |
| 2023 | 78 | 2775 | 216 | 41 |
| 2024 | 74 | 2826 | 198 | 32 |
| 2025 | 102 | 3085 | 240 | 17 |
| 2026 | 109 | 3634 | 202 | 3 |
| **Total** | **1328** | **39694** | **3273** | **958** |

Recuperació d'era (issue #26): 2017-2024 regenerades amb HEAD, 2013-2016
via merge_era_fallback (sèries de pista amb cronometratge manual 11"6 i
electrònic 10''07), i els suspects de màsters reparats llegint les taules
del PDF (repair_masters_sections.py). El que queda: 31 suspects amb decisió
pendent per fitxer (issue #27), 2 files creuades a st_Cto.ESP_master_Antequera
(Gemma Solé: 'Llargada 10.87/11.33' d'altres taules/categories).
