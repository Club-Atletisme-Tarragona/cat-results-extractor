#!/usr/bin/env python3
"""Wind audit for GitHub issue #25 — measure, never repair.

A naive count says 7,170 rows sit in wind-applicable events with ``wind: null``,
but that number mixes three different things: rows whose sheet really prints a
wind the extractor lost (the defect), rows whose sheet prints no wind at all
(legitimate), and rows in indoor meets where wind is never measured (a
``is_short_track`` defect, not a wind one). This tool reopens every source PDF
and decides, per stored row, which of those it is.

It is read-only for data. The only files it writes are:

- ``reports/wind_audit.csv``          every null wind-applicable row + verdict,
- ``reports/short_track_contract.csv`` files whose sheets and ``is_short_track``
                                      flag disagree.

Classes (exactly one per row):

``pdf-has-wind``    the sheet prints a wind for this athlete's mark  (the defect)
``pdf-no-wind``     the sheet prints no wind for that mark          (legitimate)
``indoor``          pista coberta meet: wind is never measured
``combined-event``  a combined-event section: no per-attempt wind is printed
``no-pdf``          no readable PDF in ``pdf_cache`` and a dead/absent URL
``unmatched``       the athlete's line could not be located in the sheet; listed,
                    never guessed

Usage::

    python3 scripts/check_wind.py --dry-run              # full pass
    python3 scripts/check_wind.py --season 2025          # one season
    python3 scripts/check_wind.py --season 2024,2025 --no-download
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict, namedtuple
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the real extractor instead of duplicating its rules (spec: idiomatic
# reuse). `extract_text` is the `pdftotext -layout` path every extractor uses,
# `wind_applicable` is the single source of truth for "this discipline records
# wind", `detect_short_track` is the export contract's indoor detector.
from extract_catt import detect_short_track, extract_text, wind_applicable  # noqa: E402

AUDIT_CSV = REPO_ROOT / "reports" / "wind_audit.csv"
SHORT_TRACK_CSV = REPO_ROOT / "reports" / "short_track_contract.csv"

CLASSES = ("pdf-has-wind", "pdf-no-wind", "indoor", "combined-event",
           "no-pdf", "unmatched")
FAMILIES = ("sprint", "hurdles", "long jump", "triple", "other")

# ---------------------------------------------------------------------------
# Text primitives
# ---------------------------------------------------------------------------

_DOB_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_LICENSE_RE = re.compile(r"\b(?:CL|CT|CAT|IB)\s?-?\d{2,}")
_DECIMAL_RE = re.compile(r"\d+[.,]\d+")

# `Vent:` (era FCAT), `Viento:` (RFEA/Conersys), `VENT:` uppercase.
_WIND_LABEL_RE = re.compile(r"\b(?:vent|viento|vento)\s*[:=]\s*", re.IGNORECASE)
_WIND_VALUE_RE = re.compile(r"^([+-])?\s*(\d{1,2}[.,]\d{1,2})(?!\d)")
_WIND_NULL_WORDS = frozenset(("NUL", "NULO", "N.P", "NP", "N.P.", "NIL", "-", "--",
                              "\u2014", "NO"))

# Signed decimal = wind. An unsigned 2-decimal value is a mark, never a wind
# (long jump 4,10 / triple 12,07 / times 10,57). Requiring the sign is what
# keeps another athlete's attempt line from being read as a wind line.
_SIGNED_WIND_RE = re.compile(r"(?<![\d.,/+:-])([+-])\s?(\d{1,2}[.,]\d{1,2})(?![\d])")

_TITLE_HINT_RE = re.compile(
    r"(?:llisos?|llargada|longitud|altura|al[cç]ada|perxa|p\u00e8rtiga|triple"
    r"|tanques|vallas|obstacles|marxa|marcha|rel[\u00b7.]?leus|relevos"
    r"|javelina|jabalina|martell|martillo|\bdisc\b|\bdard\b|\bpes\b|\bpeso\b"
    r"|pentatl|heptatl|tetratl|hexatl|decatl|combinad"
    r"|\d{1,4}(?:[.,]\d{3})?\s*m(?![a-z\u00e0-\u00fa]))",
    re.IGNORECASE,
)
_COMBINED_TITLE_RE = re.compile(
    r"pentatl|heptatl|tetratl|hexatl|decatl|combinad|combined", re.IGNORECASE)
_JUMP_TITLE_RE = re.compile(r"llargada|longitud|triple", re.IGNORECASE)


def normalize(text):
    """Uppercase, accent-free, punctuation-to-space form used for matching."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def name_tokens(name):
    return [t for t in re.split(r"[^A-Z0-9]+", normalize(name)) if t]


def classify_family(discipline):
    """sprint / hurdles / long jump / triple / other, for the family summary."""
    name = str(discipline or "").strip().lower()
    if "llargada" in name or "longitud" in name:
        return "long jump"
    if "triple" in name:
        return "triple"
    m = re.match(r"^(\d{1,3}(?:\.\d{3})?)\s*m(?:etres)?\b(.*)$", name)
    if m:
        if re.search(r"\b(tanques|vallas)\b", m.group(2)):
            return "hurdles"
        return "sprint"
    return "other"


WindHeader = namedtuple("WindHeader", "value text")


def parse_wind_header(line):
    """The `Vent:`/`Viento:` marker of a line, or None.

    A header with no value (``Viento:``) and the explicit null forms
    (``Nul``/``Nulo``) both mean "no wind on the sheet" and are reported with
    ``value=None`` so the caller can tell "no header" from "header, no value".
    """
    if not line:
        return None
    m = _WIND_LABEL_RE.search(line)
    if not m:
        return None
    text = line.strip()
    tail = line[m.end():].strip()
    if not tail:
        return WindHeader(None, text)
    mv = _WIND_VALUE_RE.match(tail)
    if mv:
        number = mv.group(2).replace(",", ".")
        if abs(float(number)) <= 9.9:
            return WindHeader((mv.group(1) or "+") + number, text)
    word = tail.split()[0].upper().rstrip(".,;:")
    if word in _WIND_NULL_WORDS:
        return WindHeader(None, text)
    return WindHeader(None, text)


WindToken = namedtuple("WindToken", "start end value")

_LETTER_RE = re.compile(r"[A-Za-z\u00c0-\u00ff]")
_WIND_LINE_RE = re.compile(r"(?<![\d.,/])([+-]?)\s?(\d{1,2}[.,]\d{1,2})(?![\d])")


def wind_tokens(line):
    """Signed wind values of a line, with character offsets (for alignment).

    Requiring the sign is what keeps another athlete's attempt column from
    being read as a wind line; the era pure-numeric wind lines print positive
    values without one and are handled by `wind_line_tokens`.
    """
    out = []
    for m in _SIGNED_WIND_RE.finditer(str(line or "")):
        number = m.group(2).replace(",", ".")
        if abs(float(number)) <= 9.9:
            out.append(WindToken(m.start(), m.end(), m.group(1) + number))
    return out


def wind_line_tokens(line):
    """Wind values of a dedicated wind line, signed or not.

    Several sheets print the per-attempt winds under the attempts and drop the
    '+' of positive values, either on a bare line
    (``0.6    -1.7     0.0             0.0``) or on the club+licence line of an
    RFEA block (``CA Tarragona   CT18394   1.2  1.0  0.0  0.4``). Unsigned
    values are only trusted on such a line - never on a line carrying a date of
    birth, never on a line with names but no licence - and only at one decimal,
    which is what separates a wind (``0.6``) from a mark (``4,63``).
    """
    signed = wind_tokens(line)
    raw = str(line or "")
    if not raw.strip() or _DOB_RE.search(raw):
        return signed
    if _LETTER_RE.search(raw) and not _LICENSE_RE.search(raw):
        return signed
    out = []
    for m in _WIND_LINE_RE.finditer(raw):
        sign, number = m.group(1), m.group(2).replace(",", ".")
        if not sign and len(number.split(".")[1]) != 1:
            continue  # unsigned and two decimals: that is a mark
        if abs(float(number)) > 9.9:
            continue
        out.append(WindToken(m.start(), m.end(), (sign or "+") + number))
    # A lone unsigned number is not evidence of a wind line.
    return out if len(out) >= 2 else signed


def is_event_title(line):
    """Cheap "this line names an event" test, used only to reset the context."""
    s = str(line or "").strip()
    if not s or len(s) > 90:
        return False
    if not _TITLE_HINT_RE.search(s):
        return False
    if _DOB_RE.search(s) or _LICENSE_RE.search(s):
        return False
    if len(re.findall(r"\d+", s)) >= 4:
        return False
    return True


# ---------------------------------------------------------------------------
# Per-PDF text model
# ---------------------------------------------------------------------------

class Sheet:
    """Wind context of one source PDF, by line.

    Track/hurdle wind is printed once per series (``Vent: -5,6``), so it is
    carried forward line by line and reset at a page break or at a new event
    title. Jump wind is printed under the attempts and is read per row.
    """

    def __init__(self, text):
        self.text = str(text or "")
        self.lines = self.text.split("\n")
        self.norm_lines = [normalize(l) for l in self.lines]

        n = len(self.lines)
        self._wind = [None] * n
        self._wind_evidence = [None] * n
        self._title = [""] * n
        self._combined = [False] * n

        cur_value = None
        cur_evidence = None
        page_combined = False
        title = ""
        for i, line in enumerate(self.lines):
            if "\x0c" in line:
                # form feed: pdftotext's page boundary. A series never spans
                # two pages in these sheets, and combined-event pages carry
                # their own header.
                cur_value = None
                cur_evidence = None
                page_combined = False
            if is_event_title(line):
                title = line.strip()
                cur_value = None
                cur_evidence = None
                if _COMBINED_TITLE_RE.search(line):
                    page_combined = True
            header = parse_wind_header(line)
            if header is not None:
                cur_value = header.value
                cur_evidence = header.text
            self._wind[i] = cur_value
            self._wind_evidence[i] = cur_evidence
            self._title[i] = title
            self._combined[i] = page_combined

        # token -> line indices, so a name lookup is a set intersection instead
        # of a full scan per row (the 1,330-file pass has to stay cheap).
        self._token_lines = {}
        for i, norm in enumerate(self.norm_lines):
            for tok in set(re.split(r"[^A-Z0-9]+", norm)):
                if len(tok) >= 3:
                    self._token_lines.setdefault(tok, []).append(i)

    # -- context ---------------------------------------------------------
    def track_wind_at(self, index):
        if index is None or index < 0 or index >= len(self._wind):
            return None, None
        return self._wind[index], self._wind_evidence[index]

    def title_at(self, index):
        return self._title[index] if 0 <= index < len(self._title) else ""

    def combined_at(self, index):
        return self._combined[index] if 0 <= index < len(self._combined) else False

    # -- lookup ----------------------------------------------------------
    def lines_with(self, tokens):
        tokens = [t for t in (tokens or []) if len(t) >= 3]
        if not tokens:
            return []
        sets = []
        for tok in tokens:
            found = self._token_lines.get(tok)
            if not found:
                return []
            sets.append(set(found))
        return sorted(set.intersection(*sets))


def _attempt_tokens(line):
    """Mark tokens of a jump attempt line, as (start, end, value)."""
    raw = str(line or "")
    out = []
    for m in re.finditer(r"(?<![\d.,/])(\d{1,2}[.,]\d{2})(?![\d])", raw):
        value = float(m.group(1).replace(",", "."))
        if 1.5 <= value <= 20.0:
            out.append(WindToken(m.start(), m.end(), m.group(1).replace(",", ".")))
    if len(out) >= 2 and abs(float(out[-1].value) - max(float(t.value) for t in out[:-1])) < 1e-9:
        # The trailing column repeats the best mark ("Marca"/"Resultado").
        out = out[:-1]
    return out


def _same_mark(a, b):
    try:
        return abs(float(str(a).replace(",", ".")) - float(str(b).replace(",", "."))) < 1e-9
    except (TypeError, ValueError):
        return False


def _perf_variants(perf):
    """Spellings the same mark takes on these sheets.

    The era sheets print a hand time as ``7"0`` (seconds + tenths) or ``11.6-``
    and a mark with either a comma or a dot, while the JSON stores ``7.00``.
    """
    p = str(perf or "").strip()
    if not p:
        return ()
    out = {p, p.replace(".", ",")}
    m = re.match(r"^(\d{1,2})\.(\d{2})$", p)
    if m:
        whole, frac = m.groups()
        out.add(f'{whole}"{frac[0]}')
        out.add(f'{whole}"{frac[0]}-')
        out.add(f"{whole}.{frac[0]}")
        out.add(f"{whole}.{frac[0]}-")
        out.add(f"{whole},{frac[0]}")
    return tuple(out)


@lru_cache(maxsize=4096)
def _perf_patterns(perf):
    return tuple(re.compile(r"(?<![\d.,])" + re.escape(v) + r"(?![\d])")
                 for v in _perf_variants(perf))


def _perf_in_line(norm_line, perf):
    if not perf:
        return False
    return any(p.search(norm_line) for p in _perf_patterns(str(perf)))


STATUS_MARKS = frozenset(("NP", "N.P", "RET", "DQ", "DNS", "DNF", "-"))


def is_status_mark(performance):
    """A status code, not a mark: there is no wind to attach to it."""
    return str(performance or "").strip().upper().rstrip(".") in STATUS_MARKS


MAX_WIND = 9.9


def format_wind(value):
    """The dataset's spelling of a wind: sign always present, one decimal.

    The value always comes from the sheet (``wind_on_sheet`` in the audit
    CSV); this normalises only its spelling, it never invents a measurement.
    A zero wind is stored as ``+0.0``, the spelling 994 existing rows use, so
    ``-0.0`` and ``+0,00`` land there too: a signed zero is the same
    measurement as zero. Returns None for anything that is not a wind in the
    measuring range (a mark, a blank, a status word).
    """
    text = str(value or "").strip().replace(",", ".").replace(" ", "")
    if not text:
        return None
    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    if abs(number) > Decimal(str(MAX_WIND)):
        return None
    number = abs(number).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if not number:
        return "+0.0"
    return ("-" if sign == "-" else "+") + f"{number:.1f}"


def _locate_perf(sheet, index, perf):
    """Distance from a name line to the line of its block carrying the mark.

    Returns None when the mark is not inside this athlete's block, which is how
    the same athlete's rows in two different events stay apart. The window is
    bounded by the next line that carries a date of birth (the next athlete).
    """
    if _perf_in_line(sheet.norm_lines[index], perf):
        return 0
    for j in range(index + 1, min(index + 9, len(sheet.lines))):
        if _DOB_RE.search(sheet.lines[j]):
            return None
        if _perf_in_line(sheet.norm_lines[j], perf):
            return j - index
    return None


class Decision(namedtuple("Decision", "cls wind evidence note family")):
    pass


def _decide_track(sheet, name_idx, perf, perf_line):
    """Wind for a sprint/hurdle row: its own row's wind column, else its series."""
    # 1. A per-row "Resultado Viento" column prints the wind on the row itself.
    #    In a Conersys block the wind sits on the mark line, a few lines below
    #    the name (name / pos+club / club code / license / lane+mark+wind).
    for j in range(name_idx, (perf_line if perf_line is not None else name_idx) + 1):
        toks = wind_tokens(sheet.lines[j])
        if toks and _perf_in_line(sheet.norm_lines[j], perf):
            return toks[0].value, sheet.lines[j].strip(), "row-column"

    # 2. The series header printed above the rows of this series.
    anchor = perf_line if perf_line is not None else name_idx
    value, evidence = sheet.track_wind_at(anchor)
    if value is None and anchor != name_idx:
        value, evidence = sheet.track_wind_at(name_idx)
    return value, evidence, "series-header" if evidence else "no-header"


def _find_attempts(sheet, name_idx, perf):
    """(attempt tokens, their line) for a jump row.

    The attempts sit on the athlete's name line in every layout in the
    corpus; the two lines below are checked only when the row's own mark is
    there (a split attempt column), never guessed from a neighbouring athlete.
    """
    for j in (name_idx, name_idx + 1, name_idx + 2):
        if j >= len(sheet.lines):
            break
        toks = _attempt_tokens(sheet.lines[j])
        if not toks:
            continue
        if j != name_idx and _DOB_RE.search(sheet.lines[j]):
            continue  # another athlete's block, never borrow its marks
        if j == name_idx or any(_same_mark(t.value, perf) for t in toks):
            return toks, j
    return [], name_idx


def _decide_jump(sheet, name_idx, perf):
    """Wind for a jump row: the wind printed under this athlete's attempt."""
    attempts, attempt_line = _find_attempts(sheet, name_idx, perf)
    if not attempts:
        return None, None, "no-attempts"

    target = next((t for t in attempts if _same_mark(t.value, perf)), None)
    if target is None:
        return None, None, "attempt-not-found"
    center = (target.start + target.end) / 2

    # Wind may be printed on the attempt line (Conersys Viento column) or on one
    # of the lines just below it (RFEA club+licence line, era pure-numeric wind
    # line). A single 'Resultado' wind on its own line can sit between them, so
    # score every candidate line and keep the best-aligned one instead of
    # stopping at the first hit.
    candidates = []
    for j in (attempt_line, attempt_line + 1, attempt_line + 2, attempt_line + 3,
              attempt_line + 4):
        if j >= len(sheet.lines):
            break
        if j != attempt_line and _DOB_RE.search(sheet.lines[j]):
            break  # the next athlete's block starts here
        toks = (wind_tokens(sheet.lines[j]) if j == attempt_line
                else wind_line_tokens(sheet.lines[j]))
        if not toks:
            continue
        if j != attempt_line and _attempt_tokens(sheet.lines[j]):
            continue  # a marks line, not a wind line
        best, nearest = 1e9, None
        for tok in toks:
            dist = abs((tok.start + tok.end) / 2 - center)
            if dist < best:
                best, nearest = dist, tok
        if j == attempt_line:
            return nearest.value, sheet.lines[j].strip(), "attempt-wind"
        candidates.append((best, -len(toks), nearest.value,
                           sheet.lines[j].strip()))
    if not candidates:
        return None, None, "no-wind-line"
    candidates.sort(key=lambda c: (c[0], c[1]))
    best, _neg, value, evidence = candidates[0]
    if best <= 20:
        return value, evidence, "attempt-wind"
    return None, evidence, "wind-line-misaligned"


def decide(sheet, row, indoor=False):
    """Classify one null-wind wind-applicable row."""
    discipline = row.get("discipline") or ""
    family = classify_family(discipline)
    perf = row.get("performance") or ""
    tokens = name_tokens(row.get("athlete_name") or "")

    if sheet is None:
        return Decision("no-pdf", None, "", "no readable pdf", family)

    candidates = sheet.lines_with(tokens)
    if not candidates and tokens:
        # fall back to the longest token: covers truncated/extra middle names
        longest = max(tokens, key=len)
        candidates = sheet.lines_with([longest])
    if not candidates:
        return Decision("unmatched", None, "", "athlete line not found", family)

    # An athlete can appear in several events; the mark is what tells the blocks
    # apart (the same 60m hurdler runs two rounds with different times).
    located = []
    for index in candidates:
        distance = _locate_perf(sheet, index, perf)
        if distance is not None:
            located.append((distance, index))
    note = ""
    if located:
        located.sort()
        chosen = located[0][1]
        perf_line = chosen + located[0][0]
        if len(located) > 1:
            note = "multiple-lines"
    else:
        chosen = candidates[0]
        perf_line = None
        note = "mark-not-in-block"
        if len(candidates) > 1:
            note += ";multiple-lines"
            # fall back to the section kind as the tie-break
            jump = family in ("long jump", "triple")
            preferred = [i for i in candidates
                         if bool(_JUMP_TITLE_RE.search(sheet.title_at(i))) == jump]
            if preferred:
                chosen = preferred[0]

    if family in ("long jump", "triple"):
        value, evidence, why = _decide_jump(sheet, chosen, perf)
    else:
        value, evidence, why = _decide_track(sheet, chosen, perf, perf_line)

    note = why + ((";" + note) if note else "")
    if is_status_mark(perf):
        note += ";status-mark"
    # Indoor wins over a printed wind: a pista coberta meet does not measure
    # wind, so a `VENT` column there is the timing template printing its field,
    # not a measurement. The five December Cambrils combined championships are
    # the case in point: titled `DE PISTA COBERTA` and every section is 60 m /
    # 60 m hurdles (no 100 m anywhere), yet each series prints `VENT : -0,9`.
    # The same applies row-wise: a `PC` section inside a mixed meet.
    if indoor or row_says_indoor(row):
        if value:
            note += ";printed-wind-not-applicable"
        return Decision("indoor", None, evidence or "", note, family)
    if value:
        return Decision("pdf-has-wind", value, evidence or "", note, family)
    if sheet.combined_at(chosen):
        return Decision("combined-event", None, evidence or "", note, family)
    if why in ("no-attempts", "attempt-not-found", "wind-line-misaligned"):
        # The sheet's silence is not the same as a decision: list it.
        return Decision("unmatched", None, evidence or "", note, family)
    return Decision("pdf-no-wind", None, evidence or "", note, family)


# ---------------------------------------------------------------------------
# Source text
# ---------------------------------------------------------------------------

def _is_pdf(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(5).lstrip()[:4] == b"%PDF"
    except OSError:
        return False


def read_pdf_text(path):
    """pdftotext -layout text of a cached PDF, or None when it is not a PDF.

    Several pdf_cache entries are HTML error pages saved with a .pdf name
    (e.g. a 404 body); those must count as no-pdf, not crash the run.
    """
    if not _is_pdf(path):
        return None
    try:
        return extract_text(str(path))
    except (SystemExit, Exception):  # extract_text sys.exit(1)s on failure
        return None


def download_pdf(url, dest):
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # fcatletisme.cat answers 406 to unknown agents and to any UA carrying
        # a '(compatible; ...)' comment, but serves the PDF to a plain client
        # banner. The audit only fills pdf_cache; it never touches seasons/.
        req = Request(url, headers={
            "User-Agent": "curl/8.5.0",
            "Accept": "*/*",
        })
        with urlopen(req, timeout=45) as response:
            data = response.read()
        if not data.lstrip()[:4].startswith(b"%PDF"):
            return False
        tmp = dest + ".part"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dest)
        return True
    except Exception:
        return False


class TextSource:
    """Per-run text cache: one pdftotext call per PDF, never two."""

    def __init__(self, allow_download=True):
        self.allow_download = allow_download
        self._cache = OrderedDict()
        self.stats = Counter()
        self.dead_urls = []

    def get(self, season, stem, event_src):
        key = (season, stem)
        if key in self._cache:
            self.stats["cached_text_hits"] += 1
            return self._cache[key]
        path = REPO_ROOT / "pdf_cache" / season / (stem + ".pdf")
        text = read_pdf_text(path)
        if text is None:
            if os.path.exists(path):
                self.stats["cache_not_a_pdf"] += 1
            else:
                self.stats["cache_miss"] += 1
            if event_src and self.allow_download and download_pdf(event_src, str(path)):
                self.stats["downloaded"] += 1
                text = read_pdf_text(path)
            else:
                if event_src:
                    self.stats["dead_url"] += 1
                    self.dead_urls.append((season, stem, event_src))
                else:
                    self.stats["no_url"] += 1
        self._cache[key] = text
        if len(self._cache) > 16:
            self._cache.popitem(last=False)
        return text


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

_AUDIT_FIELDS = ("file", "season", "family", "athlete", "discipline",
                 "performance", "class", "wind_on_sheet", "evidence", "note",
                 "file_indoor")
_SHORT_TRACK_FIELDS = ("file", "season", "event_name", "is_short_track",
                       "header_says_indoor", "disciplines_say_indoor", "verdict")

_PC_DISCIPLINE_RE = re.compile(r"\bPC\b|pista coberta|pista cubierta|short track",
                               re.IGNORECASE)
_AL_DISCIPLINE_RE = re.compile(r"\bAL\b|aire lliure|aire libre", re.IGNORECASE)


def row_says_indoor(row):
    """The row's own discipline says pista coberta.

    Mixed meets (a combined event whose 60 m runs indoors and whose throws run
    outdoors) label the discipline, not the file: '60m S12 Hombres PC' next to
    '60m S14 Hombres AL'.
    """
    return bool(_PC_DISCIPLINE_RE.search(row.get("raw_discipline_name") or ""))


def disciplines_say_indoor(results):
    """Disciplines are marked pista coberta and none is marked aire lliure.

    Conersys sheets label each section with its track: 'PC' (pista coberta) or
    'AL' (aire lliure). A file whose sections carry no AL marker is an indoor
    meet, even when only part of its sections carry the PC marker. A meet that
    prints both runs part of the day outdoors and is not an indoor meet: a
    threshold on the PC share cannot tell those apart, the absence of AL can.
    """
    names = [r.get("raw_discipline_name") or "" for r in results]
    if not names:
        return False
    pc = any(_PC_DISCIPLINE_RE.search(n) for n in names)
    al = any(_AL_DISCIPLINE_RE.search(n) for n in names)
    return pc and not al


def season_dirs(selected):
    seasons = sorted(p.name for p in (REPO_ROOT / "seasons").iterdir()
                     if p.is_dir() and (p / "json").is_dir())
    if not selected:
        return seasons
    wanted = []
    for item in selected:
        wanted.extend(part.strip() for part in str(item).split(",") if part.strip())
    unknown = [w for w in wanted if w not in seasons]
    if unknown:
        raise SystemExit(f"unknown season(s): {', '.join(unknown)}")
    return wanted


def audit(seasons, allow_download=True, limit=None, verbose=False):
    source = TextSource(allow_download=allow_download)
    audit_rows = []
    short_track_rows = []
    completed = []

    for season in seasons:
        json_dir = REPO_ROOT / "seasons" / season / "json"
        files = sorted(json_dir.glob("*.json"))
        if limit:
            files = files[:limit]
        if not files:
            continue
        completed.append(season)
        for path in files:
            try:
                with open(path, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, ValueError) as exc:
                if verbose:
                    print(f"  ! unreadable {path.name}: {exc}", file=sys.stderr)
                continue
            results = doc.get("results") or []
            flag = doc.get("is_short_track") is True
            event_src = doc.get("event_src") or ""
            stem = path.stem

            pending = [r for r in results
                       if r.get("wind") is None
                       and wind_applicable(r.get("discipline") or "")]
            text = source.get(season, stem, event_src)
            header_indoor = bool(text) and detect_short_track(text, event_src or stem)
            disc_indoor = disciplines_say_indoor(results)

            # S4: the is_short_track contract, independent of the wind rows.
            verdict = ""
            if text is None and not disc_indoor:
                verdict = "unverified-no-pdf"
            elif flag and not header_indoor and not disc_indoor:
                verdict = "flag-true-but-outdoor"
            elif not flag and (header_indoor or disc_indoor):
                verdict = "flag-false-but-indoor"
            if verdict:
                short_track_rows.append({
                    "file": str(path.relative_to(REPO_ROOT)),
                    "season": season,
                    "event_name": doc.get("event_name") or "",
                    "is_short_track": flag,
                    "header_says_indoor": header_indoor,
                    "disciplines_say_indoor": disc_indoor,
                    "verdict": verdict,
                })

            if not pending:
                continue

            sheet = Sheet(text) if text is not None else None
            file_indoor = flag or header_indoor or disc_indoor
            for row in pending:
                decision = decide(sheet, row,
                                  indoor=file_indoor or row_says_indoor(row))
                audit_rows.append({
                    "file": str(path.relative_to(REPO_ROOT)),
                    "season": season,
                    "family": decision.family,
                    "athlete": row.get("athlete_name") or "",
                    "discipline": row.get("discipline") or "",
                    "performance": row.get("performance") or "",
                    "class": decision.cls,
                    "wind_on_sheet": decision.wind or "",
                    "evidence": (decision.evidence or "").strip()[:200],
                    "note": decision.note or "",
                    "file_indoor": "true" if file_indoor else "false",
                })
            if verbose:
                print(f"  {season}/{path.name}: {len(pending)} rows", file=sys.stderr)

    return audit_rows, short_track_rows, source, completed


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
    os.replace(tmp, path)


def summarize(audit_rows, short_track_rows, source, completed):
    total = len(audit_rows)
    classes = Counter(r["class"] for r in audit_rows)
    families = Counter(r["family"] for r in audit_rows)

    print(f"Seasons completed: {', '.join(completed) if completed else '(none)'}")
    print(f"Null wind-applicable rows audited: {total}")
    print("")
    print("By class:")
    for cls in CLASSES:
        if classes.get(cls):
            print(f"  {cls:<14} {classes[cls]:>6}")
    print("")
    print(f"{'family':<12}{'rows':>8}{'pdf-has-wind':>14}{'pdf-no-wind':>13}"
          f"{'indoor':>8}{'combined':>10}{'unmatched':>11}")
    for fam in FAMILIES:
        if not families.get(fam):
            continue
        subset = [r for r in audit_rows if r["family"] == fam]
        c = Counter(r["class"] for r in subset)
        print(f"{fam:<12}{len(subset):>8}{c.get('pdf-has-wind', 0):>14}"
              f"{c.get('pdf-no-wind', 0):>13}{c.get('indoor', 0):>8}"
              f"{c.get('combined-event', 0):>10}{c.get('unmatched', 0):>11}")

    has_wind = [r for r in audit_rows if r["class"] == "pdf-has-wind"]
    if has_wind:
        print("")
        print("pdf-has-wind rows grouped by file (repair worklist):")
        grouped = Counter(r["file"] for r in has_wind)
        for file, count in grouped.most_common():
            fams = Counter(r["family"] for r in has_wind if r["file"] == file)
            detail = ", ".join(f"{k} {v}" for k, v in fams.most_common())
            print(f"  {count:>4}  {file}  ({detail})")

    if has_wind:
        indoor_wind = [r for r in has_wind if r["file_indoor"] == "true"]
        print("")
        print(f"  of these, {len(indoor_wind)} sit in files whose header or "
              f"disciplines say pista coberta (fix the flag first: see "
              f"short_track_contract.csv)")

    unmatched = [r for r in audit_rows if r["class"] == "unmatched"]
    if unmatched:
        print("")
        print(f"Undecided from the sheet ({len(unmatched)} rows), listed in the CSV:")
        for r in unmatched[:15]:
            print(f"  ! {r['season']} {r['athlete']} | {r['discipline']} "
                  f"{r['performance']} | {r['note']}")
        if len(unmatched) > 15:
            print(f"  ... and {len(unmatched) - 15} more")

    no_pdf = [r for r in audit_rows if r["class"] == "no-pdf"]
    if no_pdf:
        print("")
        print(f"no-pdf rows: {len(no_pdf)} in "
              f"{len(set(r['file'] for r in no_pdf))} files")

    print("")
    print("Source stats: " + ", ".join(f"{k}={v}" for k, v in sorted(source.stats.items())))
    if source.dead_urls:
        print(f"Dead/unfetchable URLs ({len(source.dead_urls)}):")
        for season, stem, url in source.dead_urls[:20]:
            print(f"  {season}/{stem}: {url}")
        if len(source.dead_urls) > 20:
            print(f"  ... and {len(source.dead_urls) - 20} more")

    verdicts = Counter(r["verdict"] for r in short_track_rows)
    print("")
    print("is_short_track contract:")
    for verdict, count in sorted(verdicts.items()):
        print(f"  {verdict:<22} {count}")
    shown = 0
    for r in short_track_rows:
        if r["verdict"] == "unverified-no-pdf" or shown >= 12:
            continue
        shown += 1
        print(f"  * {r['verdict']}: {r['file']} (flag={r['is_short_track']}, "
              f"header={r['header_says_indoor']}, "
              f"disciplines={r['disciplines_say_indoor']})")
    if verdicts.get("flag-false-but-indoor", 0) > shown:
        print(f"  ... and {verdicts['flag-false-but-indoor'] - shown} more "
              f"flag-false-but-indoor (see the CSV)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure how many null-wind rows have a wind on the sheet "
                    "(issue #25). Read-only for data.")
    parser.add_argument("--season", action="append", default=[],
                        help="season dir name (repeatable or comma separated)")
    parser.add_argument("--limit", type=int, default=None,
                        help="only the first N json files per season")
    parser.add_argument("--no-download", action="store_true",
                        help="never fetch a missing PDF from event_src")
    parser.add_argument("--dry-run", action="store_true",
                        help="explain what would be written (nothing is repaired)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    seasons = season_dirs(args.season)
    print("wind audit — dry run, no data is modified"
          f" (seasons: {', '.join(seasons) or 'all'})")
    audit_rows, short_track_rows, source, completed = audit(
        seasons,
        allow_download=not args.no_download,
        limit=args.limit,
        verbose=args.verbose,
    )
    audit_rows.sort(key=lambda r: (r["file"], r["discipline"], r["athlete"],
                                   r["performance"], r["class"]))
    short_track_rows.sort(key=lambda r: r["file"])
    write_csv(AUDIT_CSV, _AUDIT_FIELDS, audit_rows)
    write_csv(SHORT_TRACK_CSV, _SHORT_TRACK_FIELDS, short_track_rows)
    print("")
    summarize(audit_rows, short_track_rows, source, completed)
    print("")
    print(f"Wrote {AUDIT_CSV.relative_to(REPO_ROOT)} "
          f"({len(audit_rows)} rows) and "
          f"{SHORT_TRACK_CSV.relative_to(REPO_ROOT)} ({len(short_track_rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
