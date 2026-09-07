#!/usr/bin/env python3
"""Split athlete files that accidentally merged two different people.

The two known cases (found while assigning internal_id, see
athletes/internal_id_report.md):

  athletes/diaz-jose-marcal.json
      -> Marc Jose Diaz  (socis 294, license CT17220/CL17220, DOB 08/01/1993)
      -> Edgar Jose Diaz (socis 653, license CL71711/CL27846, DOB 08/04/2002)
  athletes/montserrat-montanes-arbo.json
      -> Maria Montañes Arbó       (socis 354, license CT19595, DOB 11/05/1995)
      -> Montserrat Montañes Arbo  (socis 497, licenses CT24566/CL57989/CL71723,
                                    DOB 22/02/2001)

Results are assigned by license first (strongest evidence), then by
distinguishing given-name token. Bare-surname rows that cannot be separated by
name go to the person whose age category matches the event (documented below):
  - "JOSE DIAZ" LLARGADA Infantil 2015 -> Edgar (born 2002 = Infantil age;
    Marc born 1993 cannot be Infantil)
  - "MONTANES ARBO" PES Cadet 2015 -> Montserrat (born 2001 = Cadet age;
    Maria born 1995 cannot be Cadet)

The originals are removed and athletes/index.json is regenerated accordingly.
New filenames already carry the internal_id suffix (naming convention).
"""

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from add_internal_id import _NOISE_TOKENS  # noqa: E402

ATHLETES = ROOT / "athletes"

SPLITS = {
    "diaz-jose-marcal": {
        "ambiguous_owner": 653,  # bare "JOSE DIAZ" rows: see module docstring
        294: {"licenses": {"CT17220", "CL17220"}, "tokens": {"MARC"}},
        653: {"licenses": {"CL71711", "CL27846"}, "tokens": {"EDGAR", "EDGARD"}},
    },
    "montserrat-montanes-arbo": {
        "ambiguous_owner": 497,  # bare "MONTANES ARBO" rows: see module docstring
        354: {"licenses": {"CT19595", "CL58883"}, "tokens": {"MARIA"}},
        # CL58883 belongs to Maria: the 2010 cadet PDF prints "Montserrat Montañes"
        # but with Maria's DOB (11/05/1995); Montserrat (b. 2001) cannot be cadet.
        497: {
            "licenses": {"CT24566", "CL57989", "CL71723"},
            "tokens": {"MONTSERRAT", "MONTSE", "MONSERRAT", "MONTANER"},
        },
    },
}


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def split_file(stem: str, spec: dict, index_entries: list):
    path = ATHLETES / f"{stem}.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    rules = {rid: rule for rid, rule in spec.items() if isinstance(rid, int)}
    clusters = {rid: [] for rid in rules}
    for r in d["results"]:
        lic = (r.get("athlete_id") or "").upper()
        toks = set(re.sub(r"[^A-Z0-9 ]", " ", r["athlete_name"].upper()).split())
        target = None
        for rid, rule in rules.items():
            if lic and lic in rule["licenses"]:
                target = rid
                break
        if target is None:
            for rid, rule in rules.items():
                if toks & rule["tokens"]:
                    target = rid
                    break
        if target is None:
            target = spec["ambiguous_owner"]
        clusters[target].append(r)

    built = []
    for rid, rows in clusters.items():
        if not rows:
            continue

        def clean(raw: str) -> str:
            """Drop leading position/dorsal/(t) noise and trailing category markers."""
            toks = raw.upper().replace("(", " ").replace(")", " ").split()
            while toks and (toks[0].isdigit() or toks[0] in _NOISE_TOKENS):
                toks.pop(0)
            while toks and toks[-1] in _NOISE_TOKENS:
                toks.pop()
            return " ".join(toks)

        raw_names = Counter(clean(r["athlete_name"]) for r in rows if clean(r["athlete_name"]))
        canonical = raw_names.most_common(1)[0][0]
        lics = Counter(r["athlete_id"] for r in rows if r.get("athlete_id"))
        dobs = Counter(r["athlete_dob"] for r in rows if r.get("athlete_dob"))
        variants = sorted({clean(r["athlete_name"]) for r in rows} | {canonical})
        srcs = {r.get("event_src") for r in rows}
        dates = sorted({r["event_date"] for r in rows if r.get("event_date")})
        out = {
            "athlete_name": canonical,
            "athlete_id": lics.most_common(1)[0][0] if lics else "",
            "internal_id": rid,
            "athlete_dob": dobs.most_common(1)[0][0] if dobs else "",
            "total_results": len(rows),
            "name_variants_found": variants,
            "license_variants_found": sorted(lics),
            "source_files_count": len(srcs),
            "results": rows,
        }
        fname = f"{rid}-{slugify(canonical)}.json"
        (ATHLETES / fname).write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        built.append((fname, out))
        print(f"  wrote {fname}: {len(rows)} results, id={rid}, "
              f"lic={out['athlete_id']}, dob={out['athlete_dob']}")

    # update index.json: replace the old entry with the new ones
    index_entries[:] = [e for e in index_entries if e.get("file") != f"{stem}.json"]
    for fname, out in built:
        index_entries.append({
            "athlete_id": out["athlete_id"],
            "athlete_name": out["athlete_name"],
            "file": fname,
            "total_results": out["total_results"],
            "first_event_date": min((r["event_date"] for r in out["results"] if r.get("event_date")),
                                    key=lambda s: tuple(int(x) for x in reversed(s.split("/")))),
            "last_event_date": max((r["event_date"] for r in out["results"] if r.get("event_date")),
                                   key=lambda s: tuple(int(x) for x in reversed(s.split("/")))),
            "internal_id": out["internal_id"],
        })
    path.unlink()
    print(f"  removed {stem}.json")


def main():
    index_path = ATHLETES / "index.json"
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    entries = idx["athletes"]
    for stem, spec in SPLITS.items():
        print(f"splitting {stem}.json")
        split_file(stem, spec, entries)
    entries.sort(key=lambda e: (-e.get("total_results", 0), e.get("athlete_name", "")))
    idx["total_athletes"] = len(entries)
    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"index.json: {len(entries)} athletes")


if __name__ == "__main__":
    main()