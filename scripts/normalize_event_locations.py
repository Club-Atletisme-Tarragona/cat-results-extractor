#!/usr/bin/env python3
"""One-off/backfill migration: canonicalize event_location in result JSONs.

Applies the rules from location_normalization.py to every JSON already in the
repository. Scope is seasons/*/json/*.json plus the top-level json/*.json
(current season). json/imported/ is never touched.

Three passes, in order, per file:

  A  exact variant rewrite: normalize_location(event_location) turns
     "Joan Serrahima" / "Serrahima" / "BCN-SE" into "Barcelona-SE". Gated: a legacy
     stored value is NOT evidence, so a rewrite that would put a file onto one of
     the canonical Barcelona venues needs the venue corroborated by event_name.
     Without corroboration the file is reported as a conflict and left untouched
     (the old value may have been wrong all along -- the meeting can have been held
     in another city entirely).
  B  event_name evidence: when the location is not canonical yet but the event
     name quotes the Serrahima (or Palau Sant Jordi) venue line, the venue line
     wins. This also repairs wrong cities ("Sabadell") and header garbage
     ("Club   Lic ...") on Serrahima meetings. Corroboration, not proof: the event
     name keeps the PDF header verbatim and can quote a record line ("RCAM ...
     Serrahima-BCN"), which names where a record was set rather than where the
     meeting was held. Pass B is therefore only trusted when the stored value is
     already Barcelona-ish or unusable; pass A never promotes on name evidence it
     cannot check.
  C  --resolve-barcelona: files still on the ambiguous plain "Barcelona"
     location are resolved from the source PDF header (event_src). Serrahima ->
     "Barcelona-SE", Palau Sant Jordi -> "Barcelona - Palau Sant Jordi",
     neither -> left as "Barcelona" and reported as unresolved.

Writes are atomic: the new content goes to a sibling .json.tmp and is moved into
place with os.replace(), so an interrupted run cannot leave a truncated JSON.

The migration is idempotent: a second run finds nothing to change. Only
event_location is modified; results and every other key are left untouched, and
files without a change are never rewritten.

Usage:
    python3 scripts/normalize_event_locations.py --dry-run
    python3 scripts/normalize_event_locations.py --dry-run --season 2015
    python3 scripts/normalize_event_locations.py --dry-run --resolve-barcelona --pdf-batch 40
    python3 scripts/normalize_event_locations.py            # real run
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path('/tmp/fca_locations')

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from location_normalization import (CANONICAL_PALAU, CANONICAL_SERRAHIMA,  # noqa: E402
                                    classify_pdf_header, matches_palau,
                                    matches_serrahima, normalize_location)
# get_pdf_text() downloads the PDF and caches the pdftotext text under TMP,
# sharing the cache with scripts/fix_event_locations.py.
from fix_event_locations import get_pdf_text  # noqa: E402

CANONICAL = (CANONICAL_SERRAHIMA, CANONICAL_PALAU)
PLAIN_BARCELONA = "Barcelona"


def needs_fix(loc):
    """Simplified garbage check (same idea as fix_event_locations.needs_fix)."""
    if not loc or not loc.strip():
        return True
    for bad in ('Club', 'Lic', 'Semifinal', 'Final', 'Ronda', 'Pto', 'Dor',
                'RESULTATS', '60m', '100m', '200m', '300m', '80m', '150m',
                '1.000m', '600m'):
        if bad in loc:
            return True
    if len(loc) > 80:
        return True
    return False


def as_text(value):
    """Return a stripped string for a JSON value that may be missing or odd."""
    return value.strip() if isinstance(value, str) else ''


def iter_json_files(season=None):
    """Yield (label, path) for every JSON in scope, sorted, seasons first."""
    paths = sorted(glob.glob(str(REPO / 'seasons' / '*' / 'json' / '*.json')))
    paths += sorted(glob.glob(str(REPO / 'json' / '*.json')))
    seen = set()
    for f in paths:
        if f in seen:
            continue
        seen.add(f)
        rel = Path(f).relative_to(REPO)
        # seasons/<label>/json/x.json -> <label>;  json/x.json -> "json" (current season)
        label = rel.parts[1] if rel.parts[0] == 'seasons' else 'json'
        if season and season not in label:
            continue
        yield label, f


def corroborated_by_event_name(name, candidate):
    """True when event_name names the venue that `candidate` claims.

    event_name keeps the PDF header verbatim, so agreement is corroboration and not
    proof (the header can quote a record line). Disagreement is enough to refuse a
    promotion: a legacy "Serrahima" string in event_location, on a sheet whose event
    name does not mention the stadium, cannot be trusted to mean the meeting was
    held there.
    """
    if candidate == CANONICAL_SERRAHIMA:
        return matches_serrahima(name)
    if candidate == CANONICAL_PALAU:
        return matches_palau(name)
    return True


def plan_passes_ab(data):
    """Apply passes A and B.

    Returns (new_location, stage, conflict_candidate):
      (None, None, None)        nothing to change
      (new, 'A'|'B'|'A+B', None) rewrite to `new`
      (None, 'conflict', cand)  pass A would promote the stored value onto a
                                canonical venue that event_name does not back up;
                                the file is reported instead of rewritten
    """
    old = data.get('event_location', '')
    if not isinstance(old, str):
        old = ''
    name = as_text(data.get('event_name', ''))

    # Pass A: normalize the location string itself. A legacy value is only a
    # spelling of the truth if something else agrees with it, so promoting onto a
    # canonical Barcelona venue requires event_name corroboration.
    current = normalize_location(old)
    changed_a = current != old
    if changed_a and current in CANONICAL and not corroborated_by_event_name(name, current):
        return None, 'conflict', current

    # Pass B: the event name carries the PDF venue line, so it is authoritative
    # -- but only when the location is not already one of the canonical ones.
    changed_b = False
    if current not in CANONICAL:
        replacement = None
        if matches_serrahima(name):
            replacement = CANONICAL_SERRAHIMA
        elif matches_palau(name) and (current == PLAIN_BARCELONA or needs_fix(current)):
            replacement = CANONICAL_PALAU
        if replacement is not None and replacement != current:
            current = replacement
            changed_b = True

    if not (changed_a or changed_b):
        return None, None, None
    if changed_a and changed_b:
        stage = 'A+B'
    elif changed_a:
        stage = 'A'
    else:
        stage = 'B'
    return current, stage, None


def write_location(path, new_location):
    """Rewrite a JSON file with only event_location changed, atomically.

    The payload is written to a sibling temp file and then moved into place with
    os.replace(), which is atomic on POSIX: either the old file or the new one is on
    disk at every moment, never a half-written JSON. On failure the temp file is
    removed and the error re-raised, so the original stays intact.
    """
    path = Path(path)
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    data['event_location'] = new_location
    payload = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    tmp = path.with_suffix('.json.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def main():
    ap = argparse.ArgumentParser(description='Canonicalize event_location in result JSONs')
    ap.add_argument('--dry-run', action='store_true', help='print changes, write nothing')
    ap.add_argument('--season', help='restrict to one season label (substring match, e.g. 2015)')
    ap.add_argument('--batch', type=int, default=0,
                    help='max files to change in passes A/B (default: all)')
    ap.add_argument('--resolve-barcelona', action='store_true',
                    help='resolve plain "Barcelona" locations from the source PDF header')
    ap.add_argument('--pdf-batch', type=int, default=40,
                    help='max PDF reads for the --resolve-barcelona pass (default: 40)')
    args = ap.parse_args()

    files = list(iter_json_files(args.season))
    print(f'Scanning {len(files)} JSON files'
          + (f' (season filter: {args.season})' if args.season else ''))

    ab_pending = []   # (label, path, old, new, stage)
    c_pending = []    # (label, path, event_src)
    conflicts = []    # (label, path, old, canonical_candidate) -- not rewritten
    broken = 0
    canonical_now = Counter()

    for label, f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            broken += 1
            print(f'  ! {label}/{Path(f).name} unreadable ({e})')
            continue
        if not isinstance(data, dict):
            broken += 1
            continue

        new, stage, conflict = plan_passes_ab(data)
        if conflict is not None:
            conflicts.append((label, f, data.get('event_location', ''), conflict))
            continue
        current = new if new is not None else as_text(data.get('event_location', ''))
        if current in CANONICAL:
            canonical_now[current] += 1

        if new is not None:
            ab_pending.append((label, f, data.get('event_location', ''), new, stage))
            continue

        # Pass C candidate: still the ambiguous plain "Barcelona".
        if args.resolve_barcelona and current == PLAIN_BARCELONA:
            src = as_text(data.get('event_src', ''))
            if src:
                c_pending.append((label, f, src))

    ab_limit = args.batch if args.batch else len(ab_pending)
    if args.batch and len(ab_pending) > args.batch:
        print(f'  (batch limit: {args.batch} of {len(ab_pending)} pending A/B changes)')

    transitions = Counter()
    stages = Counter()
    written = 0
    write_failed = 0

    # --- passes A + B ------------------------------------------------------
    for label, f, old, new, stage in ab_pending[:ab_limit]:
        stages[stage] += 1
        transitions[f'{old} → {new}'] += 1
        print(f'  [{stage}] {label}/{Path(f).name}  {old!r} → {new!r}')
        if not args.dry_run:
            try:
                write_location(f, new)
                written += 1
            except Exception as e:
                write_failed += 1
                print(f'  ! write failed {f}: {e}')

    # --- pass C: resolve ambiguous "Barcelona" from the PDF header ---------
    resolved_c = unresolved_c = pdf_failed_c = skipped_c = 0
    if args.resolve_barcelona:
        TMP.mkdir(exist_ok=True)
        batch_c = c_pending[:args.pdf_batch]
        skipped_c = len(c_pending) - len(batch_c)
        print(f'\nPass C: resolving plain "{PLAIN_BARCELONA}" from PDF headers: '
              f'{len(batch_c)} of {len(c_pending)} candidates')
        for label, f, src in batch_c:
            fname = f'{label}/{Path(f).name}'
            try:
                pdf_text = get_pdf_text(src, TMP)
            except Exception as e:
                pdf_text = None
                print(f'  ! {fname[:52]:52s} ({e})')
            if not pdf_text:
                pdf_failed_c += 1
                print(f'  x {fname[:52]:52s} PDF unavailable, kept "{PLAIN_BARCELONA}"')
                continue
            venue = classify_pdf_header(pdf_text)
            if not venue:
                unresolved_c += 1
                print(f'  - {fname[:52]:52s} no Serrahima/Palau in header, kept "{PLAIN_BARCELONA}"')
                continue
            stages['C'] += 1
            transitions[f'{PLAIN_BARCELONA} → {venue}'] += 1
            resolved_c += 1
            print(f'  [C] {fname[:46]:46s}  {PLAIN_BARCELONA!r} → {venue!r}')
            if not args.dry_run:
                try:
                    write_location(f, venue)
                    written += 1
                except Exception as e:
                    write_failed += 1
                    print(f'  ! write failed {f}: {e}')
    elif c_pending:
        print(f'\n{len(c_pending)} files still on plain "{PLAIN_BARCELONA}" '
              f'(rerun with --resolve-barcelona to resolve them from the PDFs)')

    # --- conflicts: pass A refused to promote a legacy value ------------------
    if conflicts:
        print('\nConflicts (needs manual review):')
        for label, f, old, cand in conflicts:
            print(f'  {label}/{Path(f).name}  {old!r} → {cand!r} '
                  f'(event_name does not corroborate the venue)')

    # --- summary -----------------------------------------------------------
    print('\n=== Summary ===')
    print(f'Scanned: {len(files)} | Unreadable/not-an-object: {broken}')
    print(f'Pass A changes: {stages["A"] + stages["A+B"]}')
    print(f'Pass B changes: {stages["B"] + stages["A+B"]}')
    print(f'Conflicts (not rewritten, needs manual review): {len(conflicts)}')
    if args.resolve_barcelona:
        print(f'Pass C changes: {resolved_c} | Unresolved (kept "{PLAIN_BARCELONA}"): '
              f'{unresolved_c} | PDF unavailable: {pdf_failed_c} | '
              f'Not processed (pdf-batch): {skipped_c}')
    print(f'Pending A/B not processed (batch): {max(0, len(ab_pending) - ab_limit)}')
    print('Transitions:')
    for key, count in sorted(transitions.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f'  {key}: {count}')
    # Canonical totals after this run: files already on a canonical value plus
    # the files this run moves onto it.
    final_canonical = {c: canonical_now[c] for c in CANONICAL}
    for key, count in transitions.items():
        target = key.split(' → ')[1]
        if target in final_canonical:
            final_canonical[target] += count
    print('Canonical locations after this run: '
          + ', '.join(f'{k}={v}' for k, v in sorted(final_canonical.items())))
    total = sum(transitions.values())
    if args.dry_run:
        print(f'\nDry run: {total} files would change, nothing written')
    else:
        print(f'\nFiles rewritten: {total}'
              + (f' | write failures: {write_failed}' if write_failed else ''))


if __name__ == '__main__':
    main()
