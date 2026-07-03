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
import time
from datetime import datetime


def log(msg):
    """Print a log message with timestamp [YYYY-MM-DD HH:ii]."""
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M]")
    print(f"{ts} {msg}")

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
    """Save tracking file, removing duplicates."""
    deduped = {
        "success": list(dict.fromkeys(tracking.get("success", []))),
        "fail": list(dict.fromkeys(tracking.get("fail", []))),
        "no_cat_results": list(dict.fromkeys(tracking.get("no_cat_results", []))),
    }
    with open(TRACKING_FILE, "w") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)


XLS_PATH = "Competicions.xls"
XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2 / .xls
XLS_MIN_BYTES = 4096
XLS_DOWNLOAD_RETRIES = 3
XLS_RETRY_DELAY_SEC = 15


def _is_valid_xls(path):
    """Comprova que el fitxer descarregat és un XLS real (no HTML d'error)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False, "fitxer no accessible"
    if size < XLS_MIN_BYTES:
        return False, f"mida massa petita ({size} bytes)"
    with open(path, "rb") as f:
        header = f.read(8)
    if header != XLS_MAGIC:
        with open(path, "rb") as f:
            preview = f.read(120).decode("utf-8", errors="replace").replace("\n", " ")
        return False, f"capçalera invàlida (no és OLE/XLS): {preview[:80]}..."
    return True, None


def download_xls():
    """Descarrega l'XLS de competicions amb reintents i validació."""
    log("Descarregant XLS de competicions...")
    log(f"  URL: {XLS_URL}")

    curl_cmd = [
        "curl",
        "-fsSL",
        "--retry",
        "2",
        "--retry-delay",
        "5",
        "--connect-timeout",
        "30",
        "--max-time",
        "120",
        XLS_URL,
        "-o",
        XLS_PATH,
    ]

    last_error = None
    for attempt in range(1, XLS_DOWNLOAD_RETRIES + 1):
        if attempt > 1:
            log(f"  Reintent {attempt}/{XLS_DOWNLOAD_RETRIES} d'aquí a {XLS_RETRY_DELAY_SEC}s...")
            time.sleep(XLS_RETRY_DELAY_SEC)

        result = subprocess.run(curl_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            last_error = result.stderr.strip() or f"curl exit code {result.returncode}"
            log(f"  Error descarregant XLS (intent {attempt}): {last_error[:200]}")
            continue

        ok, reason = _is_valid_xls(XLS_PATH)
        if ok:
            size = os.path.getsize(XLS_PATH)
            log(f"  XLS descarregat correctament ({size} bytes).")
            return

        last_error = reason
        log(f"  XLS invàlid (intent {attempt}): {reason}")

    log(f"Error descarregant XLS després de {XLS_DOWNLOAD_RETRIES} intents: {last_error}")
    sys.exit(1)


def read_xls_results():
    """Llegeix l'XLS i retorna una llista de (url, titol) per a cada competició amb resultats."""
    try:
        import xlrd
    except ImportError:
        log("Error: xlrd no està instal·lat. Instal·la'l amb: pip install xlrd")
        sys.exit(1)

    wb = xlrd.open_workbook(XLS_PATH)
    sheet = wb.sheets()[0]

    results = []
    for row in range(1, sheet.nrows):
        url = sheet.cell_value(row, 10).strip()  # Columna "Resultats"
        titol = sheet.cell_value(row, 2).strip()  # Columna "Titol"
        if url:
            results.append((url, titol))

    log(f"  Trobades {len(results)} competicions amb resultats.")
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
        log(f"    Error processant PDF: {result.stderr[:200]}")
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
        log(f"    Error processant PDF amb extract_marcha: {result.stderr[:200]}")
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
        log(f"    Moure a imported: {json_name}")
        return True
    return False


def commit_and_push(new_jsons):
    """Fa commit i push dels fitxers JSON nous."""
    if not new_jsons:
        log("\nNo hi ha fitxers nous per commit.")
        return

    log(f"\nFent commit de {len(new_jsons)} fitxers nous...")

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
        log("No hi ha canvis per commit.")
        return

    # Commit
    commit_msg = f"Processar PDFs CATT - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)

    # Push
    result = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log("  Push completat correctament.")
    else:
        log(f"  Error fent push: {result.stderr[:200]}")
        # No sortim amb error - potser no hi ha remote configurat


def main():
    log("=" * 60)
    log("Cat Results Extractor - Processador Automàtic")
    log("=" * 60)

    # Assegurar que el directori json/ existeix
    os.makedirs(JSON_DIR, exist_ok=True)

    # Carregar tracking i fitxers importats
    loaded = load_tracking()
    log(f"\nTracking carregat: {len(loaded)} URLs processades")
    log(f"Fitxers importats: {len(imported_files)}")

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
            log(f"Tracking antic carregat: {len(tracking['success'])} success, {len(tracking['fail'])} fail, {len(tracking['no_cat_results'])} no_cat_results")
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
            log(f"[{i + 1}/{len(competitions)}] {titol}")
            log(f"  URL: {url[:100]}...")

            # Check if already processed (from tracking)
            if url in loaded:
                log(f"  Saltat (ja processat - tracking)")
                skipped_already += 1
                continue

            log("  Processant per primera vegada...")

            # Check if already exists as JSON (with results > 0)
            url_base = os.path.splitext(os.path.basename(url))[0]
            json_file = os.path.join(JSON_DIR, url_base + ".json")
            if os.path.exists(json_file):
                existing_count = count_results(json_file)
                if existing_count > 0:
                    log(f"  Saltat (JSON ja existeix amb {existing_count} resultats)")
                    skipped_already += 1
                    # Add to tracking so we don't re-check next time
                    tracking["success"].append(url)
                    log(f"  Afegit a success: {url[:80]}...")
                    continue
                else:
                    log("  JSON existent amb 0 resultats, re-processant...")
            else:
                log("  Cap JSON previ trobat a json/")

            # Also check if already in imported
            if url_base in imported_files:
                log(f"  Saltat (ja importat a json/imported/)")
                skipped_already += 1
                tracking["success"].append(url)
                log(f"  Afegit a success (importat): {url[:80]}...")
                continue

            # Descarregar PDF
            pdf_path = download_pdf(url, temp_dir)
            if not pdf_path:
                log(f"  Error descarregant PDF (HTTP o fitxer no creat)")
                skipped_error += 1
                tracking["fail"].append(url)
                log(f"  Afegit a fail (download): {url[:80]}...")
                continue
            else:
                log(f"  PDF descarregat ({os.path.getsize(pdf_path)} bytes)")

            # Comprovar si conté CATT
            log("  Comprovant si conté CATT...")
            if not has_catt_in_pdf(pdf_path):
                log(f"  Saltat (no conté CATT - anirà a no_cat_results)")
                skipped_no_catt += 1
                tracking["no_cat_results"].append(url)
                log(f"  Afegit a no_cat_results: {url[:80]}...")
                os.remove(pdf_path)
                continue

            log("  Conté CATT! Processant amb extract_catt.py...")

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
                        log(f"  OK - {catt_result_count} resultat(s) extrets -> {dest}")
                        processed += 1
                        tracking["success"].append(url)
                        log(f"  Afegit a success (resultats): {url[:80]}...")
                    else:
                        log(f"  OK - {catt_result_count} resultat(s) extrets (JSON ja existia a json/)")
                        processed += 1
                        tracking["success"].append(url)
                        log(f"  Afegit a success (resultats, JSON existent): {url[:80]}...")
                else:
                    # extract_catt.py ran but found no results - try extract_marcha.py as fallback
                    log("  extract_catt.py ha finalitzat però 0 resultats. Provant extract_marcha.py com a fallback...")
                    if process_marcha(pdf_path, json_path, url):
                        dest = move_json(pdf_path, json_path)
                        if dest:
                            new_jsons.append(dest)
                            log(f"  OK (marcha) - resultats extrets amb extract_marcha.py -> {dest}")
                            processed += 1
                            used_marcha += 1
                            tracking["success"].append(url)
                            log(f"  Afegit a success (marcha): {url[:80]}...")
                        else:
                            log(f"  OK (marcha) - resultats extrets amb extract_marcha.py (JSON ja existia)")
                            processed += 1
                            used_marcha += 1
                            tracking["success"].append(url)
                            log(f"  Afegit a success (marcha, JSON existent): {url[:80]}...")
                    else:
                        log("  FAIL - extract_marcha.py tampoc ha trobat resultats -> anirà a fail")
                        skipped_error += 1
                        tracking["fail"].append(url)
                        log(f"  Afegit a fail (marcha 0 resultats): {url[:80]}...")
            else:
                # extract_catt.py failed completely - try extract_marcha.py as fallback
                log("  FAIL - extract_catt.py ha fallat (error d'execució). Provant extract_marcha.py...")
                if process_marcha(pdf_path, json_path, url):
                    dest = move_json(pdf_path, json_path)
                    if dest:
                        new_jsons.append(dest)
                        log(f"  OK (marcha fallback) - resultats extrets amb extract_marcha.py -> {dest}")
                        processed += 1
                        used_marcha += 1
                        tracking["success"].append(url)
                        log(f"  Afegit a success (marcha fallback): {url[:80]}...")
                    else:
                        log(f"  OK (marcha fallback) - resultats extrets amb extract_marcha.py (JSON ja existia)")
                        processed += 1
                        used_marcha += 1
                        tracking["success"].append(url)
                        log(f"  Afegit a success (marcha fallback, JSON existent): {url[:80]}...")
                else:
                    log("  FAIL - extract_marcha.py tampoc ha funcionat -> anirà a fail")
                    skipped_error += 1
                    tracking["fail"].append(url)
                    log(f"  Afegit a fail (extract fallit): {url[:80]}...")

            # Netejar PDF temporal
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if os.path.exists(json_path) and not os.path.exists(
                os.path.join(JSON_DIR, os.path.basename(json_path))
            ):
                os.remove(json_path)

    # Resum
    log("=" * 60)
    log("RESUM")
    log("=" * 60)
    log(f"  Processats:         {processed}")
    log(f"  Saltats (ja fets):  {skipped_already}")
    log(f"  Saltats (sense CATT): {skipped_no_catt}")
    log(f"  Errors:             {skipped_error}")
    log(f"  Processats (marcha): {used_marcha}")
    log(f"  Nous JSONs:         {len(new_jsons)}")

    if new_jsons:
        log("Nous fitxers JSON:")
        for jf in new_jsons:
            try:
                with open(jf, "r", encoding="utf-8") as jf2:
                    jdata = json.load(jf2)
                nres = jdata.get("total_results", len(jdata.get("results", [])))
            except:
                nres = "?"
            log(f"  - {os.path.basename(jf)} ({nres} resultats)")

    # Save tracking
    save_tracking(tracking)
    log(f"\nTracking actualitzat: {TRACKING_FILE}")
    log(f"  success: {len(tracking['success'])} URLs")
    log(f"  fail: {len(tracking['fail'])} URLs")
    log(f"  no_cat_results: {len(tracking['no_cat_results'])} URLs")

    # Commit i push
    # commit_and_push(new_jsons)

    log("\nDone!")


if __name__ == "__main__":
    main()
