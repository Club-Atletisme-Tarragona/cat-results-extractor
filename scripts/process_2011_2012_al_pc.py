#!/usr/bin/env python3
"""Download and extract CA Tarragona results from 2011-2012 AL+PC PDFs using pdftotext."""
import json, re, subprocess, urllib.request, tempfile, os
from pathlib import Path
from urllib.parse import unquote

CACHE = Path("/tmp/cache_2011_2012_al_pc")
OUT = Path("/root/workspace/cat-results-extractor/seasons/2011-2012/json")
CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

urls = [l.strip() for l in open("/tmp/aire_lliure_2011_2012.txt")]
urls += [l.strip() for l in open("/tmp/pista_coberta_2011_2012.txt")]
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

def extract_with_pdftotext(pdf_path):
    """Extract text using pdftotext -layout (preserves spatial layout)."""
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            tmp_txt = f.name
        subprocess.run(['pdftotext', '-layout', pdf_path, tmp_txt],
                       capture_output=True, timeout=10)
        text = open(tmp_txt).read()
        os.unlink(tmp_txt)
        return text
    except Exception as e:
        print(f"  pdftotext failed: {e}")
        return None

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
    """Extract CA Tarragona athletes using pdftotext layout-aware parsing."""
    results = []
    seen = set()
    lines = text.split('\n')
    i = 0
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
                nm = re.search(r'(?:\d+\s+)?\(?\w+\)?\s+([A-Z][a-zà-úÀ-Ú]+(?:\s+[A-Z][a-zà-úÀ-Ú]+)*\s+[A-Z][a-zà-úÀ-ú]+)', p)
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
                key = f"{aname}|{perf}"
                if key not in seen:
                    seen.add(key)
                    results.append({"athlete_name": aname, "discipline": "", "performance": perf})
        i += 1
    return results

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
    
    text = extract_with_pdftotext(cached_path)
    if not text:
        skipped += 1
        continue
    
    ename, edate, eloc = parse_header(text)
    athletes = extract(text)
    
    if athletes:
        event = {"event_name": ename, "event_date": edate, "event_location": eloc, "event_src": url, "results": athletes}
        total += len(athletes)
        events += 1
        json_fn = fn.replace('.pdf', '.json')
        (OUT / json_fn).write_text(json.dumps(event, ensure_ascii=False, indent=2))

print(f"\nDone! Events: {events}, Total results: {total}, Skipped (no pdftotext): {skipped}, Failed: {failed}")
