#!/usr/bin/env python3
"""Extract CA Tarragona results from 2014-2015 AL+PC PDFs (RFEA format)."""
import json, re, sys
from pathlib import Path
from urllib.parse import unquote
import pdfplumber

CACHE = Path("/tmp/cache_2014_2015_al_pc")
OUT = Path("/root/workspace/cat-results-extractor/seasons/2014-2015/json")
OUT.mkdir(parents=True, exist_ok=True)

# Read URLs
urls = [l.strip() for l in open("/tmp/aire_lliure_2014_2015.txt")]
urls += [l.strip() for l in open("/tmp/pista_coberta_2014_2015.txt")]
urls = list(dict.fromkeys(urls))

url_map = {}
for u in urls:
    fn = unquote(u.split('/')[-1])
    url_map[fn] = u

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

def extract_rfea_format(text):
    """
    RFEA format: athlete line followed by club line.
    Example:
      1 6 (t) Victor Velasco Gonzalez 11/01/2003 5 8.71 Q
      JA Sabadell CL74957
    
    We need to find club lines with "CA Tarragona" and grab the preceding athlete line.
    """
    results = []
    seen = set()
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check if this is a club line with CA Tarragona
        if re.match(r'^CA Tarragona\s+(?:CL|CT|CAT)\d+', line, re.IGNORECASE):
            # Get the PREVIOUS non-empty line as athlete data
            athlete_line = ""
            for j in range(i-1, max(i-8, -1), -1):
                prev = lines[j].strip()
                if not prev: continue
                # Must look back past section headers, club lines, etc.
                if re.match(r'^(?:Semifinal|Final|Heat|Sèrie)\s', prev): continue
                if re.match(r'^\d{2}/\d{2}/\d{4}\s+\d+:', prev): continue
                if re.match(r'^[A-Z][A-Z\s]+CL\d+', prev): continue
                if re.match(r'^T\d+\w+\s+\d+C\s+RFEA', prev): continue  # footer
                if re.match(r'^Nombre\s+F\s+de\s+Nac', prev): continue  # header
                if re.match(r'^Pto\s+Dor\s+Cat', prev): continue  # header
                if re.match(r'^Pto\s+Dor\s+Calle', prev): continue  # header
                if re.match(r'^Club\s+Lic', prev): continue  # header
                if re.match(r'^Club', prev): continue  # header
                athlete_line = prev
                break
            
            if not athlete_line:
                i += 1; continue
            
            # Parse athlete line: pos dorsal [(t/e)] NAME DD/MM/YYYY CATEGORY [CARRIL] PERFORMANCE
            am = re.search(r'\d+\s+\d+\s+(?:\([te]\)\s+)?(.+?)\s+\d{2}/\d{2}/\d{4}\s+\w+\s+(.+)$', athlete_line)
            
            if am:
                aname = am.group(1).strip()
                aperf = am.group(2).strip()
                # Clean performance: remove carril, Q/q markers, keep best mark for jumps
                aperf = re.sub(r'^\d+\s+', '', aperf)  # remove leading carril
                aperf = re.sub(r'\s+\d+\s*$', '', aperf)  # remove trailing carril
                aperf = re.sub(r'\s+[A-Z]\s*$', '', aperf)  # remove Q, q, e markers
                # For salt alçada/triple: "X 4.05 4.09 4.09" -> "4.09"
                parts = aperf.split()
                numeric = [p for p in parts if re.match(r'^[\d.]+$', p)]
                if numeric:
                    aperf = numeric[-1]
                
                if aname and aperf:
                    if re.match(r'^\d$', aperf) or re.match(r'^[A-Z]$', aperf):
                        i += 1; continue
                    key = f"{aname}|{aperf}"
                    if key not in seen:
                        seen.add(key)
                        results.append({"athlete_name": aname, "discipline": "", "performance": aperf})
        
        i += 1
    return results

# Process only PDFs that don't have JSON output yet
existing = set(f.name for f in OUT.glob('*.json'))
to_process = sorted([p for p in CACHE.glob("*.pdf") if p.name not in existing])
print(f"PDFs to process: {len(to_process)}")

total = 0
events = 0
skipped_no_url = 0

for idx, pdf in enumerate(to_process):
    if idx % 50 == 0:
        print(f"Progress: {idx}/{len(to_process)} (events:{events}, results:{total})")
    
    fn = pdf.name
    url = url_map.get(fn, "")
    if not url:
        skipped_no_url += 1
        continue
    
    try:
        pdf_obj = pdfplumber.open(str(pdf))
        text = ""
        for page in pdf_obj.pages:
            t = page.extract_text()
            if t: text += t + "\n"
        pdf_obj.close()
    except: continue
    
    ename, edate, eloc = parse_header(text)
    athletes = extract_rfea_format(text)
    
    if athletes:
        event = {"event_name": ename, "event_date": edate, "event_location": eloc, "event_src": url, "results": athletes}
        total += len(athletes)
        events += 1
        (OUT / fn).write_text(json.dumps(event, ensure_ascii=False, indent=2))

print(f"\nDone!")
print(f"Events with CA Tarragona: {events}")
print(f"Total CA Tarragona results: {total}")
print(f"Skipped (no URL): {skipped_no_url}")
