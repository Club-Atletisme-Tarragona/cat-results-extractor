#!/usr/bin/env python3
"""
Extractora de resultats de MARXA per al Club Atletisme Tarragona (CATT / CA Tarragona).

Suporta PDFs amb format inline per categoria:
  CATEGORIA (ex: 5KM Cadet Masculí)
  Pos Dorsal Atleta Nº Llicència Any Club Marca
  1 356 BASSAS GARRITY, MARIO CT 24491 1 CE Universitari 26'30''

Detecta automàticament:
- Capçaleres de prova (ex: "5KM Cadet Masculí", "3KM Infantil Femení")
- Columnes: Pos, Dorsal, Atleta, Nº Llicència, Any, Club, Marca
- Competició i data del PDF

Per a cada temporada, els PDFs poden tenir lleugeres variacions de format.
Aquest extractor intenta ser el més flexible possible.
"""

import subprocess
import sys
import re
import json
import os


def extract_text(pdf_path):
    """Extract text from PDF using pdftotext with layout preservation."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def extract_text_pypdf2(pdf_path):
    """Fallback: extract text using PyPDF2."""
    import PyPDF2
    full_text = []
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return '\n'.join(full_text)


def get_text(pdf_path):
    """Try pdftotext first, fall back to PyPDF2."""
    try:
        return extract_text(pdf_path)
    except Exception:
        pass
    try:
        return extract_text_pypdf2(pdf_path)
    except Exception as e:
        print(f"Error amb PyPDF2: {e}", file=sys.stderr)
        sys.exit(1)


def parse_header(text):
    """Parse competition header from PDF text."""
    competicio = ""
    data = ""
    lines = text.split('\n')

    # Competition name: first line with "GRAN PREMI" or "Campionat" or "Campeonato" or "Control"
    # Search wider (first 30 lines) since some PDFs have headers at bottom of page
    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        if 'GRAN PREMI' in stripped or 'Gran Premi' in stripped:
            competicio = stripped
            break
        if 'PREMI' in stripped:
            competicio = stripped
            break
        if 'Campionat' in stripped or 'Campeonato' in stripped:
            competicio = stripped
            break
        if 'Control' in stripped and 'sesión' not in stripped.lower() and 'sesion' not in stripped.lower():
            competicio = stripped
            break

    # Date: DD/MM/YYYY or DD.MM.YYYY
    for line in lines[:30]:
        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', line)
        if date_match:
            data = date_match.group(1)
            break
        date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{2,4})', line)
        if date_match:
            d = date_match.group(1).replace('.', '/')
            parts = d.split('/')
            if len(parts) == 3:
                day, month, year = parts
                if len(year) == 2:
                    year = '20' + year
                if len(month) == 1:
                    month = '0' + month
                if len(day) == 1:
                    day = '0' + day
                data = f"{day}/{month}/{year}"
            break

    return competicio, data


# License patterns: CT\d+, CL\d+, CAT-\d+..., IB-\d+...
# Supports both "CT24491" and "CT 24491" (with optional space)
LICENSE_RE = re.compile(r'(?:CT\s*\d+[\-A-Za-z]*|CL\s*\d+[\-A-Za-z]*|CAT\-\d+[A-Za-z\-\.]*|IB\-\d+[A-Za-z\-\.]*)')

# Known club names (for matching "CA Tarragona" and others)
KNOWN_CLUBS = [
    r'CA Tarragona', r'AA Catalunya', r'Barcelona At\.', r'Atletismo Barbastro',
    r'Cornell[àa] Atl[eè]tic', r"L\'Hospitalet At\.", r'UA Barber[àa]', r'UA Terrassa',
    r'CA Igualada', r'CA Viladecans', r'CA Vic', r'CA Gav[àa]', r'CA Mollet',
    r'CA Nou Barris', r'CA Parets', r'CA Sport Canet',
    r'CA Laietania', r'CA Sant Just', r'CA Castellar', r'CA Granollers',
    r'CA Montorn[eè]s', r'CA Torredembarra', r'CA Mas Piera',
    r'CA Olesa', r'CA Palafrugell-GiCB', r'CA Sant Celoni', r'CA Sant Just',
    r'CA Asc[oó]', r'CA Canaletes',
    r'GEiE Giron[íi]',
    r'Muntanyenc S[.]Cugat',
    r'Avinent Manresa', r'UGE Badalona',
    r'CE Universitari',
    r'Runners El Vendrell', r'Atletisme El Perell[oó]',
    r'JA Sabadell',
    r'ISS - L\'Hospitalet',
    r'UA Barber[àa]',
]


def is_catt_club(club_name):
    """Check if club is CA Tarragona."""
    if not club_name:
        return False
    return 'CA TARRAGONA' in club_name.upper()


def extract_athlete_from_line(line):
    """Extract athlete data from a result line.
    
    Format: Pos Dorsal Cognom, Nom CL/CT XXXXX Any Club Marca
    Returns dict with: pos, dorsal, name, license, club, marca
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Skip headers
    if stripped.startswith('Pos') or stripped.startswith('Lloc'):
        return None
    if stripped.startswith('Prova:') or stripped.startswith('Categoria:'):
        return None
    if 'Resultats per Clubs' in stripped:
        return None
    if 'Punts' in stripped and re.search(r'^\d+\s+\S+\s+\d+$', stripped):
        return None

    # Find license pattern
    license_match = LICENSE_RE.search(stripped)
    if not license_match:
        return None

    # Before license: "Pos Dorsal Cognom, Nom CL"
    before_license = stripped[:license_match.start()].strip()
    after_license = stripped[license_match.end():].strip()

    # Parse position and dorsal from before_license
    # Format: "1 356 BASSAS GARRITY, MARIO" or "19 333 SUAREZ PIZA, JULIA"
    pos_dorsal_match = re.match(r'^(\d+)\s+(\d+)\s+(.+)$', before_license)
    if not pos_dorsal_match:
        return None

    pos = int(pos_dorsal_match.group(1))
    dorsal = pos_dorsal_match.group(2).lstrip('0') or '0'
    name = pos_dorsal_match.group(3).strip()

    # After license: "Any Club Marca"
    # Year is a 1-2 digit number, then club name, then marca (time like 26'30'' or 12'41'')
    year_match = re.match(r'^(\d{1,2})\s+(.+)$', after_license)
    if not year_match:
        return None

    rest = year_match.group(2).strip()

    # Marca is the last element: MM's'' or similar time format
    marca_match = re.search(r"(\d+'[\d.]*''?)$", rest)
    if not marca_match:
        # Also try HH:MM:SS or MM:SS formats
        marca_match = re.search(r'(\d+:\d{2}(?::\d{2})?)$', rest)
    
    if marca_match:
        marca = marca_match.group(1)
        club = rest[:marca_match.start()].strip()
    else:
        # No marca found - might be DQ, DNS, DNF, or special values
        tokens = rest.split()
        if tokens:
            last = tokens[-1]
            if last in ('DQ', 'DNS', 'DNF', '---', '-----'):
                club = ' '.join(tokens[:-1]).strip()
                marca = last
            elif last.startswith('DSC'):
                club = ' '.join(tokens[:-1]).strip()
                marca = last
            else:
                club = rest
                marca = ''
        else:
            club = rest
            marca = ''

    return {
        'pos': pos,
        'dorsal': dorsal,
        'name': name,
        'license': license_match.group(0),
        'club': club.strip(),
        'marca': marca.strip(),
    }


def extract_event_from_header(line):
    """Extract event name from a category header line.
    
    Examples:
    - "5KM Cadet Masculí" -> "5KM Cadet Masculí"
    - "3KM Infantil Femení" -> "3KM Infantil Femení"
    - "2KM Aleví Femení" -> "2KM Aleví Femení"
    - "1KM Benjamí Masculí" -> "1KM Benjamí Masculí"
    """
    stripped = line.strip()
    # Match: DISTANCE Category Sex (include sex in the match)
    m = re.match(r'^(\d+(?:\.\d{3})?(?:KM|km|m)\s+(?:Cadet|Infantil|Alev[íi]|Benjam[íi]|Sub14|Sub16|Sub18|Junior|Senior|Absolut)\s+(?:Mascul[íi]|Femen[íi]|Masculi|Femeni|Masculins|Femenins|Hombres|Mujeres))', stripped, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return stripped


def parse_sections(text):
    """Parse the PDF into sections by event category.
    
    Each section has:
    - event_name: the category (e.g., "5KM Cadet Masculí")
    - athletes: list of parsed athlete dicts
    """
    lines = text.split('\n')
    sections = []
    current_section = None

    for line in lines:
        stripped = line.strip()
        
        # Detect section header: "5KM Cadet Masculí", "3KM Infantil Femení", etc.
        if re.match(r'^\d+(?:\.\d{3})?(?:KM|km|m)\s+\w+', stripped, re.IGNORECASE):
            # Check if it looks like a distance + category header
            # Not a result line (which starts with a position number)
            # Headers don't have license patterns
            if LICENSE_RE.search(stripped):
                continue  # This is a result line, not a header
            
            # Check if it has the category keywords
            category_keywords = ['Cadet', 'Infantil', 'Aleví', 'Alevi', 'Benjamí', 'Benjami', 
                                 'Sub14', 'Sub16', 'Sub18', 'Junior', 'Senior', 'Absolut',
                                 'Masculí', 'Femení', 'Masculi', 'Femeni',
                                 'Masculins', 'Femenins', 'Hombres', 'Mujeres']
            
            has_category = any(kw.lower() in stripped.lower() for kw in category_keywords)
            
            if has_category and len(stripped) < 80:
                # This looks like a section header
                if current_section:
                    sections.append(current_section)
                current_section = {
                    'event_name': extract_event_from_header(stripped),
                    'athletes': [],
                }
                continue

        # Parse athlete from line if we're in a section
        if current_section:
            athlete = extract_athlete_from_line(stripped)
            if athlete and athlete['name']:
                current_section['athletes'].append(athlete)

    if current_section:
        sections.append(current_section)

    return sections


def extract_catt_athletes(sections):
    """Extract CA Tarragona athletes from all sections."""
    results = []

    for section in sections:
        event_name = section['event_name']
        for athlete in section['athletes']:
            if not is_catt_club(athlete.get('club', '')):
                continue

            results.append({
                'atleta_nom': athlete['name'].strip(),
                'atleta_licencia': athlete.get('license', ''),
                'prova': event_name,
                'marca': athlete.get('marca', ''),
                'lloc': athlete.get('pos'),
                'dorsal': athlete.get('dorsal', ''),
            })

    return results


def deduplicate_results(results):
    """Deduplicate results - keep best entry per athlete+event."""
    groups = {}
    for r in results:
        key = (r["atleta_nom"].lower(), r["prova"].lower())
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    unique = []
    for key, entries in groups.items():
        if len(entries) == 1:
            unique.append(entries[0])
            continue

        with_result = [e for e in entries if e["marca"] and e["marca"] not in ("DQ", "DNS", "DNF", "")]
        without_result = [e for e in entries if not e["marca"] or e["marca"] in ("DQ", "DNS", "DNF")]

        if with_result:
            with_pos = [e for e in with_result if e["lloc"] is not None]
            if with_pos:
                best = min(with_pos, key=lambda e: e["lloc"])
            else:
                best = with_result[0]
            unique.append(best)
        elif without_result:
            unique.append(without_result[0])

    return unique


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_marxa_inline.py <pdf_file> [source_url]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    source_url = sys.argv[2] if len(sys.argv) > 2 else ""
    base = os.path.splitext(pdf_path)[0]

    # Output to json/ directory if it exists
    json_dir = os.path.join(os.path.dirname(pdf_path) or '.', 'json')
    os.makedirs(json_dir, exist_ok=True)
    output_path = os.path.join(json_dir, os.path.basename(base) + ".json")

    print(f"Extracting text from: {pdf_path}")
    text = get_text(pdf_path)

    lines = text.split('\n')

    print("Parsing competition header...")
    competicio, data = parse_header(text)
    print(f"  Competicio: {competicio or '(no trobat)'}")
    print(f"  Data: {data or '(no trobat)'}")

    print("\nParsing sections...")
    sections = parse_sections(text)
    print(f"  Found {len(sections)} sections")
    for s in sections:
        print(f"    {s['event_name']}: {len(s['athletes'])} athletes")

    print("\nExtracting CA Tarragona athlete results...")
    results = extract_catt_athletes(sections)
    print(f"Found {len(results)} CA Tarragona athlete entries")

    for r in results:
        status = "OK" if r["atleta_nom"] and r["marca"] else ("DNS/DNF" if r["atleta_nom"] and not r["marca"] else "INCOMPLETE")
        print(f"  [{status}] {r['atleta_nom'] or '???':40s} | {r['prova'] or '???':35s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']} | Lic: {r['atleta_licencia']}")

    # Deduplicate
    results = deduplicate_results(results)
    print(f"\nAfter deduplication: {len(results)} unique entries")

    # Build output
    output = {
        'competicio': competicio,
        'data': data,
        'source_url': source_url,
        'results': results,
    }

    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nOutput written to: {output_path}")

    return results


if __name__ == '__main__':
    main()
