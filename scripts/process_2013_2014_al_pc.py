#!/usr/bin/env python3
"""Download and extract CA Tarragona results from 2013-2014 AL+PC PDFs."""
import json, re, urllib.request
from pathlib import Path
from urllib.parse import unquote
import pdfplumber

CACHE = Path("/tmp/cache_2013_2014_al_pc")
OUT = Path("/root/workspace/cat-results-extractor/seasons/2013-2014/json")
CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

urls = [l.strip() for l in open("/tmp/aire_lliure_2013_2014.txt")]
urls += [l.strip() for l in open("/tmp/pista_coberta_2013_2014.txt")]
urls = list(dict.fromkeys(urls))
print(f"Total URLs: {len(urls)}")

def download_pdf(url, cache_dir):
    fn = unquote(url.split('/')[-1])
    cached = cache_dir / fn
    if cached.exists():
        return str(cached), fn
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        cached.write_bytes(data)
        return str(cached), fn
    except Exception as e:
        return None, fn

def parse_header(text):
    lines = text.split('\n')
    name = date = loc = ""
    for l in lines[:30]:
        u = l.strip().upper()
        if any(k in u for k in ['CAMPIONAT','TROFEE','CONTROL','JORNADA','REUNIÓ','LIGUET']):
            name = l.strip(); break
    m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', text)
    if m: date = m.group(1)
    for l in lines[:10]:
        low = l.lower()
        if any(k in low for k in ['sabadell','tarragona','manresa','barcelona','lleida','girona','mataró','vic','vilanova','caldes','granyena','castell','vilassar','badalona','sant cugat','el vendrell','montornès','calafell','palafrugell','gavà','cornellà','lloret','bages','marbella']):
            loc = l.strip()[:100]; break
    return name, date, loc

def extract(text):
    results = []
    seen = set()
    lines = text.split('\n')
    i = 0
    
    # Pre-scan: build a map of event titles to their line positions
    # Events appear 5-15 lines before the CA Tarragona club line
    event_map = {}  # line_idx -> event_title
    event_patterns = [
        r'(\d+\s*(?:metres|metres?\s+llisos|metres?\s+tanques?|marxa)\s+\w+)',
        r'(\d+\s*m\s+\w+)',
        r'([Ll]lançament\s+\w+)',
        r'([Ss]alt\s+(?:Al[cç]ada|Llargada|Perxa|Triple\s+Salt))',
        r'([Pp]rova\s+(?:Decatló|Heptatló))',
        r'([Aa]ltada)',
        r'([Pp]es)',
        r'([Dd]isc)',
        r'([Jj]avelina)',
        r'([Mm]artell)',
        r'([Ll]largada)',
        r'([Tt]riple\s+Salt)',
        r'([Pp]erxa)',
        r'([Mm]arxa)',
        r'([Tt]anques)',
        r'([Cc]ombinades)',
        r'([Cc]lub)',
    ]
    
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip header-like lines
        if re.match(r'^\d{1,2}[/\-]\d{1,2}[/\-]', stripped):
            continue
        if 'CA Tarragona' in stripped.upper():
            continue
        for pat in event_patterns:
            m = re.search(pat, stripped, re.IGNORECASE)
            if m:
                # Filter out lines that are just club standings or data
                if re.match(r'^\d+\s+C\.?\s*T\.?\s*CA\s*TARRAGONA\s+\d+$', stripped):
                    continue
                event_map[idx] = m.group(1).strip()
                break
    
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'^CA Tarragona\s+(?:CL|CT|CAT)\d+', line, re.IGNORECASE):
            aname = ""
            for j in range(max(0, i-5), i):
                p = lines[j].strip()
                if not p: continue
                if re.match(r'^[\d.\sXOxo/\-]+$', p): continue
                if re.match(r'^\d{2}/\d{2}/\d{4}$', p): continue
                if re.match(r'^[A-Z][A-Z\s]+CL\d+', p): continue
                if re.match(r'^CL\d+$', p): continue
                if re.match(r'^(SM|AF|LM|JM|JF|PM|PF|M-\d+|W-\d+|M-4\d|M-5\d|M-3\d)$', p): continue
                if re.match(r'^\d+$', p): continue
                nm = re.search(r'(?:\d+\s+)?\(?\\w+\)?\s+([A-Z][a-zà-úÀ-Ú]+(?:\s+[A-Z][a-zà-úÀ-Ú]+)*\s+[A-Z][a-zà-úÀ-ú]+)', p)
                if nm:
                    aname = re.sub(r'\s+\d{2}/\d{2}/\d{4}\s*$', '', nm.group(1)); break
            if not aname:
                for j in range(max(0, i-6), i):
                    p = lines[j].strip()
                    nm2 = re.search(r'\d+\s+\([A-Z]\)\s+(.+)', p)
                    if nm2:
                        aname = re.sub(r'\s+\d{2}/\d{2}/\d{4}\s*$', '', nm2.group(1)); break
            if not aname:
                i += 1; continue
            perf = ""
            for j in range(i+1, min(i+5, len(lines))):
                nl = lines[j].strip()
                if not nl: continue
                if re.match(r'^[A-Z][A-Z\s]+CL\d+', nl): continue
                if re.match(r'^(?:Semifinal|Final|Heat|Sèrie)\s', nl): continue
                if re.match(r'^(?:SM|AF|LM|JM|JF|PM|PF|M-\d+|W-\d+)$', nl): continue
                if re.match(r'^\d+$', nl): continue
                rm = re.search(r'([\d.,\'\"]+\s*(?:[\d.,\'\"]+\s*){0,6})', nl)
                if rm:
                    perf = re.sub(r'\s+[A-Z]{2,}\s*$', '', rm.group(1).strip())
                    perf = re.sub(r'\s+\d+\s*$', '', perf); break
            if aname and perf:
                if re.match(r'^\d$', perf) or re.match(r'^[A-Z]$', perf): i += 1; continue
                if 'Dor Cat' in aname or aname in ['El Vendrell','CNRP','Nàstic T.']: i += 1; continue
                
                # Infer discipline from event_map: find the nearest event title above this line
                discipline = ""
                best_event_line = -1
                for eline, etitle in event_map.items():
                    if eline < i and eline > best_event_line:
                        best_event_line = eline
                        discipline = etitle
                
                # If no event title found, try to infer from performance
                if not discipline:
                    discipline = infer_discipline_from_perf(perf)
                
                key = f"{aname}|{perf}"
                if key not in seen:
                    seen.add(key)
                    results.append({"athlete_name": aname, "discipline": discipline, "performance": perf})
        i += 1
    return results


def infer_discipline_from_perf(perf):
    """Infer discipline from performance value when no event title is found."""
    try:
        val = float(perf.replace(',', '.'))
    except (ValueError, TypeError):
        return perf  # Can't infer, keep as-is
    
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
    elif val < 200:
        return "PES"
    elif val < 70:
        return "DISC"
    elif val < 100:
        return "JAVELINA"
    elif val < 10:
        return "PERXA"
    return "PROVA"

# Download all
total = 0
events = 0
skipped = 0
failed = 0

for idx, url in enumerate(urls):
    if idx % 50 == 0:
        print(f"Download: {idx}/{len(urls)} (events:{events}, results:{total})")
    
    cached_path, fn = download_pdf(url, CACHE)
    if not cached_path:
        failed += 1
        continue
    
    try:
        pdf = pdfplumber.open(cached_path)
        text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t: text += t + "\n"
        pdf.close()
    except: continue
    
    ename, edate, eloc = parse_header(text)
    athletes = extract(text)
    
    if athletes:
        event = {"event_name": ename, "event_date": edate, "event_location": eloc, "event_src": url, "results": athletes}
        total += len(athletes)
        events += 1
        (OUT / fn).write_text(json.dumps(event, ensure_ascii=False, indent=2))

print(f"\nDone! Events: {events}, Total results: {total}, Failed: {failed}")
