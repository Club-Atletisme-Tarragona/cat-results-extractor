#!/usr/bin/env python3
"""One-off extraction for the 6 remaining issue-#18 zero-result files.

These PDFs use legacy "club on the same line" inline formats that the generic
extract_catt.py parsers do not cover (documented in issue #18, round 3):

  2006 resulmeetingmataro10706            pos lic NAME cat CLUB mark rank
  2009 resulcatcadet20609                 jump: pos lic SURNAME, NAME DOB CLUB attempts (X / 4,66) + wind line
  2010 resulcontroluat2710                pos carrer dorsal lic NAME year CLUB mark (pipe columns)
  2013 resulmitingveteransmarbella60713   veterans: clubcode class num First Last CLUB lic DOB age mark rank pct
  2016 resulcatmarxapromocio210216        pos dorsal SURNAME, NAME lic cat CLUB 12'41''
  2016 resulcontrolpimaveracambrils3004   pos dorsal SURNAME, NAME year CLUB 10"96

Every parser below was written against the source PDF text and its output
verified row-by-row (see issue #18 round 3 comment). Disciplines come from the
PDF section headers; raw_discipline_name records that header as the audit trail.

Usage: python3 scripts/process_issue18_inline.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# PDF-cache locations (downloaded for the issue-#18 investigation)
PDFS = {
    "2006": REPO / "pdf_cache/2006/resulmeetingmataro10706.pdf",
    "2009": REPO / "pdf_cache/2009/resulcatcadet20609.pdf",
    "2010": REPO / "pdf_cache/2010/resulcontroluat2710.pdf",
    "2013": REPO / "pdf_cache/2013/resulmitingveteransmarbella60713.pdf",
    "2016a": REPO / "pdf_cache/2016/resulcatmarxapromocio210216.pdf",
    "2016b": REPO / "pdf_cache/2016/resulcontrolpimaveracambrils3004-10516.pdf",
}

HEADERS = {
    "2006": ("XIII Míting d'Atletisme \"Ciutat de Mataró\" - Estadi Municipal d'Atletisme de Mataró",
             "10/07/2006", "Mataró"),
    "2009": ("Jornada Final del Campionat de Catalunya Cadet - El Prat de Llobregat",
             "20/06/2009", "El Prat de Llobregat"),
    "2010": ("Control Absolut UA Terrassa - Terrassa", "02/07/2010", "Terrassa"),
    "2013": ("VIII Meeting català d'atletes veteranes i veterans - CEM Mar Bella (Barcelona)",
             "06/07/2013", "Barcelona"),
    "2016a": ("1r Gran premi de Marxa del Vendrell - Campionat de Catalunya de Marxa Benjamí, Aleví, Infantil i Cadet",
              "21/02/2016", "El Vendrell"),
    "2016b": ("Control Primavera 2016 - Cambrils", "30/04/2016", "Cambrils"),
}

OUTPUTS = {
    "2006": "seasons/2006/json/resulmeetingmataro10706.json",
    "2009": "seasons/2009/json/resulcatcadet20609.json",
    "2010": "seasons/2010/json/resulcontroluat2710.json",
    "2013": "seasons/2013/json/resulmitingveteransmarbella60713.json",
    "2016a": "seasons/2016/json/resulcatmarxapromocio210216.json",
    "2016b": "seasons/2016/json/resulcontrolpimaveracambrils3004-10516.json",
}

SRC = {
    "2006": "http://old.fcatletisme.cat/Pairelliure/pairelliure2006/resulmeetingmataro10706.pdf",
    "2009": "http://old.fcatletisme.cat/Promocio/promocio2009/resulcatcadet20609.pdf",
    "2010": "http://old.fcatletisme.cat/Pairelliure/pairelliure2010/resulcontroluat2710.pdf",
    "2013": "http://old.fcatletisme.cat/Veterans/veterans2013/resulmitingveteransmarbella60713.pdf",
    "2016a": "http://old.fcatletisme.cat/Marxa/2016/resulcatmarxapromocio210216.pdf",
    "2016b": "http://old.fcatletisme.cat/Pairelliure/2016/resulcontrolpimaveracambrils3004-10516.pdf",
}


def pdf_text(key):
    r = subprocess.run(["pdftotext", "-layout", str(PDFS[key]), "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"pdftotext failed for {key}")
    return r.stdout


def norm_mark(mark):
    """PDF-era mark spellings -> canonical repository format."""
    m = re.fullmatch(r"(\d{1,2})\.(\d{2})\.(\d{2})", mark)          # 2.18.49 (800m dot-time)
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    m = re.fullmatch(r"(\d{1,2})'\s*(\d{2})''\s*(\d{2})", mark)     # 1' 06'' 50
    if m:
        return f"{m.group(1)}:{m.group(2)}.{m.group(3)}"
    m = re.fullmatch(r"(\d{1,2})'(\d{2})''", mark)                  # 12'41'' (marcha)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = re.fullmatch(r"(\d{1,2})''\s*(\d{2})", mark)                # 11'' 71 (sprint)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.fullmatch(r'(\d{1,2})"(\d{2})', mark)                    # 10"96
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.fullmatch(r'(\d{1,2})"(\d)', mark)                       # 52"6 (one decimal)
    if m:
        return f"{m.group(1)}.{m.group(2)}0"
    m = re.fullmatch(r"(\d+),(\d{2})", mark)                        # 4,66 (comma decimal)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return mark


def clean_wind(w):
    """+1,7 -> +1.7 (sign kept as printed; unsigned tailwind gets '+')."""
    w = w.strip().replace(",", ".")
    if not w:
        return None
    return w if w.startswith(("+", "-")) else f"+{w}"


def load_repo(path):
    return json.load(open(REPO / path, encoding="utf-8"))


def save_repo(path, data):
    with open(REPO / path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 2006 Mataró: "Prova: 800 m.ll." sections; inline row with licence in name column
# ---------------------------------------------------------------------------

def extract_2006(text):
    lines = text.split("\n")
    rows = []
    disciplina = ""
    for ln in lines:
        s = ln.strip()
        prova = re.match(r"Prova:\s*(.+?)\s*$", s)
        if prova:
            p = prova.group(1)
            mtrack = re.fullmatch(r"([\d.]+)\s*m\.ll\.", p)
            disciplina = f"{mtrack.group(1)} metres llisos" if mtrack else p
            continue
        m = re.match(
            r"^(\d+)\s+(\d+)\s+(C[LT]-?\d+)\s+(.+?)\s+(\d{2})\s+"
            r"C\.?A\.?\s?Tarragona\s+(\d{1,2}[.:]\d{2}\.\d{2}|\d{1,2}:\d{2}\.\d{2})\s+(\d+)$",
            s,
        )
        if m and disciplina:
            rows.append({
                "athlete_name": m.group(4).strip(),
                "athlete_dob": "",
                "athlete_id": m.group(3),
                "performance": norm_mark(m.group(6)),
                "discipline": disciplina,
                "wind": None,
                "raw_discipline_name": f"Prova: {p}",
            })
    return rows


# ---------------------------------------------------------------------------
# 2009 El Prat: SALT DE LLARGADA — all valid attempts with per-attempt wind
# ---------------------------------------------------------------------------

def extract_2009(text):
    lines = text.split("\n")
    rows = []
    disciplina = ""
    for i, ln in enumerate(lines):
        s = ln.strip()
        if re.search(r"SALT DE LLARGADA", s, re.IGNORECASE):
            disciplina = "Llargada"
            continue
        if re.match(r"^(SALT|LLANÇAMENT|100|800|3\.000)", s) and "LLARGADA" not in s.upper():
            disciplina = ""
        m = re.match(
            r"^(\d+)\s+(\d+)\s+(C[LT]\d+)\s+(.+?)\s+(\d{2}/\d{2}/\d{4})\s+"
            r"CA TARRAGONA\s+(.+?)\s*$",
            s,
        )
        if not m or disciplina != "Llargada":
            continue
        name, dob = m.group(4).strip(), m.group(5)
        lic = m.group(3)
        attempts = m.group(6).split()
        wind_line = ""
        for j in range(i + 1, min(i + 3, len(lines))):
            if re.match(r"^\s*[+-][\d,]+(\s|$)", lines[j]):
                wind_line = lines[j]
                break
        winds = re.findall(r"[+-][\d,]+", wind_line) if wind_line else []
        # last token is the best-mark column; attempts are the rest
        attempts = attempts[:-1] if len(attempts) > len(winds) else attempts
        for attempt, wind in zip(attempts, winds):
            if attempt.upper() == "X":
                continue
            rows.append({
                "athlete_name": name,
                "athlete_dob": dob,
                "athlete_id": lic,
                "performance": norm_mark(attempt),
                "discipline": disciplina,
                "wind": clean_wind(wind),
                "raw_discipline_name": "SALT DE LLARGADA",
            })
    return rows


# ---------------------------------------------------------------------------
# 2010 Terrassa control: "800 METRES LLISOS MASCULINS" sections
# ---------------------------------------------------------------------------

def extract_2010(text):
    lines = text.split("\n")
    rows = []
    disciplina = ""
    for ln in lines:
        s = ln.strip()
        ev = re.match(r"^([\d.]+)\s+METRES\s+LLISOS", s, re.IGNORECASE)
        if ev:
            d = ev.group(1)
            disciplina = f"{d} metres llisos"
            continue
        m = re.match(
            r"^(\d+)\s+(\d+)\s+(\d+)\s+(C[LT]-?\d+)\s+(.+?)\s+(\d{2})\s+"
            r"CA\s+TARRAGONA\s+(\d{1,2}:\d{2}\.\d{2})\s*$",
            s,
        )
        if m and disciplina:
            rows.append({
                "athlete_name": m.group(5).strip(),
                "athlete_dob": "",
                "athlete_id": m.group(4),
                "performance": m.group(7),
                "discipline": disciplina,
                "wind": None,
                "raw_discipline_name": s[:60],
            })
    return rows


# ---------------------------------------------------------------------------
# 2013 Marbella veterans: "400mll"/"800mll"/"100mll" ranking tables
# ---------------------------------------------------------------------------

MARBELLA_MARK = r"(\d{1,2}'\s*\d{2}''\s*\d{2}|\d{1,2}''\s*\d{2})"


def extract_2013(text):
    lines = text.split("\n")
    rows = []
    disciplina = ""
    wind = None
    for ln in lines:
        s = ln.strip()
        ev = re.match(r"^(\d{3,4})mll-", s)
        if ev:
            d = ev.group(1).rstrip(".")
            disciplina = f"{d} metres llisos"
            wind = None
            continue
        w = re.search(r"Vent:\s*([+-][\d,]+)", s)
        if w:
            wind = clean_wind(w.group(1))
            continue
        m = re.match(
            rf"^(\d{{3}})\s+(?:\d\s+)?(?:\d+\s+)?(.+?)\s+CA Tarragona\s+(CL\d+)\s+"
            rf"(\d{{2}}/\d{{2}}/\d{{4}})(?:\s+(\d{{2}}))?\s+{MARBELLA_MARK}\s+(\d+)(?:\s+([\d,]+%))?$",
            s,
        )
        if m and disciplina:
            rows.append({
                "athlete_name": " ".join(m.group(2).split()),
                "athlete_dob": m.group(4),
                "athlete_id": m.group(3),
                "performance": norm_mark(m.group(6)),
                "discipline": disciplina,
                "wind": wind,
                "raw_discipline_name": f"{m.group(1)}mll",
            })
    # dedup: same athlete+discipline+mark repeated across prova/percentatge tables
    seen, deduped = set(), []
    for r in rows:
        key = (r["athlete_name"].lower(), r["discipline"], r["performance"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


# ---------------------------------------------------------------------------
# 2016 Marxa del Vendrell: "Prova: 2KM / Categoria: Aleví Femení" tables
# ---------------------------------------------------------------------------

def extract_2016a(text):
    lines = text.split("\n")
    rows = []
    prova = categoria = ""
    for ln in lines:
        s = ln.strip()
        p = re.match(r"Prova:\s*([\d.]+KM)(?:\s+Categoria:\s*(.+))?$", s)
        if p:
            prova = p.group(1).replace(".", "")
            if p.group(2):
                categoria = p.group(2).strip()
            continue
        c = re.match(r"Categoria:\s*(.+)$", s)
        if c:
            categoria = c.group(1).strip()
            continue
        m = re.match(
            r"^(\d+)\s+(\d+)\s+(.+?),\s*(\S+)\s+(CL\s?\d+)\s+(\d)\s+"
            r"CA Tarragona\s+(\d{1,2}'\d{2}'')\s*$",
            s,
        )
        if m and prova and "Aleví Femení" in categoria:
            dist = int(re.match(r"(\d+)KM", prova).group(1)) * 1000
            rows.append({
                "athlete_name": f"{m.group(3)}, {m.group(4)}",
                "athlete_dob": "",
                "athlete_id": m.group(5).replace(" ", ""),
                "performance": norm_mark(m.group(7)),
                "discipline": f"{dist} metres marxa",
                "wind": None,
                "raw_discipline_name": f"Prova: {prova} Categoria: {categoria}",
            })
    return rows


# ---------------------------------------------------------------------------
# 2016 Cambrils control: "100 m.ll. Absolut Masculí" etc. sections
# ---------------------------------------------------------------------------

CAMBRILS_DISCIPLINES = {
    "100 m.ll. Absolut Masculí": "100 metres llisos",
    "100 m.ll. Absolut Femení": "100 metres llisos",
    "200 m.ll. Absolut Femení": "200 metres llisos",
    "110 m.t. Júnior Masculí": "110 metres tanques (1.067)",
    "100 m.t. Juvenil Femení": "100 metres tanques (0.84)",
    "300 m.ll. Cadet Masculí": "300 metres llisos",
}


def extract_2016b(text):
    lines = text.split("\n")
    rows = []
    disciplina = None
    wind = None
    for ln in lines:
        s = ln.strip()
        if s in CAMBRILS_DISCIPLINES:
            disciplina = CAMBRILS_DISCIPLINES[s]
            wind = None
            continue
        w = re.search(r"Vent\s+([+-]?[\d,]+)", s)
        if w and disciplina:
            wind = clean_wind(w.group(1))
            continue
        m = re.match(
            r"^(\d+)\s+(\d+)\s+(.+?),\s*(\S+)\s+(\d{4})\s+C\. A\. TARRAGONA\s+"
            r"(\d{1,2}\"[\d,]{1,2})\s*$",
            s,
        )
        if m and disciplina:
            rows.append({
                "athlete_name": f"{m.group(3)}, {m.group(4)}",
                "athlete_dob": "",
                "athlete_id": "",
                "performance": norm_mark(m.group(6)),
                "discipline": disciplina,
                "wind": wind,
                "raw_discipline_name": disciplina and next(
                    k for k, v in CAMBRILS_DISCIPLINES.items() if v == disciplina),
            })
    return rows


EXTRACTORS = {
    "2006": extract_2006,
    "2009": extract_2009,
    "2010": extract_2010,
    "2013": extract_2013,
    "2016a": extract_2016a,
    "2016b": extract_2016b,
}


def main():
    grand_total = 0
    for key, extractor in EXTRACTORS.items():
        rows = extractor(pdf_text(key))
        out_path = OUTPUTS[key]
        data = load_repo(out_path)
        data["event_name"] = HEADERS[key][0]
        data["event_date"] = HEADERS[key][1]
        data["event_location"] = HEADERS[key][2]
        data["event_src"] = SRC[key]
        data["total_results"] = len(rows)
        data["results"] = rows
        save_repo(out_path, data)
        grand_total += len(rows)
        print(f"{key}: {len(rows)} results -> {out_path}")
        for r in rows:
            print(f"    {r['athlete_name'][:34]:36} {r['discipline'][:28]:30} "
                  f"{r['performance']:>9}  wind={r['wind']}")
    print(f"\ntotal: {grand_total} results across 6 files")


if __name__ == "__main__":
    main()
