#!/usr/bin/env python3
"""
Extractora de resultats d'atletisme per al Club Atletisme Tarragona (CATT / CA Tarragona).
Extreu les dades dels atletes del CATT d'un PDF de resultats i les exporta en JSON.

Cada prova té el seu propi format d'extracció:
- Track (sprints, mig fons, fons, vallas): resultat a la línia CATT
- Marcha: resultat a la línia CATT
- Jumps (Longitud, Triple Salto): resultat a la línia del nom+naixement
- Height (Altura, Pértiga): resultat a la línia CATT o cap endavant
- Field (Disco, Martillo, Peso, Jabalina): resultat a la línia del nom+naixement
- Relay (4x100m, 4x400m): equip amb resultats, un registre per membre
"""

import subprocess
import sys
import re
import json
import os


def extract_text(pdf_path):
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error executant pdftotext: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def parse_header(text):
    competicio = ""
    ubicacio = ""
    localitat = ""
    data = ""
    lines = text.split('\n')

    # Generic competition name: any line containing "Jornada" and "Campionat"
    for i, line in enumerate(lines[:20]):
        stripped = line.strip()
        if 'Jornada' in stripped and 'Campionat' in stripped:
            competicio = stripped
            break

    # Generic venue: any line containing "Estadi", "Pista", "Pabellon", "Pabellón"
    for i, line in enumerate(lines[:20]):
        stripped = line.strip()
        if any(kw in stripped for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón', 'pabellon', 'pabellón']):
            ubicacio = stripped
            break

    # Extract localitat and date from the page header block
    # Pattern: competition name (or venue) → city → date, within first 30 lines
    for i, line in enumerate(lines[:30]):
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
        if date_match:
            data = date_match.group(1)
            # The localitat is the non-empty line before the date,
            # within the first 5 lines before the date
            for j in range(i - 1, max(i - 5, -1), -1):
                prev = lines[j].strip()
                if prev and not re.search(r'\d{2}/\d{2}/\d{4}', prev):
                    # Skip lines that are competition name or venue
                    if 'Jornada' in prev and 'Campionat' in prev:
                        continue
                    if any(kw in prev for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón']):
                        continue
                    localitat = prev
                    break
            break

    return competicio, ubicacio, localitat, data


# ============================================================================
# Event detection
# ============================================================================

EVENT_PATTERNS = [
    # Generic patterns that cover any event name format (Spanish + Catalan)
    # Track events: 60m, 100m, 300m, 600m, 1.000m, 3.000m, etc. (with or without space)
    r'(?:\d{1,3}(?:\.\d{3})?\s*m|\d+\s*m)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:Obst\.?\s+)?(?:Marcha\s+)?(?:Hombres|Mujeres|Mixto|masculins|femenins|masculina|femenina|masculino|femenino)',
    # Field/jump/height events (Spanish + Catalan)
    r'(?:Altura|Alçada|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|Peso|Jabalina|Dard)\s*(?:\(.*?\))?\s*(?:Hombres|Mujeres|Mixto|masculins|femenins|masculina|femenina|masculino|femenino)',
    # Relay events: 4x100m, 4x400m, 4x300m, Relleu 4x300
    r'(?:4x\d+\s*m|Relleu\s+4x\d+)',
    # Age category events
    r'(?:Longitud|Llargada|Altura|Alçada|Peso|Jabalina|Dard|Disco|Martillo|Triple\s+Salto|Triple\s+salt)\s+(?:Hombres|Mujeres|masculins|femenins)\s+U\d+[MF]',
    r'\d+\s*m\s*(?:Hombres|Mujeres|masculins|femenins)\s+U\d+[MF]',
    r'\d+\s*m\s*(?:tanques\s+)?(?:vallas\s+)?(?:Obst\.?\s+)?(?:Hombres|Mujeres|masculins|femenins)\s+U\d+[MF]',
    # Weighted events
    r'Peso\s+\(\d+k?\)\s*(?:Hombres|Mujeres)',
    r'Jabalina\s+\(\d+g\)\s*(?:Hombres|Mujeres)',
    r'Dard\s+\(\d+g\)\s*(?:Hombres|Mujeres)',
]

TRACK_PATTERNS = [
    r'(?:^|[\s(])\d{1,3}(?:\.\d{3})?\s*m\s*(?:tanques|vallas)?\s*(?:Obst\.?)?\s*(?:\(.*?\))?\s*(?:Hombres|Mujeres|Mixto|masculins|femenins|masculina|femenina)',
    r'\d{1,3}\s*m\s+(?:tanques|vallas|Obst\.?)\s+(?:Hombres|Mujeres|masculins|femenins)',
    r'\d{1,3}\s*m\s+(?:Hombres|Mujeres|masculins|femenins)',
]

MARCHA_PATTERNS = [
    r'\d+\.?\d*m\s+(?:Marcha|Marxa)',
]

JUMP_PATTERNS = [
    r'Triple\s+(?:Salto|salt)',
    r'(?:Longitud|Llargada)',
]

HEIGHT_PATTERNS = [
    r'(?:Altura|Alçada)',
    r'(?:Pértiga|Pertiga|Perxa)',
]

FIELD_PATTERNS = [
    r'Disco',
    r'(?:Martillo|Martell)',
    r'(?:Peso|Pes)',
    r'(?:Jabalina|Dard)',
]

RELAY_PATTERNS = [
    r'4x\d+m',
    r'Relleu\s+4x\d+',
]


def classify_event(event_name):
    if not event_name:
        return "unknown"
    # Check relay first (most specific pattern)
    for p in RELAY_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "relay"
    # Check marcha
    for p in MARCHA_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "marcha"
    # Check height (before field to avoid "Altura" being confused)
    for p in HEIGHT_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "height"
    # Check field events (before jump, since Peso/Jabalina are field)
    for p in FIELD_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "field"
    # Check jump events
    for p in JUMP_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "jump"
    # Track events - anything with meters that isn't already classified
    for p in TRACK_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "track"
    return "unknown"


def is_catt_line(line):
    return bool(re.search(r'\bCATT\b|\bCA\s+Tarragona\b', line))


def is_club_line(line):
    club_patterns = [
        r'\bCA\s+Granollers\b',
        r'\bGEiE\s+Giron[ía]\b',
        r'\bCA\s+Vic\b',
        r'\bJA\s+Sabadell\b',
        r'\bCAVB\b',
        r'\bCAGB\b',
        r'\bBCNB\b',
        r'\bUABB\b',
        r'\bBarcelona\s+At\.?\b',
        r'\bUA\s+Terrassa\b',
        r'\bUATB\b',
        r'\bUA\s+Barber[á]\b',
    ]
    for p in club_patterns:
        if re.search(p, line):
            return True
    return False


def is_name_line(line):
    return bool(re.search(r'\d{1,2}/\d{1,2}/\d{4}', line))


def extract_name_from_line(line):
    line = line.strip()
    line = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', line)
    line = re.sub(r'\s+RT\s+\S+', '', line)
    line = re.sub(r'\s+DQ\s*$', '', line)
    line = re.sub(r'\s+RT\s*$', '', line)
    line = re.sub(r'\s*[~>]+\w*\s*$', '', line)
    line = re.sub(r'\s*[~>]\s*$', '', line)
    line = re.sub(r'\s*\d+\.\d{2}\s*', ' ', line)
    line = re.sub(r'\s+[Xxr]\s*', ' ', line)
    line = re.sub(r'\s+[- XO]+\s*$', '', line)
    line = re.sub(r'\s+MMT\s*$', '', line)
    line = re.sub(r'\s+MMP\s*$', '', line)
    line = re.sub(r'\s+\d+\s*$', '', line)
    cleaned = ' '.join(line.split())
    return cleaned


def extract_license(lines, start_idx, end_idx):
    """Extract license from lines (already a list)."""
    for j in range(start_idx, min(end_idx, len(lines))):
        fwd_line = lines[j].strip()
        lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', fwd_line)
        if lic_match:
            lic = lic_match.group(1).strip()
            lic = re.sub(r'[\.\-]+\s*$', '', lic)
            if lic:
                return lic
    return ""


def extract_position(line):
    pos_match = re.match(r'\s*(\d+)\s+\d+\s+[A-Z]{2,}\b', line)
    if pos_match:
        return int(pos_match.group(1))
    pos_match2 = re.match(r'\s*(\d+)\s+\d+\s+CA\s+Tarragona', line)
    if pos_match2:
        return int(pos_match2.group(1))
    pos_match3 = re.match(r'\s*(\d+)\s+\d+\s+UABB', line)
    if pos_match3:
        return int(pos_match3.group(1))
    pos_match4 = re.match(r'\s*(\d+)\s+\d+\s+UATB', line)
    if pos_match4:
        return int(pos_match4.group(1))
    pos_match5 = re.match(r'\s*(\d+)\s+\d+\s+CAGB', line)
    if pos_match5:
        return int(pos_match5.group(1))
    pos_match6 = re.match(r'\s*(\d+)\s+\d+\s+CAVB', line)
    if pos_match6:
        return int(pos_match6.group(1))
    pos_match7 = re.match(r'\s*(\d+)\s+\d+\s+GEEG', line)
    if pos_match7:
        return int(pos_match7.group(1))
    pos_match8 = re.match(r'\s*(\d+)\s+\d+\s+JASB', line)
    if pos_match8:
        return int(pos_match8.group(1))
    return None


# ============================================================================
# Result extraction per event type
# ============================================================================

def extract_track_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank', 'Viento']
        if any(label in fwd_line for label in skip_labels):
            continue

        time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', fwd_line)
        if time_match:
            return time_match.group(1)

        for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', fwd_line):
            val = float(num_match.group(1))
            if val > 5.0 and val < 60.0:
                return num_match.group(1)
        for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{3})(?![\d.])', fwd_line):
            val = float(num_match.group(1))
            if val > 5.0 and val < 60.0:
                return num_match.group(1)[:5]

    return ""


def extract_marcha_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank', 'Viento', 'Pasos']
        if any(label in fwd_line for label in skip_labels):
            continue

        time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', fwd_line)
        if time_match:
            return time_match.group(1)

    return ""


def extract_jump_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        nums = re.findall(r'(\d+\.\d{2})', fwd_line)
        if nums:
            for num in reversed(nums):
                val = float(num)
                if val >= 3.0 and val <= 20.0:
                    return num

    return ""


def extract_height_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 15, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', fwd_line)
        if height_match:
            val = height_match.group(1)
            num_val = float(val)
            if num_val >= 1.0 and num_val <= 7.0:
                return val

    return ""


def extract_field_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        nums = re.findall(r'(\d+\.\d{2})', fwd_line)
        if nums:
            for num in reversed(nums):
                val = float(num)
                if val >= 8.0 and val <= 80.0:
                    return num

    return ""


def extract_jump_wind(lines, name_line_idx, sec_end):
    """Extract wind for the best mark in a jump event (Longitud, Triple Salto).
    
    The name line contains attempt results, and the club line below contains
    wind values per attempt. We match winds to attempts and return the wind
    for the best valid mark.
    """
    name_line = lines[name_line_idx]
    
    # Extract attempts from name line: list of (value, is_valid) where value is string or 'X'/'r'/'-'
    attempt_values = []
    # Find numeric values and special markers between name/birthdate and final result
    name_stripped = name_line.strip()
    bd_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', name_stripped)
    if not bd_match:
        return None
    
    after_birth = name_stripped[bd_match.end():]
    
    # Split into tokens and find attempt values
    # Format: "11.77     11.09        r                                    11.77 MMP"
    tokens = after_birth.split()
    attempts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token in ('X', 'r', '-', 'X', 'x'):
            attempts.append(token)
        elif re.match(r'^\d+\.\d{2}$', token):
            val = float(token)
            # Jump values are between 3.0 and 20.0
            if 3.0 <= val <= 20.0:
                attempts.append(token)
            elif val > 20.0:
                # This is likely the overall result at the end, skip
                break
    
    if not attempts:
        return None
    
    # Find the best valid mark among attempts
    valid_attempts = [(i, a) for i, a in enumerate(attempts) if a not in ('X', 'r', '-', 'x', '')]
    if not valid_attempts:
        return None
    
    # Best mark is the max valid attempt
    best_idx, best_val = max(valid_attempts, key=lambda x: float(x[1]))
    
    # Now find wind values from the club line (below position line)
    # Look for the club line that has wind values
    wind_values = []
    for j in range(name_line_idx + 1, min(name_line_idx + 10, sec_end)):
        fwd = lines[j].strip()
        if not fwd:
            continue
        # Skip lines that are just position numbers
        if re.match(r'^\s*\d+\s+\d+\s+', fwd) and not re.search(r'CA\s+Tarragona|Club|nombre', fwd, re.IGNORECASE):
            continue
        # Skip pure wind lines (single wind value centered)
        if re.match(r'^\s*[+-]?\d+\.\d\s*$', fwd):
            continue
        # Look for wind values on club lines
        # Club line pattern: "CA Tarragona  CL11323  -0.5  -0.4"
        if re.search(r'CA\s+Tarragona|Club', fwd, re.IGNORECASE):
            # Extract wind values (negative or positive decimals)
            wind_matches = re.findall(r'([+-]\d+\.\d{1,2})', fwd)
            if wind_matches:
                wind_values = [w for w in wind_matches]
                break
    
    if not wind_values:
        return None
    
    # Match wind to best attempt
    # Wind values are aligned with attempts in order by position
    # Each wind value corresponds to the attempt at the same index
    best_attempt_pos = best_idx
    
    if best_attempt_pos < len(wind_values):
        return wind_values[best_attempt_pos]
    
    # If we don't have enough winds, try to find the wind from the name-line wind line
    # (the single wind value shown on the position line)
    for j in range(name_line_idx + 1, min(name_line_idx + 5, sec_end)):
        fwd = lines[j].strip()
        if not fwd:
            continue
        # Look for a single wind value (like "-1.2" or "-0.4")
        wind_match = re.match(r'^\s*([+-]\d+\.\d{1,2})\s*$', fwd)
        if wind_match:
            return wind_match.group(1)
    
    return None


def extract_result_from_name_line(lines, name_line_idx, sec_end, event_type):
    """Extract result from the name line itself (for jumps and field events)."""
    # Check the name line and next few lines
    for j in range(name_line_idx, min(name_line_idx + 3, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        if event_type == "jump":
            nums = re.findall(r'(\d+\.\d{2})', fwd_line)
            if nums:
                for num in reversed(nums):
                    val = float(num)
                    if val >= 3.0 and val <= 20.0:
                        return num
        elif event_type == "field":
            nums = re.findall(r'(\d+\.\d{2})', fwd_line)
            if nums:
                for num in reversed(nums):
                    val = float(num)
                    if val >= 8.0 and val <= 80.0:
                        return num

    return ""


# ============================================================================
# Section parsing
# ============================================================================

def find_section_boundaries(lines):
    """Find event section boundaries.
    
    Event sections start with a page header containing:
    - Date line (DD/MM/YYYY)
    - Event name (right-aligned)
    - Time (left-aligned)
    - "Final" or similar
    
    We ONLY match page-header event starts (preceded by a date line), NOT schedule lines.
    """
    section_starts = []
    seen_events = set()
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        # Skip schedule lines (start with time pattern)
        if re.match(r'^\d{2}:\d{2}\s+', stripped):
            continue
        
        # Skip lines that are just "Final" or "HORARIO" etc
        if stripped in ('Final', 'HORARIO', 'Hora', 'Prueba', 'Ronda', 'SESIO', 'SESION'):
            continue
        
        # Check if this line matches an event pattern
        is_event = False
        for pattern in EVENT_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                is_event = True
                break
        
        if not is_event:
            continue
        
        # Must be preceded by a date line (page header event start)
        # Look back up to 10 lines for a date
        is_page_header_event = False
        for j in range(i - 1, max(i - 10, 0), -1):
            prev = lines[j].strip()
            if re.search(r'\d{2}/\d{2}/\d{4}', prev):
                is_page_header_event = True
                break
            if 'Página' in prev or 'Gestión' in prev:
                break  # Hit page footer, not a page header
            # If we hit a non-empty line that's not a date, stop looking
            if prev and not re.match(r'^\d{2}:\d{2}', prev):
                break
        
        if not is_page_header_event:
            continue
        
        # Deduplicate: skip if we've already seen this event name
        if stripped in seen_events:
            continue
        seen_events.add(stripped)
        
        section_starts.append((i, stripped))
    
    section_starts.append((len(lines), ""))
    return section_starts


def find_sumario_sections(lines):
    """Find SUMARIO sections in the PDF.
    
    SUMARIO sections contain summary results for track events with series.
    Format:
      [event name line] [sub-event like Ronda 1/Semifinal/Final] [blank] SUMARIO
      We look backwards, skipping sub-event labels, to find the real event name.
    """
    sumarios = []
    sub_event_labels = {'Ronda', 'Serie', 'Semifinal', 'Final', 'Eliminatoria',
                        'Combinadas', 'Heats', 'Heat', 'Final A', 'Final B',
                        'Final 1', 'Final 2', 'Final 3'}
    
    for i, line in enumerate(lines):
        if 'SUMARIO' in line.strip():
            event_name = ""
            for j in range(i - 1, max(i - 20, 0), -1):
                prev = lines[j].strip()
                if not prev:
                    continue
                # Skip lines that are just sub-event labels (Ronda 1, Semifinal, Final, etc.)
                # These are short lines that don't match any EVENT_PATTERN
                if len(prev) < 40 and not re.search(r'\d', prev):
                    continue
                # Skip pure sub-event label lines
                is_sub_label = False
                for label in sub_event_labels:
                    if re.match(rf'^{label}[\s\d/]*$', prev, re.IGNORECASE):
                        is_sub_label = True
                        break
                if is_sub_label:
                    continue
                # Check if this matches an event pattern
                for pattern in EVENT_PATTERNS:
                    if re.search(pattern, prev, re.IGNORECASE):
                        event_name = prev.strip()
                        break
                if event_name:
                    break
            
            if not event_name:
                continue
            
            sumarios.append((i, event_name))
    
    return sumarios


def parse_sumario_section(lines, sumario_idx, event_name, sec_end, competicio, data_comp):
    """Parse a SUMARIO section for track events.
    
    Format per athlete:
      [name] [birthdate]
      [rank] [dorsal] [club name]
      [club code] [series] [lane] [series_rank] [overall_rank] [time] [wind] [notes]
    """
    results = []
    
    # Find all CATT athletes in this sumario
    # Each athlete block is 3 lines: name, club_name, results
    i = sumario_idx + 1
    while i < min(sec_end, len(lines)):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check for athlete name line (has birthdate)
        if is_name_line(line):
            name_line = line
            name_line_idx = i
            
            # Next line should be club name with rank/dorsal
            if i + 1 >= len(lines):
                i += 1
                continue
            
            club_line = lines[i + 1].strip()
            # Check if this has a rank + dorsal + club
            rank_match = re.match(r'^\s*(\d+)\s+(\d+)\s+(.+)$', club_line)
            if not rank_match:
                i += 1
                continue
            
            rank = int(rank_match.group(1))
            dorsal = rank_match.group(2)
            club_name = rank_match.group(3).strip()
            
            # Check if this is CATT
            if 'CA Tarragona' not in club_name and 'CATT' not in club_name:
                i += 3
                continue
            
            # Next line has results
            if i + 2 >= len(lines):
                i += 1
                continue
            
            result_line = lines[i + 2].strip()
            
            # Extract time from result line
            time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', result_line)
            if time_match:
                marca = time_match.group(1)
            else:
                # Try short time format (sprints)
                for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', result_line):
                    val = float(num_match.group(1))
                    if val > 5.0 and val < 60.0:
                        marca = num_match.group(1)
                        break
                else:
                    i += 3
                    continue
            
            # Extract wind
            wind = None
            wind_match = re.search(r'([+-]\d+\.\d)', result_line)
            if wind_match:
                wind = wind_match.group(1)
            
            # Extract name
            bd_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', name_line)
            name = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', name_line).strip()
            name = ' '.join(name.split())
            
            # Extract license from result line
            lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', result_line)
            licencia = lic_match.group(1) if lic_match else ""
            licencia = re.sub(r'[\.\-]+\s*$', '', licencia)
            
            results.append({
                "lloc": rank,
                "prova": event_name,
                "competicio": competicio,
                "data": data_comp,
                "atleta_nom": name,
                "atleta_naixement": bd_match.group(1) if bd_match else "",
                "atleta_licencia": licencia,
                "marca": marca,
                "vent": wind,
            })
        
        i += 1
    
    return results


def is_new_format_section(lines, sec_start, sec_end):
    """Detect if this section uses the new multi-line format.
    
    New format characteristics:
    - Name line, then pos+dorsal on next line, then club name, then club code
    - Track events have separate result lines with T.Reacción/Resultado columns
    - No inline "CATT  results" pattern on same line as position
    
    Returns True if new format detected.
    """
    # Look for the pattern: name line followed by pos+dorsal (without CATT on same line)
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i].strip()
        if not line or not is_name_line(line):
            continue
        # Next line should be pos+dorsal (numbers only, no CATT)
        if i + 1 >= sec_end:
            continue
        next_line = lines[i + 1].strip()
        if re.match(r'^\s*\d+\s+\d+\s*$', next_line):
            # Check that this line does NOT contain CATT
            if 'CATT' not in next_line and 'CA Tarragona' not in next_line:
                return True
    return False


def find_catt_athletes_in_section(lines, sec_start, sec_end):
    """Find all CATT athletes in a section. Returns list of athlete blocks.
    
    Handles both old format (position+CATT on same line) and new format
    (multi-line blocks: name, pos+dorsal, club name, club code/license, results).
    
    Each block is a dict with:
    - 'anchor_idx': index of the anchor line (position + club line)
    - 'anchor_line': the anchor line text
    - 'position': the position/rank number
    - 'name_line_idx': index of the name+birthdate line
    - 'name_line': the name line text
    - 'data_lines': list of (idx, line) for additional data lines (results, wind, etc.)
    """
    athletes = []
    
    # Detect format
    new_format = is_new_format_section(lines, sec_start, sec_end)
    
    if new_format:
        athletes = _find_catt_new_format(lines, sec_start, sec_end)
    else:
        athletes = _find_catt_old_format(lines, sec_start, sec_end)
    
    return athletes


def _find_catt_old_format(lines, sec_start, sec_end):
    """Find CATT athletes in old format (position + CATT on same line)."""
    athletes = []
    
    # Strategy 1: Find lines with position + CATT/CA Tarragona (formats 1 & 2)
    anchor_pattern = re.compile(r'^\s*(\d+)\s+\d+\s+(?:CATT|CA\s+Tarragona)')
    
    # Strategy 2: Find SUMARIO format - lines with just club name (not CATT, just club full name)
    club_name_pattern = re.compile(r'^\s*(\d+)\s+\d+\s+(?:CA\s+Tarragona|CA\s+Granollers|CA\s+Vic|JA\s+Sabadell|GEiE\s+Giron[íaà]|Barcelona\s+At\.|UA\s+Terrassa|UA\s+Barber[àá]|CAVB|CAGB|BCNB|UABB|UATB|GEEG|JASB)$')
    
    all_anchors = []  # list of (idx, is_club_name_line)
    
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i]
        stripped = line.strip()
        
        # Check for format 1/2: position + CATT/CA Tarragona on same line
        if anchor_pattern.search(line):
            all_anchors.append((i, False))
        # Check for format 3 (SUMARIO): position + club name only
        elif club_name_pattern.search(stripped):
            all_anchors.append((i, True))
    
    for anchor_idx, is_club_name in all_anchors:
        anchor_line = lines[anchor_idx]
        pos_match = re.match(r'^\s*(\d+)', anchor_line)
        if not pos_match:
            continue
        pos = int(pos_match.group(1))
        
        # For SUMARIO format, check if next line has CATT
        if is_club_name:
            if anchor_idx + 1 >= len(lines):
                continue
            next_line = lines[anchor_idx + 1]
            if 'CATT' not in next_line:
                continue
            anchor_line = next_line
        
        # Check this is actually CATT
        if 'CATT' not in anchor_line and 'CA Tarragona' not in anchor_line:
            continue
        
        # Find the name line: look backwards from anchor
        name_line_idx = None
        name_line = None
        
        for j in range(anchor_idx - 1, max(anchor_idx - 8, sec_start - 1), -1):
            prev = lines[j].strip()
            if not prev or len(prev) < 4:
                continue
            if re.match(r'^\s*\d+\s+\d+\s+[A-Z]', prev) and 'CATT' not in prev and 'CA Tarragona' not in prev:
                continue
            skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                           'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                           'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                           'Gestion', 'Pagina', 'SUMARIO', 'Rank']
            if any(label in prev for label in skip_labels):
                continue
            if is_club_line(prev):
                continue
            if re.match(r'^[\d\.\-\s]+$', prev):
                continue
            if is_name_line(prev):
                name_line_idx = j
                name_line = prev
                break
        
        # Collect data lines
        data_lines = []
        anchor_pos = all_anchors.index((anchor_idx, is_club_name))
        next_anchor_idx = all_anchors[anchor_pos + 1][0] if anchor_pos + 1 < len(all_anchors) else sec_end
        
        for j in range(anchor_idx + 1, min(next_anchor_idx, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            if re.match(r'^\s*\d+\s+\d+\s+(?:CATT|CA\s+Tarragona)', fwd):
                break
            if any(label in fwd for label in skip_labels):
                continue
            data_lines.append((j, lines[j]))
        
        athletes.append({
            'position_line_idx': anchor_idx,
            'position_line': anchor_line,
            'position': pos,
            'name_line_idx': name_line_idx,
            'name_line': name_line,
            'data_lines': data_lines,
        })
    
    return athletes


def _find_catt_new_format(lines, sec_start, sec_end):
    """Find CATT athletes in new multi-line format.
    
    New format athlete block (track events):
      Line N:   NAME DOB
      Line N+1: pos  dorsal
      Line N+2: CA Tarragona / AA Catalunya / etc.
      Line N+3: CATT / AACB / etc. (club code)
      Line N+4: license (CT438 / CAT-3930878-… / etc.)
      Line N+5: results
    
    We must verify the club name is specifically "CA Tarragona" or "CATT".
    """
    athletes = []
    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                   'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                   'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
    
    # Find all name lines
    name_line_indices = []
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i].strip()
        if is_name_line(line):
            # Make sure it's not a header line
            if not any(label in line for label in skip_labels):
                name_line_indices.append(i)
    
    for name_idx in name_line_indices:
        # Look for the multi-line block starting from this name line
        # Pattern: name -> pos+dorsal -> club_name -> club_code -> license -> results
        
        # Find pos+dorsal line (next non-empty line)
        pos_line_idx = None
        for j in range(name_idx + 1, min(name_idx + 5, sec_end)):
            fwd = lines[j].strip()
            if fwd:
                pos_line_idx = j
                break
        
        if pos_line_idx is None:
            continue
        
        # Extract position from pos line
        pos_match = re.match(r'^\s*(\d+)\s+\d+', lines[pos_line_idx])
        if not pos_match:
            continue
        pos = int(pos_match.group(1))
        
        # Look for the club name line (3 lines after pos line max)
        club_name_line_idx = None
        club_name_line = None
        for j in range(pos_line_idx + 1, min(pos_line_idx + 4, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            # Club name line contains "CA Tarragona" or other club names
            if re.search(r'\bCA\s+Tarragona\b|\bAA\s+Catalunya\b|\bFACVAC\s+Valls\b|\bCN\s+Reus\b|\bUA\s+Montsi[àa]\b', fwd, re.IGNORECASE):
                club_name_line_idx = j
                club_name_line = fwd
                break
        
        if club_name_line_idx is None:
            continue
        
        # Verify this is CA Tarragona specifically
        if 'CA Tarragona' not in club_name_line and 'CATT' not in club_name_line:
            continue
        
        # Find the club code line (CATT, AACB, etc.) - next non-empty line after club name
        club_code_line_idx = None
        club_code_line = None
        for j in range(club_name_line_idx + 1, min(club_name_line_idx + 3, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            # Club code is a short uppercase string (2-6 chars)
            if re.match(r'^[A-Z]{2,8}$', fwd):
                club_code_line_idx = j
                club_code_line = fwd
                break
        
        if club_code_line_idx is None:
            continue
        
        # Verify the club code is CATT
        if 'CATT' not in club_code_line:
            continue
        
        # Find the license line (next non-empty line after club code)
        license_line_idx = None
        license_line = None
        for j in range(club_code_line_idx + 1, min(club_code_line_idx + 3, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            # License line contains a license pattern
            if re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+)', fwd):
                license_line_idx = j
                license_line = fwd
                break
        
        # Collect all lines from name to results (up to 10 lines after name)
        block_lines = []
        for j in range(name_idx, min(name_idx + 10, sec_end)):
            block_lines.append((j, lines[j]))
        
        # Check if we've hit the next athlete block
        next_name_idx = None
        for ni in name_line_indices:
            if ni > name_idx:
                next_name_idx = ni
                break
        
        # Collect data lines (after license_line_idx until next athlete or blank+next pos)
        data_lines = []
        end_idx = next_name_idx if next_name_idx else sec_end
        for j in range(license_line_idx + 1, min(end_idx, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            # Stop at header lines
            if any(label in fwd for label in skip_labels):
                continue
            # Stop at next athlete's pos line
            if re.match(r'^\s*\d+\s+\d+\s*$', fwd):
                break
            data_lines.append((j, lines[j]))
        
        athletes.append({
            'position_line_idx': club_name_line_idx,
            'position_line': club_name_line,
            'position': pos,
            'name_line_idx': name_idx,
            'name_line': lines[name_idx].strip(),
            'data_lines': data_lines,
            'new_format': True,
            'pos_line_idx': pos_line_idx,
            'block_lines': block_lines,
        })
    
    return athletes


def find_name_line(lines, result_line_idx, sec_start):
    """Find the name+birthdate line for an athlete, looking backwards from the CATT result line."""
    for j in range(result_line_idx - 1, max(result_line_idx - 30, sec_start - 1), -1):
        prev_line = lines[j].strip()
        if not prev_line or len(prev_line) < 4:
            continue
        if re.match(r'^\d+\s+\d+', prev_line):
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                       'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                       'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in prev_line for label in skip_labels):
            continue
        if is_club_line(prev_line):
            continue
        if re.match(r'^[\d\.\-\s]+$', prev_line):
            continue
        if is_name_line(prev_line):
            return j, prev_line
    return None, None


def extract_track_result_new(lines, athlete_block, sec_end):
    """Extract track result for new multi-line format.
    
    New format: name, pos+dorsal, club name, CATT, license+result lines.
    The result is on the line(s) after the CATT line, in the Resultado column.
    """
    catt_idx = athlete_block['position_line_idx']
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all lines in the athlete's block
    all_block_texts = []
    for idx, line in block_lines:
        all_block_texts.append(line.strip())
    # Also include data lines
    for idx, line in athlete_block['data_lines']:
        all_block_texts.append(line.strip())
    
    combined = ' '.join(all_block_texts)
    
    # Try time format first (e.g., 1:11.69)
    time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', combined)
    if time_match:
        return time_match.group(1)
    
    # Try short time format (e.g., 11.59, 17.52)
    for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', combined):
        val = float(num_match.group(1))
        if val > 5.0 and val < 60.0:
            return num_match.group(1)
    
    # Try 3-decimal format
    for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{3})(?![\d.])', combined):
        val = float(num_match.group(1))
        if val > 5.0 and val < 60.0:
            return num_match.group(1)[:5]
    
    return ""


def extract_height_result_new(lines, athlete_block, sec_end):
    """Extract height result for new multi-line format.
    
    New format: name+markers, pos+dorsal, club name, CATT+license+markers, then result.
    The result is found on the line after the markers, or in the block.
    """
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all text in the block
    all_texts = []
    for idx, line in block_lines:
        all_texts.append(line.strip())
    for idx, line in athlete_block['data_lines']:
        all_texts.append(line.strip())
    
    combined = ' '.join(all_texts)
    
    # Look for height value with MMP/MMT marker
    # Pattern: "1.15 MMP" or "1.06"
    height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', combined)
    if height_match:
        val = height_match.group(1)
        num_val = float(val)
        if num_val >= 1.0 and num_val <= 7.0:
            return val
    
    # Also try to find O/XXO/XXX pattern and extract the last cleared height
    # The heights are in the section header, and we need to match them with O/XXO/XXX
    # But for simplicity, let's look for the result value at the end of the block
    
    # Find the result line - it has the final height with MMP/MMT or just a number
    for text in all_texts:
        # Skip lines with O/XXO/XXX markers
        if re.search(r'\b(O|XXO|XO|XXX)\b', text) and not re.search(r'\d+\.\d{2}', text):
            continue
        # Look for height values
        nums = re.findall(r'(\d+\.\d{2})', text)
        for num in nums:
            val = float(num)
            if 1.0 <= val <= 7.0:
                return num
    
    return ""


def extract_field_result_new(lines, athlete_block, sec_end):
    """Extract field result for new multi-line format.
    
    New format for field events (Peso, Disco, etc.):
      Line 1: NAME DOB  attempt1 attempt2 attempt3 ...
      Line 2: pos  dorsal  CA Tarragona  CATT  remaining attempts
      Line 3: license
    
    The result is the best (last) valid mark.
    """
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all text in the block
    all_texts = []
    for idx, line in block_lines:
        all_texts.append(line.strip())
    for idx, line in athlete_block['data_lines']:
        all_texts.append(line.strip())
    
    combined = ' '.join(all_texts)
    
    # Find all numeric values in range 8.0-80.0
    nums = re.findall(r'(\d+\.\d{2})', combined)
    if nums:
        for num in reversed(nums):
            val = float(num)
            if val >= 8.0 and val <= 80.0:
                return num
    
    return ""


def parse_catt_athlete(lines, athlete_block, sec_start, sec_end, event_name, wind, event_type, competicio, data_comp):
    """Parse a single CATT athlete from a block found by find_catt_athletes_in_section."""
    name_line = athlete_block['name_line']
    anchor_line = athlete_block['position_line']
    data_lines = athlete_block['data_lines']
    new_format = athlete_block.get('new_format', False)
    block_lines = athlete_block.get('block_lines', [])

    if not name_line:
        return None

    name = extract_name_from_line(name_line)
    bd_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', name_line)
    birth_date = bd_match.group(1) if bd_match else ""

    # Find license from block lines and data lines
    licencia = ""
    # Search in block lines first (new format)
    for idx, line in block_lines:
        lic = extract_license(lines, idx, min(idx + 5, sec_end))
        if lic:
            licencia = lic
            break
    # Also search in data lines
    if not licencia:
        for idx, line in data_lines:
            lic = extract_license(lines, idx, min(idx + 5, sec_end))
            if lic:
                licencia = lic
                break

    # Find position
    lloc = athlete_block['position']

    # Find result
    marca = ""
    if event_type == "track":
        if new_format:
            marca = extract_track_result_new(lines, athlete_block, sec_end)
        else:
            marca = extract_track_result(lines, athlete_block['position_line_idx'], sec_end)
    elif event_type == "marcha":
        marca = extract_marcha_result(lines, athlete_block['position_line_idx'], sec_end)
    elif event_type == "jump":
        if new_format:
            # Result is on the name line (horizontal format with attempts)
            marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "jump")
            if not marca:
                # Try block lines
                for idx, line in block_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 3.0 and val <= 20.0:
                                marca = num
                                break
                    if marca:
                        break
            # Extract wind for the best mark
            vent = extract_jump_wind(lines, athlete_block['name_line_idx'], sec_end)
            if vent:
                wind = vent
        else:
            # Old format
            marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "jump")
            if not marca:
                for idx, line in data_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 3.0 and val <= 20.0:
                                marca = num
                                break
                    if marca:
                        break
            vent = extract_jump_wind(lines, athlete_block['name_line_idx'], sec_end)
            if vent:
                wind = vent
    elif event_type == "height":
        if new_format:
            marca = extract_height_result_new(lines, athlete_block, sec_end)
        else:
            for idx, line in data_lines:
                fwd = line.strip()
                if not fwd:
                    continue
                skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                               'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                               'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                if any(label in fwd for label in skip_labels):
                    continue
                height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', fwd)
                if height_match:
                    val = height_match.group(1)
                    num_val = float(val)
                    if num_val >= 1.0 and num_val <= 7.0:
                        marca = val
                        break
    elif event_type == "field":
        if new_format:
            marca = extract_field_result_new(lines, athlete_block, sec_end)
        else:
            marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "field")
            if not marca:
                for idx, line in data_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 8.0 and val <= 80.0:
                                marca = num
                                break
                    if marca:
                        break

    marca = re.sub(r'\s+(MMT|MMP|DNS|DQ|RT.*)$', '', marca).strip()

    return {
        "lloc": lloc,
        "prova": event_name,
        "competicio": competicio,
        "data": data_comp,
        "atleta_nom": name,
        "atleta_naixement": birth_date,
        "atleta_licencia": licencia,
        "marca": marca,
        "vent": wind,
    }


def parse_relay_section(lines, sec_start, sec_end, event_name, competicio, data_comp):
    """Parse relay section. Returns one result per athlete in the CATT team."""
    results = []

    # Find the CATT team block
    # Format:
    #   5  19  CA Tarragona  CATT  3  43.85  8
    #   20  Hugo Jules SAIZ SANTOLARIA  Hombre
    #   19  Ismael VALLES FERNANDEZ  Hombre
    #   19  Jan SANS RIOLA  Hombre
    #        Unai ORTIZ DE LANDAZURI ONTOSO  Hombre

    catt_team_start = None
    catt_team_result = None

    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i]
        # Check for CATT team line: has position + CATT or CA Tarragona + result
        if (re.search(r'\bCATT\b', line) or re.search(r'\bCA\s+Tarragona\b', line)):
            pos = extract_position(line)
            if pos is not None:
                catt_team_start = i
                # Extract team result from this line
                result_match = re.search(r'(\d{1,2}:\d{2}\.\d{2}|\d+\.\d{2}|DNF|DNS|DQ)', line)
                if result_match:
                    catt_team_result = result_match.group(1).strip()
                break

    if catt_team_start is None:
        return results

    # Find all athlete names after the CATT team line
    # Athletes are listed with format: "dorsal NAME Gender" or "NAME Gender"
    # A new team block starts with: "pos  dorsal  CLUB_NAME  CLUB_CODE"
    athletes = []
    team_line_pattern = re.compile(r'^\s*\d+\s+\d+\s+(?:UA\s+Terrassa|CA\s+Vic|Barcelona\s+At\.|GEiE\s+Giron[íaà]|JA\s+Sabadell|CA\s+Granollers|UA\s+Barber[àá]|CA\s+Tarragona|CAVB|CAGB|BCNB|UABB|UATB|GEEG|JASB)')
    
    for i in range(catt_team_start + 1, min(sec_end, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # Check if we've hit the next team (new team block line)
        if team_line_pattern.match(line):
            break

        # Skip header-like lines
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                       'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                       'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in line for label in skip_labels):
            continue

        # Match athlete name lines: "dorsal NAME Gender" or "NAME Gender"
        # Gender is "Hombre" or "Mujer"
        athlete_match = re.search(r'(?:\d+\s+)?(.+?)\s+(?:Hombre|Mujer)\s*$', line)
        if athlete_match:
            athlete_name = athlete_match.group(1).strip()
            # Clean up the name
            athlete_name = ' '.join(athlete_name.split())
            if athlete_name and len(athlete_name) > 3:
                athletes.append(athlete_name)

    # Find license for the team
    licencia = ""
    for i in range(catt_team_start, min(catt_team_start + 10, sec_end)):
        lic = extract_license(lines, i, min(i + 5, sec_end))
        if lic:
            licencia = lic
            break

    # Get position
    team_line = lines[catt_team_start]
    lloc = extract_position(team_line)

    # Create one result per athlete
    for athlete_name in athletes:
        results.append({
            "lloc": lloc,
            "prova": event_name,
            "competicio": competicio,
            "data": data_comp,
            "atleta_nom": athlete_name,
            "atleta_naixement": "",
            "atleta_licencia": licencia,
            "marca": catt_team_result or "",
            "vent": None,
        })

    return results


def parse_with_section_aware(text, competicio, data_comp):
    results = []
    lines = text.split('\n')

    sections = find_section_boundaries(lines)

    for sec_idx in range(len(sections) - 1):
        sec_start, sec_name = sections[sec_idx]
        sec_end = sections[sec_idx + 1][0]

        if not sec_name.strip():
            continue

        event_type = classify_event(sec_name)

        # Get wind from section header
        wind = None
        for j in range(sec_start, min(sec_start + 15, len(lines))):
            wind_match = re.search(r'Viento:\s*([+-]?\d+\.\d)', lines[j])
            if wind_match:
                wind = wind_match.group(1)
                break

        # Handle relay events differently
        if event_type == "relay":
            relay_results = parse_relay_section(lines, sec_start, sec_end, sec_name.strip(), competicio, data_comp)
            results.extend(relay_results)
            continue

        # Find CATT athletes in this section
        catt_athletes = find_catt_athletes_in_section(lines, sec_start, sec_end)
        if not catt_athletes:
            continue

        for athlete_block in catt_athletes:
            athlete = parse_catt_athlete(
                lines, athlete_block, sec_start, sec_end, sec_name.strip(), wind,
                event_type, competicio, data_comp
            )
            if athlete:
                results.append(athlete)

    # Also process SUMARIO sections (track events with series)
    sumarios = find_sumario_sections(lines)
    for sumario_idx, event_name in sumarios:
        # Find the end of this sumario section - stop at next event section header
        # or next SUMARIO, whichever comes first
        sec_end = len(lines)
        for j in range(sumario_idx + 1, min(sumario_idx + 500, len(lines))):
            stripped = lines[j].strip()
            # Stop at next SUMARIO
            if 'SUMARIO' in stripped:
                sec_end = j
                break
            # Stop at page boundary
            if 'Página' in stripped:
                # Look ahead for next event
                for k in range(j + 1, min(j + 10, len(lines))):
                    if lines[k].strip() and 'Página' not in lines[k] and 'Gestión' not in lines[k] and 'Leyenda' not in lines[k]:
                        next_line = lines[k].strip()
                        if re.search(r'\d+m\s*(\.\d+)?\s*(vallas)?\s*(Marcha)?\s*(Hombres|Mujeres|Mixto)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'4x\d+m\s+(Hombres|Mujeres|Mixto)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'(Altura|Pértiga)\s+(Hombres|Mujeres)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'(Triple\s+Salto|Disco|Martillo|Peso|Jabalina|Longitud)\s+(Hombres|Mujeres)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'5\.?000m\s+Marcha', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        break
                continue
            # Stop at next event section header
            # Pattern 1: "HH:MM   EventName" format (schedule lines)
            if re.search(r'^\d{2}:\d{2}\s+', stripped):
                # Check if this is an event name
                for pattern in EVENT_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        sec_end = j
                        break
                if sec_end != len(lines):
                    break
                continue
            # Pattern 2: Event name after page header (date line)
            # Check if this line matches an event pattern AND is preceded by a date
            for pattern in EVENT_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    # Check if previous lines contain a date (page header)
                    is_page_header = False
                    for k in range(j - 1, max(j - 6, 0), -1):
                        if re.search(r'\d{2}/\d{2}/\d{4}', lines[k]):
                            is_page_header = True
                            break
                        if lines[k].strip() and 'Página' in lines[k]:
                            break
                    if is_page_header:
                        sec_end = j
                        break
            if sec_end != len(lines):
                break
        
        sumario_results = parse_sumario_section(lines, sumario_idx + 1, event_name, sec_end, competicio, data_comp)
        results.extend(sumario_results)

    return results


def deduplicate_results(results):
    """Remove duplicates, keeping the best entry (final over series, result over DQ/DNS)."""
    groups = {}
    for r in results:
        key = (r["atleta_nom"].lower(), r["prova"].lower())
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    unique = []
    for key, entries in groups.items():
        if len(entries) == 1:
            entry = entries[0]
            entry["atleta_nom"] = re.sub(r'\s+RT\s*$', '', entry["atleta_nom"]).strip()
            unique.append(entry)
            continue

        with_result = [e for e in entries if e["marca"] and e["marca"] not in ("DQ", "DNS", "")]
        without_result = [e for e in entries if not e["marca"] or e["marca"] in ("DQ", "DNS")]

        if with_result:
            with_wind = [e for e in with_result if e["vent"] is not None]
            if with_wind:
                best = min(with_wind, key=lambda e: e["lloc"] if e["lloc"] is not None else 999)
            else:
                with_pos = [e for e in with_result if e["lloc"] is not None]
                if with_pos:
                    best = min(with_pos, key=lambda e: e["lloc"])
                else:
                    best = with_result[0]
            best["atleta_nom"] = re.sub(r'\s+RT\s*$', '', best["atleta_nom"]).strip()
            unique.append(best)

        if without_result:
            with_wind = [e for e in without_result if e["vent"] is not None]
            if with_wind:
                best = with_wind[0]
                best["atleta_nom"] = re.sub(r'\s+RT\s*$', '', best["atleta_nom"]).strip()
                unique.append(best)
            else:
                without_result[0]["atleta_nom"] = re.sub(r'\s+RT\s*$', '', without_result[0]["atleta_nom"]).strip()
                unique.append(without_result[0])

    return unique


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_catt.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    base = os.path.splitext(pdf_path)[0]
    output_path = base + ".json"

    print(f"Extracting text from: {pdf_path}")
    text = extract_text(pdf_path)

    print("Parsing competition header...")
    competicio, ubicacio, localitat, data = parse_header(text)
    full_competicio = f"{competicio} - {ubicacio}" if ubicacio else competicio
    print(f"  Competicio: {competicio or '(no trobat)'}")
    print(f"  Ubicacio: {ubicacio or '(no trobat)'}")
    print(f"  Localitat: {localitat or '(no trobat)'}")
    print(f"  Data: {data or '(no trobat)'}")

    print("\nExtracting CATT athlete results...")
    results = parse_with_section_aware(text, full_competicio, data)

    print(f"Found {len(results)} result entries for CATT athletes")

    for r in results:
        status = "OK" if r["atleta_nom"] and r["marca"] else ("DQ/DNS" if r["atleta_nom"] and not r["marca"] else "INCOMPLETE")
        print(f"  [{status}] {r['atleta_nom'] or '???':35s} | {r['prova'] or '???':25s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']} | Vent: {r['vent']} | Lic: {r['atleta_licencia']}")

    results = deduplicate_results(results)
    print(f"\nAfter deduplication: {len(results)} unique results")

    output = {
        "event_name": full_competicio,
        "event_date": data,
        "event_location": localitat,
        "total_results": len(results),
        "results": []
    }

    for r in results:
        entry = {
            "athlete_name": r["atleta_nom"],
            "athlete_dob": r["atleta_naixement"],
            "athlete_id": r["atleta_licencia"],
            "performance": r["marca"],
            "discipline": r["prova"],
            "wind": r["vent"],
        }
        output["results"].append(entry)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {output_path}")

    events = {}
    for r in results:
        if r["prova"] not in events:
            events[r["prova"]] = []
        events[r["prova"]].append(r["atleta_nom"])

    print("\nResum per prova:")
    for prova, atletes in sorted(events.items()):
        print(f"  {prova}: {len(atletes)} atletes")


if __name__ == "__main__":
    main()
