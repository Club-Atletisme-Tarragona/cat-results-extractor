#!/usr/bin/env python3
"""
Extractora de resultats antics de promoció (2008-2009).
Extreu els resultats d'atletes de C. A. Tarragona de PDFs de la FC Atletisme.

Fonts: old.fcatletisme.cat/Promocio/promocio2009/

Format dels PDFs antics:
    1     102   PAU ARAGONÈS CAMACHO                98   UDT               9"08
    Lloc Dorsal Nom i Cognoms              Any Club                   Marca

    1.   Guillem Armengol Selvas  95            C.A.Manresa     12'10"7
    Posició Nom          Any            Club              Marca
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

    # Competition name: first line with "Jornada", "Trobada", "Control", "Campionat", etc.
    for i, line in enumerate(lines[:15]):
        stripped = line.strip()
        if not stripped:
            continue
        stripped_upper = stripped.upper()
        if any(kw in stripped_upper for kw in ['JORNADA', 'TROBADA', 'TROFEU', 'CONTROL',
                                                'CAMPIONAT', 'CAMPEONATO', 'LIGA', 'LLIGA',
                                                'PROMOCIÓ', 'PROMOCIÓN', 'FINAL']):
            competicio = stripped
            # Clean up year suffixes like "08 - 09"
            competicio = re.sub(r'\s+\d{2}\s*[-–]\s*\d{2}\s*$', '', competicio).strip()
            break

    # Venue: line with "Estadi", "Pista", "Pabellon", "Pabellón", "Camp"
    for i, line in enumerate(lines[:15]):
        stripped = line.strip()
        if any(kw in stripped for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón',
                                          'Camp', 'pabellon', 'pabellón']):
            ubicacio = stripped
            break

    # Date: DD/MM/YYYY or DD / MM / YY
    for i, line in enumerate(lines[:15]):
        # Try 4-digit year first
        date_match = re.search(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})', line)
        if date_match:
            raw = date_match.group(1)
            data = re.sub(r'\s+', '', raw)
            break

        # Try 2-digit year
        date_match = re.search(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{2})', line)
        if date_match:
            raw = date_match.group(1)
            data = re.sub(r'\s+', '', raw)
            break

    # Localitat: non-empty line between competition name and date
    # Try to find city names in header block
    for i, line in enumerate(lines[:15]):
        stripped = line.strip()
        if not stripped:
            continue
        # Look for common city/location names
        cities = ['Tarragona', 'Manresa', 'Vilafranca', 'Terrassa', 'Badalona',
                  'Mataró', 'Mollet', 'Sant Celoni', 'Girona', 'Lleida', 'Cambrils',
                  'Valls', 'Amposta', 'Reus', 'Olot', 'Figueres', 'Lloret',
                  'Palafrugell', 'Castellar', 'Granollers', 'Calella', 'El Prat',
                  'Barcelona', 'Serrahima', 'Amposta', 'L\'Hospitalet',
                  'Hospitalet', 'Can Dragó', 'Camp Clar']
        for city in cities:
            if city.lower() in stripped.lower() and city not in competicio.lower():
                localitat = city
                break
        if localitat:
            break

    return competicio, ubicacio, localitat, data


# Club detection for C. A. Tarragona
TARRAGONA_PATTERNS = [
    r'C\.\s*A\.\s*TARRAGONA',
    r'CATT',
    r'C\.\s*A\.\s*T\.\s+TARRAGONA',
    r'CA\s+TARRAGONA',
    r'Club\s+Atletisme\s+Tarragona',
]


def is_tarragona_club(club_name):
    club_normalized = club_name.strip()
    club_upper = club_normalized.upper()
    club_upper = re.sub(r'\s+', ' ', club_upper)
    # Check exact matches first
    if club_upper in ('CA TARRAGONA', 'C. A. TARRAGONA', 'CATT', 'CLUB ATLETISME TARRAGONA'):
        return True
    # Check patterns
    for pattern in TARRAGONA_PATTERNS:
        if re.search(pattern, club_upper):
            return True
    return False


def convert_mark_to_decimal(marca):
    """Convert old format marks to decimal.

    Formats:
        9"08 -> 9.08
        3'25"9 -> 205.9 (minutes:seconds.deci -> total seconds)
        12'10"7 -> 730.7
        1:23.45 -> 1:23.45 (already decimal time)
        7,69 -> 7.69
        Ret. -> Ret.
        AB -> AB
    """
    marca = marca.strip()

    if not marca or marca in ('-', 'X', 'x', 'DNF', 'DNS', 'DQ'):
        return marca

    # Already decimal with colon: 1:23.45
    if re.match(r'^\d+:\d+\.\d+$', marca):
        return marca

    # Ret. (retired)
    if marca == 'Ret.':
        return marca

    # AB (abandoned)
    if marca == 'AB':
        return marca

    # Minutes:seconds.deci format: 12'10"7, 3'25"9
    m = re.match(r"(\d+)[''](\d+)['\"](\d+)", marca)
    if m:
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        deci = int(m.group(3))
        total = minutes * 60 + seconds + deci / 10.0
        return str(total)

    # Seconds only with quote: 9"08, 8"60, 9"42
    m = re.match(r"(\d+)['\"](\d+)", marca)
    if m:
        return f"{m.group(1)}.{m.group(2)}"

    # Comma decimal: 7,69 -> 7.69
    m = re.match(r"(\d+),(\d+)", marca)
    if m:
        return f"{m.group(1)}.{m.group(2)}"

    # Already decimal: 7.69, 9.08
    if re.match(r'^\d+\.\d+$', marca):
        return marca

    return marca


def extract_event_name(line):
    """Extract event name from a line."""
    line = line.strip()
    # Remove series info: "1a. Sèrie", "2a. Sèrie"
    line = re.sub(r'^\d+[a-zèé]?\.\s*Sèrie\s*', '', line)
    line = re.sub(r'^\d+[a-zèé]?\.\s*Serie\s*', '', line)
    line = re.sub(r'^\d+[a-zèé]?\.\s*Final\s*', '', line)
    line = re.sub(r'^\d+[a-zèé]?\.\s*Ronda\s*', '', line)
    return line.strip()


def classify_event(event_name):
    """Classify event type."""
    name = event_name.upper()

    # Combined events
    for p in ['PENTATHLON', 'HEPTATHLON', 'TETRATHLON', 'HEXATHLON']:
        if p in name:
            return "combined"

    # Relays
    if re.search(r'4\s*x\s*\d+', name) or re.search(r'RELLEU', name):
        return "relay"

    # Marcha
    if 'MARXA' in name or 'MARCHA' in name:
        return "marcha"

    # Height
    if re.search(r'(ALTURA|ALTITUD|PÈRTIGA|PERTIGA|PERXA)', name):
        return "height"

    # Field events
    if re.search(r'(DISC|MARTELL|PES|JAVELINA|DARD|LLANÇAMENT|LLANZAMIENTO)', name):
        return "field"

    # Jumps
    if re.search(r'(LLARGADA|LONGITUD|LONG|TRIPLE|SALT|SALTO)', name):
        return "jump"

    # Track
    if re.search(r'\d+m', name):
        return "track"

    return "unknown"


def validate_event_value(event_type, value_str):
    """Validate extracted value is within reasonable range."""
    try:
        if ':' in value_str:
            parts = value_str.split(':')
            if len(parts) == 2:
                seconds = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            else:
                return True
        else:
            seconds = float(value_str)
    except (ValueError, IndexError):
        return True

    ranges = {
        "track": (5.0, 60.0),
        "marcha": (5.0, 60.0),
        "jump": (3.0, 20.0),
        "height": (1.0, 7.0),
        "field": (3.0, 80.0),
    }

    if event_type in ranges:
        min_val, max_val = ranges[event_type]
        if seconds < min_val or seconds > max_val:
            return False

    return True


def extract_wind_from_line(line):
    """Extract wind value from a line like 'Vent 1,7' or 'Vent +1.7'."""
    m = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', line)
    if m:
        wind = m.group(1).replace(',', '.')
        return f"+{wind}" if not wind.startswith('-') else wind
    return None


def clean_event_name(event_name):
    """Clean event name by removing wind info and extra whitespace.
    
    Returns (cleaned_name, wind_value) tuple where wind_value is extracted
    from the event name (e.g., "Vent 1,0" -> "+1.0").
    """
    wind = None
    # Extract wind info from event name
    wind_match = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', event_name)
    if wind_match:
        wind = wind_match.group(1).replace(',', '.')
        wind = f"+{wind}" if not wind.startswith('-') else wind
        event_name = re.sub(r'\s*Vent\s+[+-]?\d+[,\.]\d+\s*', '', event_name)
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', event_name).strip()
    return cleaned, wind


def clean_athlete_name(name):
    """Clean athlete name by removing license prefixes and converting COGNOM, NOM -> NOM COGNOM."""
    # Remove license code prefixes: "CL-12544   NAME", "CT-9121    NAME", "CL549", "FC", etc.
    cleaned = re.sub(r'^(?:CL|CT|CAT|IB|FC|JA|BC|GE)[-\s]*\d+\s+', '', name)
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Convert "COGNOM, NOM" to "NOM COGNOM"
    comma_match = re.match(r'(.+),\s*(.+)', cleaned)
    if comma_match:
        cleaned = f"{comma_match.group(2).strip()} {comma_match.group(1).strip()}"
    return cleaned


def is_event_header(line):
    """Check if a line is an event header."""
    line = line.strip()
    if not line:
        return False

    # Skip header lines that look like column labels
    skip_labels = ['Lloc', 'Dorsal', 'Nom', 'Any', 'Club', 'Marca',
                   'Lugar', 'Puesto', 'Nombre', 'Fecha', 'Licencia',
                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Serie',
                   'Ronda', 'Série', 'Eliminatoria', 'Heats', 'Heat',
                   'Final', 'Gestion', 'Pagina', 'SUMARIO', 'Rank',
                   'Viento', 'Pasos', 'RESULTADO', 'Puntos', 'P.Líder']
    if any(label in line for label in skip_labels):
        return False

    # Event headers are typically at the start of a line and contain event patterns
    # Must start with a number (distance) or event name
    if not re.match(r'^\d', line) and not re.match(r'^[A-ZÀ-Ú]', line):
        return False

    # Check for distance-based events at the START of the line
    # e.g., "60 m.ll.", "3.000 metres", "1.000 metres"
    if re.match(r'^\d+(?:\.\d+)?\s*(?:m|m\.|metres|meters)', line):
        return True

    # Check for event names followed by category
    event_names = ['PES', 'DISC', 'MARTELL', 'JAVELINA', 'DARD', 'ALTURA',
                   'PÈRTIGA', 'PERTIGA', 'LLARGADA', 'TRIPLE', 'SALT',
                   'RELLEU', 'MARXA', 'MARCHA', 'PENTATHLON', 'HEPTATHLON']
    for kw in event_names:
        if kw in line.upper():
            return True

    # Check for short distances (60, 100, 200, 400, 800, 1500, 3000) at start
    if re.match(r'^(?:60|100|200|400|800|1500|3000)\b', line):
        return True

    return False


def parse_with_section_aware(text):
    """Parse all lines and extract CATT results.

    Strategy: Scan line by line. When we find a CATT line, look backwards
    up to 10 lines to find the event header.
    """
    lines = text.split('\n')
    all_results = []
    current_event = None
    current_wind = None

    for line in lines:
        stripped = line.strip()

        # Check for wind in sub-event lines like "1a. Sèrie Vent 1,2"
        if not current_event or re.match(r'^\d+[a-zèé]?\.\s*(Sèrie|Serie|Ronda|Final|Eliminatoria)', current_event):
            wind_match = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', stripped)
            if wind_match:
                current_wind = wind_match.group(1).replace(',', '.')
                current_wind = f"+{current_wind}" if not current_wind.startswith('-') else current_wind

        # Check if this is an event header
        if is_event_header(stripped):
            current_event = extract_event_name(stripped)
            # Append wind to event name if available
            if current_wind:
                current_event = f"{current_event} Vent {current_wind.lstrip('+')}"
            # Skip sub-event labels
            if re.match(r'^\d+[a-zèé]?\.\s*(Sèrie|Serie|Ronda|Final|Eliminatoria)', current_event):
                current_event = None
            continue

        # Check if this is a CATT line
        if current_event and is_tarragona_line(stripped):
            result = parse_result_line(stripped, current_event)
            if result:
                all_results.append(result)

    return all_results


def is_tarragona_line(line):
    """Check if a line contains a CATT athlete result."""
    stripped = line.strip()
    if not stripped:
        return False

    # Skip header lines
    skip_labels = ['Lloc', 'Dorsal', 'Nom', 'Any', 'Club', 'Marca',
                   'Lugar', 'Puesto', 'Nombre', 'Fecha', 'Licencia',
                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Serie',
                   'Ronda', 'Série', 'Eliminatoria', 'Heats', 'Heat',
                   'Final', 'Gestion', 'Pagina', 'SUMARIO', 'Rank',
                   'Viento', 'Pasos', 'RESULTADO']
    if any(label in stripped for label in skip_labels):
        return False

    return is_tarragona_club(stripped)


def parse_result_line(line, event_name):
    """Parse a single result line for a CATT athlete.

    Handles two formats:

    Old format (2-digit year):
        8        275   MONTSE GUINOVART PEDESCOLL           94   C. A. TARRAGONA            9"08

    New format (full DOB + license prefix):
        7            2        225      CL55942 TORREDEME PASCUAL, NURIA             22/10/1994 CA TARRAGONA                     8,73
    """
    stripped = line.strip()

    # Find CATT club position in line
    club_match = re.search(r'(C\.\s*A\.\s*TARRAGONA|CATT|C\.\s*A\.\s*T\.\s+TARRAGONA|CA\s+TARRAGONA|Club\s+Atletisme\s+Tarragona)', stripped, re.IGNORECASE)
    if not club_match:
        return None

    club_pos = club_match.start()
    before_club = stripped[:club_pos].rstrip()
    after_club = stripped[club_match.end():].strip()

    # Try new format first: has full DOB (DD/MM/YYYY) before club
    dob_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*$', before_club)
    if dob_match:
        dob = dob_match.group(1)
        before_dob = before_club[:dob_match.start()].rstrip()

        # Extract name and license from before_dob
        # Format: "pos  carrer  dorsal  CL55942 NAME, SURNAME" or "pos  dorsal  CL55942 NAME, SURNAME"
        # License prefix pattern: CL55942, CT17159, CL55941, etc.
        lic_match = re.search(r'(CL|CT|CAT|IB|FC|JA|BC|GE)[\s-]*(\d+)\s+(.+)', before_dob)
        if lic_match:
            name = lic_match.group(3).strip()
            # Handle "COGNOM, NOM" format - convert to "NOM COGNOM"
            name = clean_athlete_name(name)
        else:
            return None

        # Parse position from before_dob
        pos_match = re.match(r'(\d+\.?)', before_dob)
        pos = int(pos_match.group(1).rstrip('.')) if pos_match else None

    else:
        # Old format: 2-digit year before club
        year_match = re.search(r'(\d{2})\s*$', before_club)
        if not year_match:
            return None

        year = year_match.group(1)
        name_and_pos = before_club[:year_match.start()].rstrip()

        # Parse position and name from "pos  dorsal  name"
        pos_match = re.match(r'(\d+\.?)\s+(\d+)\s+(.+)', name_and_pos)
        if not pos_match:
            return None

        pos = int(pos_match.group(1).rstrip('.'))
        name = pos_match.group(3).strip()

        # Extract DOB from year (2-digit format)
        year_int = int(year)
        if year_int <= 9:
            dob_year = 2000 + year_int
        else:
            dob_year = 1900 + year_int
        dob = f"1/1/{dob_year}"

        # Clean athlete name (remove license prefix)
        name = clean_athlete_name(name)

    # Extract mark from after_club
    converted_mark = extract_mark_from_after_club(after_club)

    # Extract wind if present (from the full line, not just after_club)
    wind = extract_wind_from_line(line)

    # Clean event name (remove wind info)
    clean_event, event_wind = clean_event_name(event_name)
    
    # Use wind from event name if not found in result line
    if not wind and event_wind:
        wind = event_wind

    return {
        "prova": clean_event,
        "atleta_nom": name.strip(),
        "atleta_naixement": dob,
        "marca": converted_mark,
        "vent": wind,
        "lloc": pos,
    }


def extract_mark_from_after_club(after_club):
    """Extract mark from text after the club name.

    Handles both simple marks and multiple attempts.
    """
    after_club = after_club.strip()
    if not after_club:
        return ""

    # Check for special markers first
    if after_club in ('Ret.', 'Ret', 'AB', 'DNF', 'DNS', 'DQ'):
        return after_club

    # Check for time format: 1:23.45 or 9"08 or 12'10"7
    # Time formats
    time_match = re.match(r'(\d+:\d+\.\d+)', after_club)
    if time_match:
        return time_match.group(1)

    minutes_seconds = re.match(r"(\d+)['\"](\d+)['\"](\d+)", after_club)
    if minutes_seconds:
        minutes = int(minutes_seconds.group(1))
        seconds = int(minutes_seconds.group(2))
        deci = int(minutes_seconds.group(3))
        total = minutes * 60 + seconds + deci / 10.0
        return str(total)

    seconds_quote = re.match(r"(\d+)['\"](\d+)", after_club)
    if seconds_quote:
        return f"{seconds_quote.group(1)}.{seconds_quote.group(2)}"

    # Multiple attempts (long jump, triple jump, height): "4,40 4,52 4,35 4,28  X  X  4,52"
    # Find all valid numeric values and X markers
    tokens = re.findall(r'(\d+[,\.]\d+|X|x|-|XO|xxo)', after_club)
    if len(tokens) >= 3:
        # Filter out X markers and find best valid mark
        valid_marks = []
        for token in tokens:
            if token in ('X', 'x', '-', 'XO', 'xxo'):
                continue
            try:
                val = float(token.replace(',', '.'))
                if 1.0 <= val <= 20.0:  # Reasonable range for jumps/heights
                    valid_marks.append(val)
            except ValueError:
                continue

        if valid_marks:
            # Return the best mark
            best = max(valid_marks)
            return f"{best:.2f}"

        # If no valid marks but we have tokens, return first numeric
        for token in tokens:
            try:
                float(token.replace(',', '.'))
                return token.replace(',', '.')
            except ValueError:
                continue

    # Single decimal/comma mark: 7,69 or 7.69
    single_match = re.match(r'(\d+[,\.]\d+)', after_club)
    if single_match:
        return single_match.group(1).replace(',', '.')

    return ""


def deduplicate_results(results):
    """Remove duplicate results for same athlete+event.

    If there's a valid result, keep only the best one.
    If no valid result, keep the best DNS/DQ entry.
    """
    key_results = {}

    for r in results:
        key = (r["atleta_nom"].upper(), r["prova"].upper())
        marca = r["marca"].strip()

        if key not in key_results:
            key_results[key] = r
        else:
            existing = key_results[key]
            existing_marca = existing["marca"].strip()

            # If current has a valid result and existing doesn't, replace
            if marca and marca not in ("DQ", "DNS", "DNF", "Ret.", "AB"):
                key_results[key] = r
            elif not marca and existing_marca and existing_marca in ("DQ", "DNS", "DNF", "Ret.", "AB"):
                # Keep the one with valid result
                pass

    return list(key_results.values())


def extract_year_from_pdf_path(pdf_path):
    """Extract year from PDF filename pattern like resulXXX221108.pdf or resulXXX17109.pdf."""
    basename = os.path.basename(pdf_path)
    # Match 6-digit date at end of filename: DDMMYY
    m = re.search(r'(\d{2})(\d{2})(\d{2})\.pdf$', basename, re.IGNORECASE)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"20{year}"
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_promocio.py <pdf_file> [output_dir] [source_url]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "json/promocio/2008"
    source_url = sys.argv[3] if len(sys.argv) > 3 else ""

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"Extracting text from: {pdf_path}")
    text = extract_text(pdf_path)

    print("Parsing competition header...")
    competicio, ubicacio, localitat, data = parse_header(text)
    full_competicio = f"{competicio} - {ubicacio}" if ubicacio else competicio
    print(f"  Competicio: {competicio or '(no trobat)'}")
    print(f"  Ubicacio: {ubicacio or '(no trobat)'}")
    print(f"  Localitat: {localitat or '(no trobat)'}")
    print(f"  Data: {data or '(no trobat)'}")

    print("\nExtracting C. A. Tarragona athlete results...")
    results = parse_with_section_aware(text)

    print(f"Found {len(results)} result entries for CATT athletes")

    for r in results:
        status = "OK" if r["marca"] else ("Ret./AB" if r["marca"] in ("Ret.", "AB") else "DQ/DNS")
        print(f"  [{status}] {r['atleta_nom'] or '???':40s} | {r['prova'] or '???':30s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']} | Vent: {r['vent']}")

    results = deduplicate_results(results)
    print(f"\nAfter deduplication: {len(results)} unique results")

    # Validate: must have athlete_name, performance, and discipline
    valid_results = []
    for r in results:
        name = r.get("atleta_nom", "").strip()
        performance = r.get("marca", "").strip()
        discipline = r.get("prova", "").strip()

        if not name or not performance or not discipline:
            missing = []
            if not name:
                missing.append("athlete_name")
            if not performance:
                missing.append("performance")
            if not discipline:
                missing.append("discipline")
            warning = f"WARNING: Skipping entry missing {', '.join(missing)}: prova='{r.get('prova', '???')}', atleta_nom='{r.get('atleta_nom', '???')}', marca='{r.get('marca', '???')}'"
            print(warning, file=sys.stderr)
            continue

        valid_results.append(r)

    results = valid_results
    print(f"\nAfter validation: {len(results)} valid results")

    # Build output JSON
    output = {
        "event_name": full_competicio,
        "event_date": data,
        "event_location": localitat,
        "total_results": len(results),
        "event_src": source_url if source_url else os.path.abspath(pdf_path),
        "results": []
    }

    for r in results:
        entry = {
            "athlete_name": r["atleta_nom"],
            "athlete_dob": r["atleta_naixement"],
            "athlete_id": "",
            "performance": r["marca"],
            "discipline": r["prova"],
            "wind": r["vent"],
        }
        output["results"].append(entry)

    # Determine output filename
    base = os.path.basename(pdf_path).replace('.pdf', '')
    # Extract year from data or filename
    year = "2008"
    if data:
        year_match = re.search(r'(\d{4})', data)
        if year_match:
            year = year_match.group(1)
        else:
            # Extract 2-digit year
            year_match = re.search(r'(\d{2})$', data)
            if year_match:
                y2 = int(year_match.group(1))
                year = f"20{y2:02d}"

    # Also try from filename
    filename_year = extract_year_from_pdf_path(pdf_path)
    if filename_year:
        year = filename_year

    output_path = os.path.join(output_dir, f"{base}.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
