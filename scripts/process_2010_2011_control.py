#!/usr/bin/env python3
"""
Extractor per a PDFs de Control (Cadet-Juvenil, CNRP) de 2010-2011.

Dos formats:
1. Control Cadet-Juvenil Calella:
   SERIE   LLOC   MARCA       DORSAL               ATLETA              ANY     LLICÈNCIA            CLUB
   2     9   1'57"84     5   MIREIA MOLNE RIONE                  1997       0         CA TARRAGONA
   (marca al principi, abans del dorsal)

2. Control CNRP:
   clasif.   serie    dorsal              atleta              any      nº llic.        club          marca
    3        1       485      Mireia López Urbano                      00                    CA Tarragona          09"4
   (marca al final, després del club)
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
        if 'CNRP' in line:
            event_location = 'CNRP'
        
        # Date: DD/MM/YYYY or "21 de maig de 2011" or "22-1-2011"
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
    
    return {
        'event_name': event_name or 'Control',
        'event_date': event_date,
        'event_location': event_location,
    }


def detect_event(lines: list, line_idx: int) -> Optional[str]:
    line = lines[line_idx].strip()
    
    if not line:
        return None
    if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', line, re.IGNORECASE):
        return None
    if 'SERIE' in line and 'LLOC' in line and 'MARCA' in line:
        return None
    if 'clasif' in line.lower() and 'dorsal' in line.lower() and 'atleta' in line.lower():
        return None
    if 'PROVA' in line:
        return None
    
    # Event patterns
    event_patterns = [
        r'\d+\s*m\.?\s+llisos?\s+\w+',
        r'\d+\s*m\.?\s+tanques?\s+\w+',
        r'\d+\s*m\.?\s+marxa\s+\w+',
        r'Perxa\s+\w+',
        r'Triple\s+Salt\s+\w+',
        r'Llan[cç]ament\s+\w+',
        r'Salt\s+(?:Al[cç]ada|Llargada)\s+\w+',
        r'\d+\s*m\s+absolut\s+\w+',
        r'\d+\s*m\s+juvenil\s+\w+',
        r'\d+\s*m\s+cadet\s+\w+',
        r'\d+\s*m\s+infantil\s+\w+',
        r'\d+\s*m\s+aleví\s+\w+',
        r'\d+\s*m\s+benjamí\s+\w+',
        r'salt de llargada\s+\w+',
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return line
    
    return None


def parse_mark(mark_str: str) -> Optional[str]:
    if not mark_str:
        return None
    
    mark_str = mark_str.strip().rstrip('*').strip()
    if not mark_str or mark_str in ('X', '-', 'NULS', '0', 'DNS', 'DQ'):
        return None
    
    # Normalize Unicode quotes to ASCII equivalents
    # U+2019 (') -> ' (apostrophe)
    # U+201D (") -> " (double quote)
    mark_str = mark_str.replace('\u2019', "'").replace('\u201d', '"')
    mark_str = mark_str.replace('\u2018', "'").replace('\u201c', '"')
    
    # Format: X'YY"ZZ (minutes'seconds.centésimes) - apostrophe + double-quote
    m = re.match(r"(\d+)'(\d{2})\"(\d{2})", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X'YY"Z
    m = re.match(r"(\d+)'(\d{2})\"(\d)", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X'YY''ZZ (double apostrophe)
    m = re.match(r"(\d+)'(\d{2})'(\d{2})", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X'YY''Z
    m = re.match(r"(\d+)'(\d{2})'(\d)", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X"YY (double quote for seconds)
    m = re.match(r'(\d+)"(\d{2})', mark_str)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    
    # Format: X"Y (single digit centésimes)
    m = re.match(r'(\d+)"(\d)', mark_str)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    
    # Format: X.YY or X,YY (distance/height)
    m = re.match(r"(\d+[.,]\d{2})", mark_str)
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
        if 'SERIE' in stripped and 'LLOC' in stripped and 'MARCA' in stripped:
            continue
        if 'clasif' in stripped.lower() and 'dorsal' in stripped.lower() and 'atleta' in stripped.lower():
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
        
        # Extract name: find all words (letter sequences) before CA TARRAGONA
        # Filter out short codes like CL, CT, CA
        words = re.findall(r'[A-ZÀ-Ú][a-zà-ú]+', before_ca, re.IGNORECASE)
        name_words = [w for w in words if len(w) >= 2 and w.upper() not in ('CL', 'CT', 'CA', 'CG')]
        athlete_name = ' '.join(name_words).upper()
        
        # Validate name
        if not athlete_name or len(athlete_name) < 5:
            continue
        
        # Extract mark: could be at the beginning (Calella format) or at the end (CNRP format)
        mark = None
        
        # Try after_ca first (CNRP format: mark is after club)
        mark_str = after_ca.strip()
        # Remove wind info: "    -0,7" or "    -1,0"
        mark_str = re.sub(r'\s+-?\d+[.,]\d+\s*$', '', mark_str).strip()
        if mark_str:
            mark = parse_mark(mark_str)
        
        # If no mark found after CA, try before CA (Calella format: mark is at the beginning)
        if not mark:
            # Format: "2     9   1'57"84     5   MIREIA MOLNE RIONE                  1997       0"
            # The mark is between the serie/pos and the name
            # Find the first number sequence that looks like a mark (has quotes or decimal)
            # Look for patterns like 1'57"84 or 11"87 or 12.41
            # Normalize Unicode quotes first
            line_normalized = stripped.replace('\u2019', "'").replace('\u201d', '"')
            line_normalized = line_normalized.replace('\u2018', "'").replace('\u201c', '"')
            
            # Try time patterns first (X'YY"ZZ, X'YY"Z)
            time_patterns = re.findall(r"(\d+)'(\d{2})\"(\d{2,3})", line_normalized)
            if time_patterns:
                for tp in time_patterns:
                    mp_clean = f"{tp[0]}'{tp[1]}\"{tp[2]}"
                    if not re.match(r'^\d{4}$', mp_clean):
                        mark = parse_mark(mp_clean)
                        if mark:
                            break
            
            # Try simple time (X"YY)
            if not mark:
                simple_times = re.findall(r'(\d+)"(\d{2})', line_normalized)
                for st in simple_times:
                    mp_clean = f'{st[0]}"{st[1]}'
                    if not re.match(r'^\d{4}$', mp_clean):
                        mark = parse_mark(mp_clean)
                        if mark:
                            break
            
            # Try distance (X.YY)
            if not mark:
                distances = re.findall(r"(\d+[.,]\d{2})", line_normalized)
                for d in distances:
                    mark = parse_mark(d)
                    if mark:
                        break
        
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
        return f"https://old.fcatletisme.cat/Promocio/promocio{year}/{filename}"
    return f"https://old.fcatletisme.cat/Promocio/promocio2011/{filename}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_2010_2011_control.py <pdf_path> [json_dir] [url]", file=sys.stderr)
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
        print(f"  {r['athlete_name']:40s} | {r['discipline'][:35]:35s} | {r['performance']}")


if __name__ == '__main__':
    main()
