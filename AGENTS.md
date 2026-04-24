# Rules & Policies for extract_catt.py

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

| Event Type | Field | Min | Max |
|------------|-------|-----|-----|
| Track | Time | 5.0 | 60.0 |
| Marcha | Time | 5.0 | 60.0 |
| Jump | Distance (m) | 3.0 | 20.0 |
| Height | Height (m) | 1.0 | 7.0 |
| Field | Distance (m) | 3.0 | 80.0 |

Values outside these ranges are discarded. For track events, prefer `HH:MM.ss` format over decimal seconds.

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

SUMARIO sections contain results for track events with series (heats, semifinals, finals).

Detection: Look for lines containing "SUMARIO", then look backwards up to 20 lines for the event name. Skip sub-event labels (Ronda, Serie, Semifinal, Final, Eliminatoria, Heats, Heat, Final A/B/1/2/3).

Format per athlete (3 lines):
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
