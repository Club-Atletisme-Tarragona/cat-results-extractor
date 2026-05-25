#!/usr/bin/env python3
"""Extract CA Tarragona results from 2011-2012 PDFs - dual format parser.

Tries BOTH tabular format AND RFEA format for each PDF.
Filters false positives (dorsal-prefixed names, points-like performances).

2011-2012 PDFs may use:
- Tabular format: DORSAL CL LIC NAME, YEAR CA Tarragona MARK (single line)
- RFEA format: athlete data on one line, club name on next line
- Both formats may appear in the same PDF

Usage: python3 scripts/process_2011_2012.py
"""
import json, re, subprocess, urllib.request
from pathlib import Path
from urllib.parse import unquote

CACHE = Path("/tmp/cache_2011_2012_al_pc")
OUT = Path("/root/workspace/cat-results-extractor/seasons/2011-2012/json")
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
    except:
        return None, fn


def extract_text(pdf_path):
    try:
        with subprocess.Popen(['pdftotext', '-layout', pdf_path, '-'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            stdout, stderr = proc.communicate(timeout=10)
            return stdout.decode('utf-8', errors='replace')
    except:
        return None


EVENT_PATTERNS = [
    (r'(\d+)\s*(?:METRES|M)\s+(?:LLISOS|LLISSOS)', r'\1m llisos'),
    (r'(\d+)\s*(?:METRES|M)\s+(?:TANQUES|TANCUES)', r'\1m tanques'),
    (r'(\d+)\s*(?:METRES|M)\s+VALLAS', r'\1m vallas'),
    (r'(\d+)\s*(?:METRES|M)\s+(?:MARXA|MARCHA)', r'\1m marxa'),
    (r'(\d+)\s*(?:METRES|M)\s+OBSTACLES', r'\1m obstacles'),
    (r'ALÇADA|ALTURA', 'alçada'),
    (r'PÈRTIGA|PERTIGA|PERXA', 'pértiga'),
    (r'LLARGADA|LLARGÀADA|LARGADA', 'llargada'),
    (r'TRIPLE\s+SALT', 'triple salt'),
    (r'DISC', 'disc'),
    (r'MARTELL|MARTILLO', 'martell'),
    (r'PES|PESO', 'pes'),
    (r'JAVELINA|JABALINA|DARD', 'javnelina'),
]


def extract_discipline(event_title):
    """Extract discipline from event title."""
    title_upper = event_title.upper()
    for pattern, discipline in EVENT_PATTERNS:
        if re.search(pattern, title_upper, re.IGNORECASE):
            m = re.search(r'(\d+)\s*(?:METRES|M)\s+(?:LLISOS|LLISSOS)', title_upper)
            if m: return f"{m.group(1)}m llisos"
            m = re.search(r'(\d+)\s*(?:METRES|M)\s+(?:TANQUES|TANCUES)', title_upper)
            if m: return f"{m.group(1)}m tanques"
            m = re.search(r'(\d+)\s*(?:METRES|M)\s+(?:MARXA|MARCHA)', title_upper)
            if m: return f"{m.group(1)}m marxa"
            return discipline
    return ""


def parse_header(text):
    lines = text.split('\n')
    name = date = loc = ""
    for l in lines[:30]:
        u = l.strip().upper()
        if any(k in u for k in ['CAMPIONAT','TROFEE','CONTROL','JORNADA','REUNIÓ','LIGUET','FASE PRÈVIA','CRITERIUM','ACTA']):
            name = l.strip(); break
    m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', text)
    if m: date = m.group(1)
    for l in lines[:10]:
        low = l.lower()
        if any(k in low for k in ['sabadell','tarragona','manresa','barcelona','lleida','girona','mataró','vic','vilanova','caldes','granyena','castell','vilassar','badalona','sant cugat','el vendrell','montornès','calafell','palafrugell','gavà','cornellà','lloret','bages','marbella','mataro','montsià','penedes','andorra','rubí','montornès','castell','palamos','serrahima','universitaria','hospitalet','s.andreu','barberà','valls','granollers','badalona','mollet','castellar','igualada','viladecans','canavetes','gavà','lleida','muntanyenc','lluisos','nadal','terrassa','empúries','girona','vic','manresa','tarragona']):
            loc = l.strip()[:100]; break
    return name, date, loc


def find_event_titles(text):
    """Find all event/prova titles in the text. Returns list of (line_index, title)."""
    lines = text.split('\n')
    titles = []
    for i, line in enumerate(lines):
        u = line.strip().upper()
        # Distance + event type
        if re.search(r'\d+\s*(?:METRES|M)\s+(?:LLISOS|LLISSOS|TANQUES|TANCUES|VALLAS|MARCHA|MARXA|OBSTACLES)', u):
            title = re.sub(r'\s+', ' ', line.strip())
            if 5 < len(title) < 80:
                titles.append((i, title))
        elif re.search(r'ALÇADA|ALTURA|PÈRTIGA|PERTIGA|PERXA|LLARGADA|LLARGÀADA|LARGADA|TRIPLE\s+SALT|DISC|MARTELL|MARTILLO|PES|PESO|JAVELINA|JABALINA|DARD|PENTATHLON|HEPTATHLON', u, re.IGNORECASE):
            title = re.sub(r'\s+', ' ', line.strip())
            if 3 < len(title) < 80:
                titles.append((i, title))
    return titles


def extract_catt_tabular(text):
    """Tabular format: DORSAL CL LIC NAME, YEAR CA Tarragona MARK (all on one line)."""
    results = []
    seen = set()
    event_titles = find_event_titles(text)

    for idx, (title_line, event_title) in enumerate(event_titles):
        section_end = event_titles[idx + 1][0] if idx + 1 < len(event_titles) else len(text.split('\n'))
        discipline = extract_discipline(event_title)

        for i in range(title_line, section_end):
            line = text.split('\n')[i]
            if 'CA Tarragona' not in line:
                continue

            m = re.search(r'(\d+)\s+(?:CL|CT|CAT)\s*(\S+)\s+(.+?)\s+(\d{4})\s+CA Tarragona\s+(.+)', line)
            if not m:
                continue

            name_part = m.group(3)
            perf_part = m.group(5).strip()
            parts = name_part.split(',')
            if len(parts) < 2:
                continue

            aname = f"{parts[1].strip()} {parts[0].strip()}".strip()
            aname = re.sub(r'\s+', ' ', aname).strip()
            perf = perf_part
            perf = re.sub(r'\s+F\s*$', '', perf).strip()
            perf = re.sub(r'\s+M\s*$', '', perf).strip()

            if perf in ('N.P.', 'DNS', 'DQ', 'DNF', 'X', ''):
                pass
            elif re.match(r'^\d{1,2}$', perf) and len(perf) <= 2:
                continue
            elif re.match(r'^\d{3,}$', perf):
                continue

            key = f"{aname}|{event_title}|{perf}"
            if key not in seen:
                seen.add(key)
                results.append({"athlete_name": aname, "discipline": discipline, "performance": perf})

    return results


def extract_catt_rfea(text):
    """RFEA format: athlete data on one line, club name on next line.

    Filters false positives:
    - Names starting with numbers (dorsal, not athlete)
    - Performance values that look like points (two numbers like "3 75")
    """
    results = []
    seen = set()
    lines = text.split('\n')
    event_titles = find_event_titles(text)

    for idx, (title_line, event_title) in enumerate(event_titles):
        section_end = event_titles[idx + 1][0] if idx + 1 < len(event_titles) else len(lines)
        discipline = extract_discipline(event_title)

        for i in range(title_line, section_end):
            line = lines[i]
            if 'CA Tarragona' not in line and 'CATT' not in line:
                continue

            # Look BACKWARD for athlete data
            aname = ""

            for j in range(max(0, i-5), i):
                prev = lines[j].strip()
                if not prev:
                    continue

                # Pattern: "DORSAL (t)? NAME  DATE  CALLE"
                nm = re.search(r'(\d+)\s+(?:\(t\)\s+)?(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d)\s*(.*)', prev)
                if nm:
                    raw_name = nm.group(2).strip()
                    aname = re.sub(r'\s+', ' ', raw_name).strip()
                    break

                # Pattern: "NAME  DATE  CALLE" without dorsal
                nm2 = re.search(r'(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d)', prev)
                if nm2 and not re.match(r'^\d+\s', prev):
                    raw_name = nm2.group(1).strip()
                    aname = re.sub(r'\s+', ' ', raw_name).strip()
                    break

            if not aname:
                continue

            # Look FORWARD for performance
            perf = ""
            for j in range(i+1, min(i+4, section_end)):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                if 'CA Tarragona' in next_line or 'CATT' in next_line:
                    continue
                if re.match(r'^[A-Z]+', next_line) and len(next_line) < 30:
                    continue

                pm = re.search(r'([\d.,:\s]+)', next_line)
                if pm:
                    perf = pm.group(1).strip()
                    perf = re.sub(r'\s+', ' ', perf).strip()
                    break

            if not perf:
                continue

            # FILTER: Skip if name starts with number (dorsal, not athlete)
            if re.match(r'^\d+\s', aname):
                continue

            # FILTER: Skip if performance looks like points (two numbers like "3 75")
            if re.match(r'^\d+\s+\d+$', perf) and not re.search(r'[:.]', perf):
                continue

            # Validate performance
            if perf in ('N.P.', 'DNS', 'DQ', 'DNF', 'X', ''):
                pass
            elif re.match(r'^\d{1,2}$', perf) and len(perf) <= 2:
                continue
            elif re.match(r'^\d{3,}$', perf):
                continue

            key = f"{aname}|{event_title}|{perf}"
            if key not in seen:
                seen.add(key)
                results.append({"athlete_name": aname, "discipline": discipline, "performance": perf})

    return results


# Process all PDFs
total = 0
events = 0
skipped = 0
failed = 0
processed = 0

for idx, url in enumerate(urls):
    if idx % 50 == 0:
        print(f"Processing: {idx}/{len(urls)} (events:{events}, results:{total})")

    cached_path, fn = download_pdf(url, CACHE)
    if not cached_path:
        failed += 1
        continue

    text = extract_text(cached_path)
    if not text:
        skipped += 1
        continue

    processed += 1

    ename, edate, eloc = parse_header(text)

    # Try BOTH formats
    athletes = extract_catt_tabular(text)
    if not athletes:
        athletes = extract_catt_rfea(text)

    if athletes:
        event = {
            "event_name": ename,
            "event_date": edate,
            "event_location": eloc,
            "event_src": url,
            "results": athletes
        }
        total += len(athletes)
        events += 1
        json_fn = fn.replace('.pdf', '.json')
        (OUT / json_fn).write_text(json.dumps(event, ensure_ascii=False, indent=2))

print(f"\nDone!")
print(f"  PDFs processed: {processed}/{len(urls)}")
print(f"  Events with CA Tarragona: {events}")
print(f"  Total results: {total}")
print(f"  Skipped (no pdftotext): {skipped}")
print(f"  Failed (download): {failed}")
