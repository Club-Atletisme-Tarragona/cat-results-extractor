#!/usr/bin/env python3
"""
Extractora de resultats de MARXA per al Club Atletisme Tarragona (CATT / CA Tarragona).

Suporta dos formats:
1. PDFs generats per marcha.apprfea.es (RFEA Marcha):
   Dorsal  POS  Nom  Pais  F.Nac  Licència  Club  Marca

2. PDFs amb format de resultats per categoria:
   CATEGORIA: X Sexe: Y DISTANCIA Z metres
   Lloc   Dorsal   Nom i cognoms   Club   Llicència   Temps   Ritme
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


def parse_header_marcha(lines):
    """Parse competition header from marcha PDF."""
    competicio = ""
    data = ""

    # Competition name: first line with "GRAN PREMI" or "Campionat" or "Campeonato" or "Control" or "PREMI"
    for line in lines[:5]:
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

    # Date: DD/MM/YYYY or DD.MM.YYYY or DD/M/YYYY or DD.M.YYYY
    for line in lines[:5]:
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


# License patterns for marcha format
LICENSE_PATTERNS = [
    r'CAT-\d+[A-Za-z\-]*',
    r'CT[\d\-]+',
    r'CL\d+',
    r'IB-\d+[A\-\.]*',
]
LICENSE_RE = re.compile('|'.join(LICENSE_PATTERNS))


def extract_license(text):
    """Extract license from text."""
    text = text.strip()
    for pat in LICENSE_PATTERNS:
        m = re.match(rf'^({pat})\s*$', text)
        if m:
            return m.group(1)
    m = LICENSE_RE.search(text)
    if m:
        return m.group(0)
    return ""


def is_catt_club(club_name):
    """Check if club is CA Tarragona."""
    return 'CA Tarragona' in club_name


def parse_marcha_line(line):
    """
    Parse a single athlete line from marcha PDF.

    Supports two formats:

    Format 1 (RFEA Marcha):
      Dorsal  POS  Name  Pais  F.Nac  License  Club  Marca
      Example:
        128    1    GINA TORRES AUBERNI  ESP  25/8/2007  CAT-3694533-A-N-s  L'Hospitalet At.  48:00

    Format 2 (Resultats per categoria):
      Lloc  Dorsal  Name  Club  License  Time  Pace
      Example:
         14     0092 STELLA             PEREIRA CONTRERA CA Tarragona                       CL7607           0:31:29       6:17
         4      0088 MARTINA            TORRES PRATS          CA Tarragona           CAT-3844273-A-T-s     0:06:45       6:45

    Returns dict with keys: dorsal, pos, name, pais, dob, license, club, marca
    """
    result = {
        'dorsal': '',
        'pos': None,
        'name': '',
        'pais': '',
        'dob': '',
        'license': '',
        'club': '',
        'marca': '',
    }

    stripped = line.strip()
    if not stripped:
        return None

    # Skip "Resultats per Clubs" lines: DORSAL SEXO NOMBRE COGNOMS CLUB LICENCIA CATEGORIA
    # Format: 0092   F      STELLA      PEREIRA CONTRERAS   CA Tarragona         CL7607            Sub-16
    # These lines have dorsal followed by F or M as gender marker
    sex_match = re.match(r'^(\d+)\s+[FM]\s+', stripped)
    if sex_match:
        return None

    # Match: optional dorsal/pos, then name
    # The line starts with spaces, then dorsal (number), then pos/name
    m = re.match(r'^\s*(\d+)\s+(\d+)?\s+(.+)$', stripped)
    if not m:
        return None

    first_num_str = m.group(1)
    second_num_str = m.group(2)
    first_num = int(first_num_str)
    second_num = int(second_num_str) if second_num_str else None

    # In the new format (CATEGORIA/DISTANCIA), the first number is position
    # and the second number (4+ digits) is the dorsal.
    # In the old RFEA format, the first number is dorsal and second is position.
    # Heuristic: if second_num_str has 3+ digits, it's a dorsal (new format)
    if second_num_str and len(second_num_str) >= 3:
        # New format: first=pos, second=dorsal
        result['pos'] = first_num
        result['dorsal'] = second_num_str.lstrip('0') or '0'
    else:
        # Old format: first=dorsal, second=pos (optional)
        result['dorsal'] = first_num_str
        result['pos'] = int(second_num_str) if second_num_str else None

    rest = m.group(3)

    # Try Format 2 first: Name  Club  License  Time  Pace
    # The key pattern: after name comes Club (containing "CA Tarragona" or other known clubs),
    # then License, then Time (MM:SS format)
    #
    # Strategy: find license pattern, then look for time pattern after it
    # Name is everything before the license, club is between name and license

    # Find license pattern in the line
    license_match = LICENSE_RE.search(rest)
    if not license_match:
        # No license found - might be the old RFEA format with DOB
        # Fall back to old parsing
        dob_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', rest)
        if dob_match:
            name_part = rest[:dob_match.start()].strip()
            after_dob = rest[dob_match.end():].strip()
            result['name'] = name_part.rstrip()
            result['name'] = re.sub(r'\s+(ESP|GBR|USA|TUN|FRA|ITA|DEU|PRT|BEL|NLD|IRL|NOR|SWE|DNK|FIN|POL|CZE|HUN|AUT|CHE|GRC|TUR|ISR|MLT|CYP|LUX|SVK|SVN|HRV|BGR|ROU|EST|LVA|LTU|MCO|AND)\s*$', '', result['name']).strip()
            dob_str = dob_match.group(1)
            parts = dob_str.split('/')
            if len(parts) == 3:
                day, month, year = parts
                if len(year) == 2:
                    year = '20' + year
                if len(month) == 1:
                    month = '0' + month
                if len(day) == 1:
                    day = '0' + day
                result['dob'] = f"{day}/{month}/{year}"
            after_license = after_dob
            license_match = LICENSE_RE.search(after_license)
            if license_match:
                result['license'] = license_match.group(0)
                after_license = after_license[license_match.end():].strip()
            # After license: Club  Marca
            after_license_clean = after_license.strip()
            if after_license_clean:
                tokens = after_license_clean.split()
                marca_idx = len(tokens)
                if tokens and re.match(r'^[~>P]+$', tokens[-1]):
                    marca_idx -= 1
                if marca_idx > 0 and re.match(r'^[~>P]+$', tokens[marca_idx - 1]):
                    marca_idx -= 1
                if marca_idx == 0:
                    result['club'] = ' '.join(tokens).strip()
                else:
                    result['marca'] = tokens[marca_idx - 1]
                    result['club'] = ' '.join(tokens[:marca_idx - 1]).strip()
        return result

    # Format 2: License found
    result['license'] = license_match.group(0)
    before_license = rest[:license_match.start()].strip()
    after_license = rest[license_match.end():].strip()

    # Name is everything before the club code
    # Club is typically right before the license
    # Try to extract club from before_license
    # Club patterns: "CA Tarragona", "AA Catalunya", "Barcelona At.", etc.
    # or single club codes: "CA Vic", "UA Barberà", etc.

    # Known club name patterns (longer names)
    known_clubs = [
        r'CA Tarragona', r'AA Catalunya', r'Barcelona At\.', r'Atletismo Barbastro',
        r'Cornellà Atlètic', r'L\'Hospitalet At\.', r'UA Barberà', r'UA Terrassa',
        r'CA Igualada', r'CA Viladecans', r'CA Vic', r'CA Gavà', r'CA Mollet',
        r'CA Nou Barris', r'CA Parets', r'CA Sport Canet', r'CA Terres de Ponent',
        r'CA Laietania', r'CA Sant Just', r'CA Castellar', r'CA Granollers',
        r'CA Terres de Ponent', r'GEiE Gironí', r'GEiE Giron[ía]',
        r'G\.A\. Lluïsos Mataro', r'UA Barber[àa]', r' runners elvendrell',
        r'Lleida UA', r'Martorell AC', r'Muntanyenc S\.Cugat',
        r'Hiru-Herri', r'Avinent Manresa', r'UGE Badalona',
        r'Lô Esport Menorca', r'Avinent Manresa', r'CE Universitari',
        r'Barcelona At\.', r'G\.A\. Lluïsos Mataro',
        r'BCNB', r'UABB', r'UA Barbera', r'UA Terrassa',
    ]

    # Try to find club name in before_license (text between name and license)
    club_found = None
    club_pattern_match = None

    # Search for known club names in reverse order (longest match first)
    for club in known_clubs:
        cm = re.search(club, before_license, re.IGNORECASE)
        if cm:
            club_found = cm.group(0)
            club_pattern_match = cm
            break

    if club_found:
        # Name is everything before the club
        name_part = before_license[:club_pattern_match.start()].strip()
        # Normalize multiple spaces in name
        result['name'] = re.sub(r'\s+', ' ', name_part).strip()
        result['club'] = club_found
    else:
        # RFEA format: club may be AFTER the license (Name  Country  DOB  License  Club  Marca)
        # Search for known club names in after_license
        club_found_after = None
        club_pattern_match_after = None
        for club in known_clubs:
            cm = re.search(club, after_license, re.IGNORECASE)
            if cm:
                club_found_after = cm.group(0)
                club_pattern_match_after = cm
                break
        
        if club_found_after:
            # Name is everything before the license (clean up country codes and DOBs)
            name_part = before_license
            # Strip DOB first (it comes after country code), then country code
            name_part = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}\s*$', '', name_part).strip()
            name_part = re.sub(r'\s+(ESP|GBR|USA|TUN|FRA|ITA|DEU|PRT|BEL|NLD|IRL|NOR|SWE|DNK|FIN|POL|CZE|HUN|AUT|CHE|GRC|TUR|ISR|MLT|CYP|LUX|SVK|SVN|HRV|BGR|ROU|EST|LVA|LTU|MCO|AND)\s*$', '', name_part).strip()
            result['name'] = re.sub(r'\s+', ' ', name_part).strip()
            result['club'] = club_found_after
        else:
            # No known club found - name is the entire before_license
            name_part = before_license
            # Strip DOB first, then country code
            name_part = re.sub(r'\s+\d{1,2}/\d{1,2}/\d{2,4}\s*$', '', name_part).strip()
            name_part = re.sub(r'\s+(ESP|GBR|USA|TUN|FRA|ITA|DEU|PRT|BEL|NLD|IRL|NOR|SWE|DNK|FIN|POL|CZE|HUN|AUT|CHE|GRC|TUR|ISR|MLT|CYP|LUX|SVK|SVN|HRV|BGR|ROU|EST|LVA|LTU|MCO|AND)\s*$', '', name_part).strip()
            result['name'] = re.sub(r'\s+', ' ', name_part).strip()

    # After license: Club  Time  (RFEA format: Club before time)
    # Time pattern: MM:SS or HH:MM:SS
    time_match = re.search(r'(\d+:\d{2}(?::\d{2})?)', after_license)
    if time_match:
        result['marca'] = time_match.group(1)
    else:
        # Check for DNS, DNF, DQ, or special values
        after_clean = after_license.strip()
        if after_clean:
            # Check if it's a special value
            if re.match(r'^D(N|Q|NF)', after_clean, re.IGNORECASE):
                result['marca'] = after_clean.split()[0]
            elif re.match(r'^\d{4}DQ', after_clean):
                result['marca'] = 'DQ'
            elif '-------' in after_clean:
                result['marca'] = 'DQ'
            elif re.match(r'^[0-9]+:[0-9]+:[0-9]+', after_clean):
                result['marca'] = after_clean.split()[0]

    return result


def is_section_header(line):
    """Check if line is a section header.

    Supports two formats:
    1. Old RFEA format: "Dorsal   POS" + "Marcha" in event name
    2. New format: "CATEGORIA:" + "DISTANCIA" on same line
    """
    stripped = line.strip()
    if not stripped:
        return False

    # New format: CATEGORIA: ... DISTANCIA ...
    if 'CATEGORIA:' in stripped and 'DISTANCIA' in stripped:
        return True

    # Old RFEA format: "Dorsal   POS" + "Marcha"
    if re.match(r'^Dorsal\s+POS', stripped):
        if 'Marcha' in stripped:
            return True

    return False


def extract_event_name(header_line):
    """Extract event name from section header line.

    Supports two formats:
    1. Old RFEA: "Dorsal   POS   10km Marcha FEM. RUTA   Pais ..."
    2. New: "CATEGORIA: Sub-23 Sexe: F DISTANCIA 10.000 metres"
    """
    stripped = header_line.strip()

    # New format: CATEGORIA: X Sexe: Y DISTANCIA Z metres
    if 'CATEGORIA:' in stripped and 'DISTANCIA' in stripped:
        m = re.match(r'.*?CATEGORIA:\s*(.+?)\s+Sexe:\s*([FM])\s+DISTANCIA\s+(\S+)\s+metres', stripped)
        if m:
            cat = m.group(1).strip()
            sexe = m.group(2)
            distancia = m.group(3).strip()
            # Convert distance: "10.000" -> "10000m", "5.000" -> "5000m", etc.
            distancia_clean = distancia.replace('.', '')
            event = f"{distancia_clean}m {cat}"
            if sexe == 'F':
                event = f"{event} Femení"
            else:
                event = f"{event} Masculí"
            return event

    # Old RFEA format: "Dorsal   POS   10km Marcha FEM. RUTA   Pais ..."
    m = re.match(r'^Dorsal\s+POS\s+(.+?)(?:\s+Pais\s+|$)', stripped)
    if m:
        return m.group(1).strip()
    return stripped


def parse_marcha_sections(text):
    """
    Parse all marcha sections from the text.

    Returns list of sections, each with:
      - event_name: the event name (e.g., "10km Marcha FEM. RUTA")
      - athletes: list of parsed athlete dicts
    """
    lines = text.split('\n')
    sections = []
    current_section = None

    for line in lines:
        if is_section_header(line):
            if current_section:
                sections.append(current_section)
            current_section = {
                'event_name': extract_event_name(line),
                'athletes': [],
            }
        elif current_section:
            parsed = parse_marcha_line(line)
            if parsed and parsed['name']:
                current_section['athletes'].append(parsed)

    if current_section:
        sections.append(current_section)

    return sections


def extract_catt_athletes(sections):
    """Extract CATT athletes from all sections."""
    results = []

    for section in sections:
        event_name = section['event_name']
        for athlete in section['athletes']:
            club = athlete.get('club', '').strip()
            if not is_catt_club(club):
                continue

            results.append({
                'atleta_nom': athlete['name'].strip(),
                'atleta_naixement': athlete.get('dob', ''),
                'atleta_licencia': athlete.get('license', ''),
                'prova': event_name,
                'marca': athlete.get('marca', ''),
                'lloc': athlete.get('pos'),
                'vent': None,
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
            entry = entries[0]
            unique.append(entry)
            continue

        with_result = [e for e in entries if e["marca"] and e["marca"] not in ("DQ", "DNS", "DNF", "")]
        without_result = [e for e in entries if not e["marca"] or e["marca"] in ("DQ", "DNS", "DNF")]

        if with_result:
            # Keep best position
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
        print("Usage: python3 extract_marcha.py <pdf_file>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    source_url = sys.argv[2] if len(sys.argv) > 2 else ""
    base = os.path.splitext(pdf_path)[0]

    # Output to json/ directory if it exists
    json_dir = os.path.join(os.path.dirname(pdf_path) or '.', 'json')
    os.makedirs(json_dir, exist_ok=True)
    output_path = os.path.join(json_dir, os.path.basename(base) + ".json")

    print(f"Extracting text from: {pdf_path}")
    text = extract_text(pdf_path)

    lines = text.split('\n')

    print("Parsing competition header...")
    competicio, data = parse_header_marcha(lines)
    full_competicio = competicio
    print(f"  Competicio: {competicio or '(no trobat)'}")
    print(f"  Data: {data or '(no trobat)'}")

    print("\nParsing marcha sections...")
    sections = parse_marcha_sections(text)
    print(f"  Found {len(sections)} sections")
    for s in sections:
        print(f"    {s['event_name']}: {len(s['athletes'])} athletes")

    print("\nExtracting CATT athlete results...")
    results = extract_catt_athletes(sections)
    print(f"Found {len(results)} CATT athlete entries")

    for r in results:
        status = "OK" if r["atleta_nom"] and r["marca"] else ("DNS/DNF" if r["atleta_nom"] and not r["marca"] else "INCOMPLETE")
        print(f"  [{status}] {r['atleta_nom'] or '???':40s} | {r['prova'] or '???':35s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']} | Lic: {r['atleta_licencia']}")

    results = deduplicate_results(results)
    print(f"\nAfter deduplication: {len(results)} unique results")

    # Filter out DNS/DQ/DNF entries from final output
    results = [r for r in results if r.get("marca", "") and r["marca"] not in ("DQ", "DNS", "DNF")]
    print(f"After filtering DNS/DQ/DNF: {len(results)} valid results")

    # Validate results
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

    if not results:
        print("No results found. Skipping JSON export.")
        return

    output = {
        "event_name": full_competicio,
        "event_date": data,
        "event_location": "",
        "total_results": len(results),
        "event_src": source_url if source_url else os.path.abspath(pdf_path),
        "results": []
    }

    for r in results:
        entry = {
            "athlete_name": r["atleta_nom"],
            "athlete_dob": r["atleta_naixement"],
            "athlete_id": r["atleta_licencia"],
            "performance": r["marca"],
            "discipline": r["prova"],
            "wind": r["vent"],
        }
        output["results"].append(entry)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {output_path}")

    events = {}
    for r in results:
        if r["prova"] not in events:
            events[r["prova"]] = []
        events[r["prova"]].append(r["atleta_nom"])

    print("\nResum per prova:")
    for prova, atletes in sorted(events.items()):
        print(f"  {prova}: {len(atletes)} atletes")


if __name__ == "__main__":
    main()
