#!/usr/bin/env python3
"""
Extractor per a PDFs de 2008-2009 (format tabular amb COGNOMS, NOM).

Format:
  Sèrie   Lloc   Carrer   Dorsal   Llicència   Nom i cognoms                   Any       Club                              Marca
  1       1       5      472      CT 18015 SANZ FEBRERO, CRISTINA          06/11/1978 FC BARCELONA                         7,89

  LLOC   DORSAL    LLIC.    NOM                                   ANY       CLUB                       1      2       3     4      5      6    MARCA
  1       45     CT2190    TIRADO CHAVES, IVAN                31/08/1977   FC BARCELONA             49,16 50,54 52,32 52,15 51,08        x    52,32

El nom està en format: COGNOM1 COGNOM2, NOM (o COGNOM1 COGNOM2 , NOM amb espai abans de la coma)
El club és CA TARRAGONA o C.A. TARRAGONA

Les marques poden ser:
- Temps curts: 7,89 / 7.89
- Temps llargs: 1'57"84 (amb quotes Unicode)
- Distàncies: 42,93
- Múltiples intents: x x x x x 42,93
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
    lines = text.split('\n')
    competicio = ""
    ubicacio = ""
    localitat = ""
    data = ""
    
    for line in lines[:30]:
        stripped = line.strip()
        
        # Competition name: "Control Pista Coberta", "Campionat de Llançaments", etc.
        if not competicio:
            if 'Campionat' in stripped or 'CAMPIONAT' in stripped:
                competicio = stripped
            elif 'Control' in stripped and 'Jornada' not in stripped:
                competicio = stripped
            elif 'Trofeu' in stripped or 'TROFEU' in stripped:
                competicio = stripped
            elif 'Meeting' in stripped or 'MEETING' in stripped:
                competicio = stripped
        
        # Location: "Vilafranca del Penedès", "Cambrils", etc.
        if not localitat:
            date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', stripped, re.IGNORECASE)
            if date_match:
                localitat_match = re.search(r'(?:a|de|al|dels?)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[a-zà-ú]+)*)', stripped)
                if localitat_match:
                    localitat = localitat_match.group(1).strip()
        
        # Date
        if not data:
            date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', stripped, re.IGNORECASE)
            if date_match:
                months = {
                    'gener': '01', 'febrer': '02', 'març': '03', 'abril': '04',
                    'maig': '05', 'juny': '06', 'juliol': '07', 'agost': '08',
                    'setembre': '09', 'octubre': '10', 'novembre': '11', 'desembre': '12',
                    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                    'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12',
                }
                day = date_match.group(1).zfill(2)
                month = months.get(date_match.group(2).lower(), '01')
                data = f"{date_match.group(3)}-{month}-{day}"
    
    # Fallback: extract location from date line if not found
    if not localitat:
        for line in lines[:30]:
            date_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', line.strip(), re.IGNORECASE)
            if date_match:
                loc_match = re.search(r'(?:a|de|al|dels?)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[a-zà-ú]+)*)', line.strip())
                if loc_match:
                    localitat = loc_match.group(1).strip()
    
    return {
        'event_name': competicio or 'Control',
        'event_date': data,
        'event_location': localitat,
    }


def detect_event(lines: list, line_idx: int) -> Optional[str]:
    line = lines[line_idx].strip()
    
    if not line:
        return None
    if re.match(r'^\d+a\.\s+(?:Semifinal|Final|Sèrie)', line, re.IGNORECASE):
        return None
    if re.match(r'^\d+\.\s+(?:Semifinal|Final|Sèrie)', line, re.IGNORECASE):
        return None
    if 'LLOC' in line and 'DORSAL' in line and ('LLIC' in line or 'LLICÈNCIA' in line):
        return None
    if 'Sèrie' in line and 'Lloc' in line and 'Dorsal' in line:
        return None
    
    # Event patterns
    event_patterns = [
        r'\d+\s*m(?:etres)?\.?\s+llisos?\s+\w+',
        r'\d+\s*m(?:etres)?\.?\s+tanques?\s+\w+',
        r'\d+\s*m(?:etres)?\.?\s+marxa\s+\w+',
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
        r'\d+\s*m\s+promesa\s+\w+',
        r'\d+\s*m\s+junior\s+\w+',
        r'PROVA\s+DECATLÓ\s+\w+',
        r'PROVA\s+HEPTATLÓ\s+\w+',
        r'60 METRES\s+\w+',
        r'100 METRES\s+\w+',
        r'200 METRES\s+\w+',
        r'400 METRES\s+\w+',
        r'800 METRES\s+\w+',
        r'1500 METRES\s+\w+',
        r'3000 METRES\s+\w+',
        r'110 TANQUES\s+\w+',
        r'LLARGADA\s+\w+',
        r'ALÇADA\s+\w+',
        r'PES\s+\w+',
        r'DISC\s+\w+',
        r'JAVELINA\s+\w+',
        r'MARTILL\s+\w+',
    ]
    
    for pattern in event_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return line
    
    return None


def parse_mark(mark_str: str) -> Optional[str]:
    if not mark_str:
        return None
    
    mark_str = mark_str.strip().rstrip('*').strip()
    if not mark_str or mark_str in ('X', '-', 'NULS', '0', 'DNS', 'DQ', 'x', 'X', 'xxx', 'x0'):
        return None
    
    # Normalize Unicode quotes
    mark_str = mark_str.replace('\u2019', "'").replace('\u201d', '"')
    mark_str = mark_str.replace('\u2018', "'").replace('\u201c', '"')
    
    # Format: X'YY"ZZ (minutes'seconds.centésimes)
    m = re.match(r"(\d+)'(\d{2})\"(\d{2})", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    m = re.match(r"(\d+)'(\d{2})\"(\d)", mark_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    
    # Format: X"YY or X"Y
    m = re.match(r'(\d+)"(\d{2})', mark_str)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
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
        if re.match(r'^\d+\.\s+(?:Semifinal|Final|Sèrie)', stripped, re.IGNORECASE):
            continue
        if 'LLOC' in stripped and 'DORSAL' in stripped and ('LLIC' in stripped or 'LLICÈNCIA' in stripped):
            continue
        if 'Sèrie' in stripped and 'Lloc' in stripped and 'Dorsal' in stripped:
            continue
        if not stripped or 'Organitza' in stripped:
            continue
        
        # Check if line has CA TARRAGONA
        if 'CA TARRAGONA' not in stripped.upper():
            continue
        
        # Find CA TARRAGONA in the line
        ca_match = re.search(r'CA\s*(?:\.)?\s*TARRAGONA', stripped, re.IGNORECASE)
        if not ca_match:
            continue
        
        before_ca = stripped[:ca_match.start()].strip()
        after_ca = stripped[ca_match.end():].strip()
        
        # Extract name: find all words (letter sequences) before CA TARRAGONA
        # Filter out short codes like CT, CL, CS
        words = re.findall(r'[A-ZÀ-Ú][a-zà-ú]+', before_ca, re.IGNORECASE)
        name_words = [w for w in words if len(w) >= 2 and w.upper() not in ('CT', 'CL', 'CS', 'CA', 'CG')]
        athlete_name = ' '.join(name_words).upper()
        
        # Validate name
        if not athlete_name or len(athlete_name) < 5:
            continue
        
        # Parse mark from after_ca
        mark_str = after_ca.strip()
        # Remove wind info
        mark_str = re.sub(r'\s+-?\d+[.,]\d+\s*$', '', mark_str).strip()
        
        if not mark_str:
            # Try to find mark before CA (some formats have it before)
            # Look for the last numeric mark-like value in before_ca
            # Format: "... 27/07/1985 CA TARRAGONA" — no mark, skip
            continue
        
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
        # Determine directory from path
        if 'Pairelliure' in pdf_path:
            return f"https://old.fcatletisme.cat/Pairelliure/pairelliure{year}/{filename}"
        elif 'Pcoberta' in pdf_path:
            return f"https://old.fcatletisme.cat/Pcoberta/pcoberta{year}/{filename}"
    return f"https://old.fcatletisme.cat/Pairelliure/pairelliure2009/{filename}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_2008_2009.py <pdf_path> [json_dir] [url]", file=sys.stderr)
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
        print(f"  {r['athlete_name']:45s} | {r['discipline'][:35]:35s} | {r['performance']}")


if __name__ == '__main__':
    main()
