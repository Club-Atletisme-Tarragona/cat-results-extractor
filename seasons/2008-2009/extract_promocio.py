#!/usr/bin/env python3
"""
Extract CATT results from old FCAT Promoció PDFs (2008-2009 era).

These PDFs store text in PostScript content streams. This script decompresses
FlateDecode streams, extracts text from PostScript operators (TJ and Tj),
and parses CATT athlete results.

Key insight: The PDFs use TWO types of text operators:
- TJ: [(text1)spacing(text2)...]TJ — used for athlete result rows (multiple fields)
- Tj: (text)Tj — used for event headers, competition titles, wind info

Each TJ block is a complete data row. Each Tj is a supplementary text element.
We extract both, track Y positions per-stream, and parse independently per-stream.
"""

import sys
import re
import json
import os
import zlib


def decompress_streams(pdf_path):
    """Decompress all FlateDecode streams from a PDF."""
    with open(pdf_path, 'rb') as f:
        data = f.read()
    pattern = rb'/Filter/FlateDecode.*?stream\r?\n(.*?)endstream'
    matches = re.findall(pattern, data, re.DOTALL)
    streams = []
    for stream in matches:
        try:
            decompressed = zlib.decompress(stream)
            text = decompressed.decode('latin-1', errors='replace')
            streams.append(text)
        except Exception:
            continue
    return streams


def extract_all_text_elements(streams):
    """Extract ALL text elements from all streams with Y position tracking.
    
    Returns list of dicts: {stream_idx, y, text, is_row}
    TJ blocks are joined into a single line per block. Tj operators individually.
    Y positions tracked per-stream by processing operators in document order.
    """
    all_elements = []
    default_leading = 12.0
    
    for stream_idx, stream in enumerate(streams):
        current_y: float = 0
        current_x: float = 0
        
        # Find ALL operators with offsets, process in order
        ops = []
        for m in re.finditer(r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+Tm', stream):
            ops.append((m.start(), 'Tm', m.group(1), m.group(2)))
        for m in re.finditer(r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+Td(?!\*)', stream):
            ops.append((m.start(), 'Td', m.group(1), m.group(2)))
        for m in re.finditer(r'(\d+\.?\d*)\s+(\d+\.?\d*)\s+TD', stream):
            ops.append((m.start(), 'TD', m.group(1), m.group(2)))
        for m in re.finditer(r'T\*', stream):
            ops.append((m.start(), 'T*', None, None))
        for m in re.finditer(r'\[(.*?)\]\s*TJ', stream, re.DOTALL):
            ops.append((m.start(), 'TJ', m.group(1), None))
        for m in re.finditer(r'\(([^)]*)\)\s*Tj', stream):
            ops.append((m.start(), 'Tj', m.group(1), None))
        
        ops.sort(key=lambda x: x[0])
        
        for _, op_type, val1, val2 in ops:
            if op_type == 'Tm':
                current_x = float(val1)
                current_y = float(val2)
            elif op_type in ('Td', 'TD'):
                current_y += float(val2)
            elif op_type == 'T*':
                current_y -= default_leading
            elif op_type == 'TJ':
                parts = re.findall(r'\(([^)]*)\)', val1)
                line_text = ' '.join(p for p in parts)
                if line_text.strip():
                    all_elements.append({
                        'stream_idx': stream_idx, 'y': current_y,
                        'text': line_text.strip(), 'is_row': True,
                    })
            elif op_type == 'Tj':
                printable = ''.join(c if 32 <= ord(c) < 127 else ' ' for c in val1)
                stripped = printable.strip()
                if stripped:
                    all_elements.append({
                        'stream_idx': stream_idx, 'y': current_y,
                        'text': stripped, 'is_row': False,
                    })
    
    return all_elements


# Club detection — 2008-2009 season
# In this era, CATT athletes were listed under "CA TARRAGONA" in the PDFs.
# CG TARRAGONA = Club Gimnàstic Tarragona (NOT CATT)
# NÀSTIC/NASTIC = Club Gimnàstic Tarragona athletics (NOT CATT)
CATT_CLUB_NAMES = {
    'CA TARRAGONA', 'C. A. TARRAGONA', 'CATT', 'CLUB ATLETISME TARRAGONA',
    'C.A. TARRAGONA', 'C.A.TARRAGONA',
    'UDT', 'UNIO DEPORTIVA TARRAGONA',
}


def is_catt_club(club_name):
    """Check if a club name matches C. A. Tarragona (any variant)."""
    club_upper = re.sub(r'\s+', ' ', club_name.strip().upper())
    if club_upper in CATT_CLUB_NAMES:
        return True
    for pattern in [r'C\.\s*A\.\s*TARRAGONA', r'C\.\s*A\.\s*T\.\s*TARRAGONA',
                    r'CA\s+TARRAGONA', r'CATT',
                    r'UNIO\s+DEPORTIVA\s+TARRAGONA', r'UDT']:
        if re.search(pattern, club_upper):
            return True
    return False


def is_catt_line(line):
    """Check if a line contains a CATT athlete result."""
    stripped = line.strip()
    if not stripped:
        return False
    skip_labels = ['Lloc', 'Dorsal', 'Nom', 'Any', 'Club', 'Marca',
                   'Lugar', 'Puesto', 'Nombre', 'Fecha', 'Licencia',
                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Serie',
                   'Ronda', 'Série', 'Eliminatoria', 'Heats', 'Heat',
                   'Final', 'Gestion', 'Pagina', 'SUMARIO', 'Rank',
                   'Viento', 'Pasos', 'RESULTADO', 'Puntos', 'P.Líder',
                   'CARRER', 'LLIC.']
    if any(label in stripped for label in skip_labels):
        return False
    return is_catt_club(stripped)


def is_event_header(line):
    """Check if a line is an event header."""
    line = line.strip()
    if not line or is_catt_club(line):
        return False
    skip_labels = ['Lloc', 'Dorsal', 'Nom', 'Any', 'Club', 'Marca',
                   'Lugar', 'Puesto', 'Nombre', 'Fecha', 'Licencia',
                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Serie',
                   'Ronda', 'Série', 'Eliminatoria', 'Heats', 'Heat',
                   'Final', 'Gestion', 'Pagina', 'SUMARIO', 'Rank',
                   'Viento', 'Pasos', 'RESULTADO', 'Puntos', 'P.Líder']
    line_upper = line.upper()
    for label in skip_labels:
        if label in line_upper:
            return False
    if re.match(r'^\d+(?:\.\d+)?\s*(?:m|m\.|metres|meters)', line):
        return True
    event_names = ['PES', 'DISC', 'MARTELL', 'JAVELINA', 'DARD', 'ALTURA',
                   'PÈRTIGA', 'PERTIGA', 'LLARGADA', 'TRIPLE', 'SALT',
                   'RELLEU', 'MARXA', 'MARCHA', 'PENTATHLON', 'HEPTATHLON']
    for kw in event_names:
        if kw in line_upper:
            return True
    if re.match(r'^(?:60|100|200|400|800|1000|1500|3000)\s+METRES', line_upper):
        return True
    if re.match(r'^SALT', line_upper):
        return True
    if re.match(r'^LLANÇAMENT', line_upper):
        return True
    if re.match(r'^(?:60)\s+METRES\s+TANQUES', line_upper):
        return True
    return False


def extract_event_name(line):
    """Extract event name from header, removing sub-event suffixes."""
    line = line.strip()
    line = re.sub(r'^\d+[a-zèé]?\.\s*(Sèrie|Serie|Ronda|Final|Eliminatoria)\s*', '', line)
    return line.strip()


def parse_header(lines):
    """Parse competition header from text lines."""
    competicio = ubicacio = localitat = data = ""
    
    for line in lines[:30]:
        s = line.strip()
        if not s:
            continue
        su = s.upper()
        if any(kw in su for kw in ['JORNADA', 'TROBADA', 'TROFEU', 'CONTROL',
                                    'CAMPIONAT', 'CAMPEONATO', 'LIGA', 'LLIGA',
                                    'PROMOCIÓ', 'PROMOCIÓN', 'FINAL']):
            competicio = re.sub(r'\s+\d{2}\s*[-–]\s*\d{2}\s*$', '', s).strip()
            break
    
    for line in lines[:30]:
        s = line.strip()
        if any(kw in s for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón',
                                   'Camp', 'pabellon', 'pabellón']):
            ubicacio = s
            break
    
    for line in lines[:30]:
        m = re.search(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})', line)
        if m:
            data = re.sub(r'\s+', '', m.group(1))
            break
        m = re.search(r'(\d{2}\s*/\s*\d{2}\s*/\s*\d{2})', line)
        if m:
            data = re.sub(r'\s+', '', m.group(1))
            break
    
    cities = ['Tarragona', 'Manresa', 'Vilafranca', 'Terrassa', 'Badalona',
              'Mataró', 'Mollet', 'Sant Celoni', 'Girona', 'Lleida', 'Cambrils',
              'Valls', 'Amposta', 'Reus', 'Olot', 'Figueres', 'Lloret',
              'Palafrugell', 'Castellar', 'Granollers', 'Calella', 'El Prat',
              'Barcelona', 'Serrahima', "L'Hospitalet", 'Hospitalet', 'Can Dragó', 'Camp Clar']
    for line in lines[:30]:
        s = line.strip()
        if not s:
            continue
        for city in cities:
            if city.lower() in s.lower() and city not in competicio.lower():
                localitat = city
                break
        if localitat:
            break
    
    return competicio, ubicacio, localitat, data


def parse_result_line(line, event_name):
    """Parse a single result line for a CATT athlete."""
    stripped = line.strip()
    club_match = re.search(
        r'(C\.\s*A\.\s*TARRAGONA|CATT|C\.\s*A\.\s*T\.\s*TARRAGONA|CA\s+TARRAGONA|Club\s+Atletisme\s+Tarragona|C\.A\.\s*TARRAGONA|C\.A\.TARRAGONA|UDT)',
        stripped, re.IGNORECASE
    )
    if not club_match:
        return None
    
    club_pos = club_match.start()
    before_club = stripped[:club_pos].rstrip()
    after_club = stripped[club_match.end():].strip()
    
    # Try full DOB format first
    dob_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*$', before_club)
    if dob_match:
        dob = dob_match.group(1)
        before_dob = before_club[:dob_match.start()].rstrip()
        # Match license number with various formats: "CL 52265", "CL - 52265", "1 CL - 52265", "1 434 CL 189"
        lic_match = re.search(r'(?:\d+\s+)?(?:CL|CT|CAT|IB|FC|JA|BC|GE)[\s-]*(\d+)\s+(.+)', before_dob)
        if lic_match:
            name = clean_athlete_name(lic_match.group(2).strip())
        else:
            return None
        pos_match = re.match(r'(\d+\.?)', before_dob)
        pos = int(pos_match.group(1).rstrip('.')) if pos_match else None
    else:
        year_match = re.search(r'(\d{2})\s*$', before_club)
        if not year_match:
            return None
        year = year_match.group(1)
        name_and_pos = before_club[:year_match.start()].rstrip()
        # Try to match: "pos pos_num license_num NAME" or "pos pos_num NAME"
        pos_match = re.match(r'(\d+\.?)\s+(\d+)\s+(CL[\s-]*\d+\s+)?(.+)', name_and_pos)
        if not pos_match:
            # Try simpler: "pos pos_num NAME"
            pos_match = re.match(r'(\d+\.?)\s+(\d+)\s+(.+)', name_and_pos)
            if not pos_match:
                return None
        pos = int(pos_match.group(1).rstrip('.'))
        # Group 3 might be license+name or just name
        if len(pos_match.groups()) >= 4 and pos_match.group(3):
            # Has license prefix
            name = clean_athlete_name(pos_match.group(4).strip())
        else:
            name = clean_athlete_name(pos_match.group(3).strip())
        year_int = int(year)
        dob_year = 2000 + year_int if year_int <= 9 else 1900 + year_int
        dob = f"1/1/{dob_year}"
    
    converted_mark = extract_mark_from_after_club(after_club)
    wind = extract_wind_from_line(line)
    clean_event, event_wind = clean_event_name(event_name)
    if not wind and event_wind:
        wind = event_wind
    
    return {
        "prova": clean_event, "atleta_nom": name.strip(),
        "atleta_naixement": dob, "marca": converted_mark,
        "vent": wind, "lloc": pos,
    }


def extract_mark_from_after_club(after_club):
    """Extract mark from text after the club name."""
    after_club = after_club.strip()
    if not after_club or after_club in ('Ret.', 'Ret', 'AB', 'DNF', 'DNS', 'DQ'):
        return after_club if after_club else ""
    
    time_match = re.match(r'(\d+:\d+\.\d+)', after_club)
    if time_match:
        return time_match.group(1)
    
    ms = re.match(r"(\d+)['\"](\d+)['\"](\d+)", after_club)
    if ms:
        return str(int(ms.group(1)) * 60 + int(ms.group(2)) + int(ms.group(3)) / 10.0)
    
    sq = re.match(r"(\d+)['\"](\d+)", after_club)
    if sq:
        return f"{sq.group(1)}.{sq.group(2)}"
    
    tokens = re.findall(r'(\d+[,\.]\d+|X|x|-|XO|xxo)', after_club)
    if len(tokens) >= 3:
        valid_marks = []
        for token in tokens:
            if token in ('X', 'x', '-', 'XO', 'xxo'):
                continue
            try:
                val = float(token.replace(',', '.'))
                if 1.0 <= val <= 20.0:
                    valid_marks.append(val)
            except ValueError:
                continue
        if valid_marks:
            return f"{max(valid_marks):.2f}"
        for token in tokens:
            try:
                float(token.replace(',', '.'))
                return token.replace(',', '.')
            except ValueError:
                continue
    
    single = re.match(r'(\d+[,\.]\d+)', after_club)
    if single:
        return single.group(1).replace(',', '.')
    return ""


def clean_athlete_name(name):
    """Clean athlete name from PDF artifacts."""
    # Strip leading license number patterns: "1 CL - 52265", "1 434 CL 189", "5 C T- 15201"
    cleaned = re.sub(r'^\d+\s+(?:CL[-\s]*\d+|C[-\s]*T[-\s]*\d+)', '', name)
    # Strip trailing birth year (2 digits): "JOAQUIM MORENO PACHECHO 20"
    cleaned = re.sub(r'\s+\d{2}\s*$', '', cleaned)
    # Fix space-inflated names: "M A RI A" -> "MARIA"
    # This is tricky — only fix if the name looks like it has too many spaces
    # Heuristic: if a "word" is a single letter and next word starts with a letter, merge
    parts = cleaned.split()
    merged = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1 and i + 1 < len(parts) and parts[i+1][0].isalpha():
            # Merge single letter with next word
            merged.append(parts[i] + parts[i+1])
            i += 2
        else:
            merged.append(parts[i])
            i += 1
    cleaned = ' '.join(merged)
    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Reformat: LAST, FIRST -> FIRST LAST
    comma_match = re.match(r'(.+),\s*(.+)', cleaned)
    if comma_match:
        cleaned = f"{comma_match.group(2).strip()} {comma_match.group(1).strip()}"
    return cleaned


def clean_event_name(event_name):
    """Clean event name by removing wind info."""
    wind = None
    wind_match = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', event_name)
    if wind_match:
        wind = wind_match.group(1).replace(',', '.')
        wind = f"+{wind}" if not wind.startswith('-') else wind
        event_name = re.sub(r'\s*Vent\s+[+-]?\d+[,\.]\d+\s*', '', event_name)
    return re.sub(r'\s+', ' ', event_name).strip(), wind


def extract_wind_from_line(line):
    """Extract wind value from a line."""
    m = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', line)
    if m:
        wind = m.group(1).replace(',', '.')
        return f"+{wind}" if not wind.startswith('-') else wind
    return None


def deduplicate_results(results):
    """Remove duplicate results for same athlete+event."""
    key_results = {}
    for r in results:
        key = (r["atleta_nom"].upper(), r["prova"].upper())
        marca = r["marca"].strip()
        if key not in key_results:
            key_results[key] = r
        else:
            existing = key_results[key]
            existing_marca = existing["marca"].strip()
            if marca and marca not in ("DQ", "DNS", "DNF", "Ret.", "AB"):
                key_results[key] = r
    return list(key_results.values())


def _parse_stream_lines(lines):
    """Parse lines from a single stream, tracking event headers."""
    results = []
    current_event = None
    current_wind = None
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check for wind in sub-event lines
        if not current_event or re.match(r'^\d+[a-zèé]?\.\s*(Sèrie|Serie|Ronda|Final|Eliminatoria)', current_event):
            wind_match = re.search(r'Vent\s+([+-]?\d+[,\.]\d+)', stripped)
            if wind_match:
                current_wind = wind_match.group(1).replace(',', '.')
                current_wind = f"+{current_wind}" if not current_wind.startswith('-') else current_wind
        
        # Check if event header
        if is_event_header(stripped):
            current_event = extract_event_name(stripped)
            if current_wind:
                current_event = f"{current_event} Vent {current_wind.lstrip('+')}"
            if re.match(r'^\d+[a-zèé]?\.\s*(Sèrie|Serie|Ronda|Final|Eliminatoria)', current_event):
                current_event = None
            continue
        
        # Check if CATT result
        if current_event and is_catt_line(stripped):
            result = parse_result_line(stripped, current_event)
            if result:
                results.append(result)
    
    return results


def parse_pdf(pdf_path):
    """Parse a PDF and extract CATT athlete results.
    
    Each stream is processed independently to track event headers.
    """
    print(f"  Decompressing streams...")
    streams = decompress_streams(pdf_path)
    print(f"  Found {len(streams)} compressed streams")
    
    print(f"  Extracting text elements (TJ + Tj)...")
    elements = extract_all_text_elements(streams)
    print(f"  Found {len(elements)} text elements")
    
    # Group by stream
    by_stream = {}
    for elem in elements:
        si = elem['stream_idx']
        if si not in by_stream:
            by_stream[si] = []
        by_stream[si].append(elem)
    
    # Parse header from first few streams
    print(f"  Parsing competition header...")
    header_lines = []
    for si in sorted(by_stream.keys())[:5]:
        for elem in sorted(by_stream[si], key=lambda x: -x['y']):
            header_lines.append(elem['text'])
    
    competicio, ubicacio, localitat, data = parse_header(header_lines)
    print(f"    Competicio: {competicio or '(no trobat)'}")
    print(f"    Ubicacio: {ubicacio or '(no trobat)'}")
    print(f"    Localitat: {localitat or '(no trobat)'}")
    print(f"    Data: {data or '(no trobat)'}")
    
    # Extract CATT results — process each stream independently
    print(f"  Extracting CATT athlete results...")
    all_results = []
    for si in sorted(by_stream.keys()):
        stream_elements = sorted(by_stream[si], key=lambda x: -x['y'])
        stream_lines = [elem['text'] for elem in stream_elements]
        results = _parse_stream_lines(stream_lines)
        all_results.extend(results)
    
    print(f"  Found {len(all_results)} CATT result entries")
    
    all_results = deduplicate_results(all_results)
    print(f"  After deduplication: {len(all_results)} unique results")
    
    for r in all_results:
        status = "OK" if r["marca"] else ("Ret./AB" if r["marca"] in ("Ret.", "AB") else "DQ/DNS")
        print(f"    [{status}] {r['atleta_nom'] or '???':40s} | {r['prova'] or '???':30s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']}")
    
    header = {'competicio': competicio, 'ubicacio': ubicacio,
              'localitat': localitat, 'data': data}
    return header, all_results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_promocio.py <pdf_file> [output_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "json"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Extracting from: {pdf_path}")
    print()
    
    header, results = parse_pdf(pdf_path)
    
    if not results:
        print("\nNo results found. Skipping JSON export.")
        return
    
    # Validate
    valid_results = []
    for r in results:
        name = r.get("atleta_nom", "").strip()
        performance = r.get("marca", "").strip()
        discipline = r.get("prova", "").strip()
        # Allow DNS/DNF/Ret entries (empty performance is valid for these)
        if not name or not discipline:
            missing = []
            if not name: missing.append("athlete_name")
            if not performance: missing.append("performance")
            if not discipline: missing.append("discipline")
            print(f"WARNING: Skipping entry missing {', '.join(missing)}", file=sys.stderr)
            continue
        # Reject entries where name looks like a license number (all digits + CL pattern)
        if re.match(r'^\d+\s+CL', name):
            print(f"WARNING: Skipping entry with license-like name: '{name}'", file=sys.stderr)
            continue
        valid_results.append(r)
    
    results = valid_results
    print(f"\nAfter validation: {len(results)} valid results")
    
    full_competicio = f"{header['competicio']} - {header['ubicacio']}" if header['ubicacio'] else header['competicio']
    
    output = {
        "event_name": full_competicio,
        "event_date": header['data'],
        "event_location": header['localitat'],
        "total_results": len(results),
        "results": []
    }
    
    for r in results:
        output["results"].append({
            "athlete_name": r["atleta_nom"],
            "athlete_dob": r["atleta_naixement"],
            "athlete_license": "",
            "performance": r["marca"],
            "discipline": r["prova"],
            "wind": r["vent"],
            "place": r.get("lloc"),
        })
    
    base = os.path.basename(pdf_path).replace('.pdf', '')
    output_path = os.path.join(output_dir, f"{base}.json")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
