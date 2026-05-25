#!/usr/bin/env python3
"""Process all cached 2013-2014 PDFs that have CA Tarragona."""
import json, re, subprocess, os
from pathlib import Path

CACHE = Path("/tmp/cache_2013_2014_universal")
OUT = Path("/root/workspace/cat-results-extractor/seasons/2013-2014/json")
OUT.mkdir(parents=True, exist_ok=True)

# Event detection patterns
EVENT_PATTERNS = [
    r'(\d+\s*m(?:etres)?\.?\s+(?:llisos?)?)\s+\w+',
    r'(\d+\s*m\s+tanques?)',
    r'(\d+x\d+\s*m)',
    r'([Ll]largada)\s+\w+',
    r'([Tt]riple\s+[Ss]alt)',
    r'([Pp]erxa)',
    r'([Aa]ltada)',
    r'([Pp]es)',
    r'([Dd]isc)',
    r'([Jj]avelina)',
    r'([Mm]artell)',
    r'([Cc]ombinades)',
    r'([Dd]ecatló)',
    r'([Hh]eptatló)',
    r'(\d+\s*m\s+marxa)',
]

def detect_event_title(text):
    lines = text.split('\n')
    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            continue
        if any(kw in stripped.upper() for kw in ['ACTA', 'CALIFICACIÓN', 'RESULTADO', 'CLUB', 'POS']):
            continue
        if re.match(r'^\d+\s+C\.?\s*T\.?\s*CA\s*TARRAGONA\s+\d+$', stripped):
            continue
        for pat in EVENT_PATTERNS:
            m = re.search(pat, stripped, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return ""

def extract_name_from_line(line):
    m = re.match(r'\d+\s+\d+\s+\(?[te]\)?\s+(.+?)\s+\d{2}/\d{2}/\d{4}', line)
    if not m:
        m = re.match(r'\d+\s+\d+\s+(.+?)\s+\d{2}/\d{2}/\d{4}', line)
    if m:
        name = m.group(1).strip().rstrip(',.-')
        name = re.sub(r'\s+\d+\s*$', '', name)
        words = name.split()
        if len(words) >= 2 and not name.upper().startswith(('Pto', 'Dor', 'NOM', 'NOMBRE', 'CLUB')):
            return name
    return ""

def extract_performance(line):
    if re.match(r'^[A-Z][A-Z\s]+(?:CL|CT)\d+', line):
        return None, None
    
    stripped = line.strip()
    if not stripped or stripped in ('q', 'Q', '', 'NP', 'N.P.', 'DNS', 'DQ', 'RET.', 'DNF', 'NULS'):
        return None, None
    
    values = re.findall(r'(\d+(?:[.,:]\d{2})?(?:\'?\d{2})?(?:"\d{2})?)', stripped)
    if not values:
        return None, None
    
    perf_str = values[-1]
    
    try:
        val = float(perf_str.replace(',', '.'))
        if 0 < val < 6.0:
            return None, None
        if 1900 <= val <= 2099:
            return None, None
        if val == int(val) and 1 <= val <= 999:
            return None, None
    except (ValueError, TypeError):
        pass
    
    if "'" in perf_str or '"' in perf_str:
        m = re.match(r"(\d+)'(\d{2})\"(\d{2})", perf_str)
        if m:
            perf_str = f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
        m = re.match(r"(\d+)'(\d{2})\"(\d)", perf_str)
        if m:
            perf_str = f"{m.group(1)}:{m.group(2)}.{m.group(3)}0"
    
    return perf_str, None

def infer_discipline(perf):
    try:
        val = float(perf.replace(',', '.'))
    except (ValueError, TypeError):
        return "PROVA"
    
    if val < 12:
        return "60 METRES LLISOS"
    elif val < 15:
        return "100 METRES LLISOS"
    elif val < 25:
        return "200 METRES LLISOS"
    elif val < 55:
        return "400 METRES LLISOS"
    elif val < 120:
        return "800 METRES LLISOS"
    elif val < 300:
        return "1500 METRES LLISOS"
    elif val < 600:
        return "3000 METRES LLISOS"
    elif val < 1000:
        return "5000 METRES LLISOS"
    elif val < 100:
        return "110 TANQUES"
    elif val < 5:
        return "ALÇADA"
    elif val < 8:
        return "LLARGADA"
    elif val < 20:
        return "TRIPLE SALT"
    elif val < 10:
        return "PERXA"
    elif val < 200:
        return "PES"
    elif val < 70:
        return "DISC"
    elif val < 100:
        return "JAVELINA"
    return "PROVA"

def validate_discipline_perf(discipline, perf):
    try:
        val = float(perf.replace(',', '.'))
    except (ValueError, TypeError):
        return True
    
    disc_upper = discipline.upper()
    track_ranges = {
        "60 METRES": (6.0, 12.0), "100 METRES": (10.0, 15.0),
        "200 METRES": (20.0, 25.0), "400 METRES": (45.0, 55.0),
        "600 METRES": (70.0, 90.0), "800 METRES": (100.0, 130.0),
        "1000 METRES": (130.0, 180.0), "1500 METRES": (220.0, 300.0),
        "2000 METRES": (300.0, 400.0), "3000 METRES": (480.0, 600.0),
        "5000 METRES": (800.0, 1000.0), "110 TANQUES": (12.0, 20.0),
    }
    for event_name, (min_t, max_t) in track_ranges.items():
        if event_name in disc_upper:
            return min_t <= val <= max_t
    
    field_ranges = {
        "ALÇADA": (0.5, 3.0), "LLARGADA": (3.0, 10.0),
        "TRIPLE SALT": (10.0, 20.0), "PERXA": (2.0, 7.0),
        "PES": (10.0, 25.0), "DISC": (30.0, 80.0), "JAVELINA": (40.0, 100.0),
    }
    for event_name, (min_v, max_v) in field_ranges.items():
        if event_name in disc_upper:
            return min_v <= val <= max_v
    
    if "RELLEUS" in disc_upper or "X" in disc_upper:
        return 30 <= val <= 400
    
    if "COMBIN" in disc_upper or "DECATLÓ" in disc_upper or "HEPTATLÓ" in disc_upper:
        return 500 <= val <= 3000
    
    return True

# Build URL mapping: filename -> original URL
url_map = {}
for url_file in ['/tmp/aire_lliure_2013_2014.txt', '/tmp/pista_coberta_2013_2014.txt']:
    if os.path.exists(url_file):
        with open(url_file) as f:
            for line in f:
                url = line.strip()
                if url and url.endswith('.pdf'):
                    fname = url.split('/')[-1]
                    url_map[fname] = url

print(f"URL mapping: {len(url_map)} PDFs -> URLs")

# Process all cached PDFs
pdfs = sorted(os.listdir(CACHE))
total = 0
events = 0
skipped = 0
failed = 0

for idx, pdf in enumerate(pdfs):
    if not pdf.endswith('.pdf'):
        continue
    
    pdf_path = CACHE / pdf
    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf_path), '-'],
        capture_output=True, text=True, timeout=10
    )
    text = result.stdout
    
    if 'CA TARRAGONA' not in text.upper():
        continue
    
    lines = text.split('\n')
    
    # Pre-scan for event titles
    event_titles = {}
    for i, line in enumerate(lines):
        title = detect_event_title(line)
        if title:
            event_titles[i] = title
    
    # Extract athletes
    athletes = []
    seen = set()
    
    # Pre-scan: extract wind values per series line
    # Each series line (Serie X / Semifinal X / Final) has a wind value
    # We need to associate the correct wind with each athlete based on which series they're in
    series_winds = {}  # line_number -> wind_value
    current_series_line = -1
    for i, line in enumerate(lines):
        # Detect series headers: "Serie 1", "Semifinal 1", "Final"
        if re.search(r'(?:Serie|Semifinal|Final)\s+\d*\s+\d{2}/\d{2}/\d{2,4}', line):
            current_series_line = i
            wm = re.search(r'Viento:\s*([+-]\d+\.?\d*)', line)
            if wm:
                series_winds[i] = wm.group(1)
    
    # Build a map: for each line, what's the nearest series line above it
    def get_wind_for_line(line_idx):
        best = -1
        best_wind = None
        for sl, sw in series_winds.items():
            if sl < line_idx and sl > best:
                best = sl
                best_wind = sw
        return best_wind
    
    for i, line in enumerate(lines):
        if re.search(r'CA\s*TARRAGONA\s+(?:CL|CT|CAT)\d+', line, re.IGNORECASE):
            # The athlete data is on the line ABOVE (RFEA format)
            # Find the athlete data line (skip blank lines and headers, look up to 15 lines)
            athlete_line = ""
            for j in range(i - 1, max(i - 15, 0), -1):
                prev = lines[j].strip()
                if not prev:
                    continue
                if re.match(r'^[A-Z][A-Z\s]+(?:CL|CT)\d+', prev):
                    continue
                if prev in ('q', 'Q', '', 'NP', 'N.P.'):
                    continue
                athlete_line = prev
                break
            
            if not athlete_line:
                continue
            
            name = extract_name_from_line(athlete_line)
            if not name:
                continue
            
            perf, wind = extract_performance(athlete_line)
            if not perf:
                continue
            
            # Get wind from series header (pre-scanned)
            if not wind:
                wind = get_wind_for_line(i)
            
            # Get event title (nearest event title above, look up to 20 lines)
            discipline = ""
            best_line = -1
            for eline, etitle in event_titles.items():
                if eline < i and eline > best_line:
                    best_line = eline
                    discipline = etitle
            
            if not discipline:
                discipline = infer_discipline(perf)
            
            # Validate coherence
            if discipline and perf:
                if not validate_discipline_perf(discipline, perf):
                    discipline = infer_discipline(perf)
            
            key = f"{name}|{perf}"
            if key not in seen:
                seen.add(key)
                athlete = {
                    "athlete_name": name,
                    "discipline": discipline,
                    "performance": perf,
                }
                # Only add wind for track sprints and horizontal jumps (60m, 100m, 200m, 110m tanques, Llargada, Triple Salt)
                disc_lower = discipline.lower()
                if wind and any(kw in disc_lower for kw in ['60 metres', '100 metres', '200 metres', '110 tanques', '60m', '100m', '200m', '110m', 'llargada', 'triple']):
                    athlete["wind"] = wind
                athletes.append(athlete)
    
    if not athletes:
        skipped += 1
        continue
    
    # Extract event metadata
    ename = edate = eloc = ""
    for l in lines[:30]:
        u = l.strip().upper()
        if any(k in u for k in ['CAMPIONAT','TROFEE','CONTROL','JORNADA','REUNIÓ','LIGUET']):
            ename = l.strip()
            break
    m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', text)
    if m:
        edate = m.group(1)
    for l in lines[:10]:
        low = l.lower()
        if any(k in low for k in ['sabadell','tarragona','manresa','barcelona','lleida','girona','mataró','vic','vilanova','caldes','granyena','castell','vilassar','badalona','sant cugat','el vendrell','montornès','calafell','palafrugell','gavà','cornellà','lloret','bages','marbella','gava','castellar','juneda','el prat','badalona','sant celoni','castellbisbal','montmeló','el bruc','arbucies','calldetenes','santa coloma','sant feliu','sant joan','sant just','sant llorenç','sant mateu','sant peres','sant quirc','sant roque','sant salvador','sant vicenç']):
            eloc = l.strip()[:100]
            break
    if not ename:
        ename = pdf.replace('.pdf', '')
    
    src_url = url_map.get(pdf, "")
    
    event = {
        "event_name": ename,
        "event_date": edate,
        "event_location": eloc,
        "event_src": src_url,
        "results": athletes,
    }
    
    total += len(athletes)
    events += 1
    json_path = OUT / pdf.replace('.pdf', '.json')
    json_path.write_text(json.dumps(event, ensure_ascii=False, indent=2))

print(f"Done! Events: {events}, Total results: {total}, Skipped (no CA): {skipped}, Failed: {failed}")

# Debug: check what was written
import os as _os
written = _os.listdir(OUT)
print(f"\nDEBUG: {len(written)} JSONs in {OUT}")
for _f in sorted(written)[:5]:
    _path = OUT / _f
    _size = _path.stat().st_size
    print(f"  {_f}: {_size} bytes")
