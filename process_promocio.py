#!/usr/bin/env python3
"""
Script batch per processar tots els PDFs de la Lliga de Promoció 2008-2009.
Escrapa les URLs dels PDFs de les pàgines HTML de la FC Atletisme antiga,
baixa cada PDF i executa extract_promocio.py per extreure resultats CATT.

Fonts:
  https://old.fcatletisme.cat/Promocio/promocio2009/calendari.html
  https://old.fcatletisme.cat/Promocio/promocio2009/lligapromocio/jornades.html
"""

import subprocess
import sys
import re
import json
import os
import time
import urllib.request
from urllib.parse import urljoin


# Page URLs and their base directories
PAGES = [
    ("https://old.fcatletisme.cat/Promocio/promocio2009/calendari.html",
     "https://old.fcatletisme.cat/Promocio/promocio2009/"),
    ("https://old.fcatletisme.cat/Promocio/promocio2009/lligapromocio/jornades.html",
     "https://old.fcatletisme.cat/Promocio/promocio2009/lligapromocio/"),
]

PDF_DIR = "pdfs/promocio_2008_2009"
JSON_DIR_2008 = "json/promocio/2008"
JSON_DIR_2009 = "json/promocio/2009"
TRACKING_FILE = "track-promocio.json"


def load_tracking():
    """Load tracking file and return set of already processed URLs."""
    processed = set()
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f:
                data = json.load(f)
            for url in data.get("success", []):
                if url:
                    processed.add(url)
        except (json.JSONDecodeError, KeyError):
            pass
    return processed


def save_tracking(tracking):
    """Save tracking file."""
    with open(TRACKING_FILE, "w") as f:
        json.dump(tracking, f, indent=2, ensure_ascii=False)


def fetch_url(url):
    """Fetch URL content and return text."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}", file=sys.stderr)
        return None


def extract_pdf_links(html, base_url):
    """Extract PDF links from HTML content, resolving relative URLs."""
    if not html:
        return []
    
    links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html)
    absolute = []
    for link in links:
        # Resolve relative URLs
        resolved = urljoin(base_url, link)
        absolute.append(resolved)
    
    return absolute


def extract_date_from_url(url):
    """Try to extract year from URL filename pattern like resulXXX221108.pdf."""
    m = re.search(r'(\d{2})(\d{2})(\d{2})\.pdf', url, re.IGNORECASE)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        full_year = f"20{year}"
        return full_year
    return None


def download_pdf(url, pdf_dir):
    """Download a PDF file. Returns local path or None."""
    filename = os.path.basename(url)
    # Clean filename
    filename = re.sub(r'[^a-zA-Z0-9_.\-]', '_', filename)
    local_path = os.path.join(pdf_dir, filename)
    
    if os.path.exists(local_path):
        return local_path
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
        
        with open(local_path, 'wb') as f:
            f.write(data)
        
        return local_path
    except Exception as e:
        print(f"  ERROR downloading {url}: {e}", file=sys.stderr)
        return None


def process_pdf(pdf_path, json_dir, pdf_url=""):
    """Run extract_promocio.py on a PDF file."""
    output_dir = json_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    try:
        cmd = ["python3", "extract_promocio.py", pdf_path, output_dir]
        if pdf_url:
            cmd.append(pdf_url)
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30
        )
        
        # Count results from output
        total = 0
        for line in result.stdout.split('\n'):
            m = re.search(r'Found (\d+) result', line)
            if m:
                total = int(m.group(1))
        
        return total
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT processing {pdf_path}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"  ERROR processing {pdf_path}: {e}", file=sys.stderr)
        return 0


def main():
    print("=" * 60)
    print("PROCESSING PROMOCIO 2008-2009 RESULTS")
    print("=" * 60)
    
    # Create directories
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(JSON_DIR_2008, exist_ok=True)
    os.makedirs(JSON_DIR_2009, exist_ok=True)
    
    # Load tracking
    loaded = load_tracking()
    print(f"\nTracking carregat: {len(loaded)} URLs processades")
    
    # Collect all PDF URLs from all pages
    all_pdf_urls = set()
    
    for page_url, base_url in PAGES:
        print(f"\nScraping: {page_url}")
        html = fetch_url(page_url)
        if html:
            pdfs = extract_pdf_links(html, base_url)
            # Filter out non-result PDFs (regulations, schedules, etc.)
            result_pdfs = [p for p in pdfs if 'resul' in p.lower() or 'result' in p.lower()]
            print(f"  Found {len(pdfs)} total PDFs, {len(result_pdfs)} result PDFs")
            for pdf in result_pdfs:
                all_pdf_urls.add(pdf)
        else:
            print(f"  WARNING: Could not fetch {page_url}", file=sys.stderr)
    
    print(f"\nTotal unique result PDFs found: {len(all_pdf_urls)}")
    
    # Process each PDF
    tracking = {"success": [], "fail": [], "no_cat_results": []}
    # Retain already processed URLs from existing tracking file
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f:
                old_tracking = json.load(f)
            tracking["success"] = list(old_tracking.get("success", []))
            tracking["fail"] = list(old_tracking.get("fail", []))
            tracking["no_cat_results"] = list(old_tracking.get("no_cat_results", []))
        except (json.JSONDecodeError, KeyError):
            pass
    
    stats = {"total": 0, "downloaded": 0, "processed": 0, "with_results": 0, "errors": 0}
    results_by_year = {}
    
    for i, pdf_url in enumerate(sorted(all_pdf_urls), 1):
        print(f"\n[{i}/{len(all_pdf_urls)}] {pdf_url}")
        stats["total"] += 1
        
        # Check if already processed (from tracking)
        if pdf_url in loaded:
            print(f"  Saltat (ja processat - tracking)")
            continue
        
        # Determine year from URL
        year = extract_date_from_url(pdf_url)
        if year == "2008":
            json_dir = JSON_DIR_2008
        elif year == "2009":
            json_dir = JSON_DIR_2009
        else:
            json_dir = JSON_DIR_2008  # Default
        
        # Download PDF
        local_path = download_pdf(pdf_url, PDF_DIR)
        if not local_path:
            stats["errors"] += 1
            tracking["fail"].append(pdf_url)
            continue
        
        stats["downloaded"] += 1
        print(f"  Year: {year}, JSON dir: {json_dir}")
        
        # Process PDF
        time.sleep(0.5)  # Be polite to the server
        num_results = process_pdf(local_path, json_dir, pdf_url)
        
        if num_results > 0:
            stats["with_results"] += 1
            results_by_year[year] = results_by_year.get(year, 0) + num_results
            print(f"  Found {num_results} CATT results!")
            tracking["success"].append(pdf_url)
            # Add to loaded so we don't re-check
            loaded.add(pdf_url)
        else:
            print(f"  No CATT athletes found")
            tracking["no_cat_results"].append(pdf_url)
    
    # Write tracking file
    tracking["summary"] = {
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "with_results": stats["with_results"],
        "errors": stats["errors"],
        "no_cat_results": len(tracking["no_cat_results"]),
        "total_results": sum(results_by_year.values()) if results_by_year else 0,
    }
    
    save_tracking(tracking)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total PDFs found:       {stats['total']}")
    print(f"  Successfully downloaded: {stats['downloaded']}")
    print(f"  With CATT results:       {stats['with_results']}")
    print(f"  No CATT results:         {len(tracking['no_cat_results'])}")
    print(f"  Errors:                  {stats['errors']}")
    print(f"\n  Total results:           {tracking['summary']['total_results']}")
    print(f"\n  Results by year:")
    for year in sorted((y for y in results_by_year.keys() if y is not None)):
        print(f"    {year}: {results_by_year[year]} results")
    if None in results_by_year:
        print(f"    (unknown year): {results_by_year[None]} results")
    print(f"\n  Tracking file: {TRACKING_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
