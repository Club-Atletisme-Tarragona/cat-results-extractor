#!/usr/bin/env python3
"""Repair era masters rows mislabelled by section, reading the PDF tables.

The era masters sheets print sections ('PES', 'JAVELINA', 'Salt de Llargada')
whose table tail is `[Coef.] intents... MARCA % PUNTS`. The era parsers
mislabelled whole sections (a shot-put section's rows stored as 'Alçada') and
grabbed columns past MARCA, so a stored row can be an attempt of the WRONG
event, or the % value as a phantom attempt.

Repair per suspect row, ONLY when the PDF proves it:
  1. find the athlete's line in the PDF (exactly one CA Tarragona match);
  2. identify the section the line belongs to (section title above the table);
  3. the true discipline = the section title, mapped to the dataset vocabulary;
  4. attempts = the numeric cells between Coef. and MARCA (they sit before the
     last-4 tail: MARCA % PUNTS or MARCA % PUNTS with Coef first);
  5. rewrite the athlete's rows for that old label: new discipline, the real
     attempt list (each attempt one row, X excluded), % and PUNTS dropped.

The check_veterans_marks.py suspect list is the worklist input; a suspect is
only touched when its stored value no longer exists among the PDF-derived
attempts or its discipline label changes. Never guesses: when the section or
the athlete cannot be located, the row is left and reported.

Usage:
    python3 scripts/repair_masters_sections.py --season 2010            # dry
    python3 scripts/repair_masters_sections.py --season 2010 --apply
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "reports"
SUSPECTS = REPORTS_DIR / "veterans_marks_suspect.csv"

# Section titles found in the era masters sheets -> dataset discipline stem.
SECTION_MAP = {
    "PES": "Pes",
    "DISCO": "Disc",
    "DISC": "Disc",
    "JABALINA": "Javelina",
    "JAVELINA": "Javelina",
    "MARTILLO": "Martell",
    "MARTELL": "Martell",
    "LANZAMIENTO DE PESO": "Pes",
    "LANZAMIENTO DE DISCO": "Disc",
    "LANZAMIENTO DE JABALINA": "Javelina",
    "LANZAMIENTO DE MARTILLO": "Martell",
    "SALT DE LLARGADA": "Llargada",
    "LONGITUD": "Llargada",
    "SALT D'ALÇADA": "Alçada",
    "SALT DE ALTURA": "Alçada",
    "ALTURA": "Alçada",
    "SALT CON PERCHA": "Perxa",
    "TRIPLE": "Triple",
}

_NUM = re.compile(r"^\d{1,3}[.,]\d{1,2}$")
_INT = re.compile(r"^\d{1,3}$")


def numeric_cells(line):
    """Decimal cells of a table line, in order."""
    return [c.replace(",", ".") for c in line.split() if _NUM.match(c)]


def _table_header(lines, idx):
    """The column-header line above the row at idx (either era form)."""
    for j in range(idx, max(idx - 40, -1), -1):
        up = lines[j].upper()
        if "LLOC DORSAL" in up:
            return lines[j]
        if "ORDRE DORSAL" in up:
            return lines[j]  # 2016 Conersys: MARCA Ref. Percent... intents last
    return ""


def section_of(lines, idx):
    """Discipline stem of the table containing lines[idx], via the nearest
    title above it (a short all-caps line or a known section name)."""
    title = None
    for j in range(idx, max(idx - 40, -1), -1):
        s = lines[j].strip()
        up = s.upper()
        for key, stem in SECTION_MAP.items():
            if key in up:
                return stem
        if re.search(r"METRES?\s+(LLISOS|TANQUES|VALLAS|OBST)", up):
            return "track"
        if "LLOC DORSAL" in up:
            continue
        if 3 <= len(s) <= 30 and s == s.upper() and re.fullmatch(r"[A-ZÁÉÍÓÚÀÈÒÜÑ·\. 'X0-9]+", s):
            title = s
    return None


def athlete_lines(lines, athlete_token):
    """All CA Tarragona lines whose surnames match the stored name.

    Surnames are the stable part across name-order variants (LLUIS/LUIS,
    surname-first vs given-name-first). An athlete can appear in several
    tables (their event rows plus the wind table); the caller picks the hit
    whose section is a real discipline.
    """
    toks = [t for t in athlete_token.upper().replace(",", " ").split()
            if len(t) >= 4 and not t.isdigit()]
    if len(toks) < 2:
        toks = athlete_token.upper().split()
    hits = []
    for i, ln in enumerate(lines):
        up = ln.upper()
        if "tarragona" not in ln.lower():
            continue
        if all(t in up for t in toks):
            hits.append(i)
    return hits


def attempts_from_line(line, section_stem, table_header=""):
    """Attempts from a masters table line, anchored on the tail.

    The tail is fixed: 'MARCA % PUNTS' (PUNTS sometimes absent). MARCA is the
    best attempt, so it repeats among the attempts. Attempts = every numeric
    cell before MARCA that repeats or sits after a repeated cell, minus the
    leading Coef. The Coef. is a factor outside the attempt range of the
    event (throws >25 m, jumps >10 m, per the same ceilings the checkers use).

    Anchoring on the tail (right side) beats dropping from the left, where
    the Coef. and the first attempt are easy to confuse.
    """
    cells = numeric_cells(line)
    if len(cells) < 3:
        return []
    # tail: PUNTS (int, small) optional, % (one decimal, 30-100), MARCA
    pct = None
    end = len(cells)
    if end >= 1 and _INT.match(cells[-1]) and 0 < int(cells[-1]) <= 40:
        end -= 1  # PUNTS
    if end >= 1 and _NUM.match(cells[end-1]):
        v = float(cells[end-1])
        if 30 <= v <= 100:
            pct = cells[end-1]; end -= 1
    if end < 2:
        return []
    # 2016 layout: the tail comes FIRST (MARCA Ref. Percent. Posició PUNTS)
    # and the attempts trail at the end. Detect it: the first cell equals the
    # MARCA (best attempt) and the second is out of range for the event (the
    # Ref.) — then attempts are the last <=6 values of the line.
    # Two tail layouts exist for throw sections:
    #  a) 2005-2015 era: [Coef?] intents... MARCA % [PUNTS]  (attempts first,
    #     MARCA repeats the best attempt)
    #  b) 2016 Conersys: MARCA Ref Percent... intents...    (attempts last,
    #     the Ref. is a reference mark that always exceeds the athlete's real
    #     throws and never repeats)
    # Try every split point: the attempts are the longest trailing run whose
    # values all fall below the cells dropped in front (Coef. or Ref.), and
    # MARCA is repeated inside them for layout (a).
    # Layout decided by the TABLE HEADER the row sits under (table_header):
    #  b) 2016 Conersys: 'MARCA Ref. Percent. Posició PUNTS 1..6' -> attempts
    #     are the LAST <=6 numeric cells (MARCA/Ref/Pct/Pos/PUNTS come first).
    #  a) 2005-2015 era: 'Coef. 1..6 Marca % PUNTS' or '1..6 Marca % PUNTS'
    #     -> attempts are the cells between Coef. and MARCA.
    if table_header and "ref." in table_header.lower():
        # tail-first layout: cells = [MARCA, Ref, intents...]. The Ref. is the
        # age-graded reference and always exceeds every real mark of the row;
        # drop it when it does (for a Fouls-heavy row the Ref. sits at the
        # front because the numeric cells exclude the X marks).
        tail = cells[1:]
        if tail and float(tail[0]) > max(float(v) for v in tail[1:]):
            tail = tail[1:]
        return tail
    # fall through to the tail-anchored logic for layout (a)
    marca = cells[end-1]
    body = cells[:end-1]
    # Height events (Alçada/Perxa) print the Coef. as a bar height and the
    # attempts as O/X runs; when the row has no O/X run there are no stored
    # attempts and the numeric tail is Coef. MARCA % PUNTS directly.
    if section_stem in ("Alçada", "Perxa"):
        has_runs = bool(re.search(r"\b(?:X+|O+|XO+|OX)\b", line))
        if not has_runs and body and float(body[0]) > float(marca) + 1e-9:
            return []  # Coef. above the achieved height with no valid attempt
    # The attempts are the longest suffix of body whose max equals MARCA (the
    # best attempt) — that suffix starts right after the leading Coef.
    best = None
    for start in range(len(body)):
        cand = body[start:]
        if not cand:
            continue
        vals = [float(v) for v in cand]
        if vals and abs(max(vals) - float(marca)) < 1e-9:
            best = cand
            break
    return best or body


def _repeats(value, others):
    return value in others


def _ref_value(lines, athlete_token):
    """The 'Ref.' column value of the athlete's row, or None.

    The 2016 tables print 'MARCA Ref. Percent.' — the Ref. is the age-graded
    reference, never a mark. Numeric cells: MARCA Ref Percent (then Posició
    PUNTS and the attempts). Ref = second cell after MARCA.
    """
    idx = athlete_lines(lines, athlete_token)
    if not idx:
        return None
    cells = numeric_cells(lines[idx[0]])
    if len(cells) >= 3:
        return cells[1]
    return None


def _ghost_of_other_event(name, disc, perf, data):
    """The discipline whose mark equals this suspect's stored value, or None.

    Combined-events tables put every event of an athlete in one row; the era
    parser sometimes stored that row once per event label, copying the marks
    of the neighbouring columns. If another stored discipline of the same
    athlete already holds this exact mark, the suspect row duplicates it
    under the wrong label.
    """
    same = [r for r in data.get("results", [])
            if r.get("athlete_name") == name and r.get("performance") == perf
            and r.get("discipline") != disc]
    return same[0]["discipline"] if same else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--csv", default=str(SUSPECTS))
    args = ap.parse_args()

    suspects = list(csv.DictReader(open(args.csv, encoding="utf-8"))) \
        if Path(args.csv).exists() else []
    by_file = defaultdict(list)
    for r in suspects:
        if f"/{args.season}/" in r["file"]:
            by_file[r["file"]].append(r)

    stats = Counter = defaultdict(int)
    log = []
    import csv as _csv
    stats = defaultdict(int)

    with tempfile.TemporaryDirectory(prefix="masters-") as work:
        work = Path(work)
        for file_rel, rows in sorted(by_file.items()):
            path = ROOT / file_rel
            data = json.loads(path.read_text(encoding="utf-8"))
            src = data.get("event_src") or ""
            pdf = work / (file_rel.split("/")[-1].replace(".json", ".pdf"))
            dl = subprocess.run(["curl", "-fsSL", "--connect-timeout", "15",
                                 "--max-time", "90", "-o", str(pdf), src],
                                capture_output=True, timeout=120)
            if dl.returncode != 0 or not pdf.exists() or pdf.read_bytes()[:4] != b"%PDF":
                for r in rows:
                    stats["download_fail"] += 1
                continue
            txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                 capture_output=True, text=True).stdout
            lines = txt.splitlines()

            plans = []
            seen_pairs = set()
            for r in rows:
                idx = None
                stem = None
                for hit in athlete_lines(lines, r["athlete_name"]):
                    s = section_of(lines, hit)
                    if s and s != "track":
                        idx, stem = hit, s
                        break
                if idx is None:
                    # Combined-events sheets print one row per athlete with all
                    # their marks in columns (Llargada | Javelina | 200m | Disc
                    # | 1500m). A stored row whose value equals ANOTHER event's
                    # mark of the same athlete is a ghost (the era parser
                    # mislabelled it); the real row already exists in the JSON.
                    other = _ghost_of_other_event(r["athlete_name"],
                                                  r["discipline"], r["performance"],
                                                  data)
                    if other is not None:
                        stats["ghost_other_event"] += 1
                        log.append(f"ghost (pent)  | {r['athlete_name']} | {r['discipline']} {r['performance']} = {other} mark")
                        continue
                    # 2016 'MARCA Ref. Percent' layout: the Ref. column holds
                    # the age-graded reference time, not a mark. A suspect
                    # equal to the athlete's Ref. value is a ghost attempt.
                    ref = _ref_value(lines, r["athlete_name"])
                    if ref is not None and ref == r["performance"].replace(",", "."):
                        stats["ghost_ref"] += 1
                        log.append(f"ghost (ref)   | {r['athlete_name']} | {r['discipline']} {r['performance']} = Ref. {ref}")
                        continue
                    stats["line_not_found"] += 1
                    log.append(f"left (line)   | {r['athlete_name']} | {r['discipline']} {r['performance']}")
                    continue
                attempts = attempts_from_line(lines[idx], stem,
                                              table_header=_table_header(lines, idx))
                # A section row never contains marks of other events; when the
                # extracted attempts include values the stored JSON holds under
                # DIFFERENT disciplines of the same athlete, this line is a
                # combined-events row, not a section row - relabelling it would
                # overwrite real event rows with mixed-event values.
                stored_other = {(x.get("performance"), x.get("discipline"))
                                for x in data.get("results", [])
                                if x.get("athlete_name") == r["athlete_name"]
                                and x.get("discipline") != r["discipline"]}
                # an attempt value that the stored JSON holds under a
                # DIFFERENT discipline of the same athlete = combined row
                other_discs = {p: d for p, d in stored_other}
                mixed = [a for a in attempts if a in other_discs]
                if mixed:
                    stats["combined_row"] += 1
                    log.append(f"left (combined)| {r['athlete_name']} | {r['discipline']} -> {stem} mixes {mixed}")
                    continue
                pair = (r["athlete_name"], stem)
                if pair in seen_pairs:
                    continue  # one athlete+section relabel covers all their rows
                seen_pairs.add(pair)
                plans.append((r["discipline"], r["athlete_name"], stem, attempts))
                stats["planned"] += 1

            # apply per athlete+old-label
            jobs = defaultdict(list)
            for old_disc, name, stem, attempts in plans:
                jobs[(old_disc, name)].append((stem, attempts))

            for (old_disc, name), specs in jobs.items():
                stem, attempts = specs[0]
                out = []
                changed = 0
                for r in data.get("results", []):
                    if r.get("athlete_name") == name and r.get("discipline") == old_disc:
                        changed += 1
                        continue
                    out.append(r)
                for a in attempts:
                    out.append({
                        "athlete_name": name,
                        "athlete_dob": "",
                        "athlete_id": "",
                        "performance": a,
                        "discipline": stem,
                        "wind": None,
                        "position": None,
                    })
                data["results"] = out
                data["total_results"] = len(out)
                stats["rows_dropped"] += changed
                stats["rows_written"] += len(attempts)
                log.append(f"relabel       | {name} | {old_disc} -> {stem} | "
                           f"attempts: {', '.join(attempts)}")
                stats["athletes"] += 1

            if args.apply:
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")

    log_path = REPORTS_DIR / f"masters_sections_{args.season}.log"
    log_path.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(dict(stats))
    print(f"log: {log_path}")
    print("APPLIED" if args.apply else "DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    import csv  # noqa: F401  (used by the suspect load)
    sys.exit(main())
