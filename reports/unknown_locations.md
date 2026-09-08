# Files with unknown event_location — NEED MANUAL REVIEW

These 15 season JSON files have empty or garbage `event_location` values.
The source PDFs are no longer available (404) or the location could not be extracted.

**Please fill in the correct city name for each file below.**

| # | Season | File | Current Location | Event Name | Date | Results |
|---|---|---|---|---|---|---|
| 1 | 2010 | `resulcatcadet19610.json` | Semifinal | (empty) | 19/6/2010 | 12 |
| 2 | 2011 | `resulcatalevi11611.json` | Club                                              Lic | (empty) | 11/6/2011 | 1 |
| 3 | 2011 | `resulcatbenjami11611.json` | Club                                                 Lic | (empty) | 11/6/2011 | 18 |
| 4 | 2011 | `resulcatcadet18611.json` | Club                                              Lic | (empty) | 18/6/2011 | 2 |
| 5 | 2011 | `resulcatclubsbenjami7511.json` | Club                                                Lic | (empty) | 7/5/2011 | 11 |
| 6 | 2011 | `resulcatinfantil11611.json` | Club                                                 Lic | (empty) | 11/6/2011 | 4 |
| 7 | 2011 | `resulcontrolcadet-juvenilcalella21511.json` | (empty) | 6a JORNADA CONTROL CADET-JUVENIL | 21/5/2011 | 0 |
| 8 | 2012 | `resulcatalevi90612.json` | Club                                             Lic | (empty) | 09/06/2012 | 15 |
| 9 | 2012 | `resulcatbenjami90612.json` | Club                                             Lic | (empty) | 09/06/2012 | 3 |
| 10 | 2012 | `resulcatcadet170612.json` | Club                                             Lic | (empty) | 17/06/2012 | 1 |
| 11 | 2012 | `resulcatcadetprevia260512.json` | Club                                                Lic | (empty) | 26/05/2012 | 1 |
| 12 | 2012 | `resulcatclubsalevi130512.json` | Final | (empty) | 13/05/2012 | 19 |
| 13 | 2012 | `resulcatclubsbenjami130512.json` | Club                                                  Lic | (empty) | 13/05/2012 | 6 |
| 14 | 2012 | `resulcatclubsinfantil120512.json` | Club                                                  Lic | (empty) | 12/05/2012 | 25 |
| 15 | 2012 | `resulcatinfantil90612.json` | Club                                             Lic | (empty) | 09/06/2012 | 9 |

## How to fill in

1. Edit the `event_location` field in each JSON file with the correct **city name**
2. The location should be just the city (e.g. "Barcelona", "Sabadell", "Mataró")
3. After filling in all locations, re-run: `python3 scripts/fix_event_locations.py --dry-run` to verify


## Hints from file names

- `resulcatcadet19610.json` → hints: cadet19610
- `resulcatalevi11611.json` → hints: alevi11611
- `resulcatbenjami11611.json` → hints: benjami11611
- `resulcatcadet18611.json` → hints: cadet18611
- `resulcatclubsbenjami7511.json` → hints: clubsbenjami7511
- `resulcatinfantil11611.json` → hints: infantil11611
- `resulcontrolcadet-juvenilcalella21511.json` → hints: controlcadet-juvenilcalella21511
- `resulcatalevi90612.json` → hints: alevi90612
- `resulcatbenjami90612.json` → hints: benjami90612
- `resulcatcadet170612.json` → hints: cadet170612
- `resulcatcadetprevia260512.json` → hints: cadetprevia260512
- `resulcatclubsalevi130512.json` → hints: clubsalevi130512
- `resulcatclubsbenjami130512.json` → hints: clubsbenjami130512
- `resulcatclubsinfantil120512.json` → hints: clubsinfantil120512
- `resulcatinfantil90612.json` → hints: infantil90612