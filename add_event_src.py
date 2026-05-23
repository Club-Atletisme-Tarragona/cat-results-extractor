#!/usr/bin/env python3
"""Add event_src URLs to all JSON files that are missing them."""
import os
import re
import json

base = '/root/workspace/cat-results-extractor'

# URL patterns: filename prefixes -> (context_dir, url_context_dir)
context_patterns = [
    (r'cadetpc|juvenilpc|cadet.*pc|infantil.*pc|benjami.*pc|control.*pc', 'Pcoberta', 'pcoberta'),
    (r'airelliure', 'Pairelliure', 'airelliure'),
    (r'catclub|catcadet|catbenjami|catinfantil|catalevi|catcombi|catcombialeinfcad', 'Pairelliure', 'airelliure'),
    (r'cros', 'Cros', 'cros'),
    (r'marxa', 'Marxa', 'marxa'),
    (r'territorial|territcombi|cnatterrit', 'promocio', 'promocio'),
    (r'controlfcat|fcat', 'Pcoberta', 'pcoberta'),
    (r'catalevi', 'Pairelliure', 'airelliure'),
    (r'resul-', 'Pairelliure', 'airelliure'),
]

def extract_year_from_filename(filename):
    """Extract the competition year from the filename.
    
    Filenames end with DDMMYY (e.g., resulcatcadet18611.pdf -> 18/6/2011,
    resulcalella131208.pdf -> 13/12/2008).
    """
    name = filename.replace('.pdf', '').replace('.json', '')
    # Match last 2 digits as YY
    m = re.search(r'(\d{2})$', name)
    if m:
        return f"20{m.group(1)}"
    return None

def reconstruct_url(filename, year):
    """Reconstruct the FCAT URL from the PDF filename and year."""
    if not year:
        return None
    
    for pattern, context, url_context in context_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return f"https://old.fcatletisme.cat/{context}/{url_context}{year}/{filename}"
    
    return None

def main():
    seasons = ['2008-2009', '2009-2010', '2010-2011', '2011-2012']
    total = 0
    updated = 0
    skipped = 0
    errors = 0
    
    for season in seasons:
        json_dir = os.path.join(base, 'seasons', season, 'json')
        if not os.path.exists(json_dir):
            continue
        
        for jf in sorted(os.listdir(json_dir)):
            if not jf.endswith('.json'):
                continue
            
            jp = os.path.join(json_dir, jf)
            total += 1
            
            try:
                with open(jp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if data.get('event_src', ''):
                    skipped += 1
                    continue
                
                # Extract year from filename
                pdf_name = jf.replace('.json', '.pdf')
                year = extract_year_from_filename(pdf_name)
                url = reconstruct_url(pdf_name, year)
                
                if url:
                    data['event_src'] = url
                    with open(jp, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    updated += 1
                else:
                    print(f"  SKIP (no URL pattern): {season}/{jf}")
                    skipped += 1
                    
            except Exception as e:
                print(f"  ERROR: {season}/{jf}: {e}")
                errors += 1
    
    print(f"\nDONE: {total} total, {updated} updated, {skipped} skipped, {errors} errors")

if __name__ == '__main__':
    main()
