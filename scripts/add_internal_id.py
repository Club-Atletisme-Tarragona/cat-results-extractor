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
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOCIS_MD = ROOT / "TMP_SOCIS_LIST.md"
# Curated athlete roster (nom,cognoms,id). Primary source: it lists exactly
# the club's athletes, past and present. TMP_SOCIS_LIST.md is the wider
# socis dump and remains a fallback for names this file does not carry.
ATHLETE_ROSTER = ROOT / "socis_athletes.csv"
# Former athletes (nom,cognoms,id,baixa): left the club but still appear in
# historical results, so they must resolve to their socisCAT id too.
FORMER_ATHLETES = ROOT / "socis_former_athletes.csv"
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
    # The club register holds the nickname; the sheet prints the legal name.
    # Owner: "we have in our athletes list Xavi, Baz Vidal, 887".
    "FRANCISCO JAVIER BAZ VIDAL": 887,
    # Owner: the club's Juan González is 1079 (1523 is someone else).
    "JUAN GONZALEZ": 1079,
    # Owner: Sara Bakhtaoui El Maslouhi is 1668 (1667 is the other registration).
    "SARA BAKHTAOUI EL MASLOUHI": 1668,
    # Owner review 2026-11-19 of the remaining unknowns:
    #   Samuel Rodriguez Barrios is registered twice, father and son under the
    #   same name; the competing athlete in these results is the son (1390).
    "SAMUEL RODRIGUEZ BARRIOS": 1390,
    #   "AHANOTU" is truncated by the PDF column width; the competing athlete is
    #   Victoria Chiamaka Onyemaekwu Ahanotu (1391), not Cellina Nonye (1201).
    "AHANOTU": 1391,
    "ONYEMAEKWU AHANOTU": 1391,
    #   The sheet prints ARLET SALDAÑA DURAN; the club record says Saldaña
    #   Fresno (1461) and the owner confirms they are the same person.
    "ARLET SALDANA DURAN": 1461,
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
    "RCAM", "RCAT",  # regional record markers, glued into legacy names
    "AB",            # absolut category marker glued into legacy names
    "E",  # (E) foreign-athlete marker
    "M", "W",  # gender + age-category markers (M-45, W-35): single letters only
    "X",  # foul/attempt mark in jump events (e.g. "ENZO MATE GRAS X-")
}
_RE_LICENSE = re.compile(r"\b(?:CL|CT|CAT|IB|LZ)[-\s]?\d+(?:[-.][A-Z0-9]+)*\b", re.IGNORECASE)
_RE_PARENS = re.compile(r"\([^)]*\)")


def normalize(s: str) -> str:
    """Uppercase, strip accents/punctuation, collapse spaces; drop license/paren noise."""
    s = re.sub(r"\bM\s*[.\u00aa]\s*\u00aa?", " MARIA ", s or "", flags=re.IGNORECASE)
    s = _RE_LICENSE.sub(" ", s)
    s = _RE_PARENS.sub(" ", s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t not in _NOISE_TOKENS and not t.isdigit()]
    return " ".join(tokens)


def display_identity(name: str) -> str:
    """The athlete's name with the sheet's position/series noise removed.

    Legacy era parsers stored the whole row prefix and suffix in the name:
    "1 258 (t) Francisco Javier Baz Vidal M-50", "119 Francisco Jose Iborra
    M-50 AB NP AB", "Kilian Borreda Cervello q RCAM". Those are the same
    athlete rendered differently, so grouping by this form is what makes the
    unknown report readable - as raw strings the backlog looks 4.5x bigger
    than it is (1136 names for 255 athletes).

    Display only: matching keeps using normalize().
    """
    kept = []
    for tok in str(name or "").split():
        if normalize(tok):
            kept.append(tok)
    return " ".join(" ".join(kept).split())


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

def parse_athlete_roster():
    """(id, nom, cognoms) from the curated roster plus the former athletes.

    Both lists are authoritative: an athlete who left the club still owns the
    results they produced while active. Duplicated ids keep the first entry, so
    the active roster wins over the former list.
    """
    entries, seen = [], set()
    for path in (ATHLETE_ROSTER, FORMER_ATHLETES):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    aid = int(str(row.get("id", "")).strip())
                except (TypeError, ValueError):
                    continue
                nom = (row.get("nom") or "").strip()
                cognoms = (row.get("cognoms") or "").strip()
                if aid and (nom or cognoms) and aid not in seen:
                    seen.add(aid)
                    entries.append({"id": aid, "nom": nom, "cognoms": cognoms})
    return entries


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
        # 2b. tolerant match: initials ("Victoria C ONYEMAEKWU"), PDF-truncated
        # tokens ("VICTORIA CHIAMAKA ONYEMAEKW…"), and a stored name contained
        # in the sheet's longer form ("JOSEP MARIA PUIG LARA" vs "Josep M Puig Lara").
        tolerant = self._tolerant_match(n.split())
        if tolerant:
            return tolerant, "tolerant", None

        # 3. name-variant canonical comparison (Juan/Joan, Javier/Xavier, ...)
        cand = self._name_variant_match(set(n.split()))
        if cand:
            return cand, "name_variant", None
        # 4. fuzzy (raw and token-sorted)
        return self._fuzzy(n)

    def _tolerant_match(self, in_tokens):
        """Match allowing initials, truncated tokens and containment.

        A sheet can abbreviate a given name ("Victoria C ONYEMAEKWU"), cut a
        token at the column edge ("…ONYEMAEKW…"), or print a longer name than
        the roster holds. Each token must then be equal, an initial of the
        other, or a >=5-char prefix; at least two real tokens must agree and
        exactly one candidate may survive, otherwise the caller stays unsure.
        """
        def tok_ok(a, b):
            if a == b:
                return True
            if len(a) == 1 or len(b) == 1:
                return a[0] == b[0]
            if len(a) >= 5 and b.startswith(a):
                return True
            if len(b) >= 5 and a.startswith(b):
                return True
            return False

        in_tokens = [t for t in in_tokens if len(t) > 0]
        if len(in_tokens) < 2:
            return None
        hits = set()
        for cid, full in self.fuzzy_pool:
            st = full.split()
            if not st:
                continue
            # every roster token must be covered by some input token and
            # vice versa (order-insensitive), allowing abbreviation
            short, long_ = (in_tokens, st) if len(in_tokens) <= len(st) else (st, in_tokens)
            # A sheet may print extra middle names the roster omits
            # ("WASIM ABDEL AS SAMAD BOUCHIBANE MOKHTARI" vs "Wasim Bouchibane
            # Mokhtari"), so allow a small surplus - but only when the shorter
            # side carries a real name (>=2 tokens), which keeps one-token
            # nicknames from matching everything.
            surplus = len(long_) - len(short)
            if surplus > 3 or (surplus and len(short) < 2):
                continue
            used = set()
            ok = True
            for tok in short:
                match = [i for i, other in enumerate(long_)
                         if i not in used and tok_ok(tok, other)]
                if not match:
                    ok = False
                    break
                used.add(match[0])
            if not ok:
                continue
            real = sum(1 for tok in short if len(tok) >= 2)
            if real < 2:
                continue
            hits.add(cid)
        if len(hits) == 1:
            return hits.pop()
        return None

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

    roster = parse_athlete_roster()
    socis_dump = parse_socis()
    if roster:
        seen = {e["id"] for e in roster}
        socis = roster + [e for e in socis_dump if e["id"] not in seen]
        print(f"  athlete roster: {len(roster)} entries "
              f"(+{len(socis) - len(roster)} from the socis dump as fallback)")
    else:
        socis = socis_dump
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
        f"Generated by `scripts/add_internal_id.py`. Unmatched stored names: {len(unknown)} "
        f"(ambiguous: {len(amb)}, no-match: {len(nom)}).",
        "",
        "Legacy era parsers stored each row's position, lane and category inside the name "
        "(`1 56 (t) Kilian Borreda Cervello BM`, `119 Francisco Jose Iborra M-50 AB NP AB`), "
        "so one athlete appears under many renderings. The no-match section groups by the "
        "name with that bookkeeping stripped: the stored names below belong to far fewer "
        "athletes, and it is those athletes that need adding to `socis_athletes.csv` "
        "or `excluded_athletes.csv`.",
        "",
    ]
    if amb:
        lines += ["## Ambiguous (multiple socis candidates)", ""]
        for u in sorted(amb, key=lambda x: x["athlete_name"]):
            lines.append(f"- **{u['athlete_name']}** → candidates: {u['candidates']} "
                         f"| e.g. `{u['refs'][0]['file']}` ({u['refs'][0]['discipline']}, "
                         f"{u['refs'][0]['performance']})")
        lines.append("")
    # Group the no-match rows per ATHLETE, not per stored string: legacy era
    # parsers carried the row's position/lane/category inside the name, so one
    # athlete shows up under many renderings and a per-string list overstates
    # the backlog several times over.
    groups = {}
    for u in nom:
        identity = display_identity(u["athlete_name"]) or u["athlete_name"]
        g = groups.setdefault(normalize(identity), {"identity": identity, "variants": [],
                                                    "rows": 0, "years": set(), "sample": None})
        g["variants"].append(u["athlete_name"])
        g["rows"] += u.get("refs_total", 1)
        for ref in u["refs"]:
            date = ref.get("event_date") or ""
            if len(date) >= 4 and date[-4:].isdigit():
                g["years"].add(date[-4:])
        if g["sample"] is None:
            g["sample"] = u["refs"][0]

    def close_names(key, limit=2):
        """Club names sharing a token, for the owner to confirm in one pass."""
        want = set(key.split())
        scored = []
        for entry in socis:
            full = normalize(f"{entry['nom']} {entry['cognoms']}")
            have = set(full.split())
            if not (want & have):
                continue
            ratio = SequenceMatcher(None, key, full).ratio()
            if ratio >= 0.80:
                scored.append((ratio, entry))
        scored.sort(key=lambda x: -x[0])
        return [f"{e['nom']} {e['cognoms']} ({e['id']}, {r:.2f})"
                for r, e in scored[:limit]]

    pending_rows = [
        {
            "name": g["identity"],
            "rows": g["rows"],
            "stored_renderings": len(set(g["variants"])),
            "first_season": min(g["years"]) if g["years"] else "",
            "last_season": max(g["years"]) if g["years"] else "",
            "example_file": g["sample"]["file"],
        }
        for g in groups.values()
    ]
    pending_rows.sort(key=lambda r: (-r["rows"], r["name"]))
    with (REPORTS_DIR / "athletes_pending_migration.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name", "rows", "stored_renderings",
                                                "first_season", "last_season", "example_file"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(pending_rows)

    lines += [f"## Former athletes pending creation in the club database ({len(groups)})", "",
              "Confirmed by the owner: these are all former club athletes whose database "
              "records do not exist yet, not foreign athletes. Their results stay unmapped "
              "until the records are created; add them to `socis_former_athletes.csv` "
              "(`nom, cognoms, id, baixa`) and re-run this script. The same list, sorted by "
              "row count, is exported to `reports/athletes_pending_migration.csv`.",
              ""]
    for key in sorted(groups, key=lambda k: (-groups[k]["rows"], groups[k]["identity"])):
        g = groups[key]
        years = sorted(g["years"])
        span = f"{years[0]}-{years[-1]}" if len(years) > 1 else (years[0] if years else "?")
        head = f"- **{g['identity']}** — {g['rows']} rows"
        if len(g["variants"]) > 1:
            head += f", {len(g['variants'])} renderings"
        head += f", {span}"
        lines.append(head)
        others = [v for v in sorted(set(g["variants"])) if v != g["identity"]][:3]
        if others:
            lines.append("  - as stored: " + " | ".join(f"`{v}`" for v in others)
                         + (f" (+{len(set(g['variants'])) - 1 - len(others)} more)"
                            if len(set(g["variants"])) - 1 > len(others) else ""))
        suggestions = close_names(key)
        if suggestions:
            lines.append("  - closest club names: " + "; ".join(suggestions))
        s = g["sample"]
        lines.append(f"  - e.g. `{s['file']}` ({s['discipline']}, {s['performance']})")
    (REPORTS_DIR / "unknown_athletes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreports written to {REPORTS_DIR}/")


if __name__ == "__main__":
    main()
