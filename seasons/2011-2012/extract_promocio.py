#!/usr/bin/env python3
"""
Extract CATT results from old FCAT Promoció PDFs.

Auto-detects PDF format:
- FCAT inline: "CL 57703 NAME YEAR CA TARRAGONA MARK"
- RFEA multi-line: "NAME DD/MM/YYYY MARK" + "CA TARRAGONA CLxxxxx"
- Table-based: pdfplumber extract_tables

Only extracts CA Tarragona (NOT CG Tarragona or other CA XXX).
"""
import sys
import os
import re
import json
import pdfplumber


# ── Helpers ──────────────────────────────────────────────────────────

def clean_athlete_name(name):
    name = name.strip()
    # Remove trailing noise: dates, percentages, ellipsis, RT/DQ
    name = re.sub(r'\s+\d{2}/\d{2}/\d{4}\s*$', '', name).strip()
    name = re.sub(r'\s+\d+,\d+%?\s*$', '', name).strip()
    name = re.sub(r'\s*[\u2026]+\s*$', '', name).strip()
    name = re.sub(r'\s+(RT|DQ|DNS|DNF)\s*$', '', name, flags=re.IGNORECASE).strip()
    
    # Convert "LAST, FIRST" -> "FIRST LAST"
    comma_match = re.match(r'(.+),\s*(.+)', name)
    if comma_match:
        last, first = comma_match.groups()
        name = f"{first.strip()} {last.strip()}"
    
    # Remove trailing F (final indicator)
    name = re.sub(r'\s+F\s*$', '', name).strip()
    return name.strip()


def is_valid_name(name):
    if not name or len(name.strip()) < 5:
        return False
    words = name.strip().split()
    if len(words) < 2 or len(words) > 4:
        return False
    valid_particles = {'DE', 'DEL', 'DA', 'DI', 'DOS', 'DAS', 'Y', 'E',
                       'VAZ', 'VON', 'VAN', 'DEN', 'DER', 'TER', 'LA', 'LE',
                       'LOS', 'LAS', 'EL', 'AL', 'TOR', 'BER', 'GARC', 'MART',
                       'LOPE', 'FERN', 'PERE', 'GOME', 'RODR', 'SANC', 'RAMO',
                       'FLORES', 'MORE', 'RIV', 'SERR', 'CAM', 'MONT', 'GONZ'}
    for word in words[1:]:
        w = word.upper()
        if len(word) <= 2 and w not in valid_particles:
            return False
    return True


def is_ca_tarragona(club):
    """Check if club is CA Tarragona ONLY (not CG Tarragona, not other CA XXX)."""
    club = club.strip()
    # Must contain "CA Tarragona" but NOT "CG Tarragona"
    if re.search(r'\bCG\s*TARRAGONA\b', club, re.IGNORECASE):
        return False
    if re.search(r'\bCA\s*TARRAGONA\b', club, re.IGNORECASE):
        return True
    # Also check for "C.A. Tarragona" or "CATT"
    if re.search(r'\bC\.A\.\s*Tarragona\b', club, re.IGNORECASE):
        return True
    if re.search(r'\bCATT\b', club, re.IGNORECASE):
        return True
    return False


def parse_performance(event, mark_str):
    if not mark_str:
        return ''
    event_upper = event.upper()

    # Marcha
    if 'MARXA' in event_upper:
        m = re.search(r"(\d{1,2})'(\d{2})''(\d)", mark_str)
        if m: return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
        m = re.search(r'(\d{1,2}:\d{2}\.\d{2})', mark_str)
        if m: return m.group(1)
        parts = mark_str.split(',')
        if len(parts) == 3:
            try:
                if 1 <= int(parts[0]) <= 59:
                    return f"{parts[0]}:{parts[1]}.{parts[2]}"
            except ValueError:
                pass
        return ''

    # Race (METRES LLISOS/TANQUES/VALLS or XXXm format)
    is_race = any(kw in event_upper for kw in ['METRES LLISOS', 'METRES TANQUES', 'METRES VALLS'])
    # Also check XXXm format: "3.000m FEM. AL", "100m FEM. AL"
    if not is_race:
        m = re.search(r'(\d[\d.,]*)m', event_upper, re.IGNORECASE)
        if m:
            meters_clean = m.group(1).replace('.', '').replace(',', '')
            try:
                val = int(meters_clean)
                if 60 <= val <= 10000:
                    is_race = True
            except ValueError:
                pass
    if is_race:
        m = re.search(r"(\d{1,2})'(\d{2})''(\d)", mark_str)
        if m: return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
        m = re.search(r'(\d{1,2}:\d{2}\.\d{2})', mark_str)
        if m: return m.group(1)
        parts = mark_str.split(',')
        if len(parts) == 3:
            try:
                if 1 <= int(parts[0]) <= 59:
                    return f"{parts[0]}:{parts[1]}.{parts[2]}"
            except ValueError:
                pass
        # Decimal seconds: 9.85, 11.79, etc.
        for nm in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', mark_str):
            val = float(nm.group(1))
            if 5.0 <= val <= 60.0:
                return nm.group(1)
        return ''

    # Height
    if any(kw in event_upper for kw in ["SALT D'ALÇADA", "SALT D'ALTADA", "ALTURA", "ALÇADA", "ALTADA"]):
        m = re.search(r'(\d+[,.]\d{2})', mark_str)
        if m:
            val = float(m.group(1).replace(',', '.'))
            if 0.5 <= val <= 7.0:
                return m.group(1).replace(',', '.')
        return ''

    # Jump (largada, triple, pertiga, perxa)
    if any(kw in event_upper for kw in ['LLARGADA', 'TRIPLE', 'PÈRTIGA', 'PERTIGA', 'PERXA']):
        for nm in re.finditer(r'(\d+[,.]\d{2})', mark_str):
            val = float(nm.group(1).replace(',', '.'))
            if 1.5 <= val <= 20.0:
                return nm.group(1).replace(',', '.')
        return ''

    # Throw (disc, pes, mart, javelina, dard, pilota)
    if any(kw in event_upper for kw in ['LLANÇAMENT', 'LLANAMENT', 'DISC', 'PES', 'MART', 'JAVELINA', 'DARD', 'PILOTA']):
        for nm in re.finditer(r'(\d+[,.]\d{2})', mark_str):
            val = float(nm.group(1).replace(',', '.'))
            if 3.0 <= val <= 80.0:
                return nm.group(1).replace(',', '.')
        return ''

    # Fallback: decimal seconds
    for nm in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', mark_str):
        val = float(nm.group(1))
        if 5.0 <= val <= 60.0:
            return nm.group(1)
    return ''


def detect_event(line):
    """Detect event name from a line of text."""
    line = line.strip()
    if not line:
        return None

    # Skip athlete lines (start with digit + digit pattern)
    if re.match(r'^\d+\s+\d+\s+', line):
        return None
    # Skip club lines (contain CL followed by digits)
    if re.search(r'CL\d+', line):
        return None
    # Skip lines that look like results (contain O/X patterns or multiple numbers)
    if re.search(r'[OX\-]+/[OX\-]+', line):
        return None
    # Skip header/footer lines
    if re.search(r'Nombre F de Nac|Pto Dor|Club Lic|Calificación|Semifinal|Final\s', line, re.IGNORECASE):
        return None
    if line.startswith('RCAT') or line.startswith('T2011'):
        return None

    # METRES LLISOS/TANQUES/VALLS with optional category and gender
    m = re.search(r'(\d+\s+)?METRES\s+(LLISOS|TANQUES|VALLS)\s+(BENJAMÍ|INFANTIL|JÚNIOR|SÈNIOR|ALEVÍ|CADET|JÚNIOR|SÈNIOR)?\s*(MASCULÍ|FEMENÍ|MASCULINA|FEMENINA|MA|FE)?', line, re.IGNORECASE)
    if m:
        parts = [m.group(1).strip() if m.group(1) else '', 'METRES', m.group(2)]
        if m.group(3): parts.append(m.group(3))
        if m.group(4): parts.append(m.group(4))
        return ' '.join(p for p in parts if p)

    # RFEA XXXm format: "3.000m FEM. AL", "100m FEM. AL", "600m FEM. AL"
    m = re.search(r'(\d[\d.,]*)m\s+(\S+)', line, re.IGNORECASE)
    if m:
        meters = m.group(1)
        meters_clean = meters.replace('.', '').replace(',', '')
        try:
            val = int(meters_clean)
            if 60 <= val <= 10000:
                return line
        except ValueError:
            pass

    # LLANÇAMENT DE XXX
    m = re.search(r'(LLANÇAMENT|LLANAMENT)\s+DE\s+(\w+)', line, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} DE {m.group(2).upper()}"

    # SALT D'XXX
    m = re.search(r'SALT\s+D\'(\w+)', line, re.IGNORECASE)
    if m:
        return f"SALT D'{m.group(1).upper()}"

    # RFEA-style events: "Alçada FEM. AL", "Llargada MASC. AL", "Pes (2kg) MASC. AL"
    event_keywords = ['ALÇADA', 'ALTADA', 'ALTURA', 'LLARGADA', 'TRIPLE SALT', 'TRIPLE',
                      'PÈRTIGA', 'PERTIGA', 'PERXA', 'DISC', 'PES', 'JAVELINA',
                      'DARD', 'PILOTA', 'MARXA']
    for kw in event_keywords:
        if kw in line.upper():
            return line
            break
    
    return None



# ── RFEA Format Parser ──────────────────────────────────────────────

def extract_rfea_format(pdf_path):
    """
    Extract results from RFEA-format PDFs.
    
    Format:
    pos dorsal NAME DD/MM/YYYY MARK
    CLUB CLxxxxx
    [optional detail lines]
    """
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ''
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + '\n'

    lines = full_text.split('\n')
    seen = set()
    results = []
    current_event = ''
    header_date = ''
    header_location = ''

    # Parse header from first 30 lines
    for i, line in enumerate(lines[:30]):
        line = line.strip()
        date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', line)
        if date_match:
            months = {'gener': '1', 'febrer': '2', 'març': '3', 'abril': '4', 'maig': '5', 'juny': '6',
                      'juliol': '7', 'agost': '8', 'setembre': '9', 'octubre': '10', 'novembre': '11', 'desembre': '12'}
            day = date_match.group(1).zfill(2)
            month = months.get(date_match.group(2).lower(), '01')
            year = date_match.group(3)
            header_date = f"{year}-{month}-{day}"
            header_location = line.replace(',', '').strip()

    # Parse athlete blocks
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Detect event lines
        detected = detect_event(line)
        if detected:
            current_event = detected
            i += 1
            continue

        # Skip header lines
        if re.search(r'LLOC\s+.*NOM.*CLUB', line, re.IGNORECASE):
            i += 1
            continue
        if re.search(r'Pto Dor|Nombre F de Nac|Club Lic|Semifinal|Final|Calificación', line, re.IGNORECASE):
            i += 1
            continue
        if line.startswith('RCAT') or line.startswith('T2011'):
            i += 1
            continue

        # Try to match athlete line: pos dorsal NAME DD/MM/YYYY MARK
        athlete_match = re.match(r'(\d+)\s+(\d+)\s+(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(.+)$', line)
        if not athlete_match:
            i += 1
            continue

        pos = athlete_match.group(1)
        dorsal = athlete_match.group(2)
        name = athlete_match.group(3).strip()
        dob = athlete_match.group(4)
        mark = athlete_match.group(5).strip()

        # Next line should be: CLUB CLxxxxx
        club_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
        
        # Check if this line has CA Tarragona
        if not is_ca_tarragona(club_line):
            i += 1
            continue

        # Extract club name and license from club line
        club_match = re.match(r'(.+?)\s+(CL\d+|CT\d+|CAT-\d+|IB-\d+)', club_line)
        if not club_match:
            i += 1
            continue

        club_name = club_match.group(1).strip()
        license_num = club_match.group(2).strip()

        # Verify it's CA Tarragona
        if not is_ca_tarragona(club_name):
            i += 1
            continue

        # Clean name
        name = clean_athlete_name(name)
        if not is_valid_name(name):
            i += 1
            continue

        # Parse performance
        performance = parse_performance(current_event, mark)
        if not performance:
            i += 1
            continue

        key = (name.lower(), current_event.lower(), performance)
        if key in seen:
            i += 1
            continue
        seen.add(key)

        results.append({
            'athlete_name': name,
            'discipline': current_event,
            'performance': performance,
        })

        # Skip detail lines (O/XXX patterns)
        j = i + 2
        while j < len(lines):
            detail = lines[j].strip()
            if detail and ('O/' in detail or detail.startswith('1.03') or detail.startswith('X') or
                          detail.startswith('O') or detail.startswith('-')):
                # Check if it's a detail line (contains O/ or X patterns)
                if re.search(r'[OX\-]+/[OX\-]+', detail):
                    j += 1
                    continue
            break
        i = j

    return header_date, header_location, '', results


# ── FCAT Inline Format Parser ───────────────────────────────────────

def extract_from_tables(pdf_path):
    """Try to extract results using pdfplumber table extraction."""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ''
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + '\n'

    header_date, header_location, header_event = extract_header_info(full_text)

    seen = set()
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables(table_settings={
                'vertical_strategy': 'text',
                'horizontal_strategy': 'text',
            })

            for table in tables:
                if not table or len(table) < 2:
                    continue

                header_row = None
                for row in table:
                    if row and any('NOM' in str(cell) for cell in row if cell):
                        header_row = row
                        break

                if not header_row:
                    continue

                col_map = {}
                for i, cell in enumerate(header_row):
                    if cell:
                        c = str(cell).strip().upper()
                        if 'NOM' in c: col_map['name'] = i
                        elif 'CLUB' in c: col_map['club'] = i
                        elif 'MARCA' in c: col_map['mark'] = i

                name_col = col_map.get('name')
                club_col = col_map.get('club')
                mark_col = col_map.get('mark')

                if name_col is None or club_col is None or mark_col is None:
                    continue

                page_text = page.extract_text() or ''
                event = ''
                for line in page_text.split('\n'):
                    detected = detect_event(line)
                    if detected:
                        event = detected

                if not event:
                    continue

                for row in table[1:]:
                    if not row:
                        continue

                    name = str(row[name_col]).strip() if name_col < len(row) else ''
                    club = str(row[club_col]).strip() if club_col < len(row) else ''
                    mark = str(row[mark_col]).strip() if mark_col < len(row) else ''

                    if not is_ca_tarragona(club):
                        continue

                    name = clean_athlete_name(name)
                    if not is_valid_name(name):
                        continue

                    performance = parse_performance(event, mark)
                    if not performance:
                        continue

                    key = (name.lower(), event.lower(), performance)
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append({
                        'athlete_name': name,
                        'discipline': event,
                        'performance': performance,
                    })

    return header_date, header_location, header_event, results


def extract_header_info(text):
    lines = text.split('\n')
    header_date = ''
    header_location = ''

    for line in lines:
        line = line.strip()
        date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', line)
        if date_match and not header_date:
            months = {'gener': '1', 'febrer': '2', 'març': '3', 'abril': '4', 'maig': '5', 'juny': '6',
                      'juliol': '7', 'agost': '8', 'setembre': '9', 'octubre': '10', 'novembre': '11', 'desembre': '12'}
            day = date_match.group(1).zfill(2)
            month = months.get(date_match.group(2).lower(), '01')
            year = date_match.group(3)
            header_date = f"{year}-{month}-{day}"
        if re.search(r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}', line):
            header_location = line.replace(',', '').strip()

    return header_date, header_location, ''


def extract_from_lines(pdf_path):
    """Fallback: extract results by parsing each line of text (FCAT inline format)."""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ''
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + '\n'

    header_date, header_location, header_event = extract_header_info(full_text)

    seen = set()
    results = []
    current_event = ''

    for line in full_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        detected = detect_event(line)
        if detected:
            current_event = detected
            continue

        if re.search(r'LLOC\s+.*NOM.*CLUB', line, re.IGNORECASE):
            continue

        if not re.search(r'CA\s*TARRAGONA', line, re.IGNORECASE):
            continue
        if re.search(r'CG\s*TARRAGONA', line, re.IGNORECASE):
            continue

        if not current_event:
            continue

        ca_match = re.search(r'(CA\s*TARRAGONA)\s+(.+)$', line, re.IGNORECASE)
        if not ca_match:
            continue

        before_ca = line[:ca_match.start(1)].strip()
        mark = ca_match.group(2).strip()
        mark = re.sub(r'\s+F\s*$', '', mark).strip()

        cl_match = re.search(r'CL\s*(\S+)\s+(.+)', before_ca)
        if cl_match:
            name = cl_match.group(2).strip()
            name = re.sub(r'\s+\d{2,4}\s*$', '', name).strip()
        else:
            name_match = re.search(r'CL\s*\S+\s+(.+?)(?:\s+\d{2,4})?\s*$', before_ca)
            if name_match:
                name = name_match.group(1).strip()
                name = re.sub(r'\s+\d{2,4}\s*$', '', name).strip()
            else:
                continue

        name = clean_athlete_name(name)
        if not is_valid_name(name):
            continue

        performance = parse_performance(current_event, mark)
        if not performance:
            continue

        key = (name.lower(), current_event.lower(), performance)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            'athlete_name': name,
            'discipline': current_event,
            'performance': performance,
        })

    return header_date, header_location, header_event, results


# ── Main ────────────────────────────────────────────────────────────

def extract_catt_from_pdf(pdf_path):
    """Extract CA Tarragona results from a PDF.
    
    Strategy:
    1. Try RFEA multi-line format first (newer PDFs)
    2. Try table-based extraction (FCAT with tables)
    3. Try line-based extraction (FCAT inline)
    """
    # Strategy 1: Try RFEA format
    rfea_results = []
    try:
        header_date, header_location, header_event, rfea_results = extract_rfea_format(pdf_path)
        if rfea_results:
            # Verify: RFEA format should have DD/MM/YYYY in the text
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ''
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + '\n'
                if re.search(r'\d{2}/\d{2}/\d{4}', full_text):
                    return header_date, header_location, header_event, rfea_results
    except Exception:
        pass

    # Strategy 2: Try table-based
    header_date, header_location, header_event, table_results = extract_from_tables(pdf_path)
    if table_results:
        # Check for suspiciously short names (broken table extraction)
        use_lines = False
        for r in table_results:
            name = r['athlete_name']
            words = name.split()
            valid_particles = {'DE', 'DEL', 'DA', 'DI', 'Y', 'VAZ'}
            if any(len(w) <= 3 and w.upper() not in valid_particles for w in words):
                use_lines = True
                break
        if not use_lines:
            return header_date, header_location, header_event, table_results

    # Strategy 3: Line-based fallback
    return extract_from_lines(pdf_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_promocio.py <pdf_file> [output_dir] [pdf_url]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "json"
    pdf_url = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(output_dir, exist_ok=True)

    print(f"Extracting from: {pdf_path}")
    print()

    header_date, header_location, header_event, results = extract_catt_from_pdf(pdf_path)

    if not results:
        print("No CA Tarragona results found. Skipping JSON export.")
        return

    print(f"Found {len(results)} CA Tarragona results:")
    for r in results:
        print(f"  {r['athlete_name']:35s} | {r['discipline']:50s} | {r['performance']}")

    output = {
        'event_name': header_event if header_event else 'CAMPIONAT DE CATALUNYA',
        'event_date': header_date,
        'event_location': header_location,
        'event_src': pdf_url,
        'results': results,
    }

    basename = os.path.basename(pdf_path).replace('.pdf', '')
    output_path = os.path.join(output_dir, f"{basename}.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {output_path}")


if __name__ == '__main__':
    main()
