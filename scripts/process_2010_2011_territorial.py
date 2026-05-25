#!/usr/bin/env python3
"""
Extractor per a PDFs Territorial Promoció de 2010-2011.

Format tabular universal:
  Lloc Dorsal Nom Cognoms ... Any Club Marca

Exemple:
  60 m.ll. Benjamí Masculí
  1a. Semifinal
    2      436    Hugo Berenguel Torres                  2003   CA Tarragona              11''49

També suporta:
- Curses llargues: 9'10''87
- Distàncies múltiples: 7,86  7,79  7,90  8,17  7,52  7,71  8,17
- Pilota: X  21,84  22,18  22,18
"""

import subprocess
import sys
import os
import json
import re
from typing import Optional


def extract_text(pdf_path: str) -> str:
    result = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout


def parse_header(text: str) -> dict:
    lines = text.split('\n')[:50]
    event_name = ""
    event_date = ""
    event_location = ""
    
    for line in lines:
        line = line.strip()
        if not event_name and ('TERRITORIAL' in line.upper() or 'PROMOCIÓ' in line.upper()):
            event_name = line
        
        date_match = re.search(r'(\d{1,2})[ /\-](\w+)[ /\-](\d{4})', line)
        if date_match:
            months = {
                'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12',
                'ener': '01', 'febr': '02', 'mar': '03', 'abr': '04',
                'jun': '06', 'jul': '07', 'ago': '08', 'set': '09',
                'oct': '10', 'nov': '11', 'dic': '12',
                'gener': '01', 'febrer': '02', 'març': '03', 'abril': '04',
                'maig': '05', 'juny': '06', 'juliol': '07', 'agost': '08',
                'setembre': '09', 'octubre': '10', 'novembre': '11', 'desembre': '12',
            }
            day = date_match.group(1).zfill(2)
            month = months.get(date_match.group(2).lower(), '01')
            event_date = f"{date_match.group(3)}-{month}-{day}"
        
        if 'Valls' in line and not event_location:
            event_location = 'Valls'
    
    return {
        'event_name': event_name or 'Territorial Promoció',
        'event_date': event_date or '',
        'event_location': event_location,
    }


def is_event_line(line: str) -> bool:
    """Check if a line is an event header (not a result line)."""
    line = line.strip()
    if not line:
        return False
    if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', line, re.IGNORECASE):
        return False
    if 'Nom i Cognoms' in line:
        return False
    if 'Organitza' in line or 'FCA' in line or 'Els atletes' in line:
        return False
    if 'Suspesa' in line:
        return False
    
    # Result lines start with: position + dorsal + name
    # They have a number at the start, then another number, then a word (name)
    if re.match(r'^\s*\d+\s+\d+\s+\w', line):
        return False
    
    # Lines with #N/A
    if '#N/A' in line:
        return False
    
    # Lines with just numbers (pole vault heights)
    if re.match(r'^\s*\d+[.,]\d+\s+\d+[.,]\d+', line):
        return False
    
    # Lines with "GENERAL"
    if 'GENERAL' in line.upper():
        return False
    
    # Event lines: contain patterns like "60 m.ll.", "Perxa", "Javelina", "Pilota", etc.
    event_indicators = [
        r'\d+\s*m(?:\.ll\.?|llisos|metres(?:\s+llisos)?)',
        r'\d+\s*m(?:\.marxa\.?|metres\s+marxa)',
        r'Perxa',
        r'Triple\s+\w+',
        r'Javelina',
        r'Pilota',
        r'Llan[cç]ament',
        r'Salt\s+(?:Al[cç]ada|Llargada)',
        r'Relleus',
    ]
    
    for indicator in event_indicators:
        if re.search(indicator, line, re.IGNORECASE):
            return True
    
    return False


def parse_mark(mark_str: str) -> Optional[str]:
    """Parse a single mark value."""
    if not mark_str:
        return None
    
    mark_str = mark_str.strip().rstrip('*').strip()
    if not mark_str or mark_str in ('X', '-', 'NULS', '0', '#N/A', 'DNS', 'DQ', 'n.p.', 'ret'):
        return None
    
    # Format: X'YY"ZZ or X'YY''ZZ (minutes'seconds.centésimes)
    m = re.match(r"(\d+)'(\d{2})[\"']{2}(\d{2})", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X'YY"Z or X'YY''Z
    m = re.match(r"(\d+)'(\d{2})[\"']{2}(\d)", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X''YY
    m = re.match(r"(\d+)''(\d+)", mark_str)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    
    # Format: X.YY or X,YY (distance/height)
    m = re.match(r"(\d+[.,]\d{2})", mark_str)
    if m:
        return m.group(1).replace(',', '.')
    
    return None


def parse_best_mark(mark_str: str) -> Optional[str]:
    """Parse the best mark from multiple attempts."""
    if not mark_str:
        return None
    
    mark_str = mark_str.strip().rstrip('*').strip()
    if not mark_str or mark_str in ('X', '-', 'NULS', '0'):
        return None
    
    # Split by multiple spaces (groups of attempts)
    parts = re.split(r'\s{2,}', mark_str)
    best = None
    for part in parts:
        part = part.strip()
        if not part or part in ('X', '-', 'NULS', '0', '#N/A'):
            continue
        m = re.match(r'(\d+[.,]\d{2})', part)
        if m:
            val = float(m.group(1).replace(',', '.'))
            if val > 0 and (best is None or val > best):
                best = val
    
    if best is not None:
        return f"{best:.2f}"
    
    # Try individual marks
    parts = re.split(r'\s+', mark_str)
    best = None
    for part in parts:
        part = part.strip()
        if not part or part in ('X', '-', 'NULS', '0', '#N/A'):
            continue
        m = re.match(r'(\d+[.,]\d{2})', part)
        if m:
            val = float(m.group(1).replace(',', '.'))
            if val > 0 and (best is None or val > best):
                best = val
    
    if best is not None:
        return f"{best:.2f}"
    
    return None


def extract_athletes(text: str) -> list:
    """Extract CA Tarragona athletes from Territorial Promoció PDF text."""
    lines = text.split('\n')
    results = []
    current_event = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect event headers
        if is_event_line(stripped):
            current_event = stripped
            continue
        
        # Skip section markers, headers, empty lines
        if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', stripped, re.IGNORECASE):
            continue
        if 'Nom i Cognoms' in stripped or ('Lloc' in stripped and 'Dorsal' in stripped):
            continue
        if not stripped or 'Organitza' in stripped or 'FCA' in stripped or '#N/A' in stripped:
            continue
        if 'GENERAL' in stripped.upper() or 'Els atletes' in stripped or 'Suspesa' in stripped:
            continue
        
        # Check if line has CA Tarragona
        if 'CA TARRAGONA' not in stripped.upper():
            continue
        
        # Find CA Tarragona in the line
        ca_match = re.search(r'CA\s*TARRAGONA', stripped, re.IGNORECASE)
        if not ca_match:
            continue
        
        before_ca = stripped[:ca_match.start()].strip()
        after_ca = stripped[ca_match.end():].strip()
        
        # Extract year: the last 4-digit number in before_ca
        year_match = re.search(r'\b(\d{4})\b', before_ca)
        if not year_match:
            continue
        
        # Extract name: everything between leading numbers and the year
        name_part = re.sub(r'\s+\d{4}\s*$', '', before_ca).strip()
        name_part = re.sub(r'^\s*\d+\s+\d+\s*', '', name_part).strip()
        name_part = re.sub(r'\s+', ' ', name_part).strip()
        
        # Validate name
        name_words = name_part.split()
        if len(name_words) < 2 or len(name_part) < 5:
            continue
        
        athlete_name = name_part.upper()
        
        # Parse mark from after_ca
        mark_str = after_ca.strip()
        if not mark_str or mark_str == '-':
            continue
        
        # Detect multi-mark line (field events, combined events)
        if re.search(r'\d+[.,]\d{2}\s+\d+[.,]\d{2}', mark_str):
            mark = parse_best_mark(mark_str)
        else:
            mark = parse_mark(mark_str)
        
        if not mark:
            continue
        
        results.append({
            'athlete_name': athlete_name,
            'discipline': current_event or '',
            'performance': mark,
        })
    
    return results


def reconstruct_url(pdf_path: str) -> str:
    filename = os.path.basename(pdf_path)
    date_match = re.search(r'(\d{2})(\d{2})(\d{2})\.pdf$', filename)
    if date_match:
        dd, mm, yy = date_match.groups()
        year = f"20{yy}" if int(yy) > 50 else f"20{yy}"
        return f"https://old.fcatletisme.cat/Promocio/promocio{year}/resulcnatterritpromovalls{dd}{mm}{yy}.pdf"
    return f"https://old.fcatletisme.cat/Promocio/promocio2011/{filename}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_2010_2011_territorial.py <pdf_path> [json_dir] [url]", file=sys.stderr)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    json_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(pdf_path)
    url = sys.argv[3] if len(sys.argv) > 3 else ''
    
    if not url:
        url = reconstruct_url(pdf_path)
    
    print(f"Processing: {pdf_path}", file=sys.stderr)
    
    text = extract_text(pdf_path)
    header = parse_header(text)
    athletes = extract_athletes(text)
    
    print(f"Found {len(athletes)} CA Tarragona athletes", file=sys.stderr)
    
    output = {
        'event_name': header['event_name'],
        'event_date': header['event_date'],
        'event_location': header['event_location'],
        'event_src': url,
        'results': athletes,
    }
    
    filename = os.path.basename(pdf_path).replace('.pdf', '.json')
    json_path = os.path.join(json_dir, filename)
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"Written: {json_path}", file=sys.stderr)
    
    # Group by discipline for display
    from collections import defaultdict
    by_event = defaultdict(list)
    for r in athletes:
        by_event[r['discipline']].append(r)
    
    for event, event_results in sorted(by_event.items()):
        print(f"\n=== {event} ===")
        for r in event_results:
            print(f"  {r['athlete_name']:40s} | {r['performance']}")


if __name__ == '__main__':
    main()
