#!/usr/bin/env python3
"""Add `internal_id` (socisCAT id from TMP_SOCIS_LIST.md) to every result in seasons/*/json/*.json.

Matching cascade (first hit wins), computed once per unique athlete name:
  1. exact normalized match (accents/punctuation stripped) vs "NOM COGNOMS" and "COGNOMS NOM"
  2. variant resolution: PDF name -> canonical name via athletes/*/name_variants_found,
     then re-run the cascade on the canonical name
  3. unique token-subset match (all name tokens inside socis tokens)
  4. fuzzy match (difflib ratio) with abbreviation/nickname expansion and shared-token guard;
     rejected on ties (ambiguous)

Unmatched results get "internal_id": null and are listed in reports/unknown_athletes.{md,json}.

Usage:
  python scripts/add_internal_id.py --dry-run
  python scripts/add_internal_id.py            # writes in place + reports
  python scripts/add_internal_id.py --season 2005
"""

import argparse
import glob
import json
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOCIS_MD = ROOT / "TMP_SOCIS_LIST.md"
ATHLETES_DIR = ROOT / "athletes"
SEASONS_DIR = ROOT / "seasons"
REPORTS_DIR = ROOT / "reports"

MIN_FUZZY_RATIO = 0.86
TIE_EPSILON = 0.015

# Manual decisions from the owner review of reports/unknown_athletes.md.
# Keys are normalized names (see normalize()). Mostly resolutions of duplicate
# socis entries (same person registered under two ids).
MANUAL_OVERRIDES = {
    "FERRAN MASCARO": 1362,
    "FERRAN MASCARO NAVARRO": 1362,
    "GABRIEL QUEZADA": 1383,
    "GABRIEL QUEZADA PINEDA": 1383,
    "MARC MARTI": 1108,          # Marc Martí Fernández, not Marc Martí Pérez (672)
    "MELINDA RODRIGUEZ TORTAJADA": 53,
    "EMMA SOLE VILELLA": 1470,
    "JAVIER MARTIN ALVAREZ": 3,  # Fco. Javier Martín Álvarez
    "ENZO MATE": 1343,
    "ENZO MATE GRAS": 1343,
    # Bare-surname rows from resulcontrolcambrils240115 (24/01/2015); both clusters
    # could match two socis siblings, DOB/age-category evidence decides:
    #   JOSE DIAZ      -> Edgar (653, DOB 08/04/2002) fits Infantil 2015; Marc (294,
    #                     DOB 1993) cannot be Infantil. See scripts/split_athlete_files.py
    #   MONTANES ARBO  -> Montserrat (497, DOB 22/02/2001) fits Cadet 2015;
    #                     Maria (354, DOB 1995) cannot be Cadet.
    "JOSE DIAZ": 653,
    "MONTANES ARBO": 497,
    # resulcatcadet19610.pdf (cadet 19/06/2010) prints "Montserrat Montañes" but
    # with Maria's DOB (11/05/1995) and license CL58883; Montserrat (b. 2001)
    # cannot be cadet in 2010 -> PDF name-column error, rows are Maria's (354).
    "MONTSERRAT MONTANES": 354,
    "FRANCESC IBORRA": 1,        # Quico Iborra Martínez
}

# Names confirmed NOT to be socis members despite fuzzy similarity to one
# (siblings / different people caught by the fuzzy matcher). They keep
# internal_id null and stay in the manual-review list.
MANUAL_EXCLUDES = {
    "GUIU DE LOS RIOS BLANCH",   # b. 2009, brother of Guifré (697); not a soci
    "PACO LORENZO VALLDOSERA",   # b. 2009, brother of Blanca (788); not a soci
    "DAVID BONIN BACH",          # different person from David Bonnin Obach (710)
    "DAVI BONIN BACH",
    "PEDRO ORTEGA VIDAL",        # different person from Pere Ortega Ridao (268)
    "PERE ORTEGA VIDAL",
}

# Quico Iborra Martínez (id 1) appears under many spellings; every other club
# Iborra (Emma/Ingrid Almeida, Martín Pardines) lacks the MARTINEZ token.
IBORRA_TOKENS = {"IBORRA", "MARTINEZ"}

# Explicit abbreviation / nickname map (applied symmetrically, token-level).
# Values may be lists: every expansion is tried as an alternative token set.
ABBREV_EXPANSIONS = {
    "FCO": ["FRANCISCO", "JOSE"],
    "FRAN": ["FRANCISCO"],
    "XISCO": ["FRANCISCO"],
    "PACO": ["FRANCISCO"],
    "FRANK": ["FRANCISCO"],
    "PEPE": ["JOSE"],
    "CHEMA": ["JOSE MARIA"],
    "MANOLO": ["MANUEL"],
    "QUICO": ["FRANCISCO", "FRANCESC", "JOAQUIM"],
    "KIKE": ["ENRIQUE"],
    "TONO": ["ANTONIO"],
    "TINO": ["AGUSTIN"],
    "NACHO": ["IGNACIO"],
    "CHESKO": ["IGNACIO"],
    "MERI": ["MERCEDES"],
    "MERCE": ["MERCEDES"],
    "ISIS": ["ISABEL"],
    "BEA": ["BEATRIZ"],
    "CRIS": ["CRISTINA", "CRISTOBAL"],
    "MERCHE": ["MERCEDES"],
    "MARISA": ["MARIA ISABEL"],
    "XAVI": ["XAVIER"],
    "JAVI": ["JAVIER"],
    "DAVI": ["DAVID"],
    "GABI": ["GABRIEL"],
    "ALEX": ["ALEJANDRO"],
    "SANDRO": ["ALEJANDRO"],
    "GUILLE": ["GUILLERMO"],
    "SERGI": ["SERGIO"],
    "VICKY": ["VICTORIA"],
    "PILUCA": ["PILAR"],
    "MARI": ["MARIA"],
    "TANI": ["ANTONIO"],
    "SISO": ["LUIS"],
    "LALO": ["EDUARDO"],
}

# Catalan / Spanish variants of the same given name (same person, different language
# spelling across PDFs). Applied symmetrically at token level as a last-resort step.
NAME_VARIANTS = [
    ("JUAN", "JOAN"), ("JAVIER", "XAVIER"), ("ANTONIO", "ANTONI"),
    ("MANUEL", "MANEL"), ("FRANCISCO", "FRANCESC"), ("JOSE", "JOSEP"),
    ("JOAQUIN", "JOAQUIM"), ("LUIS", "LLUIS"), ("JORGE", "JORDI"),
    ("ANA", "ANNA"), ("ENRIQUE", "ENRIC"), ("PEDRO", "PERE"),
    ("PABLO", "PAU"), ("MIGUEL", "MIQUEL"), ("AGUSTIN", "AGUSTI"),
    ("VICENTE", "VICENC"), ("CARMEN", "CARME"), ("MARIA", "MARIA"),
    ("ALBERTO", "ALBERT"), ("FELIPE", "FELIP"), ("GABRIEL", "GABRIEL"),
    ("JAIME", "JAUME"), ("SERGIO", "SERGI"), ("CRISTINA", "CRISTINA"),
    ("MONTSERRAT", "MONTSERRAT"), ("ROSER", "ROSER"), ("THERESA", "TERESA"),
    ("ISABEL", "ISABEL"), ("GERARD", "GERARD"), ("RAIMON", "RAMON"),
    ("RAMON", "RAIMON"), ("ARNAU", "ARNAU"), ("IGNACIO", "IGNASI"),
    ("SALVADOR", "SALVADOR"), ("NURIA", "NURIA"), ("MERCEDES", "MERCHE"),
    ("EUGENIO", "EUGENI"), ("ANDRES", "ANDREU"), ("ANDREW", "ANDREU"),
    ("ESTEBAN", "ESTEVE"), ("STEVE", "ESTEVE"), ("BERNAT", "BERNAT"),
]

def _canonical_name_tokens():
    m = {}
    for a, b in NAME_VARIANTS:
        if a == b:
            continue
        lo, hi = sorted([a, b])
        m[hi] = lo
    return m

_CANON_TOKEN = _canonical_name_tokens()

def canonicalize_tokens(tk):
    return frozenset(_CANON_TOKEN.get(t, t) for t in tk)

# Noise tokens stripped from athlete names before matching.
_NOISE_TOKENS = {
    "IM", "IF", "SM", "SF", "LM", "LF", "PM", "PF", "AM", "AF", "BM", "BF",
    "CM", "CF", "JM", "JF", "JNM", "JNF", "JVF", "PBM", "PBF",
    "DNS", "DNF", "DQ", "RET", "NP", "MMT", "MMF", "MMP", "DOR", "ARGENT",
    "BRONZE", "PLATA", "OR", "GOLD", "SILVER", "Q", "QB", "QN", "QC",
    "E",  # (E) foreign-athlete marker
    "M", "W",  # gender + age-category markers (M-45, W-35): single letters only
    "X",  # foul/attempt mark in jump events (e.g. "ENZO MATE GRAS X-")
}
_RE_LICENSE = re.compile(r"\b(?:CL|CT|CAT|IB|LZ)[-\s]?\d+(?:[-.][A-Z0-9]+)*\b", re.IGNORECASE)
_RE_PARENS = re.compile(r"\([^)]*\)")


def normalize(s: str) -> str:
    """Uppercase, strip accents/punctuation, collapse spaces; drop license/paren noise."""
    s = _RE_LICENSE.sub(" ", s or "")
    s = _RE_PARENS.sub(" ", s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t not in _NOISE_TOKENS and not t.isdigit()]
    return " ".join(tokens)


def tokens(s: str):
    return set(normalize(s).split())


def expand_tokens(tk):
    """Yield the token set plus all nickname-expanded variants."""
    out = [tk]
    frontier = [tk]
    seen = {frozenset(tk)}
    while frontier:
        cur = frontier.pop()
        for t in list(cur):
            for exp in ABBREV_EXPANSIONS.get(t, []):
                if exp in cur:
                    continue
                alt = (cur - {t}) | set(exp.split())
                if frozenset(alt) not in seen:
                    seen.add(frozenset(alt))
                    out.append(alt)
                    frontier.append(alt)
    return out


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def parse_socis():
    entries = []
    for line in SOCIS_MD.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if m and m.group(1) != "id":
            entries.append({"id": int(m.group(1)), "nom": m.group(2), "cognoms": m.group(3)})
    return entries


def load_athlete_variants():
    """variant-normalized-name -> set of canonical names."""
    variants = defaultdict(set)
    for path in ATHLETES_DIR.glob("*.json"):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        canon = d.get("athlete_name")
        if not canon:
            continue
        for v in d.get("name_variants_found", []) or []:
            n = normalize(v)
            if n:
                variants[n].add(canon)
        n = normalize(canon)
        if n:
            variants[n].add(canon)
    return variants


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class SocisMatcher:
    def __init__(self, socis):
        self.socis = socis
        self.exact = defaultdict(list)      # normalized full name -> [ids]
        self.exact_rev = defaultdict(list)  # normalized "cognoms nom" -> [ids]
        self.fuzzy_pool = []                # (id, normalized_full, token_sets)
        for e in socis:
            full = normalize(f"{e['nom']} {e['cognoms']}")
            rev = normalize(f"{e['cognoms']} {e['nom']}")
            if full:
                self.exact[full].append(e["id"])
                self.fuzzy_pool.append((e["id"], full))
            if rev and rev != full:
                self.exact_rev[rev].append(e["id"])
                self.fuzzy_pool.append((e["id"], rev))

    def match(self, name: str):
        """Return (internal_id | None, strategy | None, detail | None)."""
        n = normalize(name)
        if not n:
            return None, "empty_name", None
        # 1. exact
        hit = self.exact.get(n) or self.exact_rev.get(n)
        if hit and len(set(hit)) == 1:
            return hit[0], "exact", None
        if hit:
            return None, "ambiguous", sorted(set(hit))
        # 2. unique token subset (with nickname-expansion attempts)
        for tk in expand_tokens(set(n.split())):
            cands = self._subset_candidates(tk)
            ids = {cid for cid, _ in cands}
            if len(ids) == 1 and cands:
                return ids.pop(), "subset", None
            if len(ids) > 1:
                # prefer candidates whose token set equals the name exactly
                eq = {cid for cid, st in cands if st == tk}
                if len(eq) == 1:
                    return eq.pop(), "subset_exact", None
                return None, "ambiguous", sorted(ids)
        # 3. name-variant canonical comparison (Juan/Joan, Javier/Xavier, ...)
        cand = self._name_variant_match(set(n.split()))
        if cand:
            return cand, "name_variant", None
        # 4. fuzzy (raw and token-sorted)
        return self._fuzzy(n)

    def _subset_candidates(self, tk):
        out = []
        for cid, full in self.fuzzy_pool:
            st = set(full.split())
            if tk and tk <= st:
                out.append((cid, st))
        return out

    def _name_variant_match(self, tk):
        """Exact multiset match modulo Catalan/Spanish given-name variants.
        Requires surname coverage: at most 2 differing tokens, all mapped."""
        ct = canonicalize_tokens(tk)
        hits = set()
        for cid, full in self.fuzzy_pool:
            st = set(full.split())
            if len(st) != len(tk):
                continue
            if canonicalize_tokens(st) == ct:
                hits.add(cid)
        if len(hits) == 1:
            return hits.pop()
        return None

    def _fuzzy(self, n):
        n_tokens = set(n.split())
        n_sorted = " ".join(sorted(n_tokens))
        best = []  # (ratio, id)
        for cid, full in self.fuzzy_pool:
            if abs(len(full) - len(n)) > 12:
                continue
            st = set(full.split())
            shared = n_tokens & st
            long_shared = any(len(t) >= 4 for t in shared)
            if not shared or (not long_shared and len(shared) < len(st)):
                continue
            full_sorted = " ".join(sorted(st))
            r = max(SequenceMatcher(None, n, full).ratio(),
                    SequenceMatcher(None, n_sorted, " ".join(sorted(st))).ratio())
            # require solid token evidence, not just character similarity:
            # either >=2 shared name tokens, or a near-certain ratio
            if len(shared) < 2 and r < 0.93:
                continue
            if r >= MIN_FUZZY_RATIO:
                best.append((r, cid))
        if not best:
            return None, "no_match", None
        top = max(r for r, _ in best)
        winners = sorted({cid for r, cid in best if top - r <= TIE_EPSILON})
        if len(winners) == 1:
            return winners[0], "fuzzy", round(top, 3)
        return None, "ambiguous", winners


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def iter_season_files(season=None):
    pattern = f"{season}/json/*.json" if season else "*/json/*.json"
    for path in sorted(glob.glob(str(SEASONS_DIR / pattern))):
        yield Path(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--season", help="limit to one season (e.g. 2005)")
    args = ap.parse_args()

    socis = parse_socis()
    matcher = SocisMatcher(socis)
    variants = load_athlete_variants()
    print(f"socis: {len(socis)}  athlete files: {len(list(ATHLETES_DIR.glob('*.json')))}")

    decisions = {}  # normalized result name -> (id, strategy, detail)

    def decide(name):
        key = normalize(name)
        if key in decisions:
            return decisions[key]
        if key in MANUAL_EXCLUDES:
            decisions[key] = (None, "manual_exclude", None)
            return decisions[key]
        if key in MANUAL_OVERRIDES:
            decisions[key] = (MANUAL_OVERRIDES[key], "manual_override", None)
            return decisions[key]
        if IBORRA_TOKENS <= set(key.split()):
            decisions[key] = (1, "manual_override_iborra", None)
            return decisions[key]
        rid, strat, detail = matcher.match(name)
        if rid is None and strat in ("no_match", "ambiguous"):
            # try resolving via athletes/ canonical names
            for canon in sorted(variants.get(key, [])):
                if normalize(canon) == key:
                    continue
                rid, strat, detail = matcher.match(canon)
                if rid is not None:
                    strat = f"variant:{strat}"
                    break
        decisions[key] = (rid, strat, detail)
        return decisions[key]

    files = list(iter_season_files(args.season))
    stats = defaultdict(int)
    unknown = {}  # name -> {"internal_id": None, "strategy":..., "candidates":..., "refs": [...]}

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"!! invalid JSON {rel}: {e}", file=sys.stderr)
            continue
        changed = False
        for r in data.get("results", []):
            stats["total_results"] += 1
            name = r.get("athlete_name", "")
            rid, strat, detail = decide(name)
            if rid is not None:
                r["internal_id"] = rid
                stats[f"strategy:{strat.split(':')[0]}"] += 1
                changed = True
            else:
                r["internal_id"] = None
                stats[f"unknown:{strat}"] += 1
                changed = True
                u = unknown.setdefault(normalize(name), {
                    "athlete_name": name,
                    "strategy": strat,
                    "candidates": detail if strat == "ambiguous" else None,
                    "refs": [],
                })
                if len(u["refs"]) < 5:
                    u["refs"].append({
                        "file": rel,
                        "discipline": r.get("discipline"),
                        "performance": r.get("performance"),
                        "event_date": data.get("event_date"),
                    })
                else:
                    u["refs_total"] = u.get("refs_total", 5) + 1
        if changed and not args.dry_run:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ report
    matched_ids = {rid for rid, s, _ in decisions.values() if rid}
    matched_names = sum(1 for rid, _, _ in decisions.values() if rid)
    print(f"\nfiles: {len(files)}  unique names: {len(decisions)}  "
          f"matched names: {matched_names}  distinct socis matched: {len(matched_ids)}")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")

    REPORTS_DIR.mkdir(exist_ok=True)
    decisions_out = {k: {"internal_id": v[0], "strategy": v[1], "detail": v[2]}
                     for k, v in sorted(decisions.items())}
    (REPORTS_DIR / "match_decisions.json").write_text(
        json.dumps(decisions_out, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS_DIR / "unknown_athletes.json").write_text(
        json.dumps(sorted(unknown.values(), key=lambda u: u["athlete_name"]), indent=2, ensure_ascii=False),
        encoding="utf-8")

    amb = [u for u in unknown.values() if u["strategy"] == "ambiguous"]
    nom = [u for u in unknown.values() if u["strategy"] == "no_match" or u["strategy"] == "empty_name"]
    lines = [
        "# Unknown athletes (no internal_id)",
        "",
        f"Generated by `scripts/add_internal_id.py`. Unmatched names: {len(unknown)} "
        f"(ambiguous: {len(amb)}, no-match: {len(nom)})",
        "",
    ]
    if amb:
        lines += ["## Ambiguous (multiple socis candidates)", ""]
        for u in sorted(amb, key=lambda x: x["athlete_name"]):
            lines.append(f"- **{u['athlete_name']}** → candidates: {u['candidates']} "
                         f"| e.g. `{u['refs'][0]['file']}` ({u['refs'][0]['discipline']}, "
                         f"{u['refs'][0]['performance']})")
        lines.append("")
    lines += ["## No match", ""]
    for u in sorted(nom, key=lambda x: x["athlete_name"]):
        r0 = u["refs"][0]
        extra = f" (+{u['refs_total']-1} more)" if u.get("refs_total", 0) > 1 else ""
        lines.append(f"- **{u['athlete_name']}** | `{r0['file']}` ({r0['discipline']}, "
                     f"{r0['performance']}, {r0['event_date']}){extra}")
    (REPORTS_DIR / "unknown_athletes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreports written to {REPORTS_DIR}/")


if __name__ == "__main__":
    main()
