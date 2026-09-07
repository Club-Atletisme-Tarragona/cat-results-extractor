#!/usr/bin/env python3
"""One-shot: merge athlete files that share the same internal_id.

The aggregation created one file per (license, normalized name) cluster, so a
single member can appear in several files (name variants, word-order flips,
typos, old/new licenses). Since every result now carries internal_id, files
whose results share one id are merged into a single file named
"<id>-<slug>.json".

Run AFTER scripts/add_internal_id_athletes.py (needs per-result internal_id).
athletes/index.json is refreshed accordingly.
"""

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from add_internal_id import _NOISE_TOKENS  # noqa: E402

ATHLETES = ROOT / "athletes"


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def clean_canonical(raw: str) -> str:
    toks = raw.upper().replace("(", " ").replace(")", " ").split()
    while toks and (toks[0].isdigit() or toks[0] in _NOISE_TOKENS or toks[0] == "."):
        toks.pop(0)
    while toks and toks[-1] in _NOISE_TOKENS:
        toks.pop()
    return " ".join(toks)


def date_key(s: str):
    try:
        d, m, y = s.split("/")
        return (int(y), int(m), int(d))
    except Exception:
        return (9999, 99, 99)


def main():
    files = {}
    for p in sorted(ATHLETES.glob("*.json")):
        if p.name in ("index.json", "_report.json") or p.name.startswith("internal_id_report"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        rids = {r.get("internal_id") for r in d.get("results", [])}
        rids.discard(None)
        if len(rids) > 1:
            print(f"!! skipping mixed-id file {p.name}: {sorted(rids)}", file=sys.stderr)
            continue
        rid = next(iter(rids)) if rids else None
        files[p] = (rid, d)

    groups = defaultdict(list)
    for p, (rid, d) in files.items():
        if rid is not None:
            groups[rid].append(p)

    index_path = ATHLETES / "index.json"
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    merged_count = 0
    for rid, paths in sorted(groups.items()):
        if len(paths) < 2:
            continue
        paths_by_size = sorted(paths, key=lambda p: -len(files[p][1].get("results", [])))
        survivor = paths_by_size[0]
        _, surv_d = files[survivor]
        canonical = clean_canonical(surv_d["athlete_name"]) or surv_d["athlete_name"]

        all_results = []
        variants = set()
        licenses = set()
        srcs = set()
        for p in paths_by_size:
            d = files[p][1]
            all_results.extend(d.get("results", []))
            variants |= set(d.get("name_variants_found") or [])
            licenses |= {l for l in (d.get("license_variants_found") or []) if l}
            srcs |= {r.get("event_src") for r in d.get("results", [])}
        variants = sorted((variants | {canonical}) - {""})
        all_results.sort(key=lambda r: (date_key(r.get("event_date") or ""), r.get("event_src") or ""))
        lic_counts = Counter(r["athlete_id"] for r in all_results if r.get("athlete_id"))
        dob_counts = Counter(r["athlete_dob"] for r in all_results if r.get("athlete_dob"))
        dates = sorted({r["event_date"] for r in all_results if r.get("event_date")}, key=date_key)

        merged = {
            "athlete_name": canonical,
            "athlete_id": lic_counts.most_common(1)[0][0] if lic_counts else "",
            "athlete_dob": dob_counts.most_common(1)[0][0] if dob_counts else "",
            "total_results": len(all_results),
            "name_variants_found": variants,
            "license_variants_found": sorted(licenses),
            "source_files_count": len(srcs),
            "results": all_results,
        }
        target = ATHLETES / f"{rid}-{slugify(canonical)}.json"
        target.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for p in paths:
            if p != target:
                p.unlink()
        merged_count += 1
        print(f"id {rid}: merged {len(paths)} files -> {target.name} "
              f"({len(all_results)} results, lic={merged['athlete_id']}, dob={merged['athlete_dob']})")

        # refresh index: drop absorbed entries, point the survivor at the merged file
        removed = {p.name for p in paths if p != target}
        idx["athletes"] = [e for e in idx["athletes"] if e.get("file") not in removed]
        survivor_entry = next((e for e in idx["athletes"] if e.get("internal_id") == rid), None)
        if survivor_entry is None:
            # the survivor file itself was renamed -> its old entry was filtered
            survivor_entry = {"athlete_id": "", "athlete_name": canonical, "file": target.name,
                              "total_results": 0, "first_event_date": "", "last_event_date": ""}
            idx["athletes"].append(survivor_entry)
        survivor_entry["file"] = target.name
        survivor_entry["athlete_name"] = canonical
        survivor_entry["athlete_id"] = merged["athlete_id"]
        survivor_entry["total_results"] = merged["total_results"]
        survivor_entry["first_event_date"] = dates[0] if dates else ""
        survivor_entry["last_event_date"] = dates[-1] if dates else ""
        survivor_entry["internal_id"] = rid
        files[target] = (rid, merged)
        files = {p: v for p, v in files.items() if p not in removed or p == target}

    idx["total_athletes"] = len(idx["athletes"])

    # repair pass: ensure every athlete file on disk has an index entry
    indexed = {e.get("file") for e in idx["athletes"]}
    repaired = 0
    for p, (rid, d) in files.items():
        if p.name in indexed:
            continue
        dates = sorted({r["event_date"] for r in d.get("results", []) if r.get("event_date")}, key=date_key)
        idx["athletes"].append({
            "athlete_id": d.get("athlete_id", ""),
            "athlete_name": d.get("athlete_name", ""),
            "file": p.name,
            "total_results": len(d.get("results", [])),
            "first_event_date": dates[0] if dates else "",
            "last_event_date": dates[-1] if dates else "",
            "internal_id": rid,
        })
        repaired += 1
    if repaired:
        print(f"repaired {repaired} missing index entries")

    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"merged {merged_count} id groups; index now {len(idx['athletes'])} athletes")


if __name__ == "__main__":
    main()
