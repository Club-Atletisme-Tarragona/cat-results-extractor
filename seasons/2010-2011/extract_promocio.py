#!/usr/bin/env python3
"""
Extract CATT results from old FCAT Promoció PDFs.

Uses pdfplumber to extract text, then parses it to find CA Tarragona athletes.
Tries table extraction first, falls back to line-by-line parsing.
"""
import sys
import os
import re
import json
import pdfplumber


def is_race_event(event):
    return any(kw in event.upper() for kw in ['METRES LLISOS', 'METRES TANQUES', 'METRES VALLS'])

def is_marcha_event(event):
    return 'MARXA' in event.upper()

def is_jump_event(event):
    return any(kw in event.upper() for kw in ['LLARGADA', 'TRIPLE', 'PÈRTIGA', 'PERTIGA', 'PERXA'])

def is_height_event(event):
    return "SALT D'ALÇADA" in event.upper() or "SALT D'ALTADA" in event.upper() or "ALTURA" in event.upper()

def is_throw_event(event):
    return any(kw in event.upper() for kw in ['LLANÇAMENT', 'LLANAMENT', 'DISC', 'PES', 'MART', 'JAVELINA', 'DARD'])


def parse_performance(event, mark_str):
    if not mark_str:
        return ''

    event_upper = event.upper()

    if is_marcha_event(event):
        m = re.search(r'(\d{1,2}:\d{2}\.\d{2})', mark_str)
        if m: return m.group(1)
        m = re.search(r"(\d{1,2})'(\d{2})''(\d)", mark_str)
        if m: return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
        parts = mark_str.split(',')
        if len(parts) == 3:
            try:
                if 1 <= int(parts[0]) <= 59:
                    return f"{parts[0]}:{parts[1]}.{parts[2]}"
            except ValueError:
                pass
        return ''

    if is_race_event(event):
        m = re.search(r'(\d{1,2}:\d{2}\.\d{2})', mark_str)
        if m: return m.group(1)
        m = re.search(r"(\d{1,2})'(\d{2})''(\d)", mark_str)
        if m: return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
        parts = mark_str.split(',')
        if len(parts) == 3:
            try:
                if 1 <= int(parts[0]) <= 59:
                    return f"{parts[0]}:{parts[1]}.{parts[2]}"
            except ValueError:
                pass
        for nm in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', mark_str):
            val = float(nm.group(1))
            if 5.0 <= val <= 60.0:
                return nm.group(1)
        return ''

    if is_jump_event(event):
        # Jumps use comma as decimal: 3,40 or space-separated: 3,40 3,57 3,08
        for nm in re.finditer(r'(\d+[,.]\d{2})', mark_str):
            val = float(nm.group(1).replace(',', '.'))
            if 1.5 <= val <= 20.0:
                return nm.group(1).replace(',', '.')
        return ''

    if is_height_event(event):
        # Height uses comma as decimal: 0,90 or 1,06
        m = re.search(r'(\d+[,.]\d{2})', mark_str)
        if m:
            val = float(m.group(1).replace(',', '.'))
            if 0.5 <= val <= 7.0:
                return m.group(1).replace(',', '.')
        return ''

    if is_throw_event(event):
        # Throws use space-separated marks: 17,63 17,68 17,43 17,68
        # Also handle comma-separated: 3,40,60
        # Extract all X,XX or X.XX values
        for nm in re.finditer(r'(\d+[,.]\d{2})', mark_str):
            val = float(nm.group(1).replace(',', '.'))
            if 3.0 <= val <= 80.0:
                return nm.group(1).replace(',', '.')
        return ''

    for nm in re.finditer(r'(?<![\d.])(\d+\.\d{2})(?![\d.])', mark_str):
        val = float(nm.group(1))
        if 5.0 <= val <= 60.0:
            return nm.group(1)
    return ''


def clean_athlete_name(name):
    name = name.strip()
    comma_match = re.match(r'(.+),\s*(.+)', name)
    if comma_match:
        last, first = comma_match.groups()
        name = f"{first} {last}"
    name = re.sub(r'\s+F\s*$', '', name).strip()
    return name.strip()


def is_valid_name(name):
    if not name or len(name.strip()) < 5:
        return False
    words = name.strip().split()
    if len(words) < 2:
        return False
    if len(words) > 4:
        return False
    valid_particles = {'DE', 'DEL', 'DA', 'DI', 'DOS', 'DAS', 'Y', 'E', 'VAZ', 'VON', 'VAN', 'DEN', 'DER', 'TER', 'LA', 'LE', 'LOS', 'LAS', 'EL', 'AL'}
    for word in words[1:]:
        w = word.upper()
        if len(word) <= 2 and w not in valid_particles:
            return False
    return True


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


def detect_event(line):
    """Detect event name from a line of text. Returns event string or None."""
    line = line.strip()
    if not line:
        return None

    # METRES LLISOS/TANQUES/VALLS with optional category and gender
    m = re.search(r'(\d+\s+)?METRES\s+(LLISOS|TANQUES|VALLS)\s+(BENJAMÍ|INFANTIL|JÚNIOR|SÈNIOR)?\s*(MASCULÍ|FEMENÍ)?', line, re.IGNORECASE)
    if m:
        # Reconstruct clean event name
        parts = [m.group(1).strip() if m.group(1) else '', 'METRES', m.group(2)]
        if m.group(3):
            parts.append(m.group(3))
        if m.group(4):
            parts.append(m.group(4))
        return ' '.join(p for p in parts if p)

    # LLANÇAMENT DE XXX
    m = re.search(r'(LLANÇAMENT|LLANAMENT)\s+DE\s+(\w+)', line, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} DE {m.group(2).upper()}"

    # SALT D'XXX
    m = re.search(r'SALT\s+D\'(\w+)', line, re.IGNORECASE)
    if m:
        return f"SALT D'{m.group(1).upper()}"

    # MARXA
    if 'MARXA' in line.upper():
        return line

    return None


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

                # Find header row
                header_row = None
                for row in table:
                    if row and any('NOM' in str(cell) for cell in row if cell):
                        header_row = row
                        break

                if not header_row:
                    continue

                # Build column index map
                col_map = {}
                for i, cell in enumerate(header_row):
                    if cell:
                        c = str(cell).strip().upper()
                        if 'NOM' in c:
                            col_map['name'] = i
                        elif 'CLUB' in c:
                            col_map['club'] = i
                        elif 'MARCA' in c:
                            col_map['mark'] = i

                name_col = col_map.get('name')
                club_col = col_map.get('club')
                mark_col = col_map.get('mark')

                if name_col is None or club_col is None or mark_col is None:
                    continue

                # Extract event from page text
                page_text = page.extract_text() or ''
                event = ''
                for line in page_text.split('\n'):
                    detected = detect_event(line)
                    if detected:
                        event = detected

                if not event:
                    continue

                # Process data rows
                for row in table[1:]:
                    if not row:
                        continue

                    name = str(row[name_col]).strip() if name_col < len(row) else ''
                    club = str(row[club_col]).strip() if club_col < len(row) else ''
                    mark = str(row[mark_col]).strip() if mark_col < len(row) else ''

                    if not re.search(r'CA\s*TARRAGONA', club, re.IGNORECASE):
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


def extract_from_lines(pdf_path):
    """Fallback: extract results by parsing each line of text."""
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

        # Detect event
        detected = detect_event(line)
        if detected:
            current_event = detected
            continue

        # Skip header lines
        if re.search(r'LLOC\s+.*NOM.*CLUB', line, re.IGNORECASE):
            continue

        # Check for CA Tarragona
        if not re.search(r'CA\s*TARRAGONA', line, re.IGNORECASE):
            continue

        if not current_event:
            continue

        # Extract name and mark
        ca_match = re.search(r'(CA\s*TARRAGONA)\s+(.+)$', line, re.IGNORECASE)
        if not ca_match:
            continue

        before_ca = line[:ca_match.start(1)].strip()
        mark = ca_match.group(2).strip()
        # Remove trailing 'F' (final indicator) from mark
        mark = re.sub(r'\s+F\s*$', '', mark).strip()

        # Extract name from before_ca
        cl_match = re.search(r'CL\s*(\S+)\s+(.+)', before_ca)
        if cl_match:
            name = cl_match.group(2).strip()
            # Remove birth year (2-4 digit number at end)
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


def extract_catt_from_pdf(pdf_path):
    """Extract CA Tarragona results from a PDF.
    
    Tries table-based extraction first, falls back to line-based parsing.
    If table-based finds results with suspiciously short names (likely broken),
    uses line-based extraction instead.
    """
    # Try table-based first
    header_date, header_location, header_event, table_results = extract_from_tables(pdf_path)

    # If table results have suspiciously short names, use line-based fallback
    use_line_based = False
    if table_results:
        for r in table_results:
            name = r['athlete_name']
            words = name.split()
            valid_particles = {'DE', 'DEL', 'DA', 'DI', 'Y', 'VAZ'}
            if any(len(w) <= 3 and w.upper() not in valid_particles for w in words):
                use_line_based = True
                break

    if use_line_based:
        header_date, header_location, header_event, results = extract_from_lines(pdf_path)
    else:
        results = table_results

    return header_date, header_location, header_event, results


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
