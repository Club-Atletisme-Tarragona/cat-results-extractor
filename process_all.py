#!/usr/bin/env python3
"""
Script principal per descarregar i processar tots els PDFs de resultats
de la federació catalana d'atletisme que continguin atletes del CATT.

Flux:
1. Descarrega l'XLS de competicions (Competicions.xls)
2. Llegeix les URLs dels PDFs de resultats
3. Per a cada PDF:
   - Si el PDF ja està al tracking, el salta
   - Si no, descarrega el PDF temporalment
   - Comprova si conté "CATT" o "CA Tarragona"
   - Si sí, executa extract_catt.py amb la URL source
   - Si extract_catt.py no troba cap resultat, executa extract_marcha.py
   - Mou el JSON generat a json/
   - Borra el PDF temporal
4. Actualitza el fitxer de tracking
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

XLS_URL = "https://fcatletisme.cat/export/Competicions.xls"
JSON_DIR = "json"
TRACKING_FILE = "track-catt.json"
CATT_PATTERNS = [
    r"\bCATT\b",
    r"\bCA\s+Tarragona\b",
    r"\bClub\s+Atletisme\s+Tarragona\b",
]

imported_files = set()


def load_imported():
    """Load list of already imported JSON filenames."""
    global imported_files
    imported_dir = os.path.join(JSON_DIR, "imported")
    if os.path.exists(imported_dir):
        imported_files = set(
            f.replace(".json", "") for f in os.listdir(imported_dir) if f.endswith(".json")
        )


def load_tracking():
    """Load tracking file and return set of already processed URLs."""
    load_imported()
    processed = set()
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, "r") as f:
                data = json.load(f)
            for category in ("success", "no_cat_results", "fail"):
                for url in data.get(category, []):
                    if url:
                        processed.add(url)
        except (json.JSONDecodeError, KeyError):
            pass
    return processed


def save_tracking(tracking):
    """Save tracking file."""
    with open(TRACKING_FILE, "w") as f:
        json.dump(tracking, f, indent=2, ensure_ascii=False)


def download_xls():
    """Descarrega l'XLS de competicions."""
    print("Descarregant XLS de competicions...")
    result = subprocess.run(
        ["curl", "-sL", XLS_URL, "-o", "Competicions.xls"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error descarregant XLS: {result.stderr[:200]}", file=sys.stderr)
        sys.exit(1)
    print("  XLS descarregat correctament.")


def read_xls_results():
    """Llegeix l'XLS i retorna una llista de (url, titol) per a cada competició amb resultats."""
    try:
        import xlrd
    except ImportError:
        print(
            "Error: xlrd no està instal·lat. Instal·la'l amb: pip install xlrd",
            file=sys.stderr,
        )
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
        ["curl", "-sL", pdf_url, "-o", pdf_path], capture_output=True, text=True
    )
    if result.returncode != 0 or not os.path.exists(pdf_path):
        return None
    return pdf_path


def has_catt_in_pdf(pdf_path):
    """Comprova si un PDF conté referències al CATT."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return False

    text = result.stdout
    for pattern in CATT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def count_results(json_path):
    """Compta els resultats en un JSON generat."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("total_results", len(data.get("results", [])))
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        return 0


def process_pdf(pdf_path, json_path, source_url=""):
    """Executa extract_catt.py sobre un PDF i retorna True si ha generat JSON."""
    extract_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "extract_catt.py"
    )
    cmd = [sys.executable, extract_script, pdf_path]
    if source_url:
        cmd.append(source_url)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"    Error processant PDF: {result.stderr[:200]}")
        return False
    if not os.path.exists(json_path):
        return False
    return True


def is_marcha_pdf(pdf_url):
    """Check if a PDF URL/filename indicates a marcha (race walk) event."""
    filename = pdf_url.lower()
    return any(kw in filename for kw in ["marx", "marxa", "marcha"])


def process_marcha(pdf_path, json_path, source_url=""):
    """Executa extract_marcha.py sobre un PDF i retorna True si ha generat JSON amb resultats."""
    extract_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "extract_marcha.py"
    )
    cmd = [sys.executable, extract_script, pdf_path]
    if source_url:
        cmd.append(source_url)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"    Error processant PDF amb extract_marcha: {result.stderr[:200]}")
        return False
    # extract_marcha.py outputs to json/<basename>.json, check there
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    marcha_json = os.path.join(os.path.dirname(pdf_path), "json", base + ".json")
    if os.path.exists(marcha_json):
        # Copy to expected json_path so move_json works
        shutil.copy2(marcha_json, json_path)
        return True
    return False


def move_json(pdf_path, json_path):
    """Mou el JSON generat al directori json/ amb el nom correcte."""
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    dest = os.path.join(JSON_DIR, base + ".json")

    if os.path.exists(dest):
        return dest

    shutil.move(json_path, dest)
    return dest


def move_to_imported(json_name):
    """Mou un JSON ja existent a json/imported/."""
    src = os.path.join(JSON_DIR, json_name + ".json")
    dest_dir = os.path.join(JSON_DIR, "imported")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, json_name + ".json")
    if os.path.exists(src):
        shutil.move(src, dest)
        print(f"    Moure a imported: {json_name}")
        return True
    return False


def commit_and_push(new_jsons):
    """Fa commit i push dels fitxers JSON nous."""
    if not new_jsons:
        print("\nNo hi ha fitxers nous per commit.")
        return

    print(f"\nFent commit de {len(new_jsons)} fitxers nous...")

    # Configurar git user (necessari per al commit de GitHub Actions)
    subprocess.run(
        ["git", "config", "user.name", "cat-results-bot"], capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "bot@cat-results.local"], capture_output=True
    )

    # Afegir fitxers nous
    for json_file in new_jsons:
        subprocess.run(["git", "add", json_file], capture_output=True)

    # Comprovar si hi ha canvis
    status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("No hi ha canvis per commit.")
        return

    # Commit
    commit_msg = f"Processar PDFs CATT - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)

    # Push
    result = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=60)
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

    # Carregar tracking i fitxers importats
    loaded = load_tracking()
    print(f"\nTracking carregat: {len(loaded)} URLs processades")
    print(f"Fitxers importats: {len(imported_files)}")

    # Descarregar i llegir XLS
    download_xls()
    competitions = read_xls_results()

    # Processar cada PDF
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

    processed = 0
    skipped_already = 0
    skipped_no_catt = 0
    skipped_error = 0
    used_marcha = 0
    new_jsons = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, (url, titol) in enumerate(competitions):
            print(f"\n[{i + 1}/{len(competitions)}] {titol}")
            print(f"  URL: {url[:100]}...")

            # Check if already processed (from tracking)
            if url in loaded:
                print(f"  Saltat (ja processat - tracking)")
                skipped_already += 1
                continue

            # Check if already exists as JSON (with results > 0)
            url_base = os.path.splitext(os.path.basename(url))[0]
            json_file = os.path.join(JSON_DIR, url_base + ".json")
            if os.path.exists(json_file):
                existing_count = count_results(json_file)
                if existing_count > 0:
                    print(f"  Saltat (JSON ja existeix amb {existing_count} resultats)")
                    skipped_already += 1
                    # Add to tracking so we don't re-check next time
                    tracking["success"].append(url)
                    continue
                else:
                    print(f"  JSON existent amb 0 resultats, re-processant...")

            # Also check if already in imported
            if url_base in imported_files:
                print(f"  Saltat (ja importat)")
                skipped_already += 1
                tracking["success"].append(url)
                continue

            # Descarregar PDF
            pdf_path = download_pdf(url, temp_dir)
            if not pdf_path:
                print(f"  Error descarregant PDF")
                skipped_error += 1
                tracking["fail"].append(url)
                continue

            # Comprovar si conté CATT
            print(f"  Comprovant si conté CATT...")
            if not has_catt_in_pdf(pdf_path):
                print(f"  Saltat (no conté CATT)")
                skipped_no_catt += 1
                tracking["no_cat_results"].append(url)
                os.remove(pdf_path)
                continue

            print(f"  Conté CATT! Processant...")

            # Processar amb extract_catt.py
            json_path = os.path.splitext(pdf_path)[0] + ".json"

            # Always try extract_catt.py first (it handles marcha PDFs too)
            if process_pdf(pdf_path, json_path, url):
                # Check if extract_catt.py actually found results
                catt_result_count = count_results(json_path)
                if catt_result_count > 0:
                    dest = move_json(pdf_path, json_path)
                    if dest:
                        new_jsons.append(dest)
                        print(f"  Processat: {dest}")
                        processed += 1
                        tracking["success"].append(url)
                    else:
                        print(f"  JSON ja existia al dir json/")
                        processed += 1
                        tracking["success"].append(url)
                else:
                    # extract_catt.py ran but found no results - try extract_marcha.py as fallback
                    print(f"  extract_catt.py no ha trobat resultats. Provant extract_marcha.py...")
                    if process_marcha(pdf_path, json_path, url):
                        dest = move_json(pdf_path, json_path)
                        if dest:
                            new_jsons.append(dest)
                            print(f"  Processat amb extract_marcha: {dest}")
                            processed += 1
                            used_marcha += 1
                            tracking["success"].append(url)
                        else:
                            print(f"  JSON ja existia al dir json/")
                            processed += 1
                            used_marcha += 1
                            tracking["success"].append(url)
                    else:
                        print(f"  extract_marcha.py tampoc ha trobat resultats")
                        skipped_error += 1
                        tracking["fail"].append(url)
            else:
                # extract_catt.py failed completely - try extract_marcha.py as fallback
                print(f"  extract_catt.py ha fallat. Provant extract_marcha.py...")
                if process_marcha(pdf_path, json_path, url):
                    dest = move_json(pdf_path, json_path)
                    if dest:
                        new_jsons.append(dest)
                        print(f"  Processat amb extract_marcha: {dest}")
                        processed += 1
                        used_marcha += 1
                        tracking["success"].append(url)
                    else:
                        print(f"  JSON ja existia al dir json/")
                        processed += 1
                        used_marcha += 1
                        tracking["success"].append(url)
                else:
                    print(f"  Error processant PDF amb extract_catt.py i extract_marcha.py")
                    skipped_error += 1
                    tracking["fail"].append(url)

            # Netejar PDF temporal
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if os.path.exists(json_path) and not os.path.exists(
                os.path.join(JSON_DIR, os.path.basename(json_path))
            ):
                os.remove(json_path)

    # Resum
    print("\n" + "=" * 60)
    print("RESUM")
    print("=" * 60)
    print(f"  Processats:         {processed}")
    print(f"  Saltats (ja fets):  {skipped_already}")
    print(f"  Saltats (sense CATT): {skipped_no_catt}")
    print(f"  Errors:             {skipped_error}")
    print(f"  Processats (marcha): {used_marcha}")
    print(f"  Nous JSONs:         {len(new_jsons)}")

    # Save tracking
    save_tracking(tracking)
    print(f"\nTracking actualitzat: {TRACKING_FILE}")

    # Commit i push
    # commit_and_push(new_jsons)

    print("\nDone!")


if __name__ == "__main__":
    main()
