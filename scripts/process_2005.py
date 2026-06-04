#!/usr/bin/env python3
"""
Extractor per a PDFs de 2005 (format tabular amb COGNOMS, NOM i comes decimals).

Els PDFs de 2005 fan servir diversos formats tabulars:

Format 1 (Pista Coberta / Aire Lliure - campionats):
  LLOC CARRER DORSAL LLIC. NOM ANY CLUB MARCA
  7   7   152  CT-13834 TORTOSA PRADILLO, FERRAN  86  CA TARRAGONA  7,50

Format 2 (Controls):
  LLOC DORSAL CARRER LLIC. NOM ANY CLUB MARCA
  1   6   8   1694  CL-13435 FERRER BARBERAN, CARLOS  70  CA TARRAGONA  4,14,04

Format 3 (Campmany / JJP):
  LLOC CARRER LLIC. NOM ANY CLUB MARCA
  4   2   CL-11148  ERNESTO NUÑEZ LOPEZ  83  CA TARRAGONA  2,02,22

Format 4 (Llançaments):
  LLOC DORSAL LLIC. NOM ANY CLUB 1 2 3 4 5 6 MARCA
  3a. 420 CT-13219 PINTADO DUCH, BARBARA 85 CA TARRAGONA X X X 9,43 9,15 8,68 9,43

Format 5 (Veterans):
  LLOC DORSAL CARRER LLIC. CATEGORIA NOM ANY CLUB MARCA
  1   2   3   392  CL-13212 M-PRE IBORRA MARTINEZ, FCO.JOSE  67  CA TARRAGONA  7,97

Format 6 (10000m/quotes):
  LLOC DORSAL NOM ANY CLUB MARCA (amb cometes)
  1   5   101  Carlos Ferrer Barberán  70  C.A. Tarragona  32'23\"45
"""

import subprocess
import sys
import os
import json
import re


def extract_text(pdf_path):
    result = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Error extracting text: {result.stderr}", file=sys.stderr)
        return ""
    return result.stdout


def parse_header(text):
    lines = text.split('\n')
    competicio = ""
    ubicacio = ""
    localitat = ""
    data = ""

    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue

        if not competicio:
            if 'Campionat' in stripped or 'CAMPIONAT' in stripped:
                competicio = stripped
            elif 'Control' in stripped:
                competicio = stripped
            elif 'Trofeu' in stripped or 'TROFEU' in stripped:
                competicio = stripped
            elif 'Meeting' in stripped or 'MEETING' in stripped:
                competicio = stripped

    for line in lines[:30]:
        stripped = line.strip()
        if any(kw in stripped for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón']):
            ubicacio = stripped
            break

    for line in lines[:30]:
        stripped = line.strip()
        date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', stripped, re.IGNORECASE)
        if date_match:
            if not localitat:
                loc_match = re.search(r'(?:a|de|al|dels?)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[a-zà-ú]+)*)', stripped)
                if loc_match:
                    localitat = loc_match.group(1).strip()
            months = {
                'gener': '01', 'febrer': '02', 'març': '03', 'abril': '04',
                'maig': '05', 'juny': '06', 'juliol': '07', 'agost': '08',
                'setembre': '09', 'octubre': '10', 'novembre': '11', 'desembre': '12',
                'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12',
            }
            day = date_match.group(1).zfill(2)
            month_name = date_match.group(2).lower()
            month = months.get(month_name, '01')
            data = f"{day}/{month}/{date_match.group(3)}"
            break

    if not data:
        for line in lines[:30]:
            dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if dm:
                data = dm.group(1)
                break

    for line in lines[:30]:
        stripped = line.strip()
        dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', stripped)
        if dm:
            data = dm.group(1)
            break

    return {
        'event_name': competicio or '',
        'event_date': data,
        'event_location': localitat,
    }


def parse_performance(after_ca):
    after_ca = after_ca.strip()

    if not after_ca:
        return None, None

    # Special values
    special = {'N.P.', 'NP', 'RET.', 'RET', 'DNS', 'DQ', 'DNF', 'NULS'}
    if after_ca.upper() in special:
        return after_ca.upper(), None

    # Pure integers (positions, not marks)
    if re.match(r'^\d{1,3}$', after_ca):
        return None, None

    # Normalize Unicode quotes
    after_ca = after_ca.replace('\u2019', "'").replace('\u201d', '"')
    after_ca = after_ca.replace('\u2018', "'").replace('\u201c', '"')

    # Quote format: X'YY"ZZ (minutes'seconds.centiseconds)
    m = re.match(r"^(\d+)'(\d{2})\"(\d{2})", after_ca)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}", None

    # Quote format: X'YY"Z
    m = re.match(r"^(\d+)'(\d{2})\"(\d)", after_ca)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}", None

    # Quote format: X"YY (seconds.centiseconds)
    m = re.match(r'^(\d+)"(\d{2})', after_ca)
    if m:
        return f"{m.group(1)}.{m.group(2)}", None

    # For field/jump events with attempts: extract all attempt values
    # Format: "42,46      X      43,40    X      45,20   43,07   45,20"
    # or "6,01    6,10   5,89   5,98   5,96   5,94    6,10"
    tokens = after_ca.split()
    attempt_values = []
    for token in tokens:
        token_clean = token.strip().rstrip(',').rstrip('.')
        if token_clean in ('X', 'x', '-', '_'):
            attempt_values.append(token_clean)
        elif re.match(r'^(\d+[.,]\d{1,2})$', token_clean):
            val = float(token_clean.replace(',', '.'))
            if 1.0 <= val <= 80.0:
                attempt_values.append(token_clean.replace(',', '.'))
        elif re.match(r'^(\d+)$', token_clean):
            val = int(token_clean)
            if 20 <= val <= 9999:
                attempt_values.append(token_clean)

    if len(attempt_values) >= 3:
        valid = [(idx, a) for idx, a in enumerate(attempt_values)
                 if re.match(r'^\d+\.?\d*$', a) and a not in ('X', 'x', '-', '_')]
        if valid:
            best_idx, best_str = max(valid, key=lambda x: float(x[1]))
            return best_str, attempt_values

    # Double-comma format: MM,SS,CC → MM:SS.CC
    m = re.match(r'^(\d{1,2}),(\d{2}),(\d{2})\b', after_ca)
    if m:
        sec = int(m.group(2))
        if sec < 60:
            return f"{m.group(1)}:{m.group(2)}.{m.group(3)}", None

    # Single comma/last value
    nums = re.findall(r'(\d+[.,]\d{2})', after_ca)
    if nums:
        last = nums[-1]
        if after_ca.count(',') == 2:
            return None, None
        return last.replace(',', '.'), None

    return None, None


def extract_name_from_before(before_ca):
    before_ca = before_ca.strip()

    # Strip trailing year code (2 digits) at end
    before_ca = re.sub(r'\s+\d{1,2}\s*$', '', before_ca)

    # Strip leading position/carrer/dorsal numbers
    before_ca = re.sub(r'^\s*(?:\d+\s+)+', '', before_ca)

    # Strip license codes (CT-13834, CL-11148, CT 18015, ESC., LZ-130)
    before_ca = re.sub(r'\b(?:CT|CL|LZ|IB|FC)\s*-?\s*\d+\s*', '', before_ca)
    before_ca = re.sub(r'\bESC\.?\s*', '', before_ca)
    before_ca = re.sub(r'\bM-PRE\b', '', before_ca)

    before_ca = before_ca.strip()
    if not before_ca:
        return None

    # Now find "COGNOM, NOM" pattern
    comma_name = re.search(r'([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s\.]+),\s*([A-ZÀ-Úa-zà-ú][A-ZÀ-Úa-zà-ú\s\.]+?)\s*$', before_ca)
    if comma_name:
        surname = comma_name.group(1).strip()
        given = comma_name.group(2).strip()
        full = f"{given} {surname}"
        return re.sub(r'\s+', ' ', full).strip()

    # Try with lowercase characters
    comma_name = re.search(r'([A-Za-zÀ-Úà-ú\s\.]+),\s*([A-Za-zÀ-Úà-ú\s\.]+?)\s*$', before_ca)
    if comma_name:
        surname = comma_name.group(1).strip()
        given = comma_name.group(2).strip()
        if not re.search(r'\d', surname) and not re.search(r'\d', given):
            full = f"{given} {surname}"
            return re.sub(r'\s+', ' ', full).strip()

    # No comma: extract uppercase words (NOM COGNOM format)
    before_ca = re.sub(r'\s+/?\s*a$', '', before_ca)  # trailing "/a" markers
    words = re.findall(r"[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú]+(?:['\u2019][A-ZÀ-Úa-zà-ú]+)?", before_ca)
    stop_words = {'CT', 'CL', 'CS', 'CA', 'CG', 'ESC', 'LZ', 'M', 'F'}
    name_words = [w for w in words if w.upper() not in stop_words and len(w) >= 2]

    if len(name_words) >= 2:
        name = ' '.join(name_words[-4:])
        if len(name) >= 4:
            return name.upper()

    return None


def detect_event(lines, line_idx):
    line = lines[line_idx].strip()
    if not line:
        return None

    if re.match(r'^\d+[a-zèé]?\.\s+(?:Semifinal|Final|Sèrie|Serie|Ronda)', line, re.IGNORECASE):
        return None
    if re.match(r'^\d+\.\s+(?:Semifinal|Final|Sèrie|Serie|Ronda)', line, re.IGNORECASE):
        return None
    if 'LLOC' in line and 'DORSAL' in line and ('LLIC' in line or 'LLICÈNCIA' in line):
        return None
    if 'Sèrie' in line and 'Lloc' in line and 'Dorsal' in line:
        return None
    if 'LLOC' in line and 'CARRER' in line and 'DORSAL' in line:
        return None

    event_patterns = [
        r'\d+(?:\.\d+)?\s*m(?:etres)?\.?\s+llisos?\s+\w+',
        r'\d+(?:\.\d+)?\s*m(?:etres)?\.?\s+tanques?\s+\w+',
        r'\d+(?:\.\d+)?\s*m(?:etres)?\.?\s+marxa\s+\w+',
        r'Perxa\s+\w+',
        r'Triple\s+Salt\s+\w+',
        r'Llan[cç]ament\s+\w+',
        r'Salt\s+(?:Al[cç]ada|Llargada)\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+absolut\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+juvenil\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+cadet\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+infantil\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+alev[íi]\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+benjam[íi]\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+promesa\s+\w+',
        r'\d+(?:\.\d+)?\s+m\s+junior\s+\w+',
        r'60 METRES\s+\w+',
        r'100 METRES\s+\w+',
        r'200 METRES\s+\w+',
        r'400 METRES\s+\w+',
        r'800 METRES\s+\w+',
        r'1500 METRES\s+\w+',
        r'3000 METRES\s+\w+',
        r'5000 METRES\s+\w+',
        r'110 TANQUES\s+\w+',
        r'400 TANQUES\s+\w+',
        r'\d+(?:\.\d+)?\s*m(?:etres)?\.?\s+obstacles?\s*(?:\w+)?',
        r'\d+(?:\.\d+)?\s*METRES\s+(?:LLISOS|TANQUES|MARXA|OBSTACLES)\s*(?:\w+)?',
        r'LLARGADA\s+\w+',
        r'ALÇADA\s+\w+',
        r'PES\s+\w+',
        r'DISC\s+\w+',
        r'JAVELINA\s+\w+',
        r'MARTELL\s+\w+',
    ]

    for pattern in event_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return line.strip()

    return None


def is_cg_tarragona(before_ca):
    """Check if this is CG TARRAGONA (NOT CA Tarragona - different club)."""
    before_upper = before_ca.upper()
    # If "CG TARRAGONA" appears before "CA TARRAGONA", it's a different club
    # The line contains "CA TARRAGONA" (we matched it), but if "CG" appears before,
    # the athlete might be from CG Tarragona-FAAC
    # Actually, the ca_match finds "CA TARRAGONA" but the club might be "CG TARRAGONA-FAAC"
    return False  # Handled by not matching "CG TARRAGONA" in the regex


def extract_wind_from_next_line(lines, i):
    if i + 1 >= len(lines):
        return None
    next_line = lines[i + 1].strip()
    # Wind lines look like: "  -0,2   -1,2   2,7    0,4    0,5    -0,1"
    # Match lines that are only decimals/X/-
    tokens = next_line.split()
    if len(tokens) < 2:
        return None
    wind_values = []
    for t in tokens:
        m = re.match(r'^([+-]?\d+[.,]\d+)$', t)
        if m:
            wind_values.append(m.group(1).replace(',', '.'))
    return wind_values


def extract_wind(stripped_line):
    m = re.search(r'VENT:\s*([+-]?)\s*(\d+[.,]\d+|Nul)', stripped_line, re.IGNORECASE)
    if m:
        sign = m.group(1)
        val = m.group(2)
        if val.upper() == 'NUL':
            return "0"
        val = val.replace(',', '.')
        return f"{sign}{val}" if sign else f"+{val}"
    return None


def clean_mark_suffixes(mark_str):
    return re.sub(r'\s+(?:F|f|MMP|RCAT|F/C|f/c|f MMP)$', '', mark_str).strip()


def extract_athletes(text):
    lines = text.split('\n')
    results = []
    current_event = None
    current_wind = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Detect event headers - reset wind on new event
        event = detect_event(lines, i)
        if event:
            current_event = event
            current_wind = None
            continue

        if re.match(r'^\d+[a-zèé]?\.\s+(?:Semifinal|Final|Sèrie|Serie|Ronda)', stripped, re.IGNORECASE):
            continue
        if re.match(r'^\d+\.\s+(?:Semifinal|Final|Sèrie|Serie|Ronda)', stripped, re.IGNORECASE):
            continue
        if 'LLOC' in stripped and 'DORSAL' in stripped and ('LLIC' in stripped or 'CARRER' in stripped):
            continue
        if 'Sèrie' in stripped and 'Lloc' in stripped and 'Dorsal' in stripped:
            continue
        if 'Organitza' in stripped or 'Página' in stripped or 'Pagina' in stripped:
            continue

        # Track wind from any data line with "VENT:" — it applies to subsequent athletes
        wind_on_line = extract_wind(stripped)
        if wind_on_line is not None:
            current_wind = wind_on_line

        # Check for CA TARRAGONA (various formats)
        ca_match = re.search(r'(?:CA\s*\.?\s*TARRAGONA|C\.\s*A\.\s*Tarragona)', stripped, re.IGNORECASE)
        if not ca_match:
            continue

        # Exclude CG TARRAGONA (different club)
        before_ca = stripped[:ca_match.start()].strip()
        after_ca = stripped[ca_match.end():].strip()

        # Check if this is CG TARRAGONA-FAAC (different club, not CA Tarragona)
        before_upper = before_ca.upper()
        cg_check = re.findall(r'\bCG\b', before_upper)
        if cg_check:
            continue

        # Extract name
        athlete_name = extract_name_from_before(before_ca)
        if not athlete_name or len(athlete_name) < 4:
            continue

        # Use wind: from athlete's own line if present, else from current series wind
        wind = wind_on_line if wind_on_line is not None else current_wind

        # Remove VENT suffix from after_ca so it doesn't interfere with performance parsing
        after_clean = re.sub(r'\s*VENT:\s*[+-]?\s*\d+[.,]\d+|\s*VENT:\s*[+-]?\s*Nul', '', after_ca, flags=re.IGNORECASE).strip()

        # Clean suffixes like F, MMP, RCAT
        after_clean = clean_mark_suffixes(after_clean)

        # For field/jump events with attempts, parse performance and get attempt values
        performance, attempt_values = parse_performance(after_clean)

        # For jumps/throws: extract wind from next line (wind values per attempt)
        if attempt_values and performance:
            wind_line_values = extract_wind_from_next_line(lines, i)
            if wind_line_values:
                # Find the best valid attempt and get its wind
                valid_attempts = [(idx, a) for idx, a in enumerate(attempt_values) 
                                  if re.match(r'^\d+\.?\d*$', a) and a not in ('X', 'x', '-', '_')]
                if valid_attempts and wind_line_values:
                    best_idx, best_val = max(valid_attempts, key=lambda x: float(x[1]))
                    if best_idx < len(wind_line_values):
                        wind = wind_line_values[best_idx]

        # If no performance found from after_ca, try the before_ca for combined events
        # (some formats have points/marks before the club)
        if not performance:
            # Check if there's a valid mark before the club (for combined events)
            # Format: "5 5 204 CT-11395 SERRES PARDINES, ADRIA 83 CA TARRAGONA 7,61 678"
            # The 7,61 is the mark, 678 is points - both valid as performance
            perf_from_before = None
            # Find the last numeric value in before_ca that looks like a performance
            nums = re.findall(r'(\d+[.,]\d{2})', before_ca)
            if nums:
                # These could be distances/times but more likely they're performance values
                # Only use this if after_ca is a points-only value
                perf_check = parse_performance(after_clean)
                if not perf_check[0]:
                    # after_ca might be points only (e.g., "678")
                    # Try the last value from before_ca as the mark
                    for num in reversed(nums):
                        p = parse_performance(num)
                        if p[0]:
                            performance = p[0]
                            break

            if not performance:
                continue

        # Handle combined events: if after_ca has points (e.g., "678"), store as mark
        # Points are valid performances for combined events
        if not performance and re.match(r'^\d{2,4}$', after_clean.strip()):
            performance = after_clean.strip()

        if not performance:
            continue

        results.append({
            'athlete_name': athlete_name,
            'athlete_dob': '',
            'athlete_id': '',
            'discipline': current_event or '',
            'performance': performance,
            'wind': wind,
        })

    return results


def deduplicate_results(results):
    groups = {}
    for r in results:
        key = (r['athlete_name'].upper(), r['discipline'].upper())
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    unique = []
    for key, entries in groups.items():
        if len(entries) == 1:
            unique.append(entries[0])
            continue

        # Keep best valid result, or best DNS/DQ entry
        with_result = [e for e in entries if e['performance'] and e['performance'] not in ('DQ', 'DNS', 'DNF', 'N.P.', 'RET.', '')]
        without_result = [e for e in entries if not e['performance'] or e['performance'] in ('DQ', 'DNS', 'DNF', 'N.P.', 'RET.', '')]

        if with_result:
            best = with_result[-1]
            unique.append(best)
        elif without_result:
            unique.append(without_result[0])

    return unique


def process_pdf(pdf_path, json_dir, url):
    print(f"Processing: {pdf_path}", file=sys.stderr)

    text = extract_text(pdf_path)
    if not text:
        print("ERROR: No text extracted", file=sys.stderr)
        return []

    header = parse_header(text)

    print(f"  Event: {header['event_name']}", file=sys.stderr)
    print(f"  Date: {header['event_date']}", file=sys.stderr)
    print(f"  Location: {header['event_location']}", file=sys.stderr)

    athletes = extract_athletes(text)
    athletes = deduplicate_results(athletes)
    print(f"Found {len(athletes)} CA Tarragona athletes", file=sys.stderr)

    valid = []
    for a in athletes:
        name = a.get('athlete_name', '').strip()
        perf = a.get('performance', '').strip()
        disc = a.get('discipline', '').strip()

        if not name or not perf or not disc:
            missing = []
            if not name:
                missing.append('athlete_name')
            if not perf:
                missing.append('performance')
            if not disc:
                missing.append('discipline')
            print(f"  WARNING: Skipping entry missing {', '.join(missing)}: {a}", file=sys.stderr)
            continue

        valid.append(a)

    athletes = valid

    output = {
        'event_name': header['event_name'],
        'event_date': header['event_date'],
        'event_location': header['event_location'],
        'event_src': url or pdf_path,
        'total_results': len(athletes),
        'results': athletes,
    }

    filename = os.path.basename(pdf_path).replace('.pdf', '.json')
    json_path = os.path.join(json_dir, filename)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Written: {json_path}", file=sys.stderr)
    print()

    for a in athletes:
        print(f"  {a['athlete_name']:45s} | {a['discipline'][:35]:35s} | {a['performance']}")

    return athletes


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/process_2005.py <pdf_path> [json_dir] [url]", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    json_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(pdf_path)
    url = sys.argv[3] if len(sys.argv) > 3 else ''

    if not os.path.exists(json_dir):
        os.makedirs(json_dir, exist_ok=True)

    process_pdf(pdf_path, json_dir, url)


if __name__ == '__main__':
    main()