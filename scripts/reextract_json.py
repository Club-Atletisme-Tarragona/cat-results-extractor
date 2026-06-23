#!/usr/bin/env python3
"""Re-extract JSON files in json/ and json/imported/ using extract_catt.py."""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT_CATT = os.path.join(ROOT, "extract_catt.py")
EXTRACT_MARCHA = os.path.join(ROOT, "extract_marcha.py")
TRACK_FILE = os.path.join(ROOT, "track-catt.json")


def load_url_map():
    url_map = {}
    if os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for category in ("success", "fail", "no_cat_results"):
            for url in data.get(category, []):
                if url:
                    url_map[os.path.basename(url)] = url
    return url_map


def infer_url_from_filename(filename):
    base = os.path.splitext(filename)[0]
    m = re.match(r"resultat-(\d{4})(\d{2})\d{2}-", base)
    if m:
        year, month = m.group(1), m.group(2)
        return f"https://fcatletisme.cat/wp-content/uploads/{year}/{month}/{base}.pdf"
    if base.startswith("st_"):
        return f"https://www.rfeacontent.es/resultados/2026/short_track/{base}.pdf"
    if base.startswith(("al_", "2d_")):
        return f"https://www.rfeacontent.es/resultados/2026/airelibre/{base}.pdf"
    return ""


def find_cached_pdf(basename):
    for path in glob.glob(os.path.join(ROOT, "pdf_cache", "**", basename), recursive=True):
        if os.path.isfile(path):
            return path
    return ""


def download_pdf(url, dest):
    result = subprocess.run(
        ["curl", "-sL", "-f", url, "-o", dest],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 0


def add_position_null(data):
    changed = False
    for entry in data.get("results", []):
        if "position" not in entry:
            entry["position"] = None
            changed = True
    return changed


def run_extractor(script, pdf_path, source_url):
    cmd = [sys.executable, script, pdf_path]
    if source_url:
        cmd.append(source_url)
    cmd.append("--quiet")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return result.returncode == 0


def process_json(json_path, url_map):
    with open(json_path, encoding="utf-8") as f:
        original = json.load(f)

    basename = os.path.basename(json_path)
    pdf_name = basename.replace(".json", ".pdf")
    source_url = original.get("event_src") or original.get("source_url") or ""
    if not source_url:
        source_url = url_map.get(pdf_name, "")
    if not source_url:
        source_url = infer_url_from_filename(basename)

    if not source_url:
        if add_position_null(original):
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(original, f, ensure_ascii=False, indent=2)
        return "no_url", 0

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, pdf_name)
        cached = find_cached_pdf(pdf_name)
        if cached:
            shutil.copy2(cached, pdf_path)
        elif not download_pdf(source_url, pdf_path):
            if add_position_null(original):
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(original, f, ensure_ascii=False, indent=2)
            return "download_fail", 0

        generated = os.path.join(tmp, pdf_name.replace(".pdf", ".json"))
        ok = run_extractor(EXTRACT_CATT, pdf_path, source_url)
        if ok and os.path.exists(generated) and json.load(open(generated)).get("total_results", 0) == 0:
            ok = False
        if not ok or not os.path.exists(generated):
            ok = run_extractor(EXTRACT_MARCHA, pdf_path, source_url)
            marcha_json = os.path.join(tmp, "json", pdf_name.replace(".pdf", ".json"))
            if ok and os.path.exists(marcha_json):
                generated = marcha_json

        if ok and os.path.exists(generated):
            new_data = json.load(open(generated, encoding="utf-8"))
            if not new_data.get("event_src") and source_url:
                new_data["event_src"] = source_url
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            positions = sum(1 for r in new_data.get("results", []) if r.get("position") is not None)
            return "ok", positions

        if add_position_null(original):
            if not original.get("event_src") and source_url:
                original["event_src"] = source_url
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(original, f, ensure_ascii=False, indent=2)
        return "extract_fail", 0


def main():
    url_map = load_url_map()
    targets = sorted(glob.glob(os.path.join(ROOT, "json", "*.json")))
    targets += sorted(glob.glob(os.path.join(ROOT, "json", "imported", "*.json")))

    stats = {"ok": 0, "no_url": 0, "download_fail": 0, "extract_fail": 0, "positions": 0}
    for json_path in targets:
        rel = os.path.relpath(json_path, ROOT)
        status, positions = process_json(json_path, url_map)
        stats[status] = stats.get(status, 0) + 1
        stats["positions"] += positions
        print(f"[{status}] {rel} ({positions} positions)")

    print(
        f"\nDone: {len(targets)} files | "
        f"ok={stats['ok']} no_url={stats['no_url']} "
        f"download_fail={stats['download_fail']} extract_fail={stats['extract_fail']} | "
        f"total positions={stats['positions']}"
    )


if __name__ == "__main__":
    main()
