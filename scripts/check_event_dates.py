#!/usr/bin/env python3
"""Audit stored `event_date` values against the source PDF headers.

The era parsers could not read Catalan month names ('29 de gener de 2005'), so
some 2005-2016 rows carry a date derived from the FILENAME, misreading '29105'
(29 Jan) as 29 October. This script downloads each stored PDF, reads the header
with the current `parse_header` (Spanish + Catalan months), and compares.

It never writes by itself: it writes a worklist of mismatches with the header
date as evidence, and `--apply` copies the header date into the JSONs (date
only; location/name mismatches are logged for manual review because the header
parser's city guess can be worse than a stored value that came from a full
re-extraction).

Dates are compared as DATES, not as strings: `26/4/2006` and `26/04/2006` are the
same day and the old string comparison reported 15 such rows as mismatches
(issue #28). PDFs are read from `pdf_cache/` when present and only downloaded
when missing.

Usage:
    python3 scripts/check_event_dates.py            # report only
    python3 scripts/check_event_dates.py --apply    # fix event_date mismatches
"""

import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from extract_catt import parse_header  # noqa: E402

SEASONS_DIR = ROOT / "seasons"
REPORTS_DIR = ROOT / "reports"
PDF_CACHE = ROOT / "pdf_cache"

# `DD/MM/YYYY` with optional zero padding on day and month: era JSONs and
# hand-edited files write `26/4/2006` while `parse_header` always pads.
_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_date(value):
    """Return the `datetime.date` a stored/header string denotes, or None.

    Accepts padded and unpadded `D/M/YYYY`. Impossible calendar days
    (`32/01/2016`) and non-dates return None, which callers treat as a
    conflict worth reporting rather than as agreement.
    """
    if not isinstance(value, str):
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def dates_conflict(stored, header):
    """True when `stored` and `header` denote different days (or are unreadable).

    Comparing parsed dates kills the formatting noise (`26/4/2006` vs
    `26/04/2006`), which is what the audit used to report as a mismatch.
    """
    left, right = parse_date(stored), parse_date(header)
    if left is None or right is None:
        return True
    return left != right


def cached_pdf(src, season, cache_root=PDF_CACHE):
    """Return the cached PDF for `src` under `pdf_cache/<season>/`, or None.

    Cache names are the URL basename, and some carry a doubled extension
    (`...combinadespc13140216.pdf.pdf`) because the source URL did. Fall back
    to any season directory: old files were filed under the calendar year of
    the download, not necessarily the event's season.
    """
    name = unquote(Path(urlparse(src).path).name)
    if not name:
        return None
    cache_root = Path(cache_root)
    candidate = cache_root / str(season) / name
    if candidate.is_file():
        return candidate
    for candidate in sorted(cache_root.glob(f"*/{name}")):
        if candidate.is_file():
            return candidate
    return None


def _read_pdf_text(pdf):
    result = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                            capture_output=True, text=True)
    return result.stdout or ""


def _write_json(path, data):
    """Sibling temp file + os.replace: an interrupted run never truncates."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class KeepStored:
    """A decided "keep the stored date" conflict, pinned to its two values.

    `class_` mirrors the worklist vocabulary: `span-2-dies` when the meeting
    genuinely ran over several days and the stored date is one of them,
    `non-header-line` when the audit date comes from a line that is not the
    meeting header (season best, record, stamp, birth date).
    """

    stored: str
    header: str
    class_: str
    evidence: str


def keep_decision(rel_path, stored, header):
    """Return the recorded decision when it still describes this exact pair.

    Keyed on the (stored, header) pair on purpose: if either date moves, the
    row stops matching and resurfaces as an open mismatch instead of hiding
    behind a stale decision.
    """
    decision = KEEP_STORED.get(rel_path)
    if decision is None:
        return None
    if parse_date(decision.stored) != parse_date(stored):
        return None
    if parse_date(decision.header) != parse_date(header):
        return None
    return decision


# Documented "keep the stored date" decisions (issue #28). Each one needed the
# PDF open; the evidence string is the header text actually read from it.
#
# This registry is a decision record, not a dumping ground: an entry only exists
# while `parse_header` still reads a different date for that sheet for a reason
# the data must keep (a range the sheet only names as a range, a garbled line
# that is not the header). When the parser learns the case, the entry goes —
# that is why the eight `non-header-line`/`span-2-dies` cases of issue #32 are no
# longer here (their headers are pinned by tests/test_parse_header_dates.py).
KEEP_STORED = {
    "seasons/2010/json/resulmitingveteransreus8510.json": KeepStored(
        "8/5/2010", "09/05/2010", "non-header-line",
        "The meeting header reads '8 de maig de 2010' (3r Meeting Ciutat de "
        "Reus), which is the stored date. The audit date comes from the garbled "
        "line '9:0109/05/2010' (print time + date), not the meeting header."),
    "seasons/2013/json/resulcatcombinadespromocio25260513.json": KeepStored(
        "26/05/2013", "25/05/2013", "span-2-dies",
        "'Barcelona (Serrahima), 25-26 mayo 2013': per-session dates in the acta "
        "show CA Tarragona results on both 25/05 and 26/05; the file covers the "
        "whole meeting, so the stored closing day is kept."),
    "seasons/2013/json/resulcontrolprimaveracambrils18190513.json": KeepStored(
        "19/05/2013", "18/05/2013", "span-2-dies",
        "Section headers inside the sheet read both 'Cambrils, 18 / 05 / 2013' "
        "and 'Cambrils, 19 / 05 / 2013', and CA Tarragona has results on both "
        "days (e.g. Marta Targa 1'39\"34 on 19/05). Stored closing day kept."),
    "seasons/2013/json/resulcatjunior120613.json": KeepStored(
        "02/06/2013", "01/06/2013", "span-2-dies",
        "'Estadi Municipal d'Igualada, 1-2 junio 2013', and the acta prints session "
        "dates: CA Tarragona results on 01/06 (Nuria Torrademe 13.90, Montse "
        "Guinovart 1.46, Marina Tibau 9.25) and on 02/06 (Montse Guinovart 5.03 "
        "long jump, Maria Montañes 32.42 discus). The file covers the meeting, so "
        "the closing day is kept; the audit date is its first session."),
    "seasons/2015/json/resulcatcombinades30310515.json": KeepStored(
        "31/05/2015", "30/05/2015", "span-2-dies",
        "'Barcelona-SE, 30-31 mayo 2015': per-session dates ('Serie 1 30/05/2015', "
        "'Serie 1 31/05/2015') show CA Tarragona results on both days; stored "
        "closing day kept."),
    "seasons/2015/json/resulcatcombinadesjuvenilpc21220215.json": KeepStored(
        "22/02/2015", "21/02/2015", "span-2-dies",
        "'Sabadell (Pista Coberta de Catalunya), 21-22 febrero 2015': the heptathlon "
        "acta has Jan Sans Riola on 21/02 (60m) and on 22/02 (day 2 events); "
        "stored closing day kept."),
    "seasons/2015/json/resulcontrolcambrils16170515.json": KeepStored(
        "17/05/2015", "16/05/2015", "span-2-dies",
        "Section headers inside the sheet read both 'Cambrils, 16 / 05 / 2015' "
        "and 'Cambrils, 17 / 05 / 2015', and CA Tarragona has results on both "
        "days. Stored closing day kept."),
    "seasons/2015/json/resulcombinadescambrils20121214.json": KeepStored(
        "20/12/2014", "21/12/2014", "span-2-dies",
        "'Cambrils, 20 i 21 de desembre de 2014': the sheet names the range only "
        "and has no per-session dates, so both days are in it. The stored day "
        "(20/12) is the opening day and the parser now reads the range's "
        "closing day; both are defensible, so the stored day is kept."),
    "seasons/2017/json/resultat-20170114-controlabsolutpc.json": KeepStored(
        "15/01/2017", "14/01/2017", "span-2-dies",
        "The title reads 'Sabadell (Pista Coberta de Catalunya), 14 enero 2017' "
        "but every session line in the acta reads 'Semifinal N 15/01/2017 17:10' "
        "(15 of them). The sheet contradicts itself; the stored day is the one "
        "the printed sessions support, so it is kept."),
    "seasons/2017/json/resultat-20170212-controlabsolutpcmati.json": KeepStored(
        "10/02/2017", "12/02/2017", "span-2-dies",
        "The title reads 'Sabadell (Pista Coberta de Catalunya), 12 febrero 2017' "
        "while the acta prints session lines dated 10/02/2017 (15 of them) as well "
        "as 12/02/2017: the control ran over both days and the stored day is the "
        "first of them, so it is kept."),
    "seasons/2018/json/resultat-20180211-controlpctardasabadell.json": KeepStored(
        "07/02/2018", "11/02/2018", "span-2-dies",
        "The title reads 'Sabadell (Pista Cobertade Catalunya), 11 febrero 2018' "
        "while the acta prints session lines dated 07/02/2018 (15 of them) and "
        "11/02/2018 (23): the jornada covers both days and the stored day is the "
        "first of them, so it is kept."),
    "seasons/2016/json/resulcatcadetcombinadescpc20210216.json": KeepStored(
        "21/02/2016", "20/02/2016", "span-2-dies",
        "'Sabadell (Pista Coberta de Catalunya), 20-21 febrero 2016': the hexathlon "
        "acta runs over both days (Bernat Verdu, Sira Bo); stored closing day "
        "kept."),
    "seasons/2016/json/resulcatjuniorcombinadespc13140216.json": KeepStored(
        "14/02/2016", "13/02/2016", "span-2-dies",
        "'Sabadell (Pista Coberta de Catalunya), 13-14 febrero 2016': the heptathlon "
        "acta has Jan Sans Riola on 13/02 (60m) and 14/02 (day 2 events); stored "
        "closing day kept."),
    "seasons/2016/json/resulcatjuniorcombinadespc13140216.json.json": KeepStored(
        "14/02/2016", "13/02/2016", "span-2-dies",
        "Same sheet as resulcatjuniorcombinadespc13140216.json "
        "('Sabadell (Pista Coberta de Catalunya), 13-14 febrero 2016'); stored "
        "closing day kept."),
    "seasons/2016/json/resulcatjuvenilcombinadespc13140216.json.json": KeepStored(
        "14/02/2016", "13/02/2016", "span-2-dies",
        "'Sabadell (Pista Coberta de Catalunya), 13-14 febrero 2016': Mireia Lopez "
        "Urbano competes on 14/02 (day 2 events); stored closing day kept."),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="fix event_date from the PDF header")
    ap.add_argument("--season", help="limit to one season (e.g. 2005)")
    args = ap.parse_args()

    targets = sorted(SEASONS_DIR.glob(f"{args.season or '*'}/json/*.json"))
    stats = Counter()
    mismatches = []
    kept = []

    with tempfile.TemporaryDirectory(prefix="dates-") as work:
        work = Path(work)
        for path in targets:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                stats["bad_json"] += 1
                continue
            stored = (data.get("event_date") or "").strip()
            src = data.get("event_src") or ""
            if not src.startswith(("http://", "https://")):
                stats["no_url"] += 1
                continue
            pdf = cached_pdf(src, path.parent.parent.name)
            if pdf is not None:
                stats["cache_hit"] += 1
                txt = _read_pdf_text(pdf)
            else:
                stats["downloaded"] += 1
                pdf = work / path.name.replace(".json", ".pdf")
                dl = subprocess.run(["curl", "-fsSL", "--connect-timeout", "15",
                                     "--max-time", "90", "-o", str(pdf), src],
                                    capture_output=True, timeout=120)
                if dl.returncode != 0 or not pdf.exists() \
                        or pdf.read_bytes()[:4] != b"%PDF":
                    stats["download_fail"] += 1
                    continue
                txt = _read_pdf_text(pdf)
            _, _, _, header_date = parse_header(txt)
            header_date = (header_date or "").strip()
            if not header_date:
                stats["header_no_date"] += 1
                continue
            if stored and dates_conflict(stored, header_date):
                rel = str(path.relative_to(ROOT))
                decision = keep_decision(rel, stored, header_date)
                if decision is not None:
                    stats["date_kept"] += 1
                    kept.append({
                        "class": decision.class_,
                        "file": rel,
                        "stored": stored,
                        "header": header_date,
                        "decision": "keep-stored",
                        "evidence": decision.evidence,
                        "source": src,
                    })
                    continue
                stats["date_mismatch"] += 1
                mismatches.append({
                    "file": rel,
                    "stored": stored,
                    "header": header_date,
                    "source": src,
                })

    mismatches.sort(key=lambda m: m["file"])
    print(f"scanned {len(targets)} files: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    for m in mismatches[:15]:
        print(f"  {m['file'].split('json/')[1][:44]:46s} stored={m['stored']} header={m['header']}")
    if len(mismatches) > 15:
        print(f"  ... and {len(mismatches) - 15} more")

    REPORTS_DIR.mkdir(exist_ok=True)
    # Open conflicts only. Rows decided as "keep stored" live in the manual
    # review file with their evidence, so the worklist is a to-do list again.
    out = REPORTS_DIR / "event_date_mismatches.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "stored", "header", "source"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(mismatches)
    print(f"worklist: {out} ({len(mismatches)} open)")

    review = REPORTS_DIR / "event_date_manual_review.csv"
    with review.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["class", "file", "stored", "header",
                                          "decision", "evidence", "source"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(kept, key=lambda k: k["file"]))
    print(f"decisions: {review} ({len(kept)} documented keep-stored)")
    if args.apply:
        fixed = 0
        for m in mismatches:
            p = ROOT / m["file"]
            d = json.loads(p.read_text(encoding="utf-8"))
            d["event_date"] = m["header"]
            _write_json(p, d)
            fixed += 1
        print(f"APPLIED: {fixed} dates fixed from PDF headers")
    else:
        print("DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
