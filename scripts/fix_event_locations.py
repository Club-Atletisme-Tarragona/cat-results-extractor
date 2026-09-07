#!/usr/bin/env python3
"""Fix event_location in season JSONs by extracting from the source PDF.

Scans the first ~15 lines of the PDF text for known Catalan/Spanish city names.
The location is usually in the header: 'Sabadell, 20-21 de gener de 2005'

Usage:
    python3 scripts/fix_event_locations.py --dry-run --batch 50
    python3 scripts/fix_event_locations.py --season 2010
    python3 scripts/fix_event_locations.py
"""
import re, json, glob, subprocess, sys, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path('/tmp/fca_locations')

# Known cities (sorted longest-first for greedy matching)
KNOWN_CITIES = sorted([
    "El Prat de Llobregat", "L'Hospitalet de Llobregat", "Vilanova i La Geltrú",
    "Sant Cugat del Vallès", "Cornellà de Llobregat", "Sant Boi de Llobregat",
    "Barberà del Vallès", "Cerdanyola del Vallès", "Sant Andreu de la Barca",
    "Olesa de Montserrat", "Vilafranca del Penedès", "Mollet del Vallès",
    "La Roca del Vallès", "Sant Vicenç dels Horts", "Santa Perpètua de Mogoda",
    "Santa Coloma de Gramenet", "Sant Adrià de Besòs", "Sant Just Desvern",
    "Sant Feliu de Guíxols", "Sant Carles de la Ràpita", "La Bisbal del Penedès",
    "La Seu d'Urgell", "Malgrat de Mar", "Sant Pol de Mar", "Premià de Mar",
    "Arenys de Mar", "Sant Celoni", "Castellar del Vallès", "Montcada i Reixac",
    "Viladecavalls", "Palau-solità i Plegrafites", "Sant Jaume d'Enveja",
    "Barcelona", "Sabadell", "Terrassa", "Tarragona", "Reus", "Lleida",
    "Girona", "Badalona", "Mataró", "Manresa", "Igualada", "Granollers",
    "Mollet", "Vilafranca", "Rubí", "Sant Cugat", "Cornellà", "El Prat",
    "L'Hospitalet", "Cerdanyola", "Sant Boi", "Barberà", "Cambrils",
    "Tortosa", "Amposta", "Valls", "El Vendrell", "Calafell", "Sitges",
    "Castelldefels", "Gavà", "Olesa", "Esparreguera", "Martorell",
    "Palafrugell", "Blanes", "Lloret de Mar", "Lloret", "Figueres", "Olot",
    "Ripoll", "Puigcerdà", "La Seu", "Tremp", "Balaguer", "Mollerussa",
    "Fraga", "Monzón", "Vilanova", "Premià", "El Masnou", "Alella",
    "Teià", "Arenys", "Calella", "Malgrat", "Sant Feliu", "Sant Pol",
    "Tordera", "Breda", "Sant Celoni", "Cardedeu", "Canovelles",
    "La Roca", "Salt", "Sarrià", "Vilablareix", "Celrà", "Banyoles",
    "Porqueres", "Camprodon", "Alp", "Ponts", "Santpedor", "Sallent",
    "Balsareny", "Navàs", "Súria", "Cardona", "Òdena", "Castellbisbal",
    "Ripollet", "Montcada", "Santa Perpètua", "Polinyà", "Vacarisses",
    "Viladecavalls", "Castellar", "Sant Vicenç", "Sant Just",
    "Sant Adrià", "Santa Coloma", "Molins", "Masnou", "Argentona",
    "Cabrera de Mar", "Vilassar de Mar", "Vilassar", "Montgat", "Tiana",
    "Torredembarra", "Creixell", "Altafulla", "La Pobla de Mafumet",
    "La Pobla", "Sant Carles", "Masdenverge", "Santa Bàrbara", "Roquetes",
    "La Bisbal", "Vila-seca", "Salou", "Coma-ruga", "Garraf",
    "Camp Clar", "Serrahima", "Vic", "Vic (Tarragona)", "Joan Serrahima",
    "Vilanova i la Geltrú",
], key=len, reverse=True)


def extract_location(pdf_text):
    """Extract the city/venue from the first ~15 lines of a PDF text."""
    lines = pdf_text.splitlines()[:25]
    text = '\n'.join(lines)
    text_lower = text.lower()
    for city in KNOWN_CITIES:
        if city.lower() in text_lower:
            return city
    return None


def get_pdf_text(src_url, tmp_dir):
    """Download PDF from src_url and extract text."""
    fname = src_url.split('/')[-1]
    pdf_path = tmp_dir / fname
    txt_path = tmp_dir / (fname.replace('.pdf', '.txt'))

    if txt_path.exists():
        return txt_path.read_text()

    if not pdf_path.exists():
        result = subprocess.run(
            ['curl', '-sL', '--max-time', '30', '-o', str(pdf_path), src_url],
            capture_output=True, timeout=35)
        if result.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size < 500:
            return None

    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf_path), str(txt_path)],
        capture_output=True, timeout=15)
    if result.returncode != 0 or not txt_path.exists():
        return None

    return txt_path.read_text()


def needs_fix(loc):
    """Check if the location is garbage/empty."""
    if not loc or not loc.strip():
        return True
    for bad in ('Club', 'Lic', 'Semifinal', 'Final', 'Ronda', 'Pto', 'Dor',
                'RESULTATS', '60m', '100m', '200m', '300m', '80m', '150m',
                '1.000m', '600m', 'Pto'):
        if bad in loc:
            return True
    if len(loc) > 80:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--season', help='fix one season only')
    ap.add_argument('--batch', type=int, default=50, help='max files per run')
    args = ap.parse_args()

    TMP.mkdir(exist_ok=True)

    to_fix = []
    for season in range(2005, 2026):
        s = str(season)
        if args.season and s != args.season:
            continue
        for f in sorted(glob.glob(str(REPO / f'seasons/{s}/json/*.json'))):
            try: d = json.load(open(f))
            except: continue
            loc = d.get('event_location', '').strip()
            src = d.get('event_src', '')
            if needs_fix(loc) and src:
                to_fix.append((s, f, src, loc[:30]))

    print(f'Files needing location fix: {len(to_fix)}')
    if not to_fix:
        print('All locations OK')
        return

    batch = to_fix[:args.batch]
    fixed = failed = 0
    for s, f, src, old_loc in batch:
        fname = Path(f).name
        try:
            pdf_text = get_pdf_text(src, TMP)
            if not pdf_text:
                failed += 1
                continue
            loc = extract_location(pdf_text)
            if loc:
                if not args.dry_run:
                    d = json.load(open(f))
                    d['event_location'] = loc
                    Path(f).write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
                fixed += 1
                print(f'  \u2713 {s}/{fname[:42]:42s} \u2192 {loc}')
            else:
                failed += 1
                print(f'  \u2717 {s}/{fname[:42]:42s} (no city in PDF header)')
        except Exception as e:
            failed += 1
            print(f'  \u2717 {s}/{fname[:42]:42s} ({e})')

    print(f'\nProcessed: {len(batch)} | Fixed: {fixed} | Failed: {failed}')
    print(f'Remaining: {len(to_fix) - len(batch)}')
    if args.dry_run:
        print('(dry run)')


if __name__ == '__main__':
    main()
