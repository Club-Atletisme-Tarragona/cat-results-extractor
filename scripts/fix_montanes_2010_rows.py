#!/usr/bin/env python3
"""One-shot fix: move the 12 resulcatcadet19610 rows from Montserrat to Maria.

The 2010 cadet PDF prints "Montserrat Montañes" but with Maria's DOB
(11/05/1995) and license CL58883; Montserrat (b. 2001) cannot be cadet in 2010.
Season rows are already re-assigned (internal_id 354) by the MANUAL_OVERRIDES
entry in scripts/add_internal_id.py; this script moves the matching result rows
from athletes/montserrat-montanes-arbo-497.json to athletes/maria-montanes-arbo-354.json,
recomputes derived fields and refreshes athletes/index.json.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from add_internal_id import normalize  # noqa: E402

ATHLETES = ROOT / "athletes"
SRC_ID = 497
DST_ID = 354
MATCH_NAME = "MONTSERRAT MONTANES"  # normalized form of the mislabeled rows


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def find_file(rid: int, fallback_slug: str) -> Path:
    for pattern in (f"{rid}-*.json", f"*-{rid}.json"):
        hits = sorted(ATHLETES.glob(pattern))
        if hits:
            return hits[0]
    return ATHLETES / f"{fallback_slug}.json"


def refresh(d: dict, drop_licenses=()) -> None:
    d["total_results"] = len(d["results"])
    d["source_files_count"] = len({r.get("event_src") for r in d["results"]})
    d["license_variants_found"] = sorted(({r["athlete_id"] for r in d["results"] if r.get("athlete_id")}
                                          | set(d["license_variants_found"])) - {""} - set(drop_licenses))
    d["name_variants_found"] = sorted({r["athlete_name"] for r in d["results"]}
                                      | {d["athlete_name"]})


def main():
    src_path = find_file(SRC_ID, "montserrat-montanes-arbo")
    dst_path = find_file(DST_ID, "maria-montanes-arbo")
    src = json.loads(src_path.read_text(encoding="utf-8"))
    dst = json.loads(dst_path.read_text(encoding="utf-8"))

    moved = [r for r in src["results"] if normalize(r["athlete_name"]) == MATCH_NAME]
    keep = [r for r in src["results"] if normalize(r["athlete_name"]) != MATCH_NAME]
    assert len(moved) == 12, f"expected 12 rows, found {len(moved)}"
    moved_dates = [r["event_date"] for r in moved if r.get("event_date")]

    src["results"] = keep
    refresh(src, drop_licenses={"CL58883"})
    # the mislabeled name variant is Maria's, drop it from Montserrat
    src["name_variants_found"] = [v for v in src["name_variants_found"]
                                  if normalize(v) != MATCH_NAME]
    dst["results"] = dst["results"] + moved
    refresh(dst)

    src_path.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dst_path.write_text(json.dumps(dst, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"moved {len(moved)} rows: {src_path.name} ({src['total_results']}) -> "
          f"{dst_path.name} ({dst['total_results']})")

    index_path = ATHLETES / "index.json"
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    key = lambda s: tuple(int(x) for x in reversed(s.split("/")))
    for entry in idx["athletes"]:
        if entry.get("file") == src_path.name:
            entry["total_results"] = src["total_results"]
            dates = [r["event_date"] for r in src["results"] if r.get("event_date")]
            entry["first_event_date"], entry["last_event_date"] = min(dates, key=key), max(dates, key=key)
        elif entry.get("file") == dst_path.name:
            entry["total_results"] = dst["total_results"]
            dates = [r["event_date"] for r in dst["results"] if r.get("event_date")] + moved_dates
            entry["first_event_date"], entry["last_event_date"] = min(dates, key=key), max(dates, key=key)
    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("index.json refreshed")


if __name__ == "__main__":
    main()
