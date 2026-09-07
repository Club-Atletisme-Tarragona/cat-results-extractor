#!/usr/bin/env python3
"""Add top-level `internal_id` (socisCAT id) to every athletes/*.json file.

Reuses the name-level decisions produced by scripts/add_internal_id.py
(reports/match_decisions.json): every name variant of an athlete file is
normalized and looked up, then the distinct matched socis ids are collected.

  - exactly one distinct id -> athlete gets that id
  - zero ids                -> "internal_id": null, listed as no_match
  - multiple distinct ids   -> "internal_id": null, listed as conflict
                               (aggregation likely merged two people)

Reports (kept inside athletes/ to distinguish from the season-level ones):
  athletes/internal_id_report.md
  athletes/internal_id_report.json

Usage:
  python scripts/add_internal_id_athletes.py --dry-run
  python scripts/add_internal_id_athletes.py
  python scripts/add_internal_id_athletes.py --athlete "adolf-milla-guasch"
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from add_internal_id import normalize  # noqa: E402

ATHLETES_DIR = ROOT / "athletes"
DECISIONS_FILE = ROOT / "reports" / "match_decisions.json"


def load_decisions():
    raw = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
    return {k: v["internal_id"] for k, v in raw.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--athlete", help="process a single athlete file (name or slug)")
    args = ap.parse_args()

    decisions = load_decisions()
    paths = sorted(p for p in ATHLETES_DIR.glob("*.json")
                   if not p.name.startswith("internal_id_report"))
    if args.athlete:
        paths = [p for p in paths if args.athlete in p.stem]

    stats = defaultdict(int)
    unmatched = []  # {"athlete_name", "file", "license_variants_found", "variants_checked"}
    conflicts = []  # {"athlete_name", "file", "ids": {id: [variants]}}
    id_by_file = {}  # athlete-file stem -> internal_id, for mirroring into index.json
    rename_map = {}  # old stem -> new stem (after appending -<id> suffix)
    index_path = None

    for path in paths:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"!! invalid JSON {path}: {e}", file=sys.stderr)
            continue

        if "total_athletes" in d and "athletes" in d:
            index_path = path
            stats["skipped:index"] += 1
            continue
        if not d.get("athlete_name"):
            stats["skipped:non_athlete"] += 1
            continue

        # candidate names: canonical + every variant + per-result names
        names = set()
        if d.get("athlete_name"):
            names.add(d["athlete_name"])
        names.update(d.get("name_variants_found") or [])
        for r in d.get("results", []):
            if r.get("athlete_name"):
                names.add(r["athlete_name"])

        by_id = defaultdict(list)
        for v in names:
            key = normalize(v)
            rid = decisions.get(key)
            if rid is not None:
                by_id[rid].append(v)

        rel = path.relative_to(ROOT).as_posix()
        entry = {
            "athlete_name": d.get("athlete_name"),
            "file": rel,
            "license_variants_found": d.get("license_variants_found") or [],
        }
        if len(by_id) == 1:
            rid = next(iter(by_id))
            stats["matched"] += 1
        elif len(by_id) > 1:
            rid = None
            conflicts.append({**entry, "ids": {k: v for k, v in sorted(by_id.items())}})
            stats["conflict"] += 1
        else:
            rid = None
            unmatched.append({**entry, "variants_checked": sorted(names)})
            stats["no_match"] += 1

        if not args.dry_run:
            # internal_id lives on each result (like the season files),
            # not at athlete level
            d.pop("internal_id", None)
            for r in d.get("results", []):
                r["internal_id"] = rid
            path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        # naming convention: matched athletes carry the id as a filename PREFIX
        # ("<id>-<slug>.json"); missing ids are identified by the ABSENCE of a
        # prefix. Previous suffix-convention names ("<slug>-<id>.json") are
        # converted; digit suffixes that are part of license-based slugs are
        # only stripped when they exactly equal the id.
        stem = path.stem
        if rid is None:
            m = re.match(r"^\d+-(.*)$", stem)
            new_stem = m.group(1) if m else stem
            if new_stem != stem and not args.dry_run:
                path.rename(path.with_name(new_stem + ".json"))
            rename_map[stem] = new_stem
            id_by_file[new_stem] = None
        elif stem.startswith(f"{rid}-"):
            rename_map[stem] = stem
            id_by_file[stem] = rid
        elif args.dry_run:
            rename_map[stem] = f"{rid}-{stem}"
            id_by_file[rename_map[stem]] = rid
            stats["renamed"] += 1
        else:
            m = re.match(r"^(.*)-(\d+)$", stem)
            base = m.group(1) if (m and m.group(2) == str(rid)) else stem
            new_stem = f"{rid}-{base}"
            new_path = path.with_name(f"{new_stem}.json")
            if new_path.exists():
                print(f"!! rename collision: {new_path.name} already exists", file=sys.stderr)
                rename_map[stem] = stem
                id_by_file[stem] = rid
            else:
                path.rename(new_path)
                rename_map[stem] = new_stem
                id_by_file[new_stem] = rid
                stats["renamed"] += 1

    total = stats.get("matched", 0) + stats.get("no_match", 0) + stats.get("conflict", 0)
    print(f"athlete files: {total}")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")

    if args.dry_run:
        return

    # mirror internal_id into athletes/index.json entries (and fix file refs)
    if index_path is not None:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        mirrored = 0
        for entry in idx.get("athletes", []):
            slug = (entry.get("file") or "").removesuffix(".json")
            new_slug = rename_map.get(slug, slug)
            entry["file"] = f"{new_slug}.json"
            entry["internal_id"] = id_by_file.get(new_slug)
            mirrored += 1
        index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"index.json: {mirrored} entries updated")

    out_dir = ATHLETES_DIR
    (out_dir / "internal_id_report.json").write_text(
        json.dumps({"conflicts": conflicts, "no_match": unmatched}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    socis = {}
    for line in (ROOT / "TMP_SOCIS_LIST.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if m and m.group(1) != "id":
            socis[int(m.group(1))] = f"{m.group(2)} {m.group(3)}"

    lines = [
        "# Athletes without a single internal_id",
        "",
        f"Generated by `scripts/add_internal_id_athletes.py`. "
        f"Conflicts: {len(conflicts)} · no-match: {len(unmatched)} · "
        f"matched: {stats.get('matched', 0)}/{total}",
        "",
    ]
    if conflicts:
        lines += ["## Conflicts (variants matched different socis ids)", ""]
        for c in sorted(conflicts, key=lambda x: x["athlete_name"] or ""):
            cand = ", ".join(f"{i} ({socis.get(i)})" for i in c["ids"])
            lines.append(f"- **{c['athlete_name']}** → {cand}")
            for rid, vs in c["ids"].items():
                shown = ", ".join(f"`{v}`" for v in sorted(vs)[:6])
                lines.append(f"  - id {rid}: {shown}")
        lines.append("")
    lines += ["## No match (not identified as a soci)", ""]
    for u in sorted(unmatched, key=lambda x: x["athlete_name"] or ""):
        lic = ", ".join(u["license_variants_found"][:3]) or "—"
        lines.append(f"- **{u['athlete_name']}** | licenses: {lic} | `{u['file']}`")
    (out_dir / "internal_id_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"reports written to {out_dir}/internal_id_report.{{md,json}}")


if __name__ == "__main__":
    main()