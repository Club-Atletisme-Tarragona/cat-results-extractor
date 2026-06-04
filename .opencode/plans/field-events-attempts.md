# Field Events - All Attempts Implementation Plan

## Problem

Currently, field events (Longitud, Triple Salto, Peso, Disco, Martillo, Jabalina) only extract the best mark. The PDF contains all 6 attempts with wind values per attempt for jumps. We need to generate one result entry per valid attempt.

## PDF Format (Conersys)

```
Nombre                             Fecha Nac.
Puesto Dorsal  Club  1   2   3   4   5   6  Resultado
Club   Licencia

LUCAS BUJ FUERTES  23/6/2009  X   5.90  5.33  -   -   -   5.90
CA Tarragona  CAT-3724284-...  0.0  0.6  1.7
```

- Name line: `NAME DOB  att1 att2 att3 att4 att5 att6  Resultado`
- Values: numeric (e.g., `5.90`), `X` (foul), `r` (retired), `-` (no attempt)
- Club line below: `CA Tarragona  CL8695  -2.6  -1.0  -1.3  -0.9  -2.3  0.0` — contains wind values per attempt

## Changes to `extract_catt.py`

### 1. New function: `extract_all_attempts_from_name_line()`

Place after `extract_result_from_name_line()`. Extracts all valid attempts from the name line after the DOB.

```python
def extract_all_attempts_from_name_line(lines, name_line_idx, sec_end, event_type, min_val, max_val):
    """Extract all valid attempts from the name line for field/jump events.
    
    Returns (best_mark, attempts_list) where attempts_list is a list of dicts:
    [{"attempt": 1, "value": "5.90", "wind": "+0.6"}, ...]
    
    Only includes valid numeric values. Skips X, r, -, 0.0, and the Resultado column.
    """
    name_line = lines[name_line_idx].strip()
    bd_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', name_line)
    if not bd_match:
        return "", []
    
    after_birth = name_line[bd_match.end():]
    tokens = after_birth.split()
    attempts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Skip invalid markers
        if token in ('X', 'x', 'r', '-', 'X', 'MMT', 'MMP', '=MMT', '=MMP'):
            continue
        if re.match(r'^\d+\.\d{2}$', token):
            val = float(token)
            if min_val <= val <= max_val:
                attempts.append(token)
    
    if not attempts:
        return "", []
    
    # The last value is usually the "Resultado" (best mark repeated) — skip it
    best_val = max(attempts, key=float)
    if attempts[-1] == best_val and len(attempts) > 1:
        attempts = attempts[:-1]
    
    if not attempts:
        return "", []
    
    best_mark = best_val
    
    # Collect wind values from club line below
    wind_values = []
    for j in range(name_line_idx + 1, min(name_line_idx + 10, sec_end)):
        fwd = lines[j].strip()
        if not fwd:
            continue
        if re.search(r'CA\s+Tarragona|Club', fwd, re.IGNORECASE):
            wind_matches = re.findall(r'([+-]\d+\.\d{1,2})', fwd)
            if wind_matches:
                wind_values = [w for w in wind_matches]
            break
    
    result_attempts = []
    for i, val in enumerate(attempts):
        wind = None
        if event_type == "jump" and i < len(wind_values):
            wind = wind_values[i]
        result_attempts.append({
            "attempt": i + 1,
            "value": val,
            "wind": wind,
        })
    
    return best_mark, result_attempts
```

### 2. Modify `parse_catt_athlete()` to return a list

Currently returns a single dict. Change to return a list of dicts (one per valid attempt for field/jump events, one item for all other events).

**Signature change:**
```python
def parse_catt_athlete(lines, athlete_block, sec_start, sec_end, event_name, wind, event_type, competicio, data_comp):
```

**Return change:**
- For `event_type == "jump"` or `event_type == "field"`: returns list of dicts, one per valid attempt
- For all other event types: returns list with single dict (current behavior)

**Implementation approach:**

At the end of `parse_catt_athlete()`, instead of building a single result dict and returning it, build a list:

```python
# For jump/field events, create one entry per valid attempt
if event_type in ("jump", "field"):
    best_mark, attempts = extract_all_attempts_from_name_line(
        lines, athlete_block.get('name_line_idx', sec_start), sec_end, event_type,
        min_val=3.0, max_val=80.0  # Will be adjusted per sub-type
    )
    if attempts:
        result_list = []
        for att in attempts:
            result_list.append({
                "lloc": lloc,
                "prova": event_name,
                "competicio": competicio,
                "data": data_comp,
                "atleta_nom": name,
                "atleta_naixement": birth_date,
                "atleta_licencia": licencia,
                "marca": att["value"],
                "vent": att["wind"],
            })
        return result_list
    # Fallback: if no attempts extracted, return single entry with best mark
    return [{...}]
else:
    return [{...}]  # single-item list for non-field events
```

**Need to adjust min/max per sub-type:**
- Jumps (Longitud, Triple Salto): min=3.0, max=20.0
- Height (Altura, Pértiga): min=1.0, max=7.0 — these stay as single result
- Throws (Peso, Disco, Martillo, Jabalina): min=3.0, max=80.0

### 3. Modify `parse_with_section_aware()` loop

The loop currently does:
```python
for athlete_block in catt_athletes:
    athlete = parse_catt_athlete(...)
    if athlete:
        results.append(athlete)
```

Change to:
```python
for athlete_block in catt_athletes:
    athletes = parse_catt_athlete(...)
    if athletes:
        for a in athletes:
            results.append(a)
```

### 4. Deduplication still works

The deduplication in `deduplicate_results()` compares `prova` + athlete name + performance value. Since each attempt has a unique performance value, they won't be deduplicated against each other.

## Output JSON Structure

For field/jump events, each valid attempt becomes a separate result entry:

```json
{
  "athlete_name": "LUCAS BUJ FUERTES",
  "athlete_dob": "23/6/2009",
  "athlete_id": "CAT-3724284",
  "performance": "5.90",
  "discipline": "Longitud Hombres",
  "wind": "+0.6"
},
{
  "athlete_name": "LUCAS BUJ FUERTES",
  "athlete_dob": "23/6/2009",
  "athlete_id": "CAT-3724284",
  "performance": "5.33",
  "discipline": "Longitud Hombres",
  "wind": "+1.7"
}
```

For throws (no wind), wind is `null`:
```json
{
  "athlete_name": "ADRIA SERRES PARDINES",
  "performance": "33.08",
  "discipline": "Disco (2 kg) Hombres",
  "wind": null
},
{
  "athlete_name": "ADRIA SERRES PARDINES",
  "performance": "30.12",
  "discipline": "Disco (2 kg) Hombres",
  "wind": null
}
```

## Expected Result Counts

**2D_hombres_A_Madrid.json:**
- LUCAS BUJ FUERTES (Longitud): 2 attempts → 2 entries
- EDMAR SUBIRÓS ARVEZ (Triple Salto): 5 attempts (1 X) → 5 entries
- ALVARO JOSE FERREZ HERNANDEZ (Peso): 3 attempts (2 X) → 3 entries
- ADRIA SERRES PARDINES (Disco): 6 attempts → 6 entries
- FERRAN SAGRERA PUJOL (Martillo): 6 attempts → 6 entries
- FATHI YAHIA (Jabalina): 6 attempts → 6 entries
- Current: 29 results → ~38 results (9 new entries)

**2D_mujeres_A_Burgos.json:**
- NATALIA SANCHEZ ALVAREZ (Longitud): 3 attempts → 3 entries
- NAYLA SENTIS TORAO (Triple Salto): 3 attempts → 3 entries
- CLAUDIA MIR CASELLAS (Peso): 6 attempts → 6 entries
- NOA NIN NAVAS (Disco): 6 attempts → 6 entries
- LIDIA GOMEZ DIAZ (Martillo): 6 attempts → 6 entries
- RAQUEL PLEGUEZUELOS GARCIA (Jabalina): 6 attempts → 6 entries
- Current: 28 results → ~40 results (12 new entries)

## Implementation Order

1. Add `extract_all_attempts_from_name_line()` function
2. Modify `parse_catt_athlete()` to return list (handle jump/field separately)
3. Modify `parse_with_section_aware()` loop to extend with list items
4. Test with both PDFs
5. Copy updated JSONs to `json/` directory
