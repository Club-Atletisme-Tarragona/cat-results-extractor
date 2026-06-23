#!/usr/bin/env python3
"""
Find duplicate athlete JSON files in athletes/ directory.

Files that differ only by suffix noise (MMP, MMT, numbered qualifiers like "6 q",
license suffixes like CL93256AF, etc.) are grouped together.
"""

import json
import os
import re
import sys
from collections import defaultdict

ATHLETES_DIR = "/home/didac/projects/didacrios/cat-results-extractor/athletes"

# Noise suffixes to strip from filenames
# Order matters: longer patterns first to avoid partial matches
NOISE_PATTERNS = [
    # Numbered qualifiers: "6 q", "7 q", "8 q", "2 q", etc.
    # These appear as "-6-q", "-7-q", "-8-q" etc. in filenames
    r'-\d+[-\s]*q',
    # Suffix noise tags
    r'-mmp',
    r'-mmt',
    r'-mmf',
    r'-jnf',
    r'-jvf',
    r'-bronze',
    # Single/two letter suffixes that are noise
    r'-im',
    r'-af',
    r'-lm',
    r'-pm',
    r'-cm',
    r'-bf',
    r'-sf',
    r'-q',
]

# License-like suffixes: CL..., CT..., CAT-..., IB-...
LICENSE_SUFFIX_RE = re.compile(
    r'-(cl\d+|ct[\d\-]+|cat-\d+[a\-\.]*|ib-\d+[a\-\.]*)$',
    re.IGNORECASE
)

# Club-like suffixes: CA-..., JA-..., etc.
CLUB_SUFFIX_RE = re.compile(
    r'-(ca[-\w]+|ja[-\w]+|cag[-\w]+|g[eí]e[-\w]+|bcnb|uabb|ua[-\w]+|barcelona[-\w]+)$',
    re.IGNORECASE
)


def clean_filename_for_slug(filename):
    """Remove known noise suffixes from a filename to get a clean slug."""
    base = filename
    # Strip .json
    if base.endswith('.json'):
        base = base[:-5]

    # Apply noise patterns
    for pattern in NOISE_PATTERNS:
        base = re.sub(pattern, '', base, flags=re.IGNORECASE)

    # Strip license-like suffixes
    base = LICENSE_SUFFIX_RE.sub('', base)

    # Strip club-like suffixes (CA Tarragona, JA Sabadell, etc.)
    base = CLUB_SUFFIX_RE.sub('', base)

    # Clean up any double hyphens or trailing hyphens
    base = re.sub(r'-{2,}', '-', base)
    base = base.strip('-')

    return base.lower().strip()


def extract_info(filepath):
    """Extract key info from a JSON file."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return {
            'athlete_name': data.get('athlete_name', ''),
            'athlete_dob': data.get('athlete_dob', ''),
            'athlete_id': data.get('athlete_id', ''),
            'total_results': data.get('total_results', 0),
        }
    except (json.JSONDecodeError, KeyError) as e:
        return {
            'athlete_name': '',
            'athlete_dob': '',
            'athlete_id': '',
            'total_results': 0,
            '_error': str(e),
        }


def main():
    # Collect all JSON files (excluding index.json and _report.json)
    files = []
    for fname in sorted(os.listdir(ATHLETES_DIR)):
        if not fname.endswith('.json'):
            continue
        if fname in ('index.json', '_report.json'):
            continue
        files.append(fname)

    print(f"Found {len(files)} JSON files in athletes/\n")

    # Group by clean slug
    groups = defaultdict(list)
    for fname in files:
        filepath = os.path.join(ATHLETES_DIR, fname)
        info = extract_info(filepath)
        slug = clean_filename_for_slug(fname)
        groups[slug].append({
            'filename': fname,
            **info,
        })

    # Print duplicate groups
    duplicate_groups = {slug: members for slug, members in groups.items() if len(members) >= 2}

    if not duplicate_groups:
        print("No duplicate groups found.")
        return

    print(f"Found {len(duplicate_groups)} duplicate groups:\n")
    print("=" * 120)

    for slug, members in sorted(duplicate_groups.items()):
        print(f"\nClean slug: {slug}")
        print("-" * 80)
        for m in members:
            error = m.pop('_error', None)
            name = m['athlete_name'] or '(empty)'
            dob = m['athlete_dob'] or '(empty)'
            lic = m['athlete_id'] or '(empty)'
            tr = m['total_results']
            print(f"  File: {m['filename']}")
            print(f"    Name: {name}")
            print(f"    DOB: {dob}")
            print(f"    License: {lic}")
            print(f"    Total results: {tr}")
            if error:
                print(f"    ERROR: {error}")
            print()
        print()


if __name__ == '__main__':
    main()
