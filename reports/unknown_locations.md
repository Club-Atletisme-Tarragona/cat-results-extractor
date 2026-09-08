# Files with unknown event_location — NEED MANUAL REVIEW

These 15 season JSON files have empty or garbage `event_location` values.
The source PDFs are no longer available (404) or the location could not be extracted.

**Please fill in the "Correct Location" column** with the city name for each file.

| # | Season | File | Event Name | Date | Results | Current Location | **Correct Location** |
|---|---|---|---|---|---|---|---|
| 1 | 2010 | `resulcatcadet19610.json` | (empty) | 19/6/2010 | 12 | Semifinal | ⬜ |
| 2 | 2011 | `resulcatalevi11611.json` | (empty) | 11/6/2011 | 1 | Club                                              Lic | ⬜ |
| 3 | 2011 | `resulcatbenjami11611.json` | (empty) | 11/6/2011 | 18 | Club                                                 Lic | ⬜ |
| 4 | 2011 | `resulcatcadet18611.json` | (empty) | 18/6/2011 | 2 | Club                                              Lic | ⬜ |
| 5 | 2011 | `resulcatclubsbenjami7511.json` | (empty) | 7/5/2011 | 11 | Club                                                Lic | ⬜ |
| 6 | 2011 | `resulcatinfantil11611.json` | (empty) | 11/6/2011 | 4 | Club                                                 Lic | ⬜ |
| 7 | 2011 | `resulcontrolcadet-juvenilcalella21511.json` | 6a JORNADA CONTROL CADET-JUVENIL | 21/5/2011 | 0 | (empty) | ⬜ |
| 8 | 2012 | `resulcatalevi90612.json` | (empty) | 09/06/2012 | 15 | Club                                             Lic | ⬜ |
| 9 | 2012 | `resulcatbenjami90612.json` | (empty) | 09/06/2012 | 3 | Club                                             Lic | ⬜ |
| 10 | 2012 | `resulcatcadet170612.json` | (empty) | 17/06/2012 | 1 | Club                                             Lic | ⬜ |
| 11 | 2012 | `resulcatcadetprevia260512.json` | (empty) | 26/05/2012 | 1 | Club                                                Lic | ⬜ |
| 12 | 2012 | `resulcatclubsalevi130512.json` | (empty) | 13/05/2012 | 19 | Final | ⬜ |
| 13 | 2012 | `resulcatclubsbenjami130512.json` | (empty) | 13/05/2012 | 6 | Club                                                  Lic | ⬜ |
| 14 | 2012 | `resulcatclubsinfantil120512.json` | (empty) | 12/05/2012 | 25 | Club                                                  Lic | ⬜ |
| 15 | 2012 | `resulcatinfantil90612.json` | (empty) | 09/06/2012 | 9 | Club                                             Lic | ⬜ |

---

## Fill-in instructions

After filling in the **Correct Location** column above, run:
```
python3 scripts/apply_manual_locations.py reports/unknown_locations.md
```

The script will read this table and update the `event_location` field in each JSON file.

## JSON file paths (for direct editing)

| File | JSON path |
|---|---|
| 1 | `seasons/2010/json/resulcatcadet19610.json` |
| 2 | `seasons/2011/json/resulcatalevi11611.json` |
| 3 | `seasons/2011/json/resulcatbenjami11611.json` |
| 4 | `seasons/2011/json/resulcatcadet18611.json` |
| 5 | `seasons/2011/json/resulcatclubsbenjami7511.json` |
| 6 | `seasons/2011/json/resulcatinfantil11611.json` |
| 7 | `seasons/2011/json/resulcontrolcadet-juvenilcalella21511.json` |
| 8 | `seasons/2012/json/resulcatalevi90612.json` |
| 9 | `seasons/2012/json/resulcatbenjami90612.json` |
| 10 | `seasons/2012/json/resulcatcadet170612.json` |
| 11 | `seasons/2012/json/resulcatcadetprevia260512.json` |
| 12 | `seasons/2012/json/resulcatclubsalevi130512.json` |
| 13 | `seasons/2012/json/resulcatclubsbenjami130512.json` |
| 14 | `seasons/2012/json/resulcatclubsinfantil120512.json` |
| 15 | `seasons/2012/json/resulcatinfantil90612.json` |

## Source PDF URLs

| File | Source URL |
|---|---|
| 1 | https://old.fcatletisme.cat/Pairelliure/airelliure2010/resulcatcadet19610.pdf |
| 2 | https://old.fcatletisme.cat/Pairelliure/airelliure2011/resulcatalevi11611.pdf |
| 3 | https://old.fcatletisme.cat/Pairelliure/airelliure2011/resulcatbenjami11611.pdf |
| 4 | https://old.fcatletisme.cat/Pairelliure/airelliure2011/resulcatcadet18611.pdf |
| 5 | https://old.fcatletisme.cat/Pairelliure/airelliure2011/resulcatclubsbenjami7511.pdf |
| 6 | https://old.fcatletisme.cat/Pairelliure/airelliure2011/resulcatinfantil11611.pdf |
| 7 | https://old.fcatletisme.cat/Promocio/promocio2011/resulcontrolcadet-juvenilcalella21511.pdf |
| 8 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatalevi90612.pdf |
| 9 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatbenjami90612.pdf |
| 10 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatcadet170612.pdf |
| 11 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatcadetprevia260512.pdf |
| 12 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatclubsalevi130512.pdf |
| 13 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatclubsbenjami130512.pdf |
| 14 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatclubsinfantil120512.pdf |
| 15 | https://old.fcatletisme.cat/Pairelliure/airelliure2012/resulcatinfantil90612.pdf |