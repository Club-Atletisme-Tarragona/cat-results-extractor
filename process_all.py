#!/usr/bin/env python3
"""
Script principal per descarregar i processar tots els PDFs de resultats
de la federació catalana d'atletisme que continguin atletes del CATT.

Flux:
1. Descarrega l'XLS de competicions (Competicions.xls)
2. Llegeix les URLs dels PDFs de resultats
3. Per a cada PDF:
   - Si el JSON ja existeix a json/, el salta
   - Si no, descarrega el PDF temporalment
   - Comprova si conté "CATT" o "CA Tarragona"
   - Si sí, executa extract_catt.py
   - Mou el JSON generat a json/
   - Borra el PDF temporal
4. Fa commit i push dels nous fitxers JSON
"""

import subprocess
import sys
import re
import json
import os
import shutil
import tempfile
from datetime import datetime


XLS_URL = "https://fcatletisme.cat/export/Competicions.xls"
JSON_DIR = "json"
CATT_PATTERNS = [r'\bCATT\b', r'\bCA\s+Tarragona\b', r'\bClub\s+Atletisme\s+Tarragona\b']


def download_xls():
    """Descarrega l'XLS de competicions."""
    print("Descarregant XLS de competicions...")
    result = subprocess.run(
        ["curl", "-sL", XLS_URL, "-o", "Competicions.xls"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error descarregant XLS: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print("  XLS descarregat correctament.")


def read_xls_results():
    """Llegeix l'XLS i retorna una llista de (url, titol) per a cada competició amb resultats."""
    try:
        import xlrd
    except ImportError:
        print("Error: xlrd no està instal·lat. Instal·la'l amb: pip install xlrd", file=sys.stderr)
        sys.exit(1)

    wb = xlrd.open_workbook("Competicions.xls")
    sheet = wb.sheets()[0]

    results = []
    for row in range(1, sheet.nrows):
        url = sheet.cell_value(row, 10).strip()  # Columna "Resultats"
        titol = sheet.cell_value(row, 2).strip()  # Columna "Titol"
        if url:
            results.append((url, titol))

    print(f"  Trobades {len(results)} competicions amb resultats.")
    return results


def download_pdf(pdf_url, temp_dir):
    """Descarrega un PDF al directori temporal. Retorna la ruta del fitxer o None."""
    filename = os.path.basename(pdf_url)
    pdf_path = os.path.join(temp_dir, filename)

    result = subprocess.run(
        ["curl", "-sL", pdf_url, "-o", pdf_path],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not os.path.exists(pdf_path):
        return None
    return pdf_path


def has_catt_in_pdf(pdf_path):
    """Comprova si un PDF conté referències al CATT."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False

    text = result.stdout
    for pattern in CATT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def process_pdf(pdf_path, json_path):
    """Executa extract_catt.py sobre un PDF i retorna True si ha generat JSON."""
    extract_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_catt.py")
    result = subprocess.run(
        [sys.executable, extract_script, pdf_path],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"    Error processant PDF: {result.stderr[:200]}")
        return False
    if not os.path.exists(json_path):
        return False
    return True


def move_json(pdf_path, json_path):
    """Mou el JSON generat al directori json/ amb el nom correcte."""
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    dest = os.path.join(JSON_DIR, base + ".json")

    if os.path.exists(dest):
        return dest

    shutil.move(json_path, dest)
    return dest


def commit_and_push(new_jsons):
    """Fa commit i push dels fitxers JSON nous."""
    if not new_jsons:
        print("\nNo hi ha fitxers nous per commit.")
        return

    print(f"\nFent commit de {len(new_jsons)} fitxers nous...")

    # Configurar git user (necessari per al commit de GitHub Actions)
    subprocess.run(
        ["git", "config", "user.name", "cat-results-bot"],
        capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "bot@cat-results.local"],
        capture_output=True
    )

    # Afegir fitxers nous
    for json_file in new_jsons:
        subprocess.run(["git", "add", json_file], capture_output=True)

    # Comprovar si hi ha canvis
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("No hi ha canvis per commit.")
        return

    # Commit
    commit_msg = f"Processar PDFs CATT - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        capture_output=True, text=True
    )

    # Push
    result = subprocess.run(
        ["git", "push"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        print(f"  Push completat correctament.")
    else:
        print(f"  Error fent push: {result.stderr[:200]}", file=sys.stderr)
        # No sortim amb error - potser no hi ha remote configurat


def main():
    print("=" * 60)
    print("Cat Results Extractor - Processador Automàtic")
    print("=" * 60)

    # Assegurar que el directori json/ existeix
    os.makedirs(JSON_DIR, exist_ok=True)

    # Llistar JSONs ja processats
    existing_jsons = set()
    if os.path.exists(JSON_DIR):
        for f in os.listdir(JSON_DIR):
            if f.endswith(".json"):
                base = os.path.splitext(f)[0]
                existing_jsons.add(base)

    print(f"\nJSONs ja processats: {len(existing_jsons)}")

    # Descarregar i llegir XLS
    download_xls()
    competitions = read_xls_results()

    # Processar cada PDF
    processed = 0
    skipped_already = 0
    skipped_no_catt = 0
    skipped_error = 0
    new_jsons = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, (url, titol) in enumerate(competitions):
            print(f"\n[{i+1}/{len(competitions)}] {titol}")
            print(f"  URL: {url[:100]}...")

            # Comprovar si ja s'ha processat
            # Extreure el nom base de l'URL (ex: resultat-20260104-catcombinadesmasterpcsabadell)
            url_base = os.path.splitext(os.path.basename(url))[0]

            if url_base in existing_jsons:
                print(f"  Saltat (JSON ja existeix)")
                skipped_already += 1
                continue

            # Descarregar PDF
            pdf_path = download_pdf(url, temp_dir)
            if not pdf_path:
                print(f"  Error descarregant PDF")
                skipped_error += 1
                continue

            # Comprovar si conté CATT
            print(f"  Comprovant si conté CATT...")
            if not has_catt_in_pdf(pdf_path):
                print(f"  Saltat (no conté CATT)")
                skipped_no_catt += 1
                os.remove(pdf_path)
                continue

            print(f"  Conté CATT! Processant...")

            # Processar amb extract_catt.py
            json_path = os.path.splitext(pdf_path)[0] + ".json"
            if process_pdf(pdf_path, json_path):
                # Moure el JSON a json/
                dest = move_json(pdf_path, json_path)
                if dest:
                    new_jsons.append(dest)
                    print(f"  Processat: {dest}")
                    processed += 1
                else:
                    print(f"  JSON ja existia al dir json/")
                    processed += 1
            else:
                print(f"  Error processant PDF amb extract_catt.py")
                skipped_error += 1

            # Netejar PDF temporal
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if os.path.exists(json_path) and not os.path.exists(os.path.join(JSON_DIR, os.path.basename(json_path))):
                os.remove(json_path)

    # Resum
    print("\n" + "=" * 60)
    print("RESUM")
    print("=" * 60)
    print(f"  Processats:      {processed}")
    print(f"  Saltats (ja fets): {skipped_already}")
    print(f"  Saltats (sense CATT): {skipped_no_catt}")
    print(f"  Errors:          {skipped_error}")
    print(f"  Nous JSONs:      {len(new_jsons)}")

    # Commit i push
    commit_and_push(new_jsons)

    print("\nDone!")


if __name__ == "__main__":
    main()
