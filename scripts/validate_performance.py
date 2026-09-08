#!/usr/bin/env python3
"""Validate performance values in season JSONs against DISCIPLINES.md format spec.

Checks that each result's performance matches the expected format for its discipline:
- ss.cc: decimal seconds (e.g. "10.52") — for sprints/hurdles under 2 minutes
- mm:ss.cc: minutes:seconds.centiseconds (e.g. "2:08.15") — for middle/long distance
- HH:mm:ss: hours:minutes:seconds — for marathon/walks
- m.cm: meters.centimeters (e.g. "5.85") — for throws/jumps
- p: points (integer) — for combined events

Usage:
    python3 scripts/validate_performance.py              # validate all seasons
    python3 scripts/validate_performance.py --season 2015  # validate one season
    python3 scripts/validate_performance.py --report      # generate reports
"""
import re, json, glob, sys, argparse
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path(__file__).resolve().parent.parent

def load_formats():
    formats = {}
    for line in open(REPO / 'DISCIPLINES.md'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*\w+\s*\|\s*(\S+)\s*\|', line)
        if m and m.group(1) != 'id':
            formats[m.group(2)] = m.group(3).split('(')[0].strip()
    # APPROVED_PENDING names (same specs as their DISCIPLINES.md counterparts)
    formats.update({
        "100 metres tanques (0.91)": "ss.cc", "60 metres tanques (0.50)": "ss.cc",
        "Pes (2 Kg)": "m.cm", "Disc (600 g)": "m.cm", "Martell (2 Kg)": "m.cm",
        "Javelina (300 g)": "m.cm", "Martell pesat (7.260 Kg)": "m.cm",
        "Javelina (500 g)": "m.cm", "Javelina (700 g)": "m.cm",
        "Javelina (400 g)": "m.cm", "Javelina (800 g)": "m.cm",
        "Javelina (600 g)": "m.cm", "Martell pesat (15.88 Kg)": "m.cm",
        "Martell pesat (9.08 Kg)": "m.cm", "Martell (6 kg)": "m.cm",
        "Triatló": "p", "4x80": "ss.cc", "Javelina (500g)": "m.cm",
    })
    return formats

def check_perf(disc, perf, formats):
    fmt = formats.get(disc)
    if not fmt: return 'unknown_discipline'
    p = perf.strip()
    if not p: return 'empty'
    if p.upper() in ('N.P.','NP','DNS','DNF','DQ','RET.','RET','NULS','X'): return None
    base = fmt.split('(')[0].strip()
    if base == 'ss.cc':
        if not re.match(r'^\d{1,3}\.\d{1,3}$', p): return 'ss.cc_format_wrong'
        val = float(p)
        if val < 2.0: return 'ss_too_low_likely_height'
        if val > 120: return 'ss_too_high_likely_time'
        return None
    elif base == 'mm:ss.cc':
        if re.match(r'^\d{1,3}\.\d{1,3}$', p):
            # decimal-only seconds are never valid for >=600m events
            # (600m WR ~1:15); they are shifted marks or truncated minutes
            return 'mm:ss_stored_as_decimal'
        if re.match(r'^\d{1,3}:\d{2}\.\d{1,2}$', p): return None
        if re.match(r'^\d{1,3}:\d{2}$', p): return None
        return 'mm:ss_format_wrong'
    elif fmt == 'HH:mm:ss':
        if re.match(r'^\d{1,2}:\d{2}:\d{2}$', p): return None
        if re.match(r'^\d{1,2}:\d{2}\.\d{1,2}$', p): return 'HH:mm:ss_stored_as_mm:ss.cc'
        return 'HH:mm:ss_format_wrong'
    elif fmt == 'HH:mm:ss.cc':
        if re.match(r'^\d{1,2}:\d{2}:\d{2}\.\d', p): return None
        return 'HH:mm:ss.cc_format_wrong'
    elif fmt == 'm.cm':
        if re.match(r'^\d{1,3}\.\d{1,2}$', p):
            val = float(p)
            if val > 100: return 'm.cm_garbage_int'
            if val < 0.5: return 'm.cm_too_low'
            return None
        if re.match(r'^\d+$', p):
            return 'm.cm_garbage_int' if int(p) > 100 else 'm.cm_stored_as_int'
        if ':' in p: return 'm.cm_has_colon_likely_time'
        return 'm.cm_format_wrong'
    elif fmt == 'p':
        return None if re.match(r'^\d{3,5}$', p) else 'points_format_wrong'
    return 'unknown_format'

def categorize(issue):
    if issue == 'unknown_discipline': return 'combined_header_row'
    if 'height' in issue: return 'combined_column_shift'
    if 'veterans' in issue or 'stored_as_int' in issue or 'has_colon' in issue:
        return 'veterans_wrong_column'
    if 'stored_as_decimal' in issue: return 'veterans_wrong_column'
    if 'format_wrong' in issue and 'mm:ss' in issue: return 'marxa_quote_format'
    if 'garbage' in issue: return 'pdfplumber_garbage'
    if 'ss.cc_format_wrong' in issue: return 'veterans_wrong_column'
    return 'other'

CAT_DESC = {
    'combined_header_row': 'Combined-event table headers stored as discipline (needs re-extraction)',
    'veterans_wrong_column': 'Veterans meets: extractor grabbed age/percentage column instead of the mark',
    'combined_column_shift': 'Combined events: alçada heights stored under tanques/hurdles (column shift)',
    'pdfplumber_garbage': 'pdfplumber-quality extraction: garbage numeric values',
    'marxa_quote_format': "Old quote-based time format (12'41'') not parsed",
    'other': 'Miscellaneous extraction artifacts',
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', help='validate one season')
    ap.add_argument('--report', action='store_true', help='generate JSON + MD reports')
    args = ap.parse_args()
    formats = load_formats()

    by_file = defaultdict(list)
    total = issues_count = 0
    seasons = [args.season] if args.season else [str(s) for s in range(2005, 2026)]

    for s in seasons:
        for f in sorted(glob.glob(str(REPO / f'seasons/{s}/json/*.json'))):
            try: d = json.load(open(f))
            except: continue
            for r in d.get('results', []):
                total += 1
                disc = r.get('discipline', '')
                perf = r.get('performance', '')
                issue = check_perf(disc, perf, formats)
                if issue:
                    issues_count += 1
                    by_file[f].append({
                        'season': s, 'athlete': r.get('athlete_name','')[:30],
                        'discipline': disc[:40], 'performance': perf[:15],
                        'issue': issue, 'category': categorize(issue),
                    })

    print(f'Total: {total} | Issues: {issues_count} ({issues_count*100//max(total,1)}%)')
    cat_counts = Counter(e['category'] for entries in by_file.values() for e in entries)
    for c, n in cat_counts.most_common():
        print(f'  {n:4d} {c} — {CAT_DESC.get(c, "")}')

    if args.report:
        report = {'generated': 'auto', 'total_results': total, 'total_issues': issues_count,
                  'by_category': dict(cat_counts), 'by_file': {}}
        for f, entries in sorted(by_file.items()):
            report['by_file'][f] = {
                'issue_count': len(entries),
                'categories': dict(Counter(e['category'] for e in entries)),
                'entries': entries}
        (REPO / 'reports/performance_validation.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False))

        md = ['# Performance Format Validation Report', '',
              f'Total results: {total} | Issues: {issues_count} ({issues_count*100//max(total,1)}%)', '',
              '## By category', '', '| Category | Count |', '|---|---|']
        for c, n in cat_counts.most_common():
            md.append(f'| {c} | {n} |')
        md += ['', '## By season', '', '| Season | Issues |', '|---|---|']
        s_counts = Counter(e['season'] for entries in by_file.values() for e in entries)
        for s in sorted(s_counts): md.append(f'| {s} | {s_counts[s]} |')
        md += ['', '## Affected files', '']
        for f, entries in sorted(by_file.items()):
            if len(entries) < 2: continue
            md.append(f'### `{f}` ({len(entries)} issues)')
            md.append('')
            md.append('| Athlete | Discipline | Performance | Issue |')
            md.append('|---|---|---|---|')
            for e in entries[:10]:
                md.append(f'| {e["athlete"]} | {e["discipline"]} | {e["performance"]} | {e["issue"]} |')
            if len(entries) > 10:
                md.append(f'| ... | | | ({len(entries)-10} more) |')
            md.append('')
        (REPO / 'reports/performance_validation.md').write_text('\n'.join(md))
        print(f'\nReports saved: reports/performance_validation.json + .md')

if __name__ == '__main__':
    main()
