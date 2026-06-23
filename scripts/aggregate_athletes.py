#!/usr/bin/env python3
"""Aggregate all CA Tarragona athlete results into per-athlete JSON files.

Scans seasons/ and json/ directories, groups results by athlete identity
(license + normalized name), deduplicates, and writes one JSON per athlete
to athletes/.

Usage:
    python scripts/aggregate_athletes.py
    python scripts/aggregate_athletes.py --athlete "DIDAC RIOS MESEGUER"
    python scripts/aggregate_athletes.py --dry-run --verbose
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Name cleaning
# ---------------------------------------------------------------------------

# Category codes that appear as suffixes in names — stripped during normalization
# These include adapted athletics (AF, AM), binary (BF, BM), indoor (IM, IF),
# sprint (SF, SM), free (LF, LM), pista (PF, PM), junior (JNF, JVF, JNM),
# prebenjami (PBM, PBF), etc.
CATEGORY_SUFFIXES = frozenset({
    # Combined events
    "IF", "CF", "JF", "JM", "AM", "CM", "BF", "SM",
    # Adapted athletics
    "AF", "AM",
    # Binary
    "BF", "BM",
    # Sprint / free / pista / etc.
    "SF", "LM", "LF", "PF", "PM",
    # Indoor
    "IM",
    # Junior categories
    "JNF", "JVF", "JNM",
    # Prebenjami categories
    "PBM", "PBF",
    # Other category / noise / performance markers
    "DNS", "DQ", "DNF", "RET", "NP", "MMT", "MMF", "MMP",
    # Medal types
    "BRONZE", "PLATA", "OR", "GOLD", "SILVER",
    # Qualification markers
    "Q", "QB", "QN", "QC",
    # Club metadata / category markers / record tags
    "DOR", "CAT", "CL", "RCAM", "ARGENT",
    # Other
    "ABF", "ABM", "OT",
})

# Age/gender category suffix: M-35, W-40, M-55, W-50, etc.
_RE_AGE_CAT = re.compile(r"\s+[MW]-\d+.*$")

# Performance marker suffix: "10.1-", "9.7-", "3.5", etc.
_RE_PERF_MARKER = re.compile(r"^[0-9]+(\.[0-9]+)?-$")

# Jump mark tokens: "O--", "X-", "XO-"
_RE_JUMP_MARK = re.compile(r"^[OX-]+$")

# Leading position + dorsal: "9 25 (t) " or "9 25 "
_RE_LEAD_POS_DORSAL = re.compile(r"^\d+\s+\d+\s*(\(t\)\s*)?")
_RE_LEAD_POS = re.compile(r"^\d+\s+")

# Series marker anywhere
_RE_SERIES = re.compile(r"\(t\)|\(T\)")

# Trailing standalone digits: "Meseguer M-35 3" → "Meseguer"
_RE_TRAIL_DIGITS = re.compile(r"\s+\d+\s*$")

# Qualification marker: "Guasch 7 Q", "Guasch 7 q"
_RE_TRAIL_QUAL = re.compile(r"\s+\d+\s*[Qq]\b\s*$")

# Numeric-only tokens (15, 1.5, 10.9)
_RE_NUM_TOKEN = re.compile(r"^\d+([.,]\d+)?$")

# DOB pattern
_RE_DOB = re.compile(r"\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}")

# PDF truncation marker (U+2026) in truncated surnames/times
_RE_TRUNCATED = re.compile(r"…|\.\.\.+")

# License patterns
_RE_LICENSE = re.compile(r"(CAT-\d+[A-Z]?\b|CT[\d\-]+|CL\d+|IB-\d+[A-Z\.]?\b|LZ[\d\-]+)")


def _is_truncated_token(token: str) -> bool:
    """Return True if token was truncated by PDF layout (e.g. FERNAN…)."""
    return bool(_RE_TRUNCATED.search(token))


def _expand_compound_first_names(tokens: list[str]) -> list[str]:
    """Split glued first+middle names (e.g. LAURINEELISA -> LAURINE ELISA)."""
    expanded: list[str] = []
    for t in tokens:
        upper = _strip_accents(t).upper()
        if upper.startswith("LAURINE") and len(upper) > len("LAURINE"):
            suffix = upper[len("LAURINE"):]
            if suffix in ("ELISA", "ELI"):
                expanded.extend(["LAURINE", "ELISA"])
                continue
        expanded.append(t)
    return expanded


def _strip_accents(text: str) -> str:
    """Convert accented characters to ASCII approximations."""
    mappings = {
        "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "Å": "A",
        "È": "E", "É": "E", "Ê": "E", "Ë": "E",
        "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
        "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
        "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U",
        "Ý": "Y", "Þ": "TH",
        "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
        "è": "e", "é": "e", "ê": "e", "ë": "e",
        "ì": "i", "í": "i", "î": "i", "ï": "i",
        "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o",
        "ù": "u", "ú": "u", "û": "u", "ü": "u",
        "ý": "y", "þ": "th",
        "ÿ": "y", "Ñ": "N", "ñ": "n",
        "Ç": "C", "ç": "c",
        "Í": "I", "Ì": "I", "Ú": "U", "Ú": "U",
    }
    result = []
    for ch in text:
        result.append(mappings.get(ch, ch))
    return "".join(result)


def clean_name_for_match(raw: str) -> str | None:
    """Clean a raw athlete name and return a canonical sorted key.

    Returns the sorted token key (e.g. "NAVARRETE SILVIA VICENTE") or None
    if the name is invalid (too few tokens, purely numeric, etc.).
    """
    name = raw.strip()
    if not name:
        return None

    # 1. Strip accents and uppercase
    name = _strip_accents(name).upper()

    # 2. Remove leading position + dorsal
    name = _RE_LEAD_POS_DORSAL.sub("", name)
    name = _RE_LEAD_POS.sub("", name)

    # 3. Remove series markers
    name = _RE_SERIES.sub("", name)

    # 4. Remove qualification suffix (7 Q, 8 q)
    name = _RE_TRAIL_QUAL.sub("", name)

    # 5. Split into tokens
    tokens = name.split()

    # 6. Remove age/gender category suffixes (M-35, W-40, etc.)
    while tokens and _RE_AGE_CAT.fullmatch(" " + tokens[-1]):
        tokens.pop()
    # Also handle "M-35" style without space
    tokens = [t for t in tokens if not re.fullmatch(r"[MW]-\d+", t, re.I)]

    # 7. Remove category codes from beginning of name (IF, IM, AF, etc.)
    while tokens and _is_noise_token(tokens[0]):
        tokens.pop(0)

    # 7b. Remove category codes from ANY position (middle of names too)
    tokens = [t for t in tokens if not _is_noise_token(t)]

    # 8. Remove category codes from end of name
    while tokens and _is_noise_token(tokens[-1]):
        tokens.pop()
    # Handle "JF 3", "IF 6" pattern: category + digit
    while len(tokens) >= 2 and tokens[-1].isdigit() and _is_noise_token(tokens[-2]):
        tokens.pop()
        tokens.pop()

    # 9. Remove jump mark tokens (O--, X-, XO-)
    tokens = [t for t in tokens if not _RE_JUMP_MARK.fullmatch(t)]

    # 9b. Remove performance markers (10.9-, 7.5-, etc.)
    tokens = [t for t in tokens if not _RE_PERF_MARKER.fullmatch(t)]

    # 10. Remove trailing standalone digits
    while tokens and tokens[-1].isdigit():
        tokens.pop()

    # 11. Remove trailing NUMBER WORD patterns (e.g. "6 BRONZE", "5 Q")
    while len(tokens) >= 2 and _is_noise_token(tokens[-1]) and tokens[-2].isdigit():
        tokens.pop()
        tokens.pop()

    # 12. Remove DOB patterns from tokens
    tokens = [t for t in tokens if not _RE_DOB.fullmatch(t)]

    # 13. Collapse and filter
    tokens = [t for t in tokens if t and not t.isdigit() and not _RE_NUM_TOKEN.match(t)]

    # 14. Drop PDF-truncated tokens (FERNAN… breaks surname matching)
    tokens = [t for t in tokens if not _is_truncated_token(t)]

    # 15. Split compound first names (LAURINEELISA -> LAURINE ELISA)
    tokens = _expand_compound_first_names(tokens)

    # Apply typo normalization to tokens before building key
    typo_key = _apply_typo_fixes(" ".join(tokens))
    if typo_key:
        tokens = typo_key.split()

    # Validation
    if len(tokens) < 2:
        return None

    # Reject purely numeric or known noise-only names
    joined = " ".join(tokens).upper()
    if joined in ("DOR", "CAT", "DOR CAT"):
        return None
    if all(t.isdigit() for t in tokens):
        return None

    # Build name_key: sorted tokens (permutation-independent)
    name_key = " ".join(sorted(tokens))
    return name_key


def derive_canonical_name(raw: str) -> str:
    """Derive a display-friendly canonical name from a raw name.

    Prefers format "NOM COGNOM1 COGNOM2" — variant without prefix numbers,
    without category codes, without digits at end.
    """
    name = raw.strip()
    if not name:
        return ""

    # Remove leading position + dorsal
    name = _RE_LEAD_POS_DORSAL.sub("", name)
    name = _RE_LEAD_POS.sub("", name)

    # Remove series markers
    name = _RE_SERIES.sub("", name)

    # Remove DOB patterns
    name = _RE_DOB.sub("", name).strip()

    # Remove qualification suffix (7 Q, 8 q)
    name = _RE_TRAIL_QUAL.sub("", name)

    tokens = name.split()

    # Remove age/gender category suffixes
    tokens = [t for t in tokens if not re.fullmatch(r"[MW]-\d+", t, re.I)]

    # Remove category codes from beginning
    while tokens and _is_noise_token(tokens[0]):
        tokens.pop(0)

    # Remove category suffixes from end
    while tokens and _is_noise_token(tokens[-1]):
        tokens.pop()

    # Handle "JF 3", "IF 6" pattern: category + digit
    while len(tokens) >= 2 and tokens[-1].isdigit() and _is_noise_token(tokens[-2]):
        tokens.pop()
        tokens.pop()

    # Remove performance markers
    while tokens and _RE_PERF_MARKER.fullmatch(tokens[-1]):
        tokens.pop()

    # Remove jump marks
    tokens = [t for t in tokens if not _RE_JUMP_MARK.fullmatch(t)]

    # Remove trailing NUMBER WORD patterns (e.g. "6 BRONZE", "5 Q")
    while len(tokens) >= 2 and _is_noise_token(tokens[-1]) and tokens[-2].isdigit():
        tokens.pop()
        tokens.pop()

    # Remove trailing category suffixes (post-number cleanup)
    while tokens and _is_noise_token(tokens[-1]):
        tokens.pop()

    # Remove category codes from ANY position (middle of names too)
    tokens = [t for t in tokens if not _is_noise_token(t)]

    # Remove trailing standalone digits
    while tokens and tokens[-1].isdigit():
        tokens.pop()

    # Remove empty tokens and numeric noise
    tokens = [t for t in tokens if t and not t.isdigit() and not _RE_NUM_TOKEN.match(t)]

    # Drop PDF-truncated tokens and split compound first names
    tokens = [t for t in tokens if not _is_truncated_token(t)]
    tokens = _expand_compound_first_names(tokens)

    if not tokens:
        return raw.upper()

    return " ".join(tokens).upper()


# ---------------------------------------------------------------------------
# License normalization
# ---------------------------------------------------------------------------

def normalize_license(athlete_id: str) -> str:
    """Normalize a license string.

    - Uppercase, strip
    - Remove trailing -A suffix (e.g. CAT-3742954-A → CAT-3742954)
    - Remove hyphens within CT numbers
    """
    if not athlete_id:
        return ""
    lic = athlete_id.strip().upper()
    # Remove trailing -A or similar suffix
    lic = re.sub(r"-([A-Z]\d*)$", "", lic)
    # Normalize CT-XXX to CTXXX
    lic = re.sub(r"CT-(\d+)", r"CT\1", lic)
    return lic


def license_priority(lic: str) -> int:
    """Return priority for license type (higher = preferred)."""
    if lic.startswith("CAT-"):
        return 3
    if lic.startswith("CT"):
        return 2
    if lic.startswith("CL"):
        return 1
    if lic.startswith("IB"):
        return 1
    if lic.startswith("LZ"):
        return 1
    return 0


# ---------------------------------------------------------------------------
# DOB normalization
# ---------------------------------------------------------------------------

def normalize_dob(dob: str) -> str:
    """Normalize DOB to DD/MM/YYYY or D/M/YYYY format for comparison."""
    if not dob:
        return ""
    dob = dob.strip()
    # Try to parse and re-format
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y",
                "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(dob, fmt)
            if dt.year > 2030 or dt.year < 1900:
                continue
            return dt.strftime("%d/%m/%Y").lstrip("0").replace("/0", "/")
        except ValueError:
            continue
    return dob


def dob_compatible(dob1: str, dob2: str) -> bool:
    """Check if two DOBs are compatible (same day/month/year)."""
    n1 = normalize_dob(dob1)
    n2 = normalize_dob(dob2)
    return n1 == n2


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class UnionFind:
    """Simple union-find data structure."""

    def __init__(self):
        self.parent: dict[int, int] = {}
        self.rank: dict[int, int] = {}

    def _get(self, x: int) -> int:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        return self.parent[x]

    def find(self, x: int) -> int:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ---------------------------------------------------------------------------
# JSON collection
# ---------------------------------------------------------------------------

def collect_json_files(root: Path, scan_dirs: list[str]) -> list[Path]:
    """Collect all JSON files from scan directories, excluding pdf_cache/2005/json/."""
    paths: list[Path] = []
    for scan_dir in scan_dirs:
        base = root / scan_dir
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.json")):
            # Skip pdf_cache/2005/json/ — duplicates of seasons/2005/json/
            parts = p.parts
            if "pdf_cache" in parts and "2005" in parts and "json" in parts:
                continue
            # Skip .json.json files
            if p.name.endswith(".json.json"):
                continue
            paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def extract_results(root: Path, scan_dirs: list[str], verbose: bool = False):
    """Extract all valid results from JSON files.

    Returns:
        results: list of result dicts with source file info
        stats: dict of processing statistics
    """
    json_files = collect_json_files(root, scan_dirs)
    results = []
    stats = {
        "files_scanned": 0,
        "files_with_catt": 0,
        "total_results": 0,
        "invalid_json": [],
        "skipped_empty": 0,
    }

    for path in json_files:
        stats["files_scanned"] += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            stats["invalid_json"].append((str(path), str(exc)))
            continue

        event_name = data.get("event_name", "")
        event_date = data.get("event_date", "")
        event_location = data.get("event_location", "")
        event_src = data.get("event_src", "")

        for result in data.get("results", []):
            athlete_name = (result.get("athlete_name") or "").strip()
            athlete_dob = (result.get("athlete_dob") or "").strip()
            athlete_id = (result.get("athlete_id") or "").strip()
            performance = (result.get("performance") or "").strip()
            discipline = (result.get("discipline") or "").strip()
            wind = result.get("wind")

            # Validate required fields
            if not athlete_name or not performance or not discipline:
                stats["skipped_empty"] += 1
                continue

            stats["total_results"] += 1

            results.append({
                "event_name": event_name,
                "event_date": event_date,
                "event_location": event_location,
                "event_src": event_src,
                "athlete_name": athlete_name,
                "athlete_dob": athlete_dob,
                "athlete_id": athlete_id,
                "performance": performance,
                "discipline": discipline,
                "wind": wind,
                "_source_file": str(path),
            })

    if verbose:
        print(f"Files scanned: {stats['files_scanned']}", file=sys.stderr)
        print(f"Total results extracted: {stats['total_results']}", file=sys.stderr)
        if stats["invalid_json"]:
            print(f"Invalid JSON files: {len(stats['invalid_json'])}", file=sys.stderr)
        if stats["skipped_empty"]:
            print(f"Skipped results (empty fields): {stats['skipped_empty']}", file=sys.stderr)

    return results, stats


# ---------------------------------------------------------------------------
# Fuzzy name matching (typos, nicknames)
# ---------------------------------------------------------------------------

# Common Catalan OCR typo mappings: typo → corrected
# These are single-character or common substitutions
OCR_TYPOS = {
    # v/b confusion
    "B": "V", "V": "B",
}

# Known typo pairs for last names (set of frozensets)
# Each pair represents two spellings of the same last name
LAST_NAME_TYPOS = [
    frozenset({"PASANO", "PASANA", "PASANT", "PAISANO"}),
    frozenset({"SERRES", "SRRES"}),
    frozenset({"MESEGUER", "MESSEGUER"}),
    frozenset({"GUASCH", "GUASH"}),
]

TYPO_PREFERRED: dict[frozenset, str] = {
    frozenset({"PASANO", "PASANA", "PASANT", "PAISANO"}): "PAISANO",
    frozenset({"SERRES", "SRRES"}): "SERRES",
    frozenset({"MESEGUER", "MESSEGUER"}): "MESEGUER",
    frozenset({"GUASCH", "GUASH"}): "GUASCH",
    frozenset({"FARRE", "FERRER", "FERRÉ", "FERRE"}): "FERRER",
    frozenset({"ROMERO", "RONMERO"}): "ROMERO",
    frozenset({"BARBERA", "BARBERAN"}): "BARBERAN",
    frozenset({"CASMITJANA", "CASAMITJANA"}): "CASAMITJANA",
    frozenset({"MARIMON", "MARIMÓN", "MARIMÓ"}): "MARIMON",
    frozenset({"LAURINEELI", "LAURINE"}): "LAURINE",
    frozenset({"FERNANDEZ", "FERNÁNDEZ", "FERNANDÉZ"}): "FERNANDEZ",
    frozenset({"ESTEBAN", "ESTEBÁN"}): "ESTEBAN",
}


def _is_noise_token(token: str) -> bool:
    """Return True if token is a category/noise marker (case-insensitive)."""
    upper = token.upper()
    if upper.startswith("="):
        return True
    return upper in CATEGORY_SUFFIXES

# Nickname pairs: canonical → [variants]
NICKNAMES = {
    "ALEJANDRO": ["ALEX"],
    "AMADEO": ["AMADEU"],
    "JOSE": ["JOSEP", "JOSÉ", "JOSEP"],
    "JOSÉ": ["JOSEP", "JOSE"],
    "JORDI": ["JORDEI"],
    "MARC": ["MARÇAL"],
    "MARÇAL": ["MARC"],
    "XAVIER": ["XABI"],
    "FRANCISCO": ["FRAN", "FCO", "JAVIER"],
    "JAVIER": ["JAVI", "JAVIER"],
    "ANTONIO": ["ANTONI", "TONI"],
    "ANTONI": ["ANTONIO", "TONI"],
    "MANUEL": ["MANEL"],
    "MANEL": ["MANUEL"],
    "PEDRO": ["PERE"],
    "PERE": ["PEDRO"],
    "PABLO": ["PAU"],
    "PAU": ["PABLO"],
    "DIEGO": ["DIEGO"],
    "EMILIO": ["EMI"],
    "EMILIA": ["EMI"],
    "ELENA": ["ELNA"],
    "CARMEN": ["MARÍA", "MA", "CARM"],
    "MARÍA": ["MARIA", "MA", "CARM"],
    "MARIA": ["MARÍA", "MA", "CARM"],
    "MIGUEL": ["MIQUEL"],
    "MIQUEL": ["MIGUEL"],
    "LUIS": ["LLOÏS"],
    "ALBERT": ["ALBERTO"],
    "ALBERTO": ["ALBERT"],
    "RICARD": ["RICARDO"],
    "RICARDO": ["RICARD"],
    "SERGI": ["SERGIO"],
    "SERGIO": ["SERGI"],
    "RAFAEL": ["RAFA"],
    "RAFA": ["RAFAEL"],
    "DAVID": ["DAVI"],
    "DAVI": ["DAVID"],
    "ANDREU": ["ANDRÉU", "ANDREW"],
    "JORDI": ["JORDEI"],
}

# Build reverse lookup: variant → canonical
_NICKNAME_CANONICAL = {}
for canonical, variants in NICKNAMES.items():
    for v in variants:
        _NICKNAME_CANONICAL[v] = canonical


def _edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein edit distance."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev_row = range(len(b) + 1)
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (ca != cb)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _name_similarity(key1: str, key2: str) -> float:
    """Compute similarity between two name keys (sorted token sets).

    Returns 0.0-1.0 where 1.0 = identical.
    """
    if key1 == key2:
        return 1.0
    tokens1 = key1.split()
    tokens2 = key2.split()
    if not tokens1 or not tokens2:
        return 0.0

    # Check if token sets are the same (order-independent)
    if set(tokens1) == set(tokens2):
        return 1.0

    # Check for single-character typos
    max_len = max(len(key1), len(key2))
    if max_len > 0 and _edit_distance(key1, key2) <= 2:
        return 0.9

    # Check token-by-token similarity
    similarities = []
    for t1 in tokens1:
        best = 0
        for t2 in tokens2:
            if t1 == t2:
                best = 1.0
                break
            d = _edit_distance(t1, t2)
            ml = max(len(t1), len(t2))
            if ml > 0:
                best = max(best, 1.0 - d / ml)
        similarities.append(best)

    if similarities:
        return sum(similarities) / len(similarities)
    return 0.0


def _apply_nickname(key: str) -> str:
    """Replace nickname tokens with canonical names in a name key."""
    tokens = key.split()
    new_tokens = []
    for t in tokens:
        upper = t.upper()
        if upper in _NICKNAME_CANONICAL:
            new_tokens.append(_NICKNAME_CANONICAL[upper])
        else:
            new_tokens.append(t)
    return " ".join(sorted(new_tokens))


def _apply_typo_fixes(key: str) -> str:
    """Replace known OCR typo tokens with corrected versions."""
    tokens = key.split()
    new_tokens = []
    for t in tokens:
        upper = t.upper()
        replaced = False
        for typo_set, preferred in TYPO_PREFERRED.items():
            if upper in typo_set:
                new_tokens.append(preferred)
                replaced = True
                break
        if not replaced:
            new_tokens.append(upper)
    return " ".join(sorted(new_tokens))


def _cluster_name_key(info: dict) -> str:
    """Best cleaned name key for a cluster (from variants + canonical name)."""
    keys: set[str] = set()
    for variant in info.get("name_variants", []):
        nk = clean_name_for_match(variant)
        if nk:
            keys.add(_apply_typo_fixes(nk))
    nk = clean_name_for_match(info.get("canonical_name", ""))
    if nk:
        keys.add(_apply_typo_fixes(nk))
    if not keys:
        return info.get("canonical_name", "").upper()
    return max(keys, key=lambda k: (len(k.split()), k))


def _canonical_token(token: str) -> str:
    """Normalize a single name token (nicknames + known typos)."""
    if _is_truncated_token(token):
        return ""
    t = _strip_accents(token).upper()
    if t in _NICKNAME_CANONICAL:
        t = _NICKNAME_CANONICAL[t]
    for typo_set, preferred in TYPO_PREFERRED.items():
        if t in typo_set:
            return preferred
    return t


def _canonical_token_set(key: str) -> set[str]:
    return {ct for t in key.split() if t for ct in [_canonical_token(t)] if ct}


def _tokens_fuzzy_match(a: str, b: str) -> bool:
    ca, cb = _canonical_token(a), _canonical_token(b)
    if ca == cb:
        return True
    for typo_set in TYPO_PREFERRED:
        if ca in typo_set and cb in typo_set:
            return True
    ml = max(len(ca), len(cb))
    if ml < 6:
        return False
    return _edit_distance(ca, cb) <= 1


def _name_keys_compatible(ka: str, kb: str) -> bool:
    """Return True if two cleaned name keys likely refer to the same person."""
    ca = _canonical_token_set(ka)
    cb = _canonical_token_set(kb)
    if len(ca) < 2 or len(cb) < 2:
        return False
    if ca == cb:
        return True
    if ca <= cb or cb <= ca:
        return min(len(ca), len(cb)) >= 2

    common = ca & cb
    if len(common) < 2:
        return False

    only_a = sorted(ca - cb)
    only_b = sorted(cb - ca)
    if not only_a or not only_b:
        return True

    # Same athlete, wrong surname in one PDF line (e.g. Laurine Marimon)
    if len(common) >= 2 and len(only_a) == 1 and len(only_b) == 1:
        pair = frozenset({only_a[0], only_b[0]})
        if pair == frozenset({"ESTEBAN", "FERNANDEZ"}) and {"LAURINE", "MARIMON"} <= common:
            return True

    if len(only_a) > 2 or len(only_b) > 2:
        return False

    used: set[int] = set()
    for a in only_a:
        matched = False
        for j, b in enumerate(only_b):
            if j in used:
                continue
            if _tokens_fuzzy_match(a, b):
                used.add(j)
                matched = True
                break
        if not matched:
            return False
    return len(used) == len(only_b)


def _clusters_compatible(info_a: dict, info_b: dict) -> bool:
    """Check if two clusters represent the same athlete."""
    ka = _cluster_name_key(info_a)
    kb = _cluster_name_key(info_b)
    if not _name_keys_compatible(ka, kb):
        return False

    dob_a = info_a.get("canonical_dob", "")
    dob_b = info_b.get("canonical_dob", "")
    if dob_a and dob_b and not dob_compatible(dob_a, dob_b):
        return False
    return True


def _meaningful_common_tokens(key_a: str, key_b: str) -> set[str]:
    """Tokens shared between two name keys (already cleaned)."""
    return set(key_a.split()) & set(key_b.split())


def merge_typo_clusters(clusters: dict) -> dict:
    """Post-process clusters to merge those with similar names (typos/nicknames).

    Uses cleaned name keys only — never merges on noise tokens like MMP or Q.
    """
    if not clusters:
        return clusters

    cluster_list = list(clusters.items())
    uf = UnionFind()

    name_keys = [_cluster_name_key(info) for _, info in cluster_list]

    # Index by first token of cleaned name key
    first_token_idx: dict[str, list[int]] = defaultdict(list)
    for i, nk in enumerate(name_keys):
        tokens = nk.split()
        if tokens:
            first_token_idx[tokens[0]].append(i)

    # Index by license number
    lic_num_idx: dict[str, list[int]] = defaultdict(list)
    for i, (_, info) in enumerate(cluster_list):
        for lic in info.get("norm_licenses", {}):
            num = re.sub(r"^[A-Z]+[-]?", "", lic)
            if num:
                lic_num_idx[num].append(i)

    for i in range(len(cluster_list)):
        uf.find(i)
        key_i = name_keys[i]
        tokens_i = set(key_i.split())
        if len(tokens_i) < 2:
            continue

        candidates: set[int] = set()
        ft = key_i.split()[0]
        candidates.update(first_token_idx.get(ft, []))
        _, info_i = cluster_list[i]
        for lic in info_i.get("norm_licenses", {}):
            num = re.sub(r"^[A-Z]+[-]?", "", lic)
            if num:
                candidates.update(lic_num_idx.get(num, []))

        for j in candidates:
            if j <= i or uf.find(j) == uf.find(i):
                continue

            key_j = name_keys[j]
            tokens_j = set(key_j.split())
            if len(tokens_j) < 2:
                continue

            common = tokens_i & tokens_j
            if len(common) < 2:
                continue

            _, info_j = cluster_list[j]
            share_license = bool(
                set(info_i.get("norm_licenses", {})) & set(info_j.get("norm_licenses", {}))
            )

            nick_i = _apply_nickname(key_i)
            nick_j = _apply_nickname(key_j)
            typo_i = _apply_typo_fixes(key_i)
            typo_j = _apply_typo_fixes(key_j)

            if key_i == key_j:
                uf.union(i, j)
            elif typo_i == typo_j:
                uf.union(i, j)
            elif nick_i == nick_j:
                uf.union(i, j)
            elif share_license and len(common) >= 2:
                uf.union(i, j)
            elif (
                len(common) >= 2
                and (
                    tokens_i.issubset(tokens_j)
                    or tokens_j.issubset(tokens_i)
                )
                and min(len(tokens_i), len(tokens_j)) >= 2
            ):
                uf.union(i, j)

    # Build merged clusters
    merged: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cluster_list)):
        root = uf.find(i)
        merged[root].append(i)

    result = {}
    new_id = 100000  # Use high IDs to avoid collisions
    for root, indices in merged.items():
        if len(indices) == 1:
            # Single cluster, keep as-is
            idx = indices[0]
            cid, info = cluster_list[idx]
            result[cid] = info
        else:
            # Merge multiple clusters
            merged_indices = []
            all_variants = set()
            all_licenses = Counter()
            all_norm_licenses = Counter()
            all_dobs = Counter()
            all_norm_dobs = Counter()
            all_source_files = set()
            total_results = 0
            best_name = ""
            best_name_score = -1
            best_license = ""
            best_dob = ""

            for idx in indices:
                cid, info = cluster_list[idx]
                merged_indices.extend(info["indices"])
                all_variants.update(info["name_variants"])
                all_licenses.update(info["raw_licenses"])
                all_norm_licenses.update(info["norm_licenses"])
                all_dobs.update(info["raw_dobs"])
                all_norm_dobs.update(info["norm_dobs"])
                all_source_files.update(info["source_files"])
                total_results += info["total_results"]

                # Pick best name using derive_canonical_name to clean noise
                cleaned = derive_canonical_name(info["canonical_name"])
                # Prefer the cleaned name with most tokens
                score = len(cleaned.split())
                if best_name_score < score:
                    best_name = cleaned
                    best_name_score = score
                elif best_name_score == score and len(info["canonical_name"].split()) > len(best_name.split()):
                    # Tie-break: prefer the raw name with more tokens (more complete)
                    best_name = info["canonical_name"]
                    best_name_score = score

                # Pick best license
                if info["canonical_license"]:
                    if not best_license:
                        best_license = info["canonical_license"]
                    else:
                        # Prefer CAT- > CT > CL
                        if license_priority(info["canonical_license"]) > license_priority(best_license):
                            best_license = info["canonical_license"]

                # Pick most common DOB
                if info["canonical_dob"] and not best_dob:
                    best_dob = info["canonical_dob"]

            # Apply nickname resolution to best name
            best_name_key = clean_name_for_match(best_name) or best_name
            nick_resolved = _apply_nickname(best_name_key)
            if nick_resolved != best_name_key:
                best_name = " ".join(nick_resolved.split())
                # Re-sort: keep NOM COGNOM1 COGNOM2 format
                tokens = best_name.split()
                if len(tokens) >= 3:
                    # Keep first token as name, rest as surnames
                    best_name = f"{tokens[0]} {' '.join(sorted(tokens[1:]))}"

            result[new_id] = {
                "indices": merged_indices,
                "canonical_name": best_name,
                "canonical_license": best_license,
                "canonical_dob": best_dob,
                "name_variants": sorted(all_variants),
                "raw_licenses": dict(all_licenses),
                "norm_licenses": dict(all_norm_licenses),
                "raw_dobs": dict(all_dobs),
                "norm_dobs": dict(all_norm_dobs),
                "source_files": sorted(all_source_files),
                "source_files_count": len(all_source_files),
                "conflict_licenses": [],
                "dob_conflicts": [],
                "total_results": total_results,
                "_merged": True,
            }
            new_id += 1

    return result


def _combine_clusters(cluster_list: list[dict]) -> dict:
    """Combine multiple cluster dicts into one."""
    if len(cluster_list) == 1:
        return cluster_list[0]

    all_indices: list[int] = []
    all_variants: set[str] = set()
    all_raw_licenses: Counter = Counter()
    all_norm_licenses: Counter = Counter()
    all_raw_dobs: Counter = Counter()
    all_norm_dobs: Counter = Counter()
    all_source_files: set[str] = set()
    conflict_licenses: list = []
    best_name = ""
    best_license = ""
    best_dob = ""

    for info in cluster_list:
        all_indices.extend(info["indices"])
        all_variants.update(info["name_variants"])
        all_raw_licenses.update(info.get("raw_licenses", {}))
        all_norm_licenses.update(info.get("norm_licenses", {}))
        all_raw_dobs.update(info.get("raw_dobs", {}))
        all_norm_dobs.update(info.get("norm_dobs", {}))
        all_source_files.update(info.get("source_files", []))
        conflict_licenses.extend(info.get("conflict_licenses", []))

        lic = info.get("canonical_license", "")
        if lic and (not best_license or license_priority(lic) > license_priority(best_license)):
            best_license = lic

        dob = info.get("canonical_dob", "")
        if dob and not best_dob:
            best_dob = dob

    best_name = _pick_canonical_name(sorted(all_variants))

    if all_norm_dobs:
        best_dob = all_norm_dobs.most_common(1)[0][0]

    return {
        "indices": all_indices,
        "canonical_name": best_name or cluster_list[0]["canonical_name"],
        "canonical_license": best_license,
        "canonical_dob": best_dob,
        "name_variants": sorted(all_variants),
        "raw_licenses": dict(all_raw_licenses),
        "norm_licenses": dict(all_norm_licenses),
        "raw_dobs": dict(all_raw_dobs),
        "norm_dobs": dict(all_norm_dobs),
        "source_files": sorted(all_source_files),
        "source_files_count": len(all_source_files),
        "conflict_licenses": conflict_licenses,
        "dob_conflicts": list(all_norm_dobs.keys()) if len(all_norm_dobs) > 1 else [],
        "total_results": len(all_indices),
    }


def merge_clusters_by_license(clusters: dict) -> dict:
    """Merge clusters that share any normalized license number."""
    if not clusters:
        return clusters

    cid_list = list(clusters.keys())
    uf = UnionFind()

    lic_to_idxs: dict[str, list[int]] = defaultdict(list)
    for i, cid in enumerate(cid_list):
        uf.find(i)
        for lic in clusters[cid].get("norm_licenses", {}):
            if lic:
                lic_to_idxs[lic].append(i)

    for idxs in lic_to_idxs.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cid_list)):
        groups[uf.find(i)].append(i)

    merged: dict = {}
    next_id = 200000
    for indices in groups.values():
        cluster_group = [clusters[cid_list[i]] for i in indices]
        combined = _combine_clusters(cluster_group)
        if len(indices) == 1:
            merged[cid_list[indices[0]]] = combined
        else:
            merged[next_id] = combined
            next_id += 1

    return merged


def merge_subset_name_clusters(clusters: dict) -> dict:
    """Merge clusters where one name_key is a token subset of another and DOBs match."""
    if not clusters:
        return clusters

    cid_list = list(clusters.keys())
    keys = [_canonical_token_set(_cluster_name_key(clusters[cid])) for cid in cid_list]

    uf = UnionFind()
    for i in range(len(cid_list)):
        uf.find(i)

    for i in range(len(cid_list)):
        for j in range(i + 1, len(cid_list)):
            if not keys[i] or not keys[j]:
                continue
            if not (keys[i] <= keys[j] or keys[j] <= keys[i]):
                continue
            if len(keys[i] & keys[j]) < 2:
                continue

            dob_i = clusters[cid_list[i]].get("canonical_dob", "")
            dob_j = clusters[cid_list[j]].get("canonical_dob", "")
            if dob_i and dob_j and not dob_compatible(dob_i, dob_j):
                continue

            # Share at least one license, or one side has no license
            lics_i = set(clusters[cid_list[i]].get("norm_licenses", {}))
            lics_j = set(clusters[cid_list[j]].get("norm_licenses", {}))
            if lics_i and lics_j and not (lics_i & lics_j):
                continue

            uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cid_list)):
        groups[uf.find(i)].append(i)

    merged: dict = {}
    next_id = 300000
    for indices in groups.values():
        cluster_group = [clusters[cid_list[i]] for i in indices]
        combined = _combine_clusters(cluster_group)
        if len(indices) == 1:
            merged[cid_list[indices[0]]] = combined
        else:
            merged[next_id] = combined
            next_id += 1

    return merged


def merge_fuzzy_clusters(clusters: dict) -> dict:
    """Merge clusters with compatible fuzzy name keys (typos, nicknames, subsets)."""
    if not clusters:
        return clusters

    cluster_list = list(clusters.items())
    uf = UnionFind()
    name_keys = [_cluster_name_key(info) for _, info in cluster_list]

    token_idx: dict[str, list[int]] = defaultdict(list)
    for i, nk in enumerate(name_keys):
        uf.find(i)
        for token in nk.split():
            if len(token) >= 3:
                token_idx[_canonical_token(token)].append(i)

    lic_idx: dict[str, list[int]] = defaultdict(list)
    for i, (_, info) in enumerate(cluster_list):
        for lic in info.get("norm_licenses", {}):
            if lic:
                lic_idx[lic].append(i)

    for i in range(len(cluster_list)):
        _, info_i = cluster_list[i]
        candidates: set[int] = set()
        for token in name_keys[i].split():
            if len(token) >= 3:
                candidates.update(token_idx.get(_canonical_token(token), []))
        for lic in info_i.get("norm_licenses", {}):
            if lic:
                candidates.update(lic_idx.get(lic, []))

        for j in candidates:
            if j <= i or uf.find(j) == uf.find(i):
                continue
            _, info_j = cluster_list[j]
            if _clusters_compatible(info_i, info_j):
                uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cluster_list)):
        groups[uf.find(i)].append(i)

    merged: dict = {}
    next_id = 500000
    for indices in groups.values():
        cluster_group = [clusters[cluster_list[i][0]] for i in indices]
        combined = _combine_clusters(cluster_group)
        if len(indices) == 1:
            merged[cluster_list[indices[0]][0]] = combined
        else:
            merged[next_id] = combined
            next_id += 1

    return merged


def merge_clusters_by_name_key(clusters: dict) -> dict:
    """Merge clusters that resolve to the same cleaned name key."""
    if not clusters:
        return clusters

    key_to_cids: dict[str, list] = defaultdict(list)
    for cid, info in clusters.items():
        nk = _cluster_name_key(info)
        if nk and len(nk.split()) >= 2:
            key_to_cids[nk].append(cid)

    merged: dict = {}
    next_id = 400000
    used: set = set()

    for nk, cids in key_to_cids.items():
        if len(cids) == 1:
            cid = cids[0]
            merged[cid] = clusters[cid]
            used.add(cid)
            continue
        combined = _combine_clusters([clusters[cid] for cid in cids])
        merged[next_id] = combined
        next_id += 1
        used.update(cids)

    for cid, info in clusters.items():
        if cid not in used:
            merged[cid] = info

    return merged


# ---------------------------------------------------------------------------
# Identity grouping
# ---------------------------------------------------------------------------

def group_athletes(results: list[dict], verbose: bool = False):
    """Group results into athlete clusters using union-find.

    Returns:
        clusters: dict mapping cluster_id -> list of result indices
        cluster_info: dict mapping cluster_id -> metadata
    """
    uf = UnionFind()

    # Phase A: link by license
    license_to_idx: dict[str, int] = {}  # normalized_license -> first result idx
    # Phase B: link by name_key
    name_key_to_idx: dict[str, int] = {}  # name_key -> first result idx

    # We'll assign each result an index
    for idx, res in enumerate(results):
        norm_lic = normalize_license(res["athlete_id"])
        name_key = clean_name_for_match(res["athlete_name"])

    # Phase A: license linking
    license_to_idx: dict[str, int] = {}  # normalized_license -> first result idx
    # Phase B: link by name_key
    name_key_to_idx: dict[str, int] = {}  # name_key -> first result idx

    # We'll assign each result an index
    for idx, res in enumerate(results):
        # Ensure all indices are in the union-find
        uf.find(idx)

        norm_lic = normalize_license(res["athlete_id"])
        name_key = clean_name_for_match(res["athlete_name"])

        # Phase A: license linking
        if norm_lic and norm_lic in license_to_idx:
            uf.union(idx, license_to_idx[norm_lic])
        elif norm_lic:
            license_to_idx[norm_lic] = idx

        # Phase B: name_key linking
        if name_key and name_key in name_key_to_idx:
            uf.union(idx, name_key_to_idx[name_key])
        elif name_key:
            name_key_to_idx[name_key] = idx

    # Build clusters
    cluster_map: dict[int, list[int]] = defaultdict(list)
    for idx in range(len(results)):
        root = uf.find(idx)
        cluster_map[root].append(idx)

    # Build cluster info
    clusters = {}
    for root, indices in cluster_map.items():
        cluster_results = [results[i] for i in indices]

        # Collect licenses
        raw_licenses = Counter()
        norm_licenses = Counter()
        for r in cluster_results:
            raw = r["athlete_id"].strip()
            if raw:
                raw_licenses[raw] += 1
                norm = normalize_license(raw)
                if norm:
                    norm_licenses[norm] += 1

        # Collect DOBs
        raw_dobs = Counter()
        norm_dobs = Counter()
        for r in cluster_results:
            dob = r["athlete_dob"].strip()
            if dob:
                raw_dobs[dob] += 1
                ndob = normalize_dob(dob)
                if ndob:
                    norm_dobs[ndob] += 1

        # Collect name variants (raw, before filtering)
        raw_name_variants = list(set(r["athlete_name"].strip() for r in cluster_results))

        # Determine canonical display name
        # Prefer the variant that looks most like "NOM COGNOM1 COGNOM2"
        # (no leading numbers, no category codes, no trailing digits)
        canonical_name = _pick_canonical_name(raw_name_variants)

        # Now filter out results from different athletes that were incorrectly
        # linked by union-find (same PDF, different athletes).
        #
        # Strategy: keep results that share >= 2 tokens with the canonical name.
        # Results with < 2 shared tokens are clearly different athletes
        # (e.g., "MARINA TIBAU SENDRA" vs "ALICIA VAZQUEZ DOMINGO" = 0 overlap).
        #
        # After filtering, if the remaining results have multiple DOB groups,
        # they will be split into separate clusters in the split-by-DOB logic below.
        # This handles cases like "ADA NIN NAVAS" (DOB X) + "NOA NIN NAVAS" (DOB Y)
        # that share surnames but are different people.
        canonical_name_key = clean_name_for_match(canonical_name) if canonical_name else ""
        canonical_tokens = set(canonical_name_key.split()) if canonical_name_key else set()

        valid_indices = []
        invalid_count = 0
        for i, r in zip(indices, cluster_results):
            r_name = r["athlete_name"].strip()
            r_name_key = clean_name_for_match(r_name)
            r_name_tokens = set(r_name_key.split()) if r_name_key else set()

            # Keep if name shares >= 2 tokens with canonical name
            # This rejects completely different names (0-1 overlap)
            # but keeps same-person variants and same-surname different-people
            # (which will be split by DOB below)
            name_overlap = len(r_name_tokens & canonical_tokens) >= 2 if canonical_tokens else False

            if name_overlap:
                valid_indices.append(i)
            else:
                invalid_count += 1

        # If we filtered out a significant portion, log it
        if invalid_count > 0 and len(cluster_results) > 0:
            print(
                f"  WARN: Cluster {root} ({canonical_name}): "
                f"filtered {invalid_count}/{len(cluster_results)} results from different athletes",
                file=sys.stderr,
            )

        # Rebuild name_variants from valid results only
        name_variants = list(set(r["athlete_name"].strip() for i, r in zip(indices, cluster_results) if i in set(valid_indices)))

        # Determine canonical license
        canonic_lic = ""
        if norm_licenses:
            # Prefer CAT- > CT > CL
            candidates = []
            for lic, count in norm_licenses.most_common():
                candidates.append((license_priority(lic), count, lic))
            candidates.sort(reverse=True)
            canonic_lic = candidates[0][2] if candidates else ""

        # Determine canonical DOB
        canonic_dob = ""
        if norm_dobs:
            canonic_dob = norm_dobs.most_common(1)[0][0]

        # Check for license conflicts (multiple different licenses)
        conflict_licenses = []
        unique_norm = set(norm_licenses.keys())
        if len(unique_norm) > 1:
            # Check if any pair is CL/CT with same number
            cl_lics = [l for l in unique_norm if l.startswith("CL")]
            ct_lics = [l for l in unique_norm if l.startswith("CT")]
            # Check for CL/CT same number
            for cl in cl_lics:
                cl_num = cl[2:]  # remove "CL"
                for ct in ct_lics:
                    ct_num = ct[2:]  # remove "CT"
                    if cl_num == ct_num:
                        conflict_licenses.append({
                            "licenses": list(unique_norm),
                            "reason": f"CL/CT conflict: {cl} vs {ct} (same number {cl_num})",
                        })
                        break
            if not cl_lics:
                conflict_licenses.append({
                    "licenses": list(unique_norm),
                    "reason": f"Multiple different licenses: {list(unique_norm)}",
                })

        # Check DOB conflicts
        dob_conflicts = []
        if len(norm_dobs) > 1:
            dob_conflicts = list(norm_dobs.keys())

        # Source files
        source_files = set()
        for r in cluster_results:
            sf = r.get("_source_file", "")
            if sf:
                source_files.add(sf)

        # Use valid indices only (filter out results from different athletes)
        valid_set = set(valid_indices)
        filtered_indices = [i for i in indices if i in valid_set]

        # Recollect licenses/DOBs/source_files from valid results only
        valid_cluster_results = [results[i] for i in filtered_indices]
        valid_raw_licenses = Counter()
        valid_norm_licenses = Counter()
        valid_raw_dobs = Counter()
        valid_norm_dobs = Counter()
        valid_source_files = set()
        for r in valid_cluster_results:
            raw = r["athlete_id"].strip()
            if raw:
                valid_raw_licenses[raw] += 1
                norm = normalize_license(raw)
                if norm:
                    valid_norm_licenses[norm] += 1
            dob = r["athlete_dob"].strip()
            if dob:
                valid_raw_dobs[dob] += 1
                ndob = normalize_dob(dob)
                if ndob:
                    valid_norm_dobs[ndob] += 1
            sf = r.get("_source_file", "")
            if sf:
                valid_source_files.add(sf)

        # Base cluster data (used if no split is needed)
        cluster_data = {
            "indices": filtered_indices,
            "canonical_name": canonical_name,
            "canonical_license": canonic_lic,
            "canonical_dob": canonic_dob,
            "name_variants": sorted(name_variants),
            "raw_licenses": dict(valid_raw_licenses),
            "norm_licenses": dict(valid_norm_licenses),
            "raw_dobs": dict(valid_raw_dobs),
            "norm_dobs": dict(valid_norm_dobs),
            "source_files": sorted(valid_source_files),
            "source_files_count": len(valid_source_files),
            "conflict_licenses": conflict_licenses,
            "dob_conflicts": dob_conflicts,
            "total_results": len(valid_cluster_results),
        }

        # Split cluster by DOB if there are multiple DOB groups with significant results.
        # This handles cases like "ADA NIN NAVAS" (DOB X) and "NOA NIN NAVAS" (DOB Y)
        # that were incorrectly merged by union-find due to shared surnames.
        if len(valid_norm_dobs) > 1:
            # Find DOB groups with significant results (>= 5 results or >= 10% of cluster)
            min_threshold = max(5, len(filtered_indices) * 0.05)
            significant_dobs = {dob: count for dob, count in valid_norm_dobs.items() if count >= min_threshold}

            if len(significant_dobs) > 1:
                # Split into separate clusters by DOB
                split_count = 0
                for dob, count in significant_dobs.items():
                    # Get results for this DOB
                    dob_indices = []
                    dob_variants = set()
                    dob_licenses = Counter()
                    dob_norm_licenses = Counter()
                    dob_raw_dobs = Counter()
                    dob_valid_norm_dobs = Counter()
                    dob_source_files = set()
                    for i in filtered_indices:
                        r = results[i]
                        r_dob = normalize_dob(r["athlete_dob"].strip()) if r["athlete_dob"].strip() else ""
                        if r_dob == dob:
                            dob_indices.append(i)
                            dob_variants.add(r["athlete_name"].strip())
                            raw = r["athlete_id"].strip()
                            if raw:
                                dob_licenses[raw] += 1
                                norm = normalize_license(raw)
                                if norm:
                                    dob_norm_licenses[norm] += 1
                            dob_raw_dobs[r["athlete_dob"].strip()] += 1
                            dob_valid_norm_dobs[r_dob] += 1
                            sf = r.get("_source_file", "")
                            if sf:
                                dob_source_files.add(sf)

                    if dob_indices:
                        # Pick canonical name from this DOB's results
                        dob_name_variants = list(dob_variants)
                        dob_canonical = _pick_canonical_name(dob_name_variants)

                        # Pick best license
                        dob_best_lic = ""
                        if dob_norm_licenses:
                            candidates = [(lic, c) for lic, c in dob_norm_licenses.items()]
                            candidates.sort(key=lambda x: (license_priority(x[0]), x[1]), reverse=True)
                            dob_best_lic = candidates[0][0] if candidates else ""

                        new_id = root + split_count + 1
                        clusters[new_id] = {
                            "indices": dob_indices,
                            "canonical_name": dob_canonical,
                            "canonical_license": dob_best_lic,
                            "canonical_dob": dob,
                            "name_variants": sorted(dob_variants),
                            "raw_licenses": dict(dob_licenses),
                            "norm_licenses": dict(dob_norm_licenses),
                            "raw_dobs": dict(dob_raw_dobs),
                            "norm_dobs": dict(dob_valid_norm_dobs),
                            "source_files": sorted(dob_source_files),
                            "source_files_count": len(dob_source_files),
                            "conflict_licenses": [],
                            "dob_conflicts": [],
                            "total_results": len(dob_indices),
                        }
                        split_count += 1

                # Only remove original if we actually created split clusters
                if split_count > 0:
                    clusters[root] = cluster_data  # Keep original as fallback
            else:
                clusters[root] = cluster_data
        else:
            clusters[root] = cluster_data

    if verbose:
        print(f"Clusters: {len(clusters)}", file=sys.stderr)
        no_license = sum(1 for c in clusters.values() if not c["canonical_license"])
        print(f"Clusters without license: {no_license}", file=sys.stderr)
        conflicts = sum(1 for c in clusters.values() if c["conflict_licenses"])
        print(f"Clusters with license conflicts: {conflicts}", file=sys.stderr)

    return clusters


def _normalize_display_name(name: str) -> str:
    """Normalize display name tokens (typos + nicknames) for grouping and output."""
    tokens = name.split()
    fixed = [_canonical_token(_strip_accents(t).upper()) for t in tokens]
    fixed = [t for t in fixed if t]
    return " ".join(fixed) if fixed else name.upper()


def _pick_canonical_name(variants: list[str]) -> str:
    """Pick the best display name from a list of raw name variants.

    Prefer the most frequent cleaned display name across all variants.
    """
    cleaned_counts: Counter = Counter()
    for v in variants:
        cleaned = derive_canonical_name(v)
        if cleaned and len(cleaned.split()) >= 2:
            cleaned_counts[_normalize_display_name(cleaned)] += 1

    if cleaned_counts:
        # Prefer names with more tokens, then higher frequency
        best = max(
            cleaned_counts.items(),
            key=lambda item: (len(item[0].split()), item[1], -len(item[0])),
        )[0]
        return best

    best = None
    best_score = -1

    for v in variants:
        score = 0

        if not v[0].isdigit():
            score += 10

        tokens = v.split()
        has_cat = any(_is_noise_token(t) for t in tokens)
        if not has_cat:
            score += 5

        if tokens and not tokens[-1].isdigit():
            score += 3

        score += len(tokens)

        has_accents = any(c in v for c in "ÁÉÍÓÚÜàáèéìíòóùúñ")
        if has_accents:
            score += 2

        if score > best_score:
            best_score = score
            best = v

    if best:
        return derive_canonical_name(best)
    return variants[0] if variants else "UNKNOWN"


# ---------------------------------------------------------------------------
# Deduplication and sorting
# ---------------------------------------------------------------------------

def deduplicate_results(indices: list[int], results: list[dict]) -> list[int]:
    """Deduplicate results within a cluster.

    Dedup key: (event_date, event_src, discipline, performance, wind, athlete_dob, athlete_id)
    """
    seen = set()
    unique = []
    for idx in indices:
        res = results[idx]
        key = (
            res["event_date"],
            res["event_src"],
            res["discipline"],
            res["performance"],
            res.get("wind"),
            res["athlete_dob"],
            res["athlete_id"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(idx)
    return unique


def parse_event_date(date_str: str) -> datetime | None:
    """Parse DD/MM/YYYY date string."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def sort_results(indices: list[int], results: list[dict]) -> list[int]:
    """Sort results by event_date ascending."""
    def sort_key(idx):
        dt = parse_event_date(results[idx]["event_date"])
        if dt:
            return (0, dt)
        return (1, datetime.max)

    return sorted(indices, key=sort_key)


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    name = name.upper()
    name = re.sub(r"[^A-Z0-9\-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name[:100] or "athlete"


def slug_from_name(name: str) -> str:
    """Create a slug from a canonical name for filename.

    Strips category codes, qualifier markers, and other noise from the name
    to ensure the same athlete always gets the same slug regardless of
    suffixes like MMP, 7 q, IM, etc.
    """
    # Clean the name first to remove category/qualifier noise
    cleaned = derive_canonical_name(name)
    # Remove accents
    cleaned = _strip_accents(cleaned)
    # Lowercase and replace spaces with hyphens
    slug = cleaned.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] or "athlete"


def generate_athlete_json(cluster_id: int, cluster: dict, results: list[dict]) -> dict:
    """Generate the full athlete JSON structure."""
    unique_indices = deduplicate_results(cluster["indices"], results)
    sorted_indices = sort_results(unique_indices, results)

    # Build results list (without internal _source_file field)
    athlete_results = []
    for idx in sorted_indices:
        res = results[idx]
        athlete_results.append({
            "event_name": res["event_name"],
            "event_date": res["event_date"],
            "event_location": res["event_location"],
            "event_src": res["event_src"],
            "athlete_name": res["athlete_name"],
            "athlete_dob": res["athlete_dob"],
            "athlete_id": res["athlete_id"],
            "discipline": res["discipline"],
            "performance": res["performance"],
            "wind": res.get("wind"),
        })

    # License variants (normalized, unique)
    license_variants = sorted(set(cluster["norm_licenses"].keys()))

    return {
        "athlete_name": cluster["canonical_name"],
        "athlete_id": cluster["canonical_license"],
        "athlete_dob": cluster["canonical_dob"],
        "total_results": len(athlete_results),
        "name_variants_found": cluster["name_variants"],
        "license_variants_found": license_variants,
        "source_files_count": cluster["source_files_count"],
        "results": athlete_results,
    }


def athlete_filename(athlete_data: dict) -> str:
    """Determine stable output filename — always based on athlete name slug."""
    return slug_from_name(athlete_data["athlete_name"]) + ".json"


def clean_output_dir(output_dir: Path) -> None:
    """Remove stale per-athlete JSON files before regeneration."""
    for path in output_dir.glob("*.json"):
        if path.name in ("index.json", "_report.json"):
            continue
        path.unlink()


def _merge_output_clusters(clusters: dict) -> dict:
    """Final safety merge before writing (re-run fuzzy pass after name cleaning fixes)."""
    return merge_fuzzy_clusters(clusters)


def write_athletes(clusters: dict, results: list[dict], output_dir: Path) -> list[dict]:
    """Write per-athlete JSON files and return index entries."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_output_dir(output_dir)

    clusters = _merge_output_clusters(clusters)

    # Build athlete data first; merge clusters that map to the same filename
    by_file: dict[str, tuple[dict, dict]] = {}
    for cluster_id, cluster in sorted(clusters.items()):
        athlete_data = generate_athlete_json(cluster_id, cluster, results)
        filename = athlete_filename(athlete_data)

        if filename in by_file:
            existing_cluster, existing_data = by_file[filename]
            combined_cluster = _combine_clusters([existing_cluster, cluster])
            athlete_data = generate_athlete_json(cluster_id, combined_cluster, results)
            by_file[filename] = (combined_cluster, athlete_data)
        else:
            by_file[filename] = (cluster, athlete_data)

    index_entries = []
    for filename, (_, athlete_data) in sorted(by_file.items()):
        if not athlete_data.get("total_results"):
            continue

        filepath = output_dir / filename
        filepath.write_text(
            json.dumps(athlete_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        dates = []
        for r in athlete_data["results"]:
            dt = parse_event_date(r["event_date"])
            if dt:
                dates.append(dt)

        first_date = min(dates).strftime("%d/%m/%Y") if dates else ""
        last_date = max(dates).strftime("%d/%m/%Y") if dates else ""

        index_entries.append({
            "athlete_id": athlete_data["athlete_id"],
            "athlete_name": athlete_data["athlete_name"],
            "file": filename,
            "total_results": athlete_data["total_results"],
            "first_event_date": first_date,
            "last_event_date": last_date,
        })

    return index_entries


def write_index(index_entries: list[dict], output_dir: Path) -> None:
    """Write athletes/index.json."""
    # Sort by total_results descending
    index_entries.sort(key=lambda e: (-e["total_results"], e["athlete_name"]))

    index_data = {
        "total_athletes": len(index_entries),
        "athletes": index_entries,
    }

    (output_dir / "index.json").write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report(
    clusters: dict,
    stats: dict,
    skipped: int,
    output_dir: Path,
) -> None:
    """Write athletes/_report.json with QA information."""
    conflict_clusters = []
    no_license_clusters = 0
    top_athletes = []

    for cid, cluster in sorted(clusters.items()):
        if cluster["conflict_licenses"]:
            conflict_clusters.append({
                "canonical_name": cluster["canonical_name"],
                "canonical_license": cluster["canonical_license"],
                "conflicts": cluster["conflict_licenses"],
                "total_results": cluster["total_results"],
                "name_variants": cluster["name_variants"][:10],
            })
        if not cluster["canonical_license"]:
            no_license_clusters += 1
        top_athletes.append({
            "name": cluster["canonical_name"],
            "license": cluster["canonical_license"],
            "total_results": cluster["total_results"],
        })

    top_athletes.sort(key=lambda x: -x["total_results"])

    report = {
        "summary": {
            "total_clusters": len(clusters),
            "total_results_processed": stats["total_results"],
            "files_scanned": stats["files_scanned"],
            "invalid_json_files": len(stats["invalid_json"]),
            "skipped_results_empty_fields": skipped,
            "athletes_without_license": no_license_clusters,
        },
        "license_conflicts": conflict_clusters,
        "top_athletes": top_athletes[:20],
    }

    (output_dir / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate all CA Tarragona athlete results into per-athlete JSON files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root directory",
    )
    parser.add_argument(
        "--scan-dir",
        action="append",
        dest="scan_dirs",
        default=["seasons", "json"],
        help="Directory under root to scan (repeatable)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for athlete files (default: <root>/athletes/)",
    )
    parser.add_argument(
        "--athlete",
        type=str,
        default=None,
        help="Filter: only process results for this athlete name (test mode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Statistics only, don't write files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress to stderr",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or (args.root / "athletes")

    if args.verbose:
        print(f"Root: {args.root}", file=sys.stderr)
        print(f"Scan dirs: {args.scan_dirs}", file=sys.stderr)
        print(f"Output dir: {output_dir}", file=sys.stderr)
        if args.athlete:
            print(f"Filter athlete: {args.athlete}", file=sys.stderr)
        print(f"Dry run: {args.dry_run}", file=sys.stderr)

    # Step 1: Extract results
    results, stats = extract_results(args.root, args.scan_dirs, verbose=args.verbose)

    if not results:
        print("No results found.", file=sys.stderr)
        return 0

    # Step 2: Filter by athlete name if specified
    if args.athlete:
        name_key = clean_name_for_match(args.athlete)
        filtered = []
        for r in results:
            if clean_name_for_match(r["athlete_name"]) == name_key:
                filtered.append(r)
        if args.verbose:
            print(f"Filtered to {len(filtered)} results for '{args.athlete}'", file=sys.stderr)
        results = filtered

    # Step 3: Group athletes
    clusters = group_athletes(results, verbose=args.verbose)

    # Step 3.5: Merge typo/nickname clusters
    clusters = merge_typo_clusters(clusters)

    # Step 3.6: Merge clusters sharing licenses or subset names
    clusters = merge_clusters_by_license(clusters)
    clusters = merge_subset_name_clusters(clusters)
    clusters = merge_clusters_by_name_key(clusters)
    clusters = merge_fuzzy_clusters(clusters)

    if args.dry_run:
        # Print summary
        total_results = sum(c["total_results"] for c in clusters.values())
        unique_results = 0
        for c in clusters.values():
            unique_results += len(deduplicate_results(c["indices"], results))

        print(f"\nDry run summary:", file=sys.stderr)
        print(f"  Athletes (clusters): {len(clusters)}", file=sys.stderr)
        print(f"  Total result entries: {total_results}", file=sys.stderr)
        print(f"  After deduplication: {unique_results}", file=sys.stderr)
        no_license = sum(1 for c in clusters.values() if not c["canonical_license"])
        print(f"  Without license: {no_license}", file=sys.stderr)
        conflicts = sum(1 for c in clusters.values() if c["conflict_licenses"])
        print(f"  With license conflicts: {conflicts}", file=sys.stderr)

        # Top 10
        top = sorted(clusters.values(), key=lambda c: -c["total_results"])[:10]
        print(f"\n  Top 10 athletes:", file=sys.stderr)
        for c in top:
            lic = c["canonical_license"] or "(no license)"
            print(f"    {c['canonical_name']} ({lic}): {c['total_results']} results", file=sys.stderr)
        return 0

    # Step 4: Write output
    index_entries = write_athletes(clusters, results, output_dir)
    write_index(index_entries, output_dir)

    skipped = stats["skipped_empty"]
    write_report(clusters, stats, skipped, output_dir)

    # Print summary
    total_results = sum(c["total_results"] for c in clusters.values())
    unique_results = sum(
        len(deduplicate_results(c["indices"], results))
        for c in clusters.values()
    )

    print(f"Athletes: {len(clusters)}")
    print(f"Total result entries: {total_results}")
    print(f"After deduplication: {unique_results}")

    no_license = sum(1 for c in clusters.values() if not c["canonical_license"])
    print(f"Without license: {no_license}")

    conflicts = sum(1 for c in clusters.values() if c["conflict_licenses"])
    print(f"With license conflicts: {conflicts}")

    print(f"Files written: {output_dir}")
    print(f"Index: {output_dir / 'index.json'}")
    print(f"Report: {output_dir / '_report.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
