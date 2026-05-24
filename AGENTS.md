# Rules & Policies for extract_catt.py

## Extraction Pipeline Order

Always try `extract_catt.py` first for all PDFs, regardless of type. Only use `extract_marcha.py` as a fallback when `extract_catt.py` finds no results (0 entries). Do not skip `extract_catt.py` based on URL patterns or filename detection.

## Marcha Extraction

`extract_marcha.py` may be needed as a fallback for certain marcha PDFs that `extract_catt.py` cannot parse. After `deduplicate_results(results)` in extract_marcha.py, filter out entries with `marca` in ("DQ", "DNS", "DNF") before the validation step to exclude invalid entries from the final JSON output.

## Name Cleaning

When extracting athlete names from PDF lines, always strip trailing noise:

- **Dates**: Remove `DD/MM/YYYY`
- **Percentages**: Remove values like `70,41%`, `71,69%` (appear in combined events master next to names)
- **Truncated times**: Remove values like `3:07.…` (ellipsis character U+2026, appears when PDF truncates time display)
- **Standard noise**: RT, DQ, ~ markers, decimal numbers (times, marks), MMT/MMP, trailing numbers

Apply cleaning in both `extract_name_from_line()` and `parse_combined_section()`.

## Deduplication Rules

When the same athlete+prova appears multiple times (from different extraction paths like SUMARIO vs regular section):

1. **If there's a valid result** (marca exists and is not DQ/DNS/empty): Keep ONLY the best valid result, discard all empty/DNS entries for that athlete+prova
2. **If there's NO valid result**: Keep the best DNS/DNS entry (prefer one with wind info)

The key change: use `elif without_result` instead of `if without_result` after processing `with_result`.

## Combined Events

Combined events (pentathlon, heptathlon, tetrathlon, hexathlon) produce two types of results:

1. **Combined event itself**: The main event (e.g., "Pentathlon Mujeres PC") with total points as performance
2. **Sub-events**: Individual events within the combination (e.g., "60m vallas Mujeres Pentatlón", "Longitud Mujeres Pentathlón") with individual results

Both should be extracted as separate events/entries.

## Event Pattern Matching

Patterns must include Catalan variants with accents: `Masculí`, `Femení`, `Alçada`, `Llargada`, `Pértiga`, `tanques`, `vallas`, `Pentathlón`, `Heptathlón`, etc.

Combined event patterns must start with the event name (Pentathlon, Heptathlon, etc.), NOT with a sub-event name (60m, Longitud, etc.).

**CRITICAL: PDFs use two formats for distance units:**
- **Abbreviated** (older PDFs): `100m`, `300m tanques`, `1500m obstacles` — matched by `\d+\s*m(t)?`
- **Full word** (newer PDFs, e.g., May 2026+): `100 metres llisos`, `300 metres tanques`, `3000 metres marxa` — matched by `\d+\s*metres\s+...`

Both `EVENT_PATTERNS` and `TRACK_PATTERNS` MUST include patterns for both formats. The `metres` format is required for all track events:
```python
r'\d{1,3}(?:\.\d{3})?\s*metres\s+(?:llisos|tanques|vallas|obstacles)\s+(?:masculins|Mascuins|femenins|femeni|masculi)'
```

MARCHA_PATTERNS must also handle the `metres` format:
```python
r'\d+\.?\d*\s*(?:m|metres)\s+(?:Marcha|Marxa)'  # Note: \s* between number and unit
```

The `\s*` (not `\s+`) is critical — it allows matching both "3000m marxa" and "3000 metres marxa".

## Section Detection

Event sections are identified by page headers (preceded by a date line `DD/MM/YYYY`), NOT by schedule lines (starting with `HH:MM`).

## License Extraction

Licenses follow patterns: `CL\d+`, `CT[\d\-]+`, `CAT\-\d+[A\-\.]*`, `IB\-\d+[A\-\.]*`

Extract from club code lines and data lines in athlete blocks.

---

## Text Extraction

Use `pdftotext -layout` to extract text from PDFs, preserving the visual layout. This is critical for multi-line athlete blocks where position, name, and results are spatially aligned.

## Header Parsing

The competition header is parsed from the first 30 lines of the PDF:

- **Competicio**: First line containing both "Jornada" and "Campionat"/"Campeonato", or first line with just "Campionat"/"Campeonato" (fallback for PDFs without "Jornada")
- **Ubicacio**: First line containing "Estadi", "Pista", "Pabellon", or "Pabellón"
- **Localitat**: Non-empty line between the competition name/venue and the date (DD/MM/YYYY), excluding competition name and venue lines
- **Data**: First `DD/MM/YYYY` pattern found in the first 30 lines

## Event Classification Priority

Events are classified in this **strict order** (first match wins):

1. **Combined** (pentathlon, heptathlon, etc.) - must match before other patterns
2. **Relay** (4x100m, 4x400m) - most specific pattern
3. **Marcha** (race walk) - contains "Marcha" or "Marxa"
4. **Height** (Altura/Alçada, Pértiga/Pertiga/Perxa) - checked before field
5. **Field** (Disco, Martillo/Martell, Peso/Pes, Jabalina/Dard) - checked before jump
6. **Jump** (Longitud/Llargada, Triple Salto/salt)
7. **Track** - anything with meters that isn't already classified
8. **Unknown** - fallback

## Result Extraction Value Ranges

Each event type validates extracted numeric values within specific ranges:

|| Event Type | Field | Min | Max |
|------------|-------|-----|-----|
| Track | Time | 5.0 | 60.0 |
| Marcha | Time | 5.0 | 60.0 |
| Jump | Distance (m) | 3.0 | 20.0 |
| Height | Height (m) | 1.0 | 7.0 |
| Field | Distance (m) | 3.0 | 80.0 |

Values outside these ranges are discarded. For track events, prefer `HH:MM.ss` format over decimal seconds.

**CRITICAL: Time extraction priority in `extract_track_result_new()` and `extract_marcha_result_new()`:**
1. Try `HH:MM:SS` format first (for very long events)
2. Try `HH:MM.ss` format (for events like 3000m: `11:26.41`, `17:11.94`)
3. Fall back to decimal seconds (for short events: `11.79`, `41.66`)

The `HH:MM.ss` pattern must be checked BEFORE decimal seconds, otherwise `11:26.41` gets parsed as `26.41` (the decimal part after the colon). This is a common bug when the event is misclassified (e.g., as "unknown" instead of "track" or "marcha").

**Always verify event classification** — if an event like "3000 metres marxa femenins" is classified as "unknown" instead of "marcha", the wrong extraction function is used and times like `17:11.94` get truncated to `11.94`.

## Format Detection

Sections use one of two formats:

### Old Format (inline)
Position and club code on the same line: `5  19  CATT  11.59`

### New Format (multi-line)
```
NAME DOB
pos  dorsal
CA Tarragona / AA Catalunya / etc.
CATT / AACB / etc. (club code)
license (CT438 / CAT-3930878-…)
results
```

Detection: If a name line is followed by a line containing only `pos dorsal` (no CATT), it's new format.

**IMPORTANT**: `is_new_format_section()` must only return True when CATT athletes are actually found in the section. Returning True for sections without CATT athletes causes false positives where the parser grabs athletes from adjacent sections (e.g., javelina results being misassigned to track events).

### New Format Detection Pitfalls

The new format parser must handle multiple club designation patterns:

1. `pos dorsal CATT` — CATT on position line (works)
2. `pos dorsal CA Tarragona` + `CATT` on next line — club name then club code (must work)
3. `pos dorsal` (no club) + `CA Tarragona` on next line + `CATT` on next — three-line pattern (must work)
4. `pos CATT` (no dorsal) + `CA Tarragona` on next line — used in some field events (must work)

All patterns must verify the full chain: name → pos → club_name → club_code → license → results.

## New Format Athlete Block Parsing

The new format requires verifying a specific chain:

1. **Name line**: Contains DOB (`DD/MM/YYYY`)
2. **Position line**: `pos  dorsal` (numbers only, no CATT)
3. **Club name line**: Contains "CA Tarragona" or other club names
4. **Club code line**: Short uppercase string (2-8 chars), must contain "CATT"
5. **License line**: Contains license pattern (`CL\d+`, `CT[\d\-]+`, `CAT\-\d+`)
6. **Result lines**: After license, until next athlete block or blank+position line

All steps must succeed to identify a valid athlete.

## Old Format Athlete Block Parsing

Two strategies:

1. **Position+CATT on same line**: `5  19  CATT  11.59` or `5  19  CA Tarragona  11.59`
2. **SUMARIO format**: Position + club name (e.g., `5  19  CA Tarragona`) on one line, then CATT on next line

Name line is found by looking backwards from the anchor (up to 8 lines), skipping header labels, club lines, and pure numeric lines.

Data lines are collected between the anchor and the next anchor (or section end).

## SUMARIO Sections

SUMARIO sections contain aggregated results from all heats/rounds/semifinals for track events. They appear **within** larger event sections (not as separate sections), between the individual round results.

**CRITICAL: Always skip SUMARIO sub-sections within event sections.** SUMARIO is just a summary that aggregates results already present in the individual rounds. Extracting from SUMARIO creates duplicate entries and can produce incorrect times (e.g., `11:26.41` from SUMARIO vs `26.41` from the main section when the time extraction regex fails to find the full time).

SUMARIO detection within sections:
1. Find lines containing "SUMARIO"
2. The SUMARIO block extends from that line to the next event header (date line + event name) or section end
3. When finding CATT athletes in a section, skip any athletes whose name line index falls within a SUMARIO range

SUMARIO format per athlete (3 lines):
```
[athlete name] [DOB]
[rank] [dorsal] [club name]
[club code] [series] [lane] [series rank] [overall rank] [time] [wind] [notes]
```

## Relay Parsing

Relay sections are parsed differently from individual events:

1. Find the CATT team line (position + CATT/CA Tarragona + result)
2. Extract team result (time or DNF/DNS/DQ)
3. Extract individual athlete names from subsequent lines (format: `dorsal NAME Gender` or `NAME Gender`, where Gender is "Hombre" or "Mujer")
4. Create one result entry per athlete with the same team result and position

Stop parsing athletes when hitting the next team block (another club name line).

## Combined Events Parsing

Combined events (pentathlon, heptathlon, etc.) have a table format:

```
Puesto Dorsal Nombre  Club   60m va... 1.000m... Altura...  Puntos  P.Líder
1   479   ANTONI CREUS MELGOSA        9.94   3:41.07   1.45   10.54   4.48   3458
        20/11/1964      JASB
        JA Sabadell                  818,0... 650,0(1) 696,0(1) 662,0(1) 632,0(1)
```

Parsing logic:

1. Match lines with `pos  dorsal  name` or just `dorsal  name` (dorsal is 3+ digits)
2. Extract total points from end of line (3-4 digit number)
3. Remove time results (`HH:MM.ss`), decimal results (`XX.XX`), percentages (`XX,XX%`)
4. Extract DOB and license from the next line (contains DOB pattern)
5. DNS lines are skipped only if they contain NO actual numeric results

## Club Line Detection

Known club patterns for skipping non-CATT athletes:

- CA Granollers, GEiE Giron[ía], CA Vic, JA Sabadell, CAVB, CAGB, BCNB, UABB, Barcelona At., UA Terrassa, UATB, UA Barberà

These are used to skip non-CATT athletes when searching for name lines and in position extraction.

## Position Extraction

Positions are extracted from lines matching: `pos  dorsal  CLUB_CODE`

Supported club codes: CA Tarragona, UABB, UATB, CAGB, CAVB, GEEG, JASB

The position is the first number, followed by the dorsal, followed by the club code abbreviation.

## Wind Extraction (Jump Events)

For Longitud and Triple Salto, wind is extracted by matching wind values to attempts:

1. Parse attempts from the name line (values between 3.0-20.0, plus X/r/- markers)
2. Find the best valid mark (max of valid attempts)
3. Look for wind values on the club line below (`CA Tarragona  CL11323  -0.5  -0.4`)
4. Match wind to best attempt by index position

If wind values aren't found on the club line, look for a single wind value on its own line.

## Output Structure

The JSON output has this structure:

```json
{
  "event_name": "full competition name - venue",
  "event_date": "DD/MM/YYYY",
  "event_location": "city/venue",
  "total_results": 42,
  "results": [
    {
      "athlete_name": "NAME",
      "athlete_dob": "DD/MM/YYYY",
      "athlete_id": "license",
      "performance": "time/distance/points",
      "discipline": "event name",
      "wind": "+1.2 or null"
    }
  ]
}
```

## Output Validation

Every result entry in the JSON output MUST have all three required fields populated (non-empty strings):

1. **athlete_name**: The athlete's name (non-empty)
2. **performance**: The result value (time, distance, points - non-empty)
3. **discipline**: The event name (non-empty)

Before writing the JSON output, validate each entry. If any of these fields is empty or missing:
- **Do NOT include** the entry in the output JSON
- **Print a warning** to stderr identifying the problematic entry

This prevents exporting incomplete/broken results. Warnings help identify extraction issues that need fixing in the parsing logic.

## Skip Labels

The following labels are used to skip header/metadata lines in multiple functions:

`Puesto`, `Dorsal`, `Club`, `Nombre`, `Fecha`, `Licencia`, `RESULT`, `Calle`, `Hora`, `Leyenda`, `Resultado`, `Serie`, `Gestion`, `Pagina`, `SUMARIO`, `Rank`, `Viento`, `Pasos`, `RESULTADOS`, `Ord`

These are used consistently across `_find_catt_old_format`, `_find_catt_new_format`, `parse_sumario_section`, and `parse_relay_section`.

## Long Race Time Format (1000m, 1500m, 3000m, 5000m)

**CRITICAL: Long-distance races use the `X'YY"ZZ` format** (e.g., `3'53"86` for 3 minutes, 53 seconds, 86 centiseconds).

The PDF uses:
- `'` (apostrophe) for minutes
- `"` (double quote) for seconds
- Two digits for centiseconds

**Regex patterns:**
- `parse_performance()` (territorial): `r"(\d{1,2})'(\d{2})\"(\d{2})"` for marcha and race events
- `parse_territorial_performance()`: Same pattern, but **MUST be checked BEFORE sprint logic**

**Bug to avoid:** The old regex `''` (two apostrophes) was wrong — the PDF uses `'` + `"` not `''`. Also centiseconds are always 2 digits (`\d{2}`), not 1 (`\d`).

**Order matters in `parse_territorial_performance()`:**
1. Check long race events (`['1000', '1500', '3000', '5000']`) FIRST with the `'` + `"` pattern
2. Then check sprints (`['60', '80', '100', '200', '400', '600', '800']`) with the `"` pattern only

**Never include `1000`, `1500`, `3000`, `5000` in the sprint keyword list** — they use minutes and would be misparsed as seconds if checked first.

**Output format:** Convert `X'YY"ZZ` to `X:YY.ZZ` (e.g., `3'53"86` → `3:53.86`).

## License vs Club Code

`CT-` prefixed codes (e.g., `CT-18283`, `CT18283`) are **license numbers**, NOT club codes. They follow the pattern `CT[\d\-]+`. Club codes are short uppercase strings like `CATT`, `JASB`, `BCNB`, etc. The parser must extract license numbers from license lines (after the club code line) and NOT treat them as club identifiers.

## CT- Code in Names

Some PDFs embed the license number directly in the name field (e.g., `CT-18283 MARINA MARTIN GONZALEZ`). The name extraction logic should NOT strip `CT-` codes from names — they are part of the athlete's license and appear in the PDF as-is. The license is also extracted separately from the license line below the name block.

## Season Summary

|| Season | PDFs with CA Tarragona | JSON files | Total results | Unique athletes |
|--------|----------------------|------------|---------------|-----------------|
| 2008-2009 | 47 | 47 | 117 | ~50 |
| 2009-2010 | 52 | 52 | 143 | ~60 |
| 2010-2011 | 55 | 55 | 119 | ~55 |
| 2011-2012 | 39 | 39 | 191 | TBD |
| 2012-2013 | 82 | 82 | 390 | TBD |
| 2013-2014 | 39 | 39 | 226 | 68 |
| 2014-2015 (AL+PC) | 62 | 62 | 255 | TBD |
| 2014-2015 | 43 | 43 | 406 | 115 |
| 2015-2016 | 41 | 41 | 409 | 98 |

**Notes:**
- 2013-2014: 154 total PDFs in calendar, 55 mention "TARRAGONA" or "CATT" in text, but only 39 have actual CA Tarragona results. The rest are other clubs (Nàstic, FAAC, etc.) that share the word "Tarragona" in their name/location.
- 2014-2015: URL structure changed for Pairelliure and Pcoberta — use `/2015/` instead of `/pairelliure2014/` or `/pcoberta2014/`. The `_CONTEXT_PATTERNS` in extract_promocio.py uses `url_context='20'` to detect this: when `url_context == '20'`, the URL subpath is just the year (e.g., `/Pairelliure/2015/`).
- 2015-2016: Promocio also uses `/2016/` instead of `/promocio2015/` (same pattern as Pairelliure/Pcoberta). 9 PDFs are combinades (RFEA format, slow ~50s each, parser generates duplicate results — needs dedicated parser). 153 total PDFs, 41 with CA Tarragona results.
- 2015-2016: Pairelliure calendar has 260 URLs (255 unique PDFs), Pcoberta has 73 URLs (71 unique PDFs). Some URLs point to `fcatletisme.cat/wp-content/uploads/` instead of `old.fcatletisme.cat`. **272 unique FCAT PDFs processed** with pdfplumber fallback (pdftotext broken on this machine due to missing libgpgme.so.11 and libpoppler.so.126). Found **63 events with CA Tarragona, 242 valid results** after filtering false positives (positions misidentified as results). JSON at `seasons/2015-2016/json/aire_lliure_pista_coberta_2015_2016.json`. Quality is lower than pdftotext-based extraction due to layout differences.
- 2014-2015 (AL+PC): **270 PDFs** from `pairelliure2014/` and `pcoberta2014/` calendars. PDFs use **RFEA format** (club name on separate line after athlete data: `3 379 (t) Adolf Milla Guasch 31/01/1998 LM 4 7.57` / `CA Tarragona CL22279`). Requires RFEA-specific parser (`process_2014_2015_rfea.py`) that looks BACK from club line to find athlete data. Found **62 events with CA Tarragona, 255 valid results**. Each PDF gets its own JSON file in `seasons/2014-2015/json/`.
- 2012-2013 (AL+PC): **242 PDFs** from `pairelliure2013/` and `pcoberta2013/` calendars. Same RFEA format as 2014-2015. Found **82 events with CA Tarragona, 390 valid results**. Each PDF gets its own JSON file in `seasons/2013-2014/json/`.
- 2011-2012 (AL+PC): **232 PDFs** from `pairelliure2012/` and `pcoberta2012/` calendars. Same RFEA format as 2014-2015. Found **39 events with CA Tarragona, 191 valid results** (28 new + 11 existing from prior extract_catt.py run). Each PDF gets its own JSON file in `seasons/2011-2012/json/`.
- **pdftotext is now functional** on this machine (version 25.03.0). Use `pdftotext -layout` for all new extractions — preserves spatial layout, much better than pdfplumber.
- Some PDFs have `(t)` markers in the text (heat/heat marker) — these are not part of athlete names and should be ignored.
- All JSONs include `event_src` with the reconstructed PDF URL.

