#!/usr/bin/env python3
"""
Extract CATT results from old FCAT Promoció PDFs (2009-2010 era).

Uses the CA Tarragona needle-in-haystack approach: decompress FlateDecode
streams, search for "CA TARRAGONA" in every TJ block, extract name and marks.

Mark parsing follows extract_catt.py conventions:
- Marcha: HH:MM:SS > HH:MM.ss > HH:MM > min,seg[,centesimes] > min'seg''cent
- Curses: HH:MM:SS > HH:MM.ss > HH:MM > min'seg''cent > decimal seconds (5-60s)
- Height: best of valid attempts (1.0-7.0m), dot decimal separator
- Jump: best of valid attempts (1.5-20.0m), dot decimal separator
- Field: best of valid attempts (3.0-80.0m), dot decimal separator
"""

import sys
import re
import json
import os
import zlib


def decompress_streams(pdf_path):
    """Decompress all content streams from a PDF (both FlateDecode and /Contents).
    
    PDFs from 2008-2010 use /Filter/FlateDecode on page-level streams.
    PDFs from 2010-2011 use /Contents references with compressed objects.
    This function handles both formats.
    """
    with open(pdf_path, 'rb') as f:
        data = f.read()
    
    streams = []
    
    # Format 1: /Filter/FlateDecode streams (2008-2010 era)
    pattern1 = rb'/Filter/FlateDecode.*?stream\r?\n(.*?)endstream'
    for stream in re.findall(pattern1, data, re.DOTALL):
        try:
            decompressed = zlib.decompress(stream)
            text = decompressed.decode('latin-1', errors='replace')
            streams.append(text)
        except Exception:
            continue
    
    # Format 2: /Contents objects (2010-2011 era)
    # Find all /Contents references: /Contents N N R
    contents_refs = re.findall(rb'/Contents\s+(\d+)\s+(\d+)\s+R', data)
    for obj_num, gen_num in contents_refs:
        # Find the object definition
        obj_pattern = obj_num + rb'\s+' + gen_num + rb'\s+obj\s+(.*?)endobj'
        obj_match = re.search(obj_pattern, data, re.DOTALL)
        if not obj_match:
            continue
        obj_content = obj_match.group(1)
        
        if b'/Filter/FlateDecode' in obj_content:
            # Compressed - decompress
            stream_match = re.search(rb'stream\r?\n(.*?)endstream', obj_content, re.DOTALL)
            if stream_match:
                try:
                    decompressed = zlib.decompress(stream_match.group(1))
                    text = decompressed.decode('latin-1', errors='replace')
                    streams.append(text)
                except Exception:
                    continue
        else:
            # Not compressed - use directly
            stream_match = re.search(rb'stream\r?\n(.*?)endstream', obj_content, re.DOTALL)
            if stream_match:
                text = stream_match.group(1).decode('latin-1', errors='replace')
                streams.append(text)
    
    return streams


# ── Mark parsing (inspired by extract_catt.py conventions) ──────────────────

def parse_performance(event, raw_marks):
    """Parse marks from legacy PDF TJ blocks following extract_catt.py patterns.
    
    Priority order for races (from AGENTS.md):
    1. HH:MM:SS (e.g. 2:47:53 for marathon)
    2. HH:MM.ss (e.g. 11:26.41 for 3000m)
    3. HH:MM (e.g. 26:29)
    4. min'seg''cent (e.g. 10'06''1)
    5. Decimal seconds (e.g. 11.79 or 11,79)
    
    For jumps/throws: best valid attempt with dot decimal separator.
    """
    if not raw_marks:
        return ''

    valid_marks = [m for m in raw_marks if m not in ('O', 'X', 'XO', 'XXX', 'dq.', 'DQ', 'DNS', 'DNF', '')]
    if not valid_marks:
        return ''

    event_upper = event.upper()

    # --- MARXA (race walk) ---
    if 'MARXA' in event_upper:
        for m in valid_marks:
            m_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', m)
            if m_match:
                return m_match.group(1)
            m_match = re.search(r'(\d{1,2}:\d{2})(?!:\d)', m)
            if m_match:
                return m_match.group(1)
            parts = m.split(',')
            if len(parts) >= 2:
                try:
                    first = int(parts[0])
                    if 1 <= first <= 59:
                        return f"{parts[0]},{parts[1]}"
                except ValueError:
                    pass
            m_match = re.search(r"(\d{1,2})'(\d{2})''(\d)", m)
            if m_match:
                return f"{m_match.group(1)}:{m_match.group(2)}.{m_match.group(3)}"
        return ''

    # --- CURSES (track events) ---
    if 'METRES LLISOS' in event_upper or 'METRES TANQUES' in event_upper or 'METRES VALLS' in event_upper:
        for m in valid_marks:
            m_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', m)
            if m_match:
                return m_match.group(1)
            m_match = re.search(r'(\d{1,2}:\d{2})(?!:\d)', m)
            if m_match:
                return m_match.group(1)
            m_match = re.search(r"(\d{1,2})'(\d{2})''(\d)", m)
            if m_match:
                return f"{m_match.group(1)}:{m_match.group(2)}.{m_match.group(3)}"
            parts = m.split(',')
            if len(parts) == 2:
                try:
                    val = float(parts[0]) + float(parts[1]) / 100
                    if 5.0 <= val <= 60.0:
                        return f"{parts[0]},{parts[1]}"
                except ValueError:
                    pass
            for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', m):
                val = float(num_match.group(1))
                if 5.0 <= val <= 60.0:
                    return num_match.group(1)
        return ''

    # --- SALT D'ALÇADA (height) ---
    if "SALT D'ALÇADA" in event_upper or "SALT D'ALTADA" in event_upper or "ALTURA" in event_upper:
        attempts = []
        for m in valid_marks:
            parts = m.split(',')
            if len(parts) == 2:
                try:
                    val = float(parts[0]) + float(parts[1]) / 100
                    if 0.5 <= val <= 7.0:
                        attempts.append(val)
                except ValueError:
                    pass
        if attempts:
            best = max(attempts)
            return f"{best:.2f}"
        return ''

    # --- SALT DE LLARGADA / TRIPLE / PÈRTIGA (jump) ---
    if 'LLARGADA' in event_upper or 'TRIPLE' in event_upper or 'PÈRTIGA' in event_upper or 'PERTIGA' in event_upper or 'PERXA' in event_upper:
        attempts = []
        for m in valid_marks:
            parts = m.split(',')
            if len(parts) == 2:
                try:
                    val = float(parts[0]) + float(parts[1]) / 100
                    if 1.5 <= val <= 20.0:
                        attempts.append(val)
                except ValueError:
                    pass
        if attempts:
            best = max(attempts)
            return f"{best:.2f}"
        return ''

    # --- LLANÇAMENT (field events) ---
    if ('LLANÇAMENT' in event_upper or 'LLANAMENT' in event_upper or
        'DISC' in event_upper or 'PES' in event_upper or
        'MART' in event_upper or 'JABALINA' in event_upper or 'DARD' in event_upper):
        attempts = []
        for m in valid_marks:
            parts = m.split(',')
            if len(parts) == 2:
                try:
                    val = float(parts[0]) + float(parts[1]) / 100
                    if 3.0 <= val <= 80.0:
                        attempts.append(val)
                except ValueError:
                    pass
        if attempts:
            best = max(attempts)
            return f"{best:.2f}"
        return ''

    # Fallback
    return ','.join(valid_marks)


# ── Event name extraction ───────────────────────────────────────────────────

def extract_event_from_stream(text):
    """Extract the event name from a stream's text."""
    tjs = re.findall(r'\(([^)]*)\)\s*Tj', text)
    for t in tjs:
        t_upper = t.upper()
        if any(kw in t_upper for kw in ['METRES', 'LLANÇAMENT', 'LLANAMENT', 'SALT', 'DISC', 'MARXA']):
            return t
    tj_blocks = re.findall(r'\[(.*?)\]\s*TJ', text, re.DOTALL)
    for block in tj_blocks[:10]:
        texts = re.findall(r'\(([^)]*)\)', block)
        for t in texts:
            t_upper = t.upper()
            if any(kw in t_upper for kw in ['METRES', 'LLANÇAMENT', 'LLANAMENT', 'SALT', 'DISC', 'MARXA']):
                return t
    return None


# ── Wind extraction ─────────────────────────────────────────────────────────

def extract_winds_from_stream(text):
    """Extract wind values from Tj operators in a stream.
    
    Format: "Vent:-1,5" or "Vent: -0,2"
    Returns list of wind strings like ['-1.5', '-0.2', ...]
    """
    tjs = re.findall(r'\(([^)]*)\)\s*Tj', text)
    winds = []
    for t in tjs:
        m = re.search(r'Vent:\s*(-?[\d,]+\.\d+|-?\d+,\d+)', t)
        if m:
            winds.append(m.group(1).replace(',', '.'))
    return winds


def extract_wind_from_tj_block(after_club_marks):
    """Extract wind value from TJ block marks (for jumps/throws).
    
    For jumps, wind appears as a separate value after the mark, e.g.:
    ['4,64', '+0.8'] or ['4,64', '-1.2']
    
    Returns wind string or None.
    """
    if not after_club_marks:
        return None
    
    for m in after_club_marks:
        # Wind values: +X.XX or -X.XX (e.g., '+0.8', '-1.2')
        wind_match = re.match(r'^[+-]\d+\.\d+$', m)
        if wind_match:
            return m
    
    return None


# ── Header extraction ───────────────────────────────────────────────────────

MONTH_MAP = {
    'gener': '01', 'febrer': '02', 'març': '03', 'abril': '04',
    'maig': '05', 'juny': '06', 'juliol': '07', 'agost': '08',
    'setembre': '09', 'octubre': '10', 'novembre': '11', 'desembre': '12',
}


def extract_header_info(streams):
    """Extract date, location, and event name from header Tj operators."""
    header_date = ''
    header_location = ''
    header_event = ''

    for stream_data in streams:
        try:
            text = zlib.decompress(stream_data).decode('latin-1', errors='replace')
        except Exception:
            continue

        tjs = re.findall(r'\(([^)]*)\)\s*Tj', text)
        for t in tjs:
            # Date: "23 de maig de 2010"
            m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', t)
            if m:
                day = m.group(1).zfill(2)
                month = MONTH_MAP.get(m.group(2).lower(), '00')
                year = m.group(3)
                header_date = f"{day}/{month}/{year}"
            # Location: "El Prat de Llobregat, 23 de maig de 2010"
            m = re.search(r'([A-Za-z\s\.\-]+),\s+\d+\s+de\s+\w+\s+de\s+\d{4}', t)
            if m:
                loc = m.group(1).strip()
                if loc and len(loc) > 3 and not re.match(r'\d', loc):
                    header_location = loc
            # Event name
            if 'CAMPIONAT' in t.upper() or 'FASE' in t.upper():
                header_event = t

        if header_date and header_event:
            break

    return header_date, header_location, header_event


# ── Name cleaning ───────────────────────────────────────────────────────────

def is_valid_name(name):
    """Check if name is valid (not broken from PDF parsing)."""
    if not name or len(name.strip()) < 5:
        return False
    words = name.strip().split()
    if len(words) < 2:
        return False
    # Filter broken names: too many words suggests PDF name splitting artifact
    if len(words) > 4:
        return False
    # Known Spanish/Catalan name particles (valid 1-2 letter words)
    valid_particles = {'DE', 'DEL', 'DA', 'DI', 'DOS', 'DAS', 'Y', 'E', 'VAZ', 'VON', 'VAN', 'DEN', 'DER', 'DER', 'TER', 'LA', 'LE', 'LOS', 'LAS', 'EL', 'AL'}
    for word in words[1:]:  # Skip first word
        w = word.upper()
        # If word is short (<=2 letters) and NOT a valid particle, it's likely a split name
        if len(word) <= 2 and w not in valid_particles:
            return False
    return True


def clean_athlete_name(raw_name):
    """Reformat: LAST, FIRST -> FIRST LAST. Clean artifacts."""
    name = raw_name.strip()
    comma_match = re.match(r'(.+),\s*(.+)', name)
    if comma_match:
        name = f"{comma_match.group(2).strip()} {comma_match.group(1).strip()}"
    return re.sub(r'\s+', ' ', name).strip()


# ── Main extraction ─────────────────────────────────────────────────────────

def is_race_event(event):
    """Check if event is a race (has series with wind)."""
    event_upper = event.upper()
    return ('METRES LLISOS' in event_upper or 'METRES TANQUES' in event_upper or
            'METRES VALLS' in event_upper or 'METRES OBSTACLES' in event_upper or
            'MARXA' in event_upper or '300 TANQUES' in event_upper)


def extract_catt_from_pdf(pdf_path):
    """Extract CA Tarragona results from a PDF using needle-in-haystack.
    
    Wind handling:
    - Races: winds from Tj operators, assigned by series number (1-indexed)
    - Jumps/throws: wind from TJ block values after the mark
    """
    with open(pdf_path, 'rb') as f:
        data = f.read()
    pattern = rb'/Filter/FlateDecode.*?stream\r?\n(.*?)endstream'
    streams = re.findall(pattern, data, re.DOTALL)

    header_date, header_location, header_event = extract_header_info(streams)

    seen = set()
    results = []

    for stream_data in streams:
        try:
            text = zlib.decompress(stream_data).decode('latin-1', errors='replace')
        except Exception:
            continue

        event = extract_event_from_stream(text)
        if not event:
            continue

        # Extract winds from Tj operators for this stream
        stream_winds = extract_winds_from_stream(text)

        tj_blocks = re.findall(r'\[(.*?)\]\s*TJ', text, re.DOTALL)
        for block in tj_blocks:
            # ONLY CA Tarragona, not CG
            if not re.search(r'\bCA\s*TARRAGONA\b', block, re.IGNORECASE):
                continue

            texts = re.findall(r'\(([^)]*)\)', block)

            # Find CA Tarragona position
            club_idx = None
            for idx, t in enumerate(texts):
                if re.match(r'(CA)\s*TARRAGONA', t, re.IGNORECASE):
                    club_idx = idx
                    break

            if club_idx is None:
                continue

            # Find license position (element starting with CL)
            lic_idx = None
            for idx, t in enumerate(texts):
                if t.strip().startswith('CL') or t.strip().startswith('Cl') or t.strip().startswith('cl'):
                    lic_idx = idx
                    break
            
            # Name is between license and club (exclusive)
            # This handles split names like "LO" + "PEZ URBANO" + ", MIREIA"
            # Exclude the birth year (2-4 digit number) which may be between lic and club
            if lic_idx is not None and lic_idx < club_idx - 1:
                name_parts = []
                for part in texts[lic_idx + 1:club_idx]:
                    p = part.strip()
                    # Skip birth year (pure digits, 2-4 chars)
                    if p.isdigit() and len(p) <= 4:
                        continue
                    name_parts.append(p)
                name = ' '.join(name_parts)
            elif club_idx >= 2:
                name = texts[club_idx - 2]
            else:
                name = ''
            
            name = clean_athlete_name(name)

            if not is_valid_name(name):
                continue

            # Marks after club_idx
            raw_marks = texts[club_idx + 1:]
            performance = parse_performance(event, raw_marks)
            if not performance:
                continue

            # Extract wind
            wind = None
            
            # For races: get wind by series number from Tj operators
            if is_race_event(event):
                # Series number is at texts[0] for series-format rows
                series_num = None
                if len(texts) >= 9:
                    # Check if first element is a series number (1-99)
                    try:
                        sn = int(texts[0])
                        if 1 <= sn <= 99:
                            series_num = sn
                    except ValueError:
                        pass
                
                if series_num and series_num <= len(stream_winds):
                    wind = stream_winds[series_num - 1]
            
            # For jumps/throws: get wind from TJ block values
            if wind is None and not is_race_event(event):
                wind = extract_wind_from_tj_block(raw_marks)

            # Deduplicate (include wind in key to avoid cross-wind duplicates)
            key = (name.lower(), event.lower(), performance, wind or '')
            if key in seen:
                continue
            seen.add(key)

            result = {
                'athlete_name': name,
                'discipline': event,
                'performance': performance,
            }
            if wind:
                result['wind'] = wind
            
            results.append(result)

    return header_date, header_location, header_event, results


# ── Entry point ─────────────────────────────────────────────────────────────

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
        wind_str = f" W:{r['wind']}" if r.get('wind') else ''
        print(f"  {r['athlete_name']:35s} | {r['discipline']:50s} | {r['performance']}{wind_str}")

    output = {
        'event_name': header_event if header_event else 'CAMPIONAT DE CATALUNYA',
        'event_date': header_date,
        'event_location': header_location,
        'event_src': pdf_url,
        'total_results': len(results),
        'results': results,
    }

    base = os.path.basename(pdf_path).replace('.pdf', '')
    output_path = os.path.join(output_dir, f"{base}.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
