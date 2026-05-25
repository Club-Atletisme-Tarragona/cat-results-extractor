#!/usr/bin/env python3
"""
Extractor per a PDFs de relleus de 2010-2011.

Format:
  LLOC   CARRER DORSAL NOMS                                                       CLUB                           MARCA
    4       7    362   E. JOSE-J. GONZALEZ-A. LAGO-N. PINYOL                      CA TARRAGONA                    39,76

Els noms dels relleus estan separats per guions: E. JOSE-J. GONZALEZ-A. LAGO-N. PINYOL
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
    lines = text.split('\n')[:30]
    event_name = ""
    event_date = ""
    event_location = ""
    
    for line in lines:
        line = line.strip()
        if 'JORNADA' in line and 'CONTROL' in line:
            event_name = line
        if 'CALELLA' in line:
            event_location = 'Calella'
        
        date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', line, re.IGNORECASE)
        if date_match:
            months = {
                'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12',
                'gener': '01', 'febrer': '02', 'març': '03', 'abril': '04',
                'maig': '05', 'juny': '06', 'juliol': '07', 'agost': '08',
                'setembre': '09', 'octubre': '10', 'novembre': '11', 'desembre': '12',
            }
            day = date_match.group(1).zfill(2)
            month = months.get(date_match.group(2).lower(), '01')
            event_date = f"{date_match.group(3)}-{month}-{day}"
    
    return {
        'event_name': event_name or 'Control Relleus',
        'event_date': event_date,
        'event_location': event_location,
    }


def detect_event(lines: list, line_idx: int) -> Optional[str]:
    line = lines[line_idx].strip()
    
    # Skip section markers, headers, empty lines
    if not line:
        return None
    if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', line, re.IGNORECASE):
        return None
    if 'LLOC' in line and 'CARRER' in line and 'DORSAL' in line:
        return None
    
    # Event patterns for relleus
    event_patterns = [
        r'(?:4\s*x\s*\d+\s*m(?:metres)?)',
        r'(?:Relleus?\s+\d+x\d+)',
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return line
    
    return None


def parse_mark(mark_str: str) -> Optional[str]:
    if not mark_str:
        return None
    
    mark_str = mark_str.strip().rstrip('*').strip()
    if not mark_str or mark_str in ('X', '-', 'NULS', '0', 'F', 'f'):
        return None
    
    # Format: X.YY (time for relleus)
    m = re.match(r'(\d+[.,]\d{2})', mark_str)
    if m:
        return m.group(1).replace(',', '.')
    
    return None


def extract_athletes(text: str) -> list:
    lines = text.split('\n')
    results = []
    current_event = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect event headers
        event = detect_event(lines, i)
        if event:
            current_event = event
            continue
        
        # Skip section markers, headers, empty lines
        if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', stripped, re.IGNORECASE):
            continue
        if 'LLOC' in stripped and 'CARRER' in stripped and 'DORSAL' in stripped:
            continue
        if not stripped or 'Organitza' in stripped:
            continue
        
        # Check if line has CA TARRAGONA
        if 'CA TARRAGONA' not in stripped.upper():
            continue
        
        # Find CA TARRAGONA in the line
        ca_match = re.search(r'CA\s*TARRAGONA', stripped, re.IGNORECASE)
        if not ca_match:
            continue
        
        before_ca = stripped[:ca_match.start()].strip()
        after_ca = stripped[ca_match.end():].strip()
        
        # Extract name: everything between position/dorsal and CA TARRAGONA
        # Remove leading position and dorsal numbers
        name_part = re.sub(r'^\s*\d+\s+\d+\s+\d+\s*', '', before_ca).strip()
        # Remove trailing numbers (could be wind info)
        name_part = re.sub(r'\s+\d+\s*$', '', name_part).strip()
        name_part = re.sub(r'\s+', ' ', name_part).strip()
        
        # Validate name (relays have hyphenated names)
        if not name_part or len(name_part) < 5:
            continue
        
        # Parse mark from after_ca
        mark_str = after_ca.strip()
        if not mark_str or mark_str in ('F', 'f'):
            continue
        
        mark = parse_mark(mark_str)
        if not mark:
            continue
        
        results.append({
            'athlete_name': name_part.upper(),
            'discipline': current_event or '4x60m Relleus',
            'performance': mark,
        })
    
    return results


def reconstruct_url(pdf_path: str) -> str:
    filename = os.path.basename(pdf_path)
    date_match = re.search(r'(\d{2})(\d{2})(\d{2})\.pdf$', filename)
    if date_match:
        dd, mm, yy = date_match.groups()
        year = f"20{yy}" if int(yy) > 50 else f"20{yy}"
        return f"https://old.fcatletisme.cat/Promocio/promocio{year}/{filename}"
    return f"https://old.fcatletisme.cat/Promocio/promocio2011/{filename}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_2010_2011_releus.py <pdf_path> [json_dir] [url]", file=sys.stderr)
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
    
    for r in athletes:
        print(f"  {r['athlete_name']:50s} | {r['discipline'][:30]:30s} | {r['performance']}")


if __name__ == '__main__':
    main()
