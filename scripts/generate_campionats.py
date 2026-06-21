#!/usr/bin/env python3
"""Generate campionats.json from season and current JSON result files."""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PAT_ESPANYA = re.compile(r"campeonato\s+de\s+esp(añ|an)a", re.IGNORECASE)
PAT_CATALUNYA = re.compile(r"campionat\s+de\s+catalunya", re.IGNORECASE)
PAT_SEASON_DIR = re.compile(r"^20\d{2}$")
PAT_FILENAME_DATE = re.compile(r"resultat-(\d{4})\d{4}-", re.IGNORECASE)
PAT_EVENT_DATE = re.compile(r"/(\d{4})$")
PAT_URL_YEAR = re.compile(r"(20\d{2})")

MIN_YEAR = 1990
MAX_YEAR = 2030


def classify_event(event_name: str) -> str | None:
    if PAT_ESPANYA.search(event_name):
        return "Espanya"
    if PAT_CATALUNYA.search(event_name):
        return "Catalunya"
    return None


def year_from_event_date(event_date: str) -> str | None:
    match = PAT_EVENT_DATE.search(event_date.strip())
    if not match:
        return None
    year = int(match.group(1))
    if MIN_YEAR <= year <= MAX_YEAR:
        return str(year)
    return None


def year_from_path(path: Path) -> str | None:
    for part in path.parts:
        if PAT_SEASON_DIR.fullmatch(part):
            return part
    return None


def year_from_filename(path: Path) -> str | None:
    match = PAT_FILENAME_DATE.search(path.name)
    if match:
        return match.group(1)
    return None


def year_from_event_src(event_src: str) -> str | None:
    for match in PAT_URL_YEAR.finditer(event_src):
        year = int(match.group(1))
        if MIN_YEAR <= year <= MAX_YEAR:
            return str(year)
    return None


def resolve_year(data: dict, path: Path) -> str:
    for resolver in (
        lambda: year_from_path(path),
        lambda: year_from_filename(path),
        lambda: year_from_event_date(data.get("event_date", "")),
        lambda: year_from_event_src(data.get("event_src", "")),
    ):
        year = resolver()
        if year:
            return year
    return "unknown"


def collect_json_paths(root: Path, scan_dirs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for scan_dir in scan_dirs:
        base = root / scan_dir
        if not base.exists():
            continue
        paths.extend(sorted(base.rglob("*.json")))
    return paths


def build_campionats(root: Path, scan_dirs: list[str]) -> tuple[dict, dict]:
    buckets: dict[str, dict[str, list[dict]]] = {
        "Catalunya": defaultdict(list),
        "Espanya": defaultdict(list),
    }
    stats = {
        "files_scanned": 0,
        "files_matched": 0,
        "entries": {"Catalunya": 0, "Espanya": 0},
        "unknown_year_files": [],
        "skipped_results": 0,
        "invalid_json": [],
    }

    for path in collect_json_paths(root, scan_dirs):
        stats["files_scanned"] += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            stats["invalid_json"].append((str(path), str(exc)))
            continue

        region = classify_event(data.get("event_name", ""))
        if not region:
            continue

        stats["files_matched"] += 1
        year = resolve_year(data, path)
        if year == "unknown":
            stats["unknown_year_files"].append(str(path))

        event_name = data.get("event_name", "")
        event_date = data.get("event_date", "")
        event_src = data.get("event_src", "")

        for result in data.get("results", []):
            athlete_name = (result.get("athlete_name") or "").strip()
            if not athlete_name:
                stats["skipped_results"] += 1
                continue

            buckets[region][year].append(
                {
                    "event_name": event_name,
                    "event_date": event_date,
                    "event_src": event_src,
                    "athlete_name": athlete_name,
                    "discipline": (result.get("discipline") or "").strip(),
                }
            )
            stats["entries"][region] += 1

    output = {
        region: {
            year: sorted(
                entries,
                key=lambda entry: (
                    entry["event_date"],
                    entry["event_name"],
                    entry["athlete_name"],
                    entry["discipline"],
                ),
            )
            for year, entries in sorted(buckets[region].items(), key=lambda item: item[0])
        }
        for region in ("Catalunya", "Espanya")
    }
    return output, stats


def print_summary(stats: dict) -> None:
    print(f"Files scanned: {stats['files_scanned']}")
    print(f"Championship files matched: {stats['files_matched']}")
    print(
        "Entries: "
        f"Catalunya={stats['entries']['Catalunya']}, "
        f"Espanya={stats['entries']['Espanya']}"
    )

    if stats["skipped_results"]:
        print(f"Skipped results without athlete_name: {stats['skipped_results']}")

    if stats["unknown_year_files"]:
        print(f"Files with unknown year: {len(stats['unknown_year_files'])}", file=sys.stderr)
        for path in stats["unknown_year_files"]:
            print(f"  {path}", file=sys.stderr)

    if stats["invalid_json"]:
        print(f"Invalid JSON files: {len(stats['invalid_json'])}", file=sys.stderr)
        for path, error in stats["invalid_json"]:
            print(f"  {path}: {error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate campionats.json")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <root>/campionats.json)",
    )
    parser.add_argument(
        "--scan-dir",
        action="append",
        dest="scan_dirs",
        default=["seasons", "json"],
        help="Directory under root to scan (repeatable)",
    )
    args = parser.parse_args()

    output_path = args.output or (args.root / "campionats.json")
    campionats, stats = build_campionats(args.root, args.scan_dirs)

    output_path.write_text(
        json.dumps(campionats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print_summary(stats)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
