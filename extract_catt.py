#!/usr/bin/env python3
"""
Extractora de resultats d'atletisme per al Club Atletisme Tarragona (CATT / CA Tarragona).
Extreu les dades dels atletes del CATT d'un PDF de resultats i les exporta en JSON.

Cada prova té el seu propi format d'extracció:
- Track (sprints, mig fons, fons, vallas): resultat a la línia CATT
- Marcha: resultat a la línia CATT
- Jumps (Longitud, Triple Salto): resultat a la línia del nom+naixement
- Height (Altura, Pértiga): resultat a la línia CATT o cap endavant
- Field (Disco, Martillo, Peso, Jabalina): resultat a la línia del nom+naixement
- Relay (4x100m, 4x400m): equip amb resultats, un registre per membre
"""

import subprocess
import sys
import re
import json
import os


def extract_text(pdf_path):
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error executant pdftotext: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def parse_header(text):
    competicio = ""
    ubicacio = ""
    localitat = ""
    data = ""
    lines = text.split('\n')

    # Generic competition name: any line containing "Jornada" and "Campionat"/"Campeonato"
    # Also accept lines with just "Campionat"/"Campeonato" (without "Jornada")
    for i, line in enumerate(lines[:30]):
        stripped = line.strip()
        if 'Jornada' in stripped and ('Campionat' in stripped or 'Campeonato' in stripped):
            competicio = stripped
            break
    if not competicio:
        for i, line in enumerate(lines[:30]):
            stripped = line.strip()
            if ('Campionat' in stripped or 'Campeonato' in stripped) and 'Campionatu' not in stripped and 'Jornada' not in stripped:
                competicio = stripped
                break
    # Fallback: accept "Jornada" alone as competition name (e.g., "3ª Jornada Llançaments Llargs d'Hivern Sub14-16")
    if not competicio:
        for i, line in enumerate(lines[:30]):
            stripped = line.strip()
            if 'Jornada' in stripped and 'sesión' not in stripped.lower() and 'sesion' not in stripped.lower():
                competicio = stripped
                break
    # Fallback: accept "Control" as competition name (e.g., "6è Control de Promoció Sub16-18")
    if not competicio:
        for i, line in enumerate(lines[:30]):
            stripped = line.strip()
            if 'Control' in stripped and 'sesión' not in stripped.lower() and 'sesion' not in stripped.lower():
                competicio = stripped
                break

    # Generic venue: any line containing "Estadi", "Pista", "Pabellon", "Pabellón"
    for i, line in enumerate(lines[:20]):
        stripped = line.strip()
        if any(kw in stripped for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón', 'pabellon', 'pabellón']):
            ubicacio = stripped
            break

    # Extract localitat and date from the page header block
    # Pattern: competition name (or venue) → city → date, within first 30 lines
    for i, line in enumerate(lines[:30]):
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
        if date_match:
            data = date_match.group(1)
            # The localitat is the non-empty line before the date,
            # within the first 5 lines before the date
            for j in range(i - 1, max(i - 5, -1), -1):
                prev = lines[j].strip()
                if prev and not re.search(r'\d{2}/\d{2}/\d{4}', prev):
                    # Skip lines that are competition name or venue
                    if 'Jornada' in prev and 'Campionat' in prev:
                        continue
                    if any(kw in prev for kw in ['Estadi', 'Pista', 'Pabellon', 'Pabellón']):
                        continue
                    localitat = prev
                    break
            break

    return competicio, ubicacio, localitat, data


# ============================================================================
# Event detection
# ============================================================================

EVENT_PATTERNS = [
    # Combined events (pentathlon/heptathlon/tetrathlon/hexathlon) - must be before other patterns
    # Master categories: "Pentathlon PC Master M60", "Pentathlón VET.Mujeres. PC Master F55"
    r'(?:Pentathlón|Pentatlón|Pentathlon|Pentatló|Heptathlón|Heptatlón|Heptathlon|Heptatló|Tetrathlón|Tetrathlon|Tetratló|Hexathlón|Hexathlon|Hexatló)\s+(?:VET\.?|Vet\.?\s+)?(?:Hombres\.?|Mujeres\.?|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)\s+(?:PC\s+)?(?:Master\s+)?(?:M\d+|F\d+|U\d+)',
    # Youth/age category combined: "Pentathlon S16 CAD.Mujeres PC-Aire libre", "Heptathlon JUV Hombres PC-AL"
    r'(?:Pentathlón|Pentatlón|Pentathlon|Pentatló|Heptathlón|Heptatlón|Heptathlon|Heptatló|Tetrathlón|Tetrathlon|Tetratló|Hexathlón|Hexathlon|Hexatló)\s*(?:S\d+\s+)?(?:JUV\.?|CAD\.?|INF\.?\s*)?\s*(?:Sub\d+\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)\s*(?:PC\s*[-.]?\s*(?:Aire\s+libre|AL|aire\s+libre))?',
    # Tetrathlón Cataluña infantil
    r'(?:Tetrathlón|Tetrathlon)\s+Cataluña\s+infantil',
    # Generic patterns that cover any event name format (Spanish + Catalan)
    # Track events with abbreviated gender: "60m S10M", "200m AbsF", "300m S16M", "400m S10F"
    # Format: distance + (S##|Abs) + M/F (Masculí/Femení abbreviated)
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:S\d+|Abs)\s*[MF]\s*(?:AL|aire\s+libre)?',
    # Track events: 60m, 100m, 300m, 600m, 1.000m, 3.000m, etc. (with or without space, with optional altaveu "mt")
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:Sub\d+\s+)?(?:Obst\.?\s+)?(?:Marcha\s+)?(?:Marxa\s+)?(?:Hombres|Mujeres|Mixto|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)',
    # Simple track with abbreviated gender: "100m M", "200m F", "400m M", "800m F"
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:Sub\d+\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)?\s+\b[MFM]\b',
    # Field/jump/height events (Spanish + Catalan)
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Disc|Martello|Martell|Martillo|Martell|\b(?:Peso|Pes)\b|Jabalina|Javelina|Dard)\s*(?:\(.*?\))?\s*(?:Sub\d+(?:-\d+)?\s+)?(?:Hombres|Mujeres|Mixto|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino|M|F)',
    # Relay events: 4x100m, 4x400m, 4x300m, Relleu 4x300, Relleus 4x200
    r'(?:4x\d+\s*m|Relleu[s]?\s+4x\d+)',
    # Age category events
    r'(?:\bLongitud\b|\bLlargada\b|\bAltura\b|\bAlçada\b|\bPeso\b|Jabalina|Dard|Disco|Martillo|Triple\s+Salto|Triple\s+salt)\s+(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s+U\d+[MF]',
    r'\d+\s*m\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s+U\d+[MF]',
    r'\d+\s*m\s*(?:tanques\s+)?(?:vallas\s+)?(?:Obst\.?\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s+U\d+[MF]',
    # Weighted events
    r'(?:Peso|Pes)\s+\(\d+k?\)\s*(?:Hombres|Mujeres)',
    r'Jabalina\s+\(\d+g\)\s*(?:Hombres|Mujeres)',
    r'Dard\s+\(\d+g\)\s*(?:Hombres|Mujeres)',
    # Youth/age category events: "60m S12 Mujeres AL", "60m vallas (0,762) S14 INF. Mujeres AL"
    # Format: event_name + S\d+ or JUV/CAD/INF + gender + optional AL/aire libre
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:S\d+\s+)?(?:JUV\.?|CAD\.?|INF\.?\s*)?\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s+(?:S\d+|JUV\.?|CAD\.?|INF\.?)\s*(?:AL|aire\s+libre)?',
    # Field/jump/height with age category: "Peso (4kg) S16 Hombres AL", "Altura S14 Mujeres AL"
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|\bPeso\b|Jabalina|Dard)\s*(?:\(.*?\))?\s*(?:S\d+\s+)?(?:JUV\.?|CAD\.?|INF\.?\s*)?\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s+(?:S\d+|JUV\.?|CAD\.?|INF\.?)\s*(?:AL|aire\s+libre)?',
    # Simple age category: "60m S18 Hombres AL", "Altura S14 Mujeres AL" (S## between event and gender)
    r'(?:\d{1,3}(?:\.\d{3})?\s*m|\d+\s*m)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:S\d+)\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s*(?:AL|aire\s+libre)?',
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|\bPeso\b|Jabalina|Dard)\s*(?:\(.*?\))?\s*(?:S\d+)\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)\s*(?:AL|aire\s+libre)?',
    r'(?:Peso|Pes)\s+\(\d+k?\)\s*(?:S\d+)\s*(?:Hombres|Mujeres|Masculí|Femení)\s*(?:AL|aire\s+libre)?',
    r'Jabalina\s+\(\d+g\)\s*(?:S\d+)\s*(?:Hombres|Mujeres|Masculí|Femení)\s*(?:AL|aire\s+libre)?',
    r'Dard\s+\(\d+g\)\s*(?:S\d+)\s*(?:Hombres|Mujeres|Masculí|Femení)\s*(?:AL|aire\s+libre)?',
    # Vallas with height spec and age category: "60m vallas (0,762) S14 INF. Mujeres AL"
    r'(?:\d{1,3}\s*m\s+vallas\s+\(.*?\)\s+S\d+\s+(?:JUV\.?|CAD\.?|INF\.?\s*)?\s*(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins))',
    # Master events: "Peso VET.Mujeres. PC Master F60", "Peso Vet. Hombres. PC Master M40"
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|\b(?:Peso|Pes)\b|Jabalina|Dard)\s+VET\.?\s*(?:Mujeres\.?|Hombres\.?)\s*PC\s+Master\s+(?:M\d+|F\d+)',
    # Marcha events with km: "5 km Marcha sub-16 Hombres", "10 km Marcha sub-20 Mujeres"
    r'\d+\s+km\s+(?:Marcha|Marxa)\s+(?:sub-\d+\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)',
    # Maratón Marcha: "Maratón Marcha Hombres", "Maratón Marcha Mujeres Master"
    r'Marat[óo]n\s+(?:Marcha|Marxa)\s+(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)?\s*(?:Master\s*(?:M\d+|F\d+))?',
    # Road marathon events: "Maratón Hombres Absoluto y Clubes", "Maratón Hombres M35", "Maratón Mujeres Absoluto", "Maratón Mujeres F35"
    r'Marat[óo]n\s+(?:Hombres|Mujeres|Masculí)\s+(?:Absoluto\s+y\s+Clubes|Absoluto|M\d+|F?\d+)',
    r'Marat[óo]n\s+Master\s+(?:Hombres|Mujeres|Masculí)\s+(?:Clubes|M\d+|F\d+)',
    # U16/U18 category events with plural gender: "60m U18 Masculins PC", "Llargada U18 Masculins PC", "Alçada U16-U18 Femenins PC"
    r'(?:\d{1,3}(?:\.\d{3})?\s*m|\d+\s*m)\s*(?:tanques\s+)?(?:vallas\s+)?(?:\(.*?\))?\s*(?:U\d+(?:-U\d+)?)\s*(?:Hombres|Mujeres|Masculins|Mascuins|Femenins|masculins|femenins)',
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|\b(?:Peso|Pes)\b|Jabalina|Dard)\s*(?:\(.*?\))?\s*(?:U\d+(?:-U\d+)?)\s*(?:Hombres|Mujeres|Masculins|Mascuins|Femenins|masculins|femenins)',
    # U-category events with single letter gender: "400m U10M", "1.000m U14M", "Altura U10F"
    r'(?:\d{1,3}(?:\.\d{3})?\s*m|\d+\s*m)\s*(?:tanques\s+)?(?:vallas\s+)?\(.*?\)?\s*(?:U\d+(?:-\d+)?)\s*[MF]',
    r'(?:\bAltura\b|\bAlçada\b|Pértiga|Pertiga|Perxa|Longitud|Llargada|Triple\s+Salto|Triple\s+salt|Disco|Martillo|\b(?:Peso|Pes)\b|Jabalina|Dard)\s*(?:\(.*?\))?\s*(?:U\d+(?:-\d+)?)\s*[MF]',
    # Full word "metres" track events: "100 metres llisos mascuins", "300 metres tanques masculins",
    # "3000 metres llisos femenins", "1500 metres obstacles femenins", "60 metres llisos femenins"
    # These use "metres" instead of "m" and include "llisos", "tanques", "obstacles", "marxa", "marxa"
    r'\d{1,3}(?:\.\d{3})?\s*metres\s+(?:llisos|tanques|vallas|obstacles|marxa|marxa)\s+(?:masculins|Mascuins|femenins|femenina|masculina|Hombres|Mujeres|Masculí|Femení)',
    # RFEA format: "60m MASC. PC", "300m FEM. PC", "Alçada MASC. PC", etc.
    # MASC = Masculí/Masculino, FEM = Femení/Femenino
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s+(?:MASC\.?|FEM\.?)\s+PC',
    r'(?:\d{1,3}(?:\.\d{3})?\s*m(t)?|\d+\s*m(t)?)\s+(?:MASC\.?|FEM\.?)\s+AL',
    r'(?:Alçada|Altura|Perxa|Pértiga|Llargada|Longitud|Triple\s+Salto|Triple\s+salt|Disco|Martello|Martell|Martillo|Pes|Peso|Dard|Jabalina|Javelina)\s+(?:MASC\.?|FEM\.?)\s+PC',
    r'(?:Alçada|Altura|Perxa|Pértiga|Llargada|Longitud|Triple\s+Salto|Triple\s+salt|Disco|Martello|Martell|Martillo|Pes|Peso|Dard|Jabalina|Javelina)\s+(?:MASC\.?|FEM\.?)\s+AL',
    r'\d{1,3}(?:\.\d{3})?\s*metres\s+(?:llisos|tanques|vallas|obstacles|marxa|marxa)\s+(?:Sub\d+\s+)?(?:masculins|Mascuins|femenins|femenina|masculina|Hombres|Mujeres|Masculí|Femení)',
]

TRACK_PATTERNS = [
    # Full word "metres" variants (new PDF format)
    r'\d{1,3}(?:\.\d{3})?\s*metres\s+(?:llisos|tanques|vallas|obstacles)\s+(?:masculins|Mascuins|femenins|femeni|masculi)',
    r'\d{1,3}(?:\.\d{3})?\s*metres\s+(?:llisos|tanques|vallas|obstacles)\s+(?:masculins|Mascuins|femenins|femeni|masculi)',
    # Abbreviated "m" variants (legacy PDF format)
    r'(?:^|[\s(])\d{1,3}(?:\.\d{3})?\s*m(t)?\s*(?:tanques|vallas)?\s*(?:Obst\.?)?\s*(?:\(.*?\))?\s*(?:Marxa\s+)?(?:Hombres|Mujeres|Mixto|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina)',
    r'\d{1,3}\s*m(t)?\s+(?:tanques|vallas|Marxa|Obst\.?)\s+(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)',
    r'\d{1,3}\s*m(t)?\s+(?:Marxa\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins)',
    # Abbreviated gender: "100m Abs M", "200m Abs F", "400m tanques Abs M", "600m Sub14-16 M"
    r'\d{1,3}(?:\.\d{3})?\s*m(t)?\s*(?:tanques|vallas)?\s+(?:Abs|Sub\d+[-\d]*)\s+[MFHM]',
    # Speed control style: "60m S10M", "400m S10F", "200m AbsF", "300m S16M"
    r'\d{1,3}(?:\.\d{3})?\s*m(t)?\s*(?:tanques|vallas)?\s*(?:Abs(?:M|F|Mascuins|Femenins)?|S\d+[MFHM])',
    # Popular/road events: "5.000m Popular"
    r'\d{1,3}(?:\.\d{3})?\s*m(t)?\s+(?:Popular|Populars?)\s*(?:Hombres|Mujeres|Masculí|Femení)?',
    # km events: "10km", "21.1km"
    r'\d+\.?\d*\s*km\s*(?:Hombres|Mujeres|Masculí|Femení|Abs|M|F)?',
]

MARCHA_PATTERNS = [
    r'\d+\.?\d*\s*(?:m|metres)\s+(?:Marcha|Marxa)',
    r'\d+\s+km\s+(?:Marcha|Marxa)',
    r'Marat[óo]n\s+(?:Marcha|Marxa)',
]

JUMP_PATTERNS = [
    r'Triple\s+(?:Salto|salt)',
    r'\b(?:Longitud|Llargada)\b',
]

HEIGHT_PATTERNS = [
    r'\b(?:Altura|Alçada)\b',
    r'\b(?:Pértiga|Pertiga|Perxa)\b',
]

FIELD_PATTERNS = [
    r'\bDisco\b|\bDisc\b',
    r'\b(?:Martillo|Martell)\b',
    r'\b(?:Peso|Pes)\b',
    r'\b(?:Jabalina|Javelina|Dard)\b',
]

RELAY_PATTERNS = [
    r'4x\d+\s*m',
    r'4x\d+\s+(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)',
    r'Relleu[s]?\s+4x\d+',
]

MARATHON_PATTERNS = [
    r'Marat[óo]n?[\s-]+(?:Master\s+)?(?:Hombres|Mujeres|Masculí|Femení)',
    # Age category marathons: "Marató Masculí M35", "Marató Femení F35", "Marató Femení F40"
    r'Marat[óo]n?[\s-]+(?:Masculí|Femení)\s+[MF]\d*',
    # Master marathons: "Marató Master"
    r'Marat[óo]n?[\s-]+Master',
]


COMBINED_PATTERNS = [
    # Combined events: "Pentathlon PC Master M60" or "Pentathlón VET.Mujeres. PC Master F55"
    # Must start with Pentathlon/Pentathlón, NOT be a sub-event like "60m vallas Hombres Pentatlón Master M60"
    r'^(?:Pentathlón|Pentatlón|Pentathlon|Pentatló|Heptathlón|Heptatlón|Heptathlon|Heptatló|Tetrathlón|Tetrathlon|Tetratló|Hexathlón|Hexathlon|Hexatló|Triatlon|Triatlón)\s+(?:VET\.?|Vet\.?\s+)?(?:Hombres\.?|Mujeres\.?|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)\s+(?:PC\s+)?(?:Master\s+)?(?:M\d+|F\d+|U\d+)',
    # Youth/age category combined: "Pentathlon S16 CAD.Mujeres PC-Aire libre", "Heptathlon JUV Hombres PC-AL"
    r'^(?:Pentathlón|Pentatlón|Pentathlon|Pentatló|Heptathlón|Heptatlón|Heptathlon|Heptatló|Tetrathlón|Tetrathlon|Tetratló|Hexathlón|Hexathlon|Hexatló|Triatlon|Triatlón)\s*(?:S\d+\s+)?(?:JUV\.?|CAD\.?|INF\.?\s*)?\s*(?:Sub\d+\s+)?(?:Hombres|Mujeres|Masculí|Femení|masculins|Mascuins|femenins|masculina|femenina|masculino|femenino)\s*(?:PC\s*[-.]?\s*(?:Aire\s+libre|AL|aire\s+libre))?',
    # Youth combined with S-class (e.g., "Triatlon S12M", "Tetrathlón S14F", "Triatlón S12F")
    r'^(?:Pentathlón|Pentatlón|Pentathlon|Pentatló|Heptathlón|Heptatlón|Heptathlon|Heptatló|Tetrathlón|Tetrathlon|Tetratló|Hexathlón|Hexathlon|Hexatló|Triatlon|Triatlón)\s+S\d+[MFHM]',
    # Tetrathlón Cataluña infantil
    r'^(?:Tetrathlón|Tetrathlon)\s+Cataluña\s+infantil',
]

def classify_event(event_name):
    if not event_name:
        return "unknown"
    # Check combined events first (before other patterns that might match parts)
    for p in COMBINED_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "combined"
    # Check relay first (most specific pattern)
    for p in RELAY_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "relay"
    # Check marathon (road events) - treat as track for result extraction
    for p in MARATHON_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "road"
    # Check marcha
    for p in MARCHA_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "marcha"
    # Check height (before field to avoid "Altura" being confused)
    for p in HEIGHT_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "height"
    # Check field events (before jump, since Peso/Jabalina are field)
    for p in FIELD_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "field"
    # Check jump events
    for p in JUMP_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "jump"
    # Track events - anything with meters that isn't already classified
    for p in TRACK_PATTERNS:
        if re.search(p, event_name, re.IGNORECASE):
            return "track"
    return "unknown"


def is_catt_line(line):
    return bool(re.search(r'\bCATT\b|\bCA\s+Tarragona\b', line))


def is_club_line(line):
    club_patterns = [
        r'\bCA\s+Granollers\b',
        r'\bGEiE\s+Giron[ía]\b',
        r'\bCA\s+Vic\b',
        r'\bJA\s+Sabadell\b',
        r'\bCAVB\b',
        r'\bCAGB\b',
        r'\bBCNB\b',
        r'\bUABB\b',
        r'\bBarcelona\s+At\.?\b',
        r'\bUA\s+Terrassa\b',
        r'\bUATB\b',
        r'\bUA\s+Barber[á]\b',
    ]
    for p in club_patterns:
        if re.search(p, line):
            return True
    return False


def is_name_line(line):
    # Exclude preliminary result lines (RCAT, RCAM, etc.) that have event dates at the end
    # These lines have format: "RCAT  J.CASTELLA-N.CAVERO-M.CODINA-M.PEULA 2:33.39  Sabadell  13/02/2022"
    if re.match(r'^\s*RC[A-Z]+\s', line):
        return False
    return bool(re.search(r'\d{1,2}/\d{1,2}/\d{4}', line))


def extract_name_from_line(line):
    line = line.strip()
    # Strip leading position + dorsal + optional (t)/(e) prefix (RFEA format)
    line = re.sub(r'^\s*\d+\s+\d+\s*\(?[te]?\)?\s*', '', line)
    line = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', line)
    line = re.sub(r'\s+RT\s+\S+', '', line)
    line = re.sub(r'\s+DQ\s*$', '', line)
    line = re.sub(r'\s+RT\s*$', '', line)
    line = re.sub(r'\s*[~>]+\w*\s*$', '', line)
    line = re.sub(r'\s*[~>]\s*$', '', line)
    line = re.sub(r'\s+\d+:\d{2}\.\d{2}(?=\s|$)', ' ', line)
    line = re.sub(r'\s+\d+\.\d{2}(?=\s|$)', ' ', line)
    line = re.sub(r'\s+[Xxr]+(?=\s|$)', '', line)
    # Remove height jump markers: -, O, XO, XXO, XXX (standalone tokens)
    line = re.sub(r'\s+(?:[-]+|[OXox]+)(?=\s|$)', '', line)
    line = re.sub(r'\s+MMT\s*$', '', line)
    line = re.sub(r'\s+MMP\s*$', '', line)
    line = re.sub(r'\s+\d+\s*$', '', line)
    # Remove percentage values (e.g., "70,41%", "71,69%") that appear next to names in combined events
    line = re.sub(r'\s+\d+[,\.]\d+%\s*', ' ', line)
    # Remove truncated time results (e.g., "3:07.…") that don't match full time pattern
    line = re.sub(r'\s+\d{1,2}:\d{2}[.\u2026]+\s*', ' ', line)
    # Remove trailing time values with 3 decimal places (e.g., "11.396" from PDF layout)
    line = re.sub(r'\s+\d+\.\d{3}(?=\s|$)', ' ', line)
    # Remove parenthetical time splits (e.g., " (.400)", " (.401)")
    line = re.sub(r'\s+\(\.\d{3}\)\s*', ' ', line)
    # Remove RFEA category codes at end: CF, CM, SM, JM, AS, AI, AM, SV, JV, AJ, etc.
    line = re.sub(r'\s+(?:CF|CM|SM|JM|AS|AI|AM|SV|JV|AJ|AM\d+|S\d+|C\d+|I\d+|B\d+|U\d+|PF|PM|PF|MF|MA)\s*$', '', line)
    cleaned = ' '.join(line.split())
    return cleaned


def extract_license(lines, start_idx, end_idx):
    """Extract license from lines (already a list)."""
    for j in range(start_idx, min(end_idx, len(lines))):
        fwd_line = lines[j].strip()
        lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', fwd_line)
        if lic_match:
            lic = lic_match.group(1).strip()
            lic = re.sub(r'[\.\-]+\s*$', '', lic)
            if lic:
                return lic
    return ""


def extract_position(line):
    pos_match = re.match(r'\s*(\d+)\s+\d+\s+[A-Z]{2,}\b', line)
    if pos_match:
        return int(pos_match.group(1))
    pos_match2 = re.match(r'\s*(\d+)\s+\d+\s+CA\s+Tarragona', line)
    if pos_match2:
        return int(pos_match2.group(1))
    pos_match3 = re.match(r'\s*(\d+)\s+\d+\s+UABB', line)
    if pos_match3:
        return int(pos_match3.group(1))
    pos_match4 = re.match(r'\s*(\d+)\s+\d+\s+UATB', line)
    if pos_match4:
        return int(pos_match4.group(1))
    pos_match5 = re.match(r'\s*(\d+)\s+\d+\s+CAGB', line)
    if pos_match5:
        return int(pos_match5.group(1))
    pos_match6 = re.match(r'\s*(\d+)\s+\d+\s+CAVB', line)
    if pos_match6:
        return int(pos_match6.group(1))
    pos_match7 = re.match(r'\s*(\d+)\s+\d+\s+GEEG', line)
    if pos_match7:
        return int(pos_match7.group(1))
    pos_match8 = re.match(r'\s*(\d+)\s+\d+\s+JASB', line)
    if pos_match8:
        return int(pos_match8.group(1))
    return None


# ============================================================================
# Result extraction per event type
# ============================================================================

def extract_track_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank', 'Viento']
        if any(label in fwd_line for label in skip_labels):
            continue

        time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', fwd_line)
        if time_match:
            return time_match.group(1)

        for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', fwd_line):
            val = float(num_match.group(1))
            if val > 5.0 and val < 60.0:
                return num_match.group(1)
        for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{3})(?![\d.])', fwd_line):
            val = float(num_match.group(1))
            if val > 5.0 and val < 60.0:
                return num_match.group(1)[:5]

    return ""


def extract_marcha_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank', 'Viento', 'Pasos']
        if any(label in fwd_line for label in skip_labels):
            continue

        # Try HH:MM:SS format first (e.g., 4:12:44)
        time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})(?!\d)', fwd_line)
        if time_match:
            return time_match.group(1)

        # Try HH:MM.ss format (e.g., 23:09.2)
        time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', fwd_line)
        if time_match:
            return time_match.group(1)

        # Try HH:MM format (e.g., 26:29) - only if not followed by more digits
        time_match = re.search(r'(\d{1,2}:\d{2})(?!\d|:\d)', fwd_line)
        if time_match:
            return time_match.group(1)

    return ""


def extract_jump_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        nums = re.findall(r'(\d+\.\d{2})', fwd_line)
        if nums:
            for num in reversed(nums):
                val = float(num)
                if val >= 3.0 and val <= 20.0:
                    return num

    return ""


def extract_height_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 15, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        # Try MMT/MMP marker format first
        height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', fwd_line)
        if height_match:
            val = height_match.group(1)
            num_val = float(val)
            if num_val >= 1.0 and num_val <= 7.0:
                return val

        # Conersys format: height result at end of line, before percentage
        # Pattern: "1.60       10 78,90%" - find the last height value before percentage
        pct_match = re.search(r'(\d+[,\.]\d+)%', fwd_line)
        if pct_match:
            # Look for height values before the percentage
            before_pct = fwd_line[:pct_match.start()]
            nums = re.findall(r'(\d+\.\d{2})', before_pct)
            for num in reversed(nums):
                val = float(num)
                if val >= 1.0 and val <= 7.0:
                    return num

    return ""


def extract_field_result(lines, catt_idx, sec_end):
    for j in range(catt_idx, min(catt_idx + 20, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                        'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                        'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        nums = re.findall(r'(\d+\.\d{2})', fwd_line)
        if nums:
            for num in reversed(nums):
                val = float(num)
                if val >= 3.0 and val <= 80.0:
                    return num

    return ""


def extract_jump_wind(lines, name_line_idx, sec_end):
    """Extract wind for the best mark in a jump event (Longitud, Triple Salto).
    
    The name line contains attempt results, and the club line below contains
    wind values per attempt. We match winds to attempts and return the wind
    for the best valid mark.
    """
    name_line = lines[name_line_idx]
    
    # Extract attempts from name line: list of (value, is_valid) where value is string or 'X'/'r'/'-'
    attempt_values = []
    # Find numeric values and special markers between name/birthdate and final result
    name_stripped = name_line.strip()
    bd_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', name_stripped)
    if not bd_match:
        return None
    
    after_birth = name_stripped[bd_match.end():]
    
    # Split into tokens and find attempt values
    # Format: "11.77     11.09        r                                    11.77 MMP"
    tokens = after_birth.split()
    attempts = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token in ('X', 'r', '-', 'X', 'x'):
            attempts.append(token)
        elif re.match(r'^\d+\.\d{2}$', token):
            val = float(token)
            # Jump values are between 3.0 and 20.0
            if 3.0 <= val <= 20.0:
                attempts.append(token)
            elif val > 20.0:
                # This is likely the overall result at the end, skip
                break
    
    if not attempts:
        return None
    
    # Find the best valid mark among attempts
    valid_attempts = [(i, a) for i, a in enumerate(attempts) if a not in ('X', 'r', '-', 'x', '')]
    if not valid_attempts:
        return None
    
    # Best mark is the max valid attempt
    best_idx, best_val = max(valid_attempts, key=lambda x: float(x[1]))
    
    # Now find wind values from the club line (below position line)
    # Look for the club line that has wind values
    wind_values = []
    for j in range(name_line_idx + 1, min(name_line_idx + 10, sec_end)):
        fwd = lines[j].strip()
        if not fwd:
            continue
        # Skip lines that are just position numbers
        if re.match(r'^\s*\d+\s+\d+\s+', fwd) and not re.search(r'CA\s+Tarragona|Club|nombre', fwd, re.IGNORECASE):
            continue
        # Skip pure wind lines (single wind value centered)
        if re.match(r'^\s*[+-]?\d+\.\d\s*$', fwd):
            continue
        # Look for wind values on club lines
        # Club line pattern: "CA Tarragona  CL11323  -0.5  -0.4"
        if re.search(r'CA\s+Tarragona|Club', fwd, re.IGNORECASE):
            # Extract wind values (signed like -2.6 or unsigned like 0.3)
            wind_matches = re.findall(r'([+-]?\d+\.\d{1,2})', fwd)
            if wind_matches:
                wind_values = [w for w in wind_matches if abs(float(w)) < 20]
                break
    
    if not wind_values:
        return None
    
    # Match wind to best attempt
    # Wind values are aligned with attempts in order by position
    # Each wind value corresponds to the attempt at the same index
    best_attempt_pos = best_idx
    
    if best_attempt_pos < len(wind_values):
        return wind_values[best_attempt_pos]
    
    # If we don't have enough winds, try to find the wind from the name-line wind line
    # (the single wind value shown on the position line)
    for j in range(name_line_idx + 1, min(name_line_idx + 5, sec_end)):
        fwd = lines[j].strip()
        if not fwd:
            continue
        # Look for a single wind value (like "-1.2" or "-0.4")
        wind_match = re.match(r'^\s*([+-]\d+\.\d{1,2})\s*$', fwd)
        if wind_match:
            return wind_match.group(1)
    
    return None


def extract_result_from_name_line(lines, name_line_idx, sec_end, event_type):
    """Extract result from the name line itself (for jumps and field events)."""
    # Check the name line and next few lines
    for j in range(name_line_idx, min(name_line_idx + 3, sec_end)):
        fwd_line = lines[j].strip()
        if not fwd_line:
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in fwd_line for label in skip_labels):
            continue

        if event_type == "jump":
            nums = re.findall(r'(\d+\.\d{2})', fwd_line)
            if nums:
                best = None
                best_val = 0
                for num in nums:
                    val = float(num)
                    if val >= 1.5 and val <= 20.0 and val > best_val:
                        best_val = val
                        best = num
                if best:
                    return best
        elif event_type == "field":
            nums = re.findall(r'(\d+\.\d{2})', fwd_line)
            if nums:
                best = None
                best_val = 0
                for num in nums:
                    val = float(num)
                    if val >= 1.5 and val <= 80.0 and val > best_val:
                        best_val = val
                        best = num
                if best:
                    return best

    return ""


def extract_all_attempts_from_name_line(lines, name_line_idx, sec_end, event_type, min_val, max_val):
    """Extract all valid attempts from the name line for field/jump events.
    
    Returns (best_mark, attempts_list) where attempts_list is a list of dicts:
    [{"attempt": 1, "value": "5.90", "wind": "+0.6"}, ...]
    
    Only includes valid numeric values. Skips X, r, -, 0.0, and the Resultado column.
    """
    name_line_raw = lines[name_line_idx]  # NOT stripped — we need char positions
    name_line = name_line_raw.strip()
    bd_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', name_line)
    if not bd_match:
        return "", []
    
    # Find DOB position in the raw line for correct char offset
    bd_match_raw = re.search(r'\d{1,2}/\d{1,2}/\d{4}', name_line_raw)
    if not bd_match_raw:
        return "", []
    
    after_birth_str = name_line[bd_match.end():].strip()
    
    # Tokenize: find all values and markers, tracking character positions for wind alignment
    # We use finditer on the original (non-stripped) name line to get char positions
    attempt_regions = []  # list of (start, end, token) for tokens after DOB
    for m in re.finditer(r'\S+', name_line_raw):
        tok = m.group()
        if m.start() < bd_match_raw.end():
            continue  # before DOB, skip
        # Check if this is an attempt value or marker
        if tok in ('X', 'x', 'r', '-', 'MMT', 'MMP', '=MMT', '=MMP'):
            attempt_regions.append((m.start(), m.end(), tok))
        elif re.match(r'^\d+\.\d{2}$', tok):
            val = float(tok)
            if min_val <= val <= max_val:
                attempt_regions.append((m.start(), m.end(), tok))
    
    # Build list of valid numeric attempts (excluding Resultado column at end)
    all_attempt_tokens = [(s, e, t) for s, e, t in attempt_regions]
    valid_attempt_tokens = [(s, e, t) for s, e, t in attempt_regions if re.match(r'^\d+\.\d{2}$', t)]
    
    if not valid_attempt_tokens:
        return "", []
    
    # The last numeric value is usually the "Resultado" (best mark repeated)
    best_mark = max((t for _, _, t in valid_attempt_tokens), key=lambda x: float(x))
    if valid_attempt_tokens[-1][2] == best_mark and len(valid_attempt_tokens) > 1:
        valid_attempt_tokens = valid_attempt_tokens[:-1]
    
    if not valid_attempt_tokens:
        return "", []
    
    # Collect wind values from club line below, with character positions
    wind_positions = []  # list of (start, end, value)
    for j in range(name_line_idx + 1, min(name_line_idx + 10, sec_end)):
        fwd_raw = lines[j]  # NOT stripped — we need char positions
        if not fwd_raw.strip():
            continue
        if re.search(r'CA\s+Tarragona|Club', fwd_raw, re.IGNORECASE):
            for wm in re.finditer(r'([+-]?\d+\.\d{1,2})', fwd_raw):
                val = wm.group(1)
                if abs(float(val)) < 20:
                    wind_positions.append((wm.start(), wm.end(), val))
            break
    
    # Match wind values to attempt tokens by proximity of character positions
    result_attempts = []
    for s, e, val in valid_attempt_tokens:
        wind = None
        if event_type == "jump" and wind_positions:
            center = (s + e) / 2
            closest = None
            closest_dist = 999
            for ws, we, wv in wind_positions:
                wcenter = (ws + we) / 2
                dist = abs(wcenter - center)
                if dist < closest_dist and dist < 15:
                    closest_dist = dist
                    closest = wv
            if closest is not None:
                wind = closest
        result_attempts.append({
            "attempt": len(result_attempts) + 1,
            "value": val,
            "wind": wind,
        })
    
    return best_mark, result_attempts


# ============================================================================
# Section parsing
# ============================================================================

def find_section_boundaries(lines):
    """Find event section boundaries.
    
    Event sections start with a page header containing:
    - Date line (DD/MM/YYYY)
    - Event name (right-aligned)
    - Time (left-aligned)
    - "Final" or similar
    
    Also detects schedule lines with series: "10:00   60 m Mujeres  Eliminatoria 1/4"
    """
    section_starts = []
    seen_events = set()
    sub_event_labels = {'Eliminatoria', 'Semifinal', 'Final', 'Ronda', 'Heats', 'Heat'}
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        # Skip lines that are just "Final" or "HORARIO" etc
        if stripped in ('Final', 'HORARIO', 'Hora', 'Prueba', 'Ronda', 'SESIO', 'SESION'):
            continue
        
        # Skip preliminary result lines (RCAT, RCAM, etc.) that have event dates at the end
        # These lines have format: "RCAT  J.CASTELLA-N.CAVERO 2:33.39  Sabadell  13/02/2022"
        if re.match(r'^\s*RC[A-Z]+\s', stripped):
            continue
        
        event_name = ""
        is_schedule = False
        
        # Check if this is a schedule line: "HH:MM   EventName  Series"
        sched_match = re.match(r'^\d{2}:\d{2}\s+(.+)$', stripped)
        if sched_match:
            rest = sched_match.group(1).strip()
            # Check if rest contains an event pattern
            is_event = False
            for pattern in EVENT_PATTERNS:
                if re.search(pattern, rest, re.IGNORECASE):
                    is_event = True
                    break
            if not is_event:
                for pattern in RELAY_PATTERNS:
                    if re.search(pattern, rest, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in COMBINED_PATTERNS:
                    if re.search(pattern, rest, re.IGNORECASE):
                        is_event = True
                        break
            if is_event:
                # Schedule lines (HH:MM format) are NOT actual result sections.
                # They're just the timetable. Skip them entirely.
                # The actual result sections are page headers with date lines.
                is_schedule = True
        
        if is_schedule:
            continue
        
        if not event_name:
            # Check if this line matches an event pattern (page header format)
            is_event = False
            for pattern in EVENT_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
            if not is_event:
                for pattern in RELAY_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in FIELD_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in JUMP_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in HEIGHT_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in MARCHA_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in MARATHON_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            if not is_event:
                for pattern in COMBINED_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        is_event = True
                        break
            
            if not is_event:
                # Additional check: for age-category events like "60m S10M", "400m S10F",
                # the pattern might not match the main EVENT_PATTERNS. Check with a more
                # permissive pattern for speed control events.
                if not re.search(r'\d+\s*m\s+S\d+[MF]', stripped, re.IGNORECASE):
                    continue
            
            # Must be preceded by a date line (page header event start)
            # Look back up to 10 lines for a date
            is_page_header_event = False
            for j in range(i - 1, max(i - 10, 0), -1):
                prev = lines[j].strip()
                if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', prev):
                    is_page_header_event = True
                    break
                if 'Página' in prev or 'Gestión' in prev:
                    break  # Hit page footer, not a page header
                # If we hit a non-empty line that's not a date, stop looking
                if prev and not re.match(r'^\d{1,2}:\d{2}', prev):
                    break
            
            # Fallback: if no date found, check if this is a known event pattern
            # that appears after a blank line (page break) - common in speed control PDFs
            if not is_page_header_event:
                # Look for blank line followed by event name pattern (page break indicator)
                for j in range(i - 1, max(i - 5, 0), -1):
                    prev = lines[j].strip()
                    if prev == '':
                        # Check if the line before the blank is a page footer or separator
                        for k in range(j - 1, max(j - 4, 0), -1):
                            footer_line = lines[k].strip()
                            if 'Página' in footer_line or 'Gestión' in footer_line or '---' in footer_line or '===' in footer_line:
                                is_page_header_event = True
                                break
                            if footer_line and '---' not in footer_line and '===' not in footer_line:
                                break
                        break
                    if 'Página' in prev or 'Gestión' in prev:
                        break
            
            if not is_page_header_event:
                continue
            
            event_name = stripped
        
        # Deduplicate: skip if we've already seen this event name
        # BUT for relay events, each heat/series is a separate section
        # so we don't deduplicate relays
        is_relay = bool(re.search(r'4x\d+|Relleu\s+4x', event_name, re.IGNORECASE))
        if not is_relay and event_name in seen_events:
            continue
        seen_events.add(event_name)
        
        section_starts.append((i, event_name))
    
    # Fallback for RFEA format: sections without date lines before event names
    # RFEA format has event names like "60m MASC. PC" or "300m FEM. PC" on their own line
    # without a preceding date line. Check for these throughout the document.
    # NOTE: In RFEA format, the same event name can appear multiple times (Final A, B, C)
    # so we DON'T deduplicate here — each occurrence is a separate section.
    # Only add RFEA sections that weren't already captured by the main detection
    rfea_added = set()
    for i in range(0, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        # Check if this is an RFEA event header (e.g., "60m MASC. PC")
        is_event = False
        for pattern in EVENT_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                is_event = True
                break
        if not is_event:
            for pattern in RELAY_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        if not is_event:
            for pattern in FIELD_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        if not is_event:
            for pattern in JUMP_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        if not is_event:
            for pattern in HEIGHT_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        if not is_event:
            for pattern in MARCHA_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        if not is_event:
            for pattern in COMBINED_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    is_event = True
                    break
        
        if is_event:
            # Check if this is a header/title line (not an event section)
            skip_titles = ['ACTA', 'CAMPEONATO', 'Campionat', 'Campeonato',
                           'Jornada', 'Control', 'Trofeu', 'Festival']
            is_title = any(t in stripped for t in skip_titles)
            if not is_title and i not in rfea_added:
                # Check if this line is already in section_starts
                already_added = any(idx == i for idx, _ in section_starts)
                if not already_added:
                    section_starts.append((i, stripped))
                    rfea_added.add(i)
    
    section_starts.append((len(lines), ""))
    return section_starts


def find_sumario_sections(lines):
    """Find SUMARIO sections in the PDF.
    
    SUMARIO sections contain summary results for track events with series.
    Format:
      [event name line] [sub-event like Ronda 1/Semifinal/Final] [blank] SUMARIO
      We look backwards, skipping sub-event labels, to find the real event name.
    """
    sumarios = []
    sub_event_labels = {'Ronda', 'Serie', 'Semifinal', 'Final', 'Eliminatoria',
                        'Combinadas', 'Heats', 'Heat', 'Final A', 'Final B',
                        'Final 1', 'Final 2', 'Final 3'}
    
    for i, line in enumerate(lines):
        if 'SUMARIO' in line.strip():
            event_name = ""
            for j in range(i - 1, max(i - 20, 0), -1):
                prev = lines[j].strip()
                if not prev:
                    continue
                # Skip lines that are just sub-event labels (Ronda 1, Semifinal, Final, etc.)
                # These are short lines that don't match any EVENT_PATTERN
                if len(prev) < 10 and not re.search(r'\d', prev):
                    continue
                # Skip pure sub-event label lines
                is_sub_label = False
                for label in sub_event_labels:
                    if re.match(rf'^{label}[\s\d/]*$', prev, re.IGNORECASE):
                        is_sub_label = True
                        break
                if is_sub_label:
                    continue
                # Check if this matches an event pattern
                for pattern in EVENT_PATTERNS:
                    if re.search(pattern, prev, re.IGNORECASE):
                        event_name = prev.strip()
                        break
                if event_name:
                    break
            
            if not event_name:
                continue
            
            sumarios.append((i, event_name))
    
    return sumarios


def parse_sumario_section(lines, sumario_idx, event_name, sec_end, competicio, data_comp):
    """Parse a SUMARIO section for track events.
    
    Format per athlete (individual events):
      [name] [birthdate]
      [rank] [dorsal] [club name]
      [club code] [series] [lane] [series_rank] [overall_rank] [time] [wind] [notes]
    
    Format per athlete (relay events):
      [rank] [dorsal] [CA Tarragona] [CATT] [series] [lane] [result]
      [dorsal] [NAME] [Hombre/Mujer]
      [dorsal] [NAME] [Hombre/Mujer]
    """
    results = []
    
    # Detect if this is a relay event
    is_relay = bool(re.search(r'4x\d+|Relleu\s+4x', event_name, re.IGNORECASE))
    
    if is_relay:
        # Relay SUMARIO format: team line followed by athlete names
        # Two possible formats:
        # 1. Single line: "pos dorsal CA Tarragona CATT result"
        # 2. Multi-line: "CA Tarragona DOB" / "pos dorsal CA Tarragona" / "CATT result"
        i = sumario_idx + 1
        while i < min(sec_end, len(lines)):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Check for single-line team format: pos + dorsal + CA Tarragona + CATT
            team_match = re.match(r'^\s*(\d+)\s+(\d+)\s+CA\s+Tarragona\s+CATT', line)
            if team_match:
                pos = int(team_match.group(1))
                dorsal = team_match.group(2)
                
                # Extract team result (time)
                result_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', line)
                if not result_match:
                    result_match = re.search(r'(\d+\.\d{2})', line)
                
                marca = result_match.group(1) if result_match else ""
                wind = None
                wind_match = re.search(r'([+-]\d+\.\d)', line)
                if wind_match:
                    wind = wind_match.group(1)
                
                # Extract license from this line or next lines
                licencia = ""
                for j in range(i, min(i + 5, sec_end)):
                    lic = extract_license(lines, j, min(j + 5, sec_end))
                    if lic:
                        licencia = lic
                        break
                
                # Collect athlete names following this team line
                athletes = []
                for j in range(i + 1, min(sec_end, len(lines))):
                    athlete_line = lines[j].strip()
                    if not athlete_line:
                        continue
                    # Stop at next team block (another CA Tarragona/CATT line)
                    if re.match(r'^\s*\d+\s+\d+\s+CA\s+Tarragona\s+CATT', athlete_line):
                        break
                    # Stop at section end markers
                    if athlete_line in ('Leyenda:', 'Leyenda'):
                        break
                    # Match athlete name lines: "dorsal NAME Gender" or "NAME Gender"
                    athlete_match = re.search(r'(?:\d+\s+)?(.+?)\s+(?:Hombre|Mujer)\s*$', athlete_line)
                    if athlete_match:
                        athlete_name = athlete_match.group(1).strip()
                        athlete_name = re.sub(r'\s+', ' ', athlete_name).strip()
                        if athlete_name and len(athlete_name) > 3:
                            athletes.append(athlete_name)
                
                # Create one result per athlete
                for athlete_name in athletes:
                    results.append({
                        "lloc": pos,
                        "prova": event_name,
                        "competicio": competicio,
                        "data": data_comp,
                        "atleta_nom": athlete_name,
                        "atleta_naixement": "",
                        "atleta_licencia": licencia,
                        "marca": marca,
                        "vent": wind,
                    })
                
                i += len(athletes) + 2
                continue
            
            # Check for multi-line relay format:
            # Line N: "CA Tarragona DOB" (club name with DOB)
            # Line N+1: "pos dorsal CA Tarragona"
            # Line N+2: "CATT result"
            club_match = re.match(r'^(?:\s*CA\s+Tarragona)\s+(\d{1,2}/\d{1,2}/\d{4})', line)
            if club_match:
                # Next line should be pos + dorsal + CA Tarragona
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                pos_match = re.match(r'^\s*(\d+)\s+(\d+)\s+CA\s+Tarragona\s*$', next_line)
                if pos_match:
                    pos = int(pos_match.group(1))
                    dorsal = pos_match.group(2)
                    
                    # Line after that should be CATT + result
                    result_line = lines[i + 2].strip() if i + 2 < len(lines) else ""
                    catt_match = re.match(r'^\s*CATT\s+', result_line)
                    if catt_match:
                        # Extract team result (time)
                        result_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', result_line)
                        if not result_match:
                            result_match = re.search(r'(\d+\.\d{2})', result_line)
                        
                        marca = result_match.group(1) if result_match else ""
                        wind = None
                        wind_match = re.search(r'([+-]\d+\.\d)', result_line)
                        if wind_match:
                            wind = wind_match.group(1)
                        
                        # Collect athlete names following the result line
                        athletes = []
                        for j in range(i + 3, min(sec_end, len(lines))):
                            athlete_line = lines[j].strip()
                            if not athlete_line:
                                continue
                            # Stop at next team block (club name with DOB pattern)
                            if re.match(r'^(?:\s*CA\s+Tarragona)\s+\d{1,2}/\d{1,2}/\d{4}', athlete_line):
                                break
                            # Stop at next team block: pos dorsal CA Tarragona
                            if re.match(r'^\s*\d+\s+\d+\s+CA\s+Tarragona\s*$', athlete_line):
                                break
                            # Stop at section end markers
                            if athlete_line in ('Leyenda:', 'Leyenda'):
                                break
                            # Match athlete name lines: "dorsal NAME Gender" or "NAME Gender"
                            athlete_match = re.search(r'(?:\d+\s+)?(.+?)\s+(?:Hombre|Mujer)\s*$', athlete_line)
                            if athlete_match:
                                athlete_name = athlete_match.group(1).strip()
                                athlete_name = re.sub(r'\s+', ' ', athlete_name).strip()
                                if athlete_name and len(athlete_name) > 3:
                                    athletes.append(athlete_name)
                        
                        # Create one result per athlete (no license for relay multi-line format)
                        for athlete_name in athletes:
                            results.append({
                                "lloc": pos,
                                "prova": event_name,
                                "competicio": competicio,
                                "data": data_comp,
                                "atleta_nom": athlete_name,
                                "atleta_naixement": "",
                                "atleta_licencia": "",
                                "marca": marca,
                                "vent": wind,
                            })
                        
                        i += len(athletes) + 4
                        continue
            
            i += 1
        
        return results
    
    # Original individual event parsing
    # Find all CATT athletes in this sumario
    # Each athlete block is: name line (with DOB), then rank/dorsal/club line, then results line
    # Must verify all 3 lines belong to the same athlete block
    i = sumario_idx + 1
    while i < min(sec_end, len(lines)):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check for athlete name line (has birthdate)
        if is_name_line(line):
            name_line = line
            name_line_idx = i
            
            # Extract DOB and name from this line
            bd_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', name_line)
            name = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', name_line).strip()
            name = ' '.join(name.split())
            
            if not name or len(name) < 3:
                i += 1
                continue
            
            # Look ahead up to 5 lines for the complete athlete block:
            # The block should have: name -> (optional blank/license) -> rank+dorsal+club -> results
            # We need to find a rank+dorsal+club line that contains CATT/CA Tarragona
            # AND a results line with a valid time/mark that belongs to the same block
            
            found_block = False
            for block_start in range(i + 1, min(i + 6, len(lines))):
                block_line = lines[block_start].strip()
                
                # Look for rank + dorsal + club line
                rank_match = re.match(r'^\s*(\d+)\s+(\d+)\s+(.+)$', block_line)
                if rank_match:
                    rank = int(rank_match.group(1))
                    dorsal = rank_match.group(2)
                    club_name = rank_match.group(3).strip()
                    
                    # Check if this is CATT
                    if 'CA Tarragona' not in club_name and 'CATT' not in club_name:
                        continue
                    
                    # The results should be on the next non-empty line
                    result_line = ""
                    for j in range(block_start + 1, min(block_start + 3, len(lines))):
                        candidate = lines[j].strip()
                        if candidate:
                            result_line = candidate
                            break
                    
                    if not result_line:
                        continue
                    
                    # Extract time from result line
                    marca = ""
                    time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', result_line)
                    if time_match:
                        marca = time_match.group(1)
                    else:
                        # Try short time format (sprints)
                        for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', result_line):
                            val = float(num_match.group(1))
                            if val > 5.0 and val < 60.0:
                                marca = num_match.group(1)
                                break
                    
                    if not marca:
                        continue
                    
                    # Extract wind
                    wind = None
                    wind_match = re.search(r'([+-]\d+\.\d)', result_line)
                    if wind_match:
                        wind = wind_match.group(1)
                    
                    # Extract license from result line or lines between name and rank
                    licencia = ""
                    lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', result_line)
                    licencia = lic_match.group(1) if lic_match else ""
                    licencia = re.sub(r'[\.\-]+\s*$', '', licencia)
                    if not licencia:
                        # Look in lines between name and rank line
                        for j in range(i + 1, block_start):
                            lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', lines[j])
                            if lic_match:
                                licencia = lic_match.group(1)
                                break
                    if not licencia:
                        # Look in the line after the rank line, and subsequent lines
                        for j in range(block_start + 1, min(block_start + 4, sec_end)):
                            lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', lines[j])
                            if lic_match:
                                licencia = lic_match.group(1)
                                break
                        if licencia:
                            licencia = re.sub(r'[\.\-]+\s*$', '', licencia)
                    
                    results.append({
                        "lloc": rank,
                        "prova": event_name,
                        "competicio": competicio,
                        "data": data_comp,
                        "atleta_nom": name,
                        "atleta_naixement": bd_match.group(1) if bd_match else "",
                        "atleta_licencia": licencia,
                        "marca": marca,
                        "vent": wind,
                    })
                    
                    # Advance past this entire block
                    i = block_start + 2
                    found_block = True
                    break
            
            if not found_block:
                i += 1
            continue
        
        i += 1
    
    return results


def is_rfea_section(lines, sec_start, sec_end):
    """Detect if this section uses the RFEA multi-line format.
    
    RFEA format characteristics:
    - Header has column labels: "Pto Dor Nombre F de Nac Cat Calle Marca" + "Club Lic"
    - Result line: position + dorsal + name + DOB + category + lane + time
    - Club line: club name + license on the NEXT line (after the result)
    - Example:
        Pto  Dor Nombre          F de Nac  Cat  Calle  Marca
                 Club                    Lic
        4   71 Mario Sanchez     02/10/2002 CM   1      7.61
             CA Tarragona          CL74367
    
    Returns True if RFEA format detected.
    """
    # Look for RFEA header pattern in the first 30 lines of the section
    for i in range(sec_start, min(sec_start + 30, sec_end)):
        line = lines[i]
        # RFEA header: "Pto  Dor Nombre  F de Nac  Cat  Calle  Marca"
        if 'Pto' in line and 'Dor' in line and 'Nombre' in line and 'F de Nac' in line:
            # Verify club line header exists
            for j in range(i + 1, min(i + 5, sec_end)):
                if 'Club' in lines[j] and 'Lic' in lines[j]:
                    # Now check if any athlete line has CA Tarragona on the NEXT line
                    for k in range(i + 5, min(sec_end, i + 200)):
                        kl = lines[k].strip()
                        if not kl or not re.search(r'\d{1,2}/\d{1,2}/\d{4}', kl):
                            continue
                        # This looks like an athlete line - check next line for club
                        if k + 1 < sec_end:
                            next_line = lines[k + 1].strip()
                            if 'CA Tarragona' in next_line or 'CATT' in next_line:
                                return True
                            # Also check if next line is a known club
                            if next_line and re.match(r'^CA\s+', next_line) and not next_line.startswith('CA Tarragona'):
                                # Found a non-CATT club - RFEA format confirmed
                                return True
    return False


def _find_catt_rfea_format(lines, sec_start, sec_end, is_in_sumario=None):
    """Find CATT athletes in RFEA format.
    
    RFEA format:
    Line N: pos  dorsal  Name  DOB  Cat  Lane  Marca
    Line N+1: Club  License
    
    Returns blocks with the same structure as _find_catt_old_format:
    name_line, name_line_idx, data_lines, position_line, position_line_idx, position
    """
    athletes = []
    
    # Find all athlete data lines (lines with DOB pattern)
    athlete_line_pattern = re.compile(r'^\s*\d+\s+\d+\s*.+\d{1,2}/\d{1,2}/\d{4}')
    
    i = sec_start
    while i < sec_end:
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines and headers
        if not stripped:
            i += 1
            continue
        
        # Skip header lines
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                       'Pto', 'Dor', 'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                       'Calle', 'Serie', 'Gestion', 'Pagina', 'SUMARIO', 'Rank',
                       'Final', 'Categoria', 'Cat']
        if any(label in stripped for label in skip_labels):
            i += 1
            continue
        
        # Check if this is an athlete data line
        if not athlete_line_pattern.match(line):
            i += 1
            continue
        
        # Check if this athlete has a club line below
        if i + 1 >= sec_end:
            i += 1
            continue
        
        club_line = lines[i + 1].strip()
        
        # Check if club line contains CA Tarragona or CATT
        if 'CA Tarragona' not in club_line and 'CATT' not in club_line:
            i += 1
            continue
        
        # This is a CATT athlete in RFEA format
        # In RFEA format, the athlete line itself IS the name line
        name = extract_name_from_line(stripped)
        if not name:
            i += 1
            continue
        
        # Extract position from the athlete line
        pos_match = re.match(r'^\s*(\d+)', stripped)
        pos = int(pos_match.group(1)) if pos_match else 0
        
        # Skip athletes found in SUMARIO sub-sections
        if is_in_sumario and is_in_sumario(i):
            i += 2
            continue
        
        # Return block with same structure as old format
        athletes.append({
            'name_line': stripped,
            'name_line_idx': i,
            'data_lines': [(i, stripped), (i + 1, lines[i + 1])],
            'position_line': stripped,
            'position_line_idx': i,
            'position': pos,
            'rfea_format': True,
        })
        
        i += 2  # Skip both the athlete line and club line
    
    return athletes


def extract_result_from_rfea_line(athlete_line, club_line):
    """Extract the result (marca) from an RFEA athlete line.
    
    RFEA line format:
    pos  dorsal  Name  DOB  Cat  Lane  Marca
    
    Examples:
    "4   71 (t) Mario Sanchez Alvarez  02/10/2002  CM  1  7.61"
    "41 (t) Eduard Guzman Montagut  15/12/2002  CM  3  NP"
    "2   151 (t) Sergi Cattaneo Adan  08/03/2003  CM  6  11.33"
    """
    stripped = athlete_line.strip()
    
    # Remove the DOB first
    stripped = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', stripped)
    
    # Remove position and dorsal at the start
    stripped = re.sub(r'^\s*\d+\s+\d+\s*\(?[te]?\)?\s*', '', stripped)
    
    # Remove category (SM, CM, IM, BM, JN, etc.)
    stripped = re.sub(r'\b(?:SM|CM|IM|BM|JN|AS|AI|AM|SV|JV|AJ|AM\d+|S\d+|C\d+|I\d+|B\d+)\b', '', stripped)
    
    # Remove lane number
    stripped = re.sub(r'\b\d+\b', '', stripped, count=1)
    
    # Now we should have just the result (time, distance, DNS, etc.)
    stripped = stripped.strip()
    
    # Skip if it looks like a category or empty
    if not stripped or re.match(r'^[A-Z]{2,4}$', stripped):
        return None
    
    # Common non-result values
    if stripped.upper() in ('NP', 'DNF', 'DNS', 'DQ', 'NW', 'RET', 'N.P.'):
        return stripped
    
    # If it's a time or distance, validate it
    # Try to extract a numeric value
    time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2}|\d{1,2}:\d{2}|\d+\.\d+)', stripped)
    if time_match:
        return time_match.group(1)
    
    # Check for quote format: 3'53"86
    quote_match = re.search(r"(\d+'(\d{2})\"(\d{2}))", stripped)
    if quote_match:
        minutes = quote_match.group(1).split("'")[0]
        seconds = quote_match.group(1).split("'")[1].split('"')[0]
        cs = quote_match.group(2)
        return f"{minutes}:{seconds}.{cs}"
    
    # Check for comma-separated time: 1.00,08 -> 1:00.08
    comma_match = re.search(r'(\d+)\.(\d{2}),(\d{2})', stripped)
    if comma_match:
        return f"{comma_match.group(1)}:{comma_match.group(2)}.{comma_match.group(3)}"
    
    # If nothing matched, return the stripped value if it looks like a result
    if stripped and len(stripped) > 0:
        return stripped
    
    return None


def is_new_format_section(lines, sec_start, sec_end):
    """Detect if this section uses the new multi-line format.
    
    New format characteristics:
    - Name line, then pos+dorsal on next line, then club name, then club code
    - Track events have separate result lines with T.Reacci\\xf3n/Resultado columns
    - No inline "CATT  results" pattern on same line as position
    
    Returns True if new format detected.
    
    IMPORTANT: We only return True if we find at least one CATT athlete block
    in the new format. This prevents false positives from sections that don't
    contain any CATT athletes (which was causing misassignment of athletes
    to wrong events like javelina).
    """
    # First pass: check if ANY CATT block exists in new format
    # This is the key fix - only detect new format if there's actual CATT data
    catt_count = 0
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i].strip()
        if not line or not is_name_line(line):
            continue
        
        # Look ahead for the multi-line block and verify it's CATT
        for j in range(i + 1, min(i + 6, sec_end)):
            fwd = lines[j].strip()
            if fwd and 'CA Tarragona' in fwd:
                # Check subsequent lines for CATT
                for k in range(j + 1, min(j + 4, sec_end)):
                    next_fwd = lines[k].strip()
                    if next_fwd and 'CATT' in next_fwd:
                        catt_count += 1
                        break
                    if next_fwd and not re.match(r'^[A-Z]{2,8}$', next_fwd) and not re.match(r'^CL\d+$', next_fwd):
                        break
                break
            elif fwd and re.match(r'^\s*\d+\s+\d+\s*$', fwd):
                # pos+dorsal line, check next lines for CA Tarragona
                for k in range(j + 1, min(j + 4, sec_end)):
                    next_fwd = lines[k].strip()
                    if next_fwd and 'CA Tarragona' in next_fwd:
                        for m in range(k + 1, min(k + 4, sec_end)):
                            m_fwd = lines[m].strip()
                            if m_fwd and 'CATT' in m_fwd:
                                catt_count += 1
                                break
                            if m_fwd and not re.match(r'^[A-Z]{2,8}$', m_fwd) and not re.match(r'^CL\d+$', m_fwd):
                                break
                        break
                    if next_fwd and not re.match(r'^\s*\d+\s+\d+$', next_fwd):
                        break
            elif fwd and 'CATT' in fwd and re.match(r'^\s*\d+\s+CATT', fwd):
                # "pos  CATT" format - check for CA Tarragona nearby
                for k in range(i + 1, min(i + 6, sec_end)):
                    if 'CA Tarragona' in lines[k]:
                        catt_count += 1
                        break
    
    # Only treat as new format if we found CATT athletes in it
    return catt_count > 0


def find_catt_athletes_in_section(lines, sec_start, sec_end):
    """Find all CATT athletes in a section. Returns list of athlete blocks.
    
    Handles both old format (position+CATT on same line) and new format
    (multi-line blocks: name, pos+dorsal, club name, club code/license, results).
    
    IMPORTANT: Skips SUMARIO sub-sections within the section to avoid duplicate
    entries. SUMARIO sections aggregate results from all heats/rounds and are
    just a summary — the individual round results are the authoritative source.
    """
    athletes = []
    
    # Detect SUMARIO sub-sections within this section
    # A SUMARIO starts with "SUMARIO" header and ends at the next event header or section end
    sumario_ranges = []
    for i in range(sec_start, min(sec_end, len(lines))):
        if 'SUMARIO' in lines[i].upper():
            # Find the end of this SUMARIO: next event header or section end
            sumario_end = sec_end
            for j in range(i + 1, min(sec_end, len(lines))):
                stripped = lines[j].strip()
                # SUMARIO ends when we hit another event header (date line + event name)
                if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', stripped) and any(
                    re.search(p, stripped, re.IGNORECASE) for p in EVENT_PATTERNS
                ):
                    sumario_end = j
                    break
            sumario_ranges.append((i, sumario_end))
    
    def is_in_sumario(idx):
        for s_start, s_end in sumario_ranges:
            if s_start <= idx < s_end:
                return True
        return False
    
    # Detect format: RFEA first (club after result), then new format, then old format
    rfea_format = is_rfea_section(lines, sec_start, sec_end)
    new_format = is_new_format_section(lines, sec_start, sec_end)
    
    if rfea_format:
        athletes = _find_catt_rfea_format(lines, sec_start, sec_end, is_in_sumario)
    elif new_format:
        athletes = _find_catt_new_format(lines, sec_start, sec_end, is_in_sumario)
    else:
        athletes = _find_catt_old_format(lines, sec_start, sec_end, is_in_sumario)
    
    return athletes


def _find_catt_old_format(lines, sec_start, sec_end, is_in_sumario=None):
    """Find CATT athletes in old format (position + CATT on same line)."""
    athletes = []
    
    # Strategy 1: Find lines with position + CATT/CA Tarragona (formats 1 & 2)
    anchor_pattern = re.compile(r'^\s*(\d+)\s+\d+\s+(?:CATT|CA\s+Tarragona)')
    
    # Strategy 2: Find SUMARIO format - lines with just club name (not CATT, just club full name)
    # Also match inline SUMARI format where CATT+results may follow on next line
    club_name_pattern = re.compile(r'^\s*(\d+)\s+\d+\s+(?:CA\s+Tarragona|CA\s+Granollers|CA\s+Vic|JA\s+Sabadell|GEiE\s+Giron[íaà]|Barcelona\s+At\.|UA\s+Terrassa|UA\s+Barber[àá]|CAVB|CAGB|BCNB|UABB|UATB|GEEG|JASB)(?:\s*$|\s+)')
    
    # Strategy 3: Conersys format - position + CA Tarragona + CATT (no dorsal between pos and club)
    # Pattern: "5          CA Tarragona                        CATT"
    conersys_pattern = re.compile(r'^\s*(\d+)\s+CA\s+Tarragona\s+CATT')
    
    all_anchors = []  # list of (idx, is_club_name_line, is_conersys)
    
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i]
        stripped = line.strip()
        
        # Check for Conersys format: position + CA Tarragona + CATT (no dorsal)
        if conersys_pattern.search(line):
            all_anchors.append((i, False, True))
        # Check for format 1/2: position + CATT/CA Tarragona on same line
        elif anchor_pattern.search(line):
            all_anchors.append((i, False, False))
        # Check for format 3 (SUMARIO): position + club name only
        elif club_name_pattern.search(stripped):
            all_anchors.append((i, True, False))
    
    for anchor_idx, is_club_name, is_conersys in all_anchors:
        anchor_line = lines[anchor_idx]
        pos_match = re.match(r'^\s*(\d+)', anchor_line)
        if not pos_match:
            continue
        pos = int(pos_match.group(1))
        
        # For SUMARIO format, check if next line has CATT
        if is_club_name:
            if anchor_idx + 1 >= len(lines):
                continue
            next_line = lines[anchor_idx + 1]
            if 'CATT' not in next_line:
                continue
            anchor_line = next_line
        
        # Check this is actually CATT
        if 'CATT' not in anchor_line and 'CA Tarragona' not in anchor_line:
            continue
        
        # Find the name line: look backwards from anchor
        name_line_idx = None
        name_line = None
        
        # Conersys format: name is typically 2 lines above (name, blank, pos)
        # Old format: name is typically 1 line above
        lookback = 3 if is_conersys else 8
        
        for j in range(anchor_idx - 1, max(anchor_idx - lookback, sec_start - 1), -1):
            prev = lines[j].strip()
            if not prev or len(prev) < 4:
                continue
            if re.match(r'^\s*\d+\s+\d+\s+[A-Z]', prev) and 'CATT' not in prev and 'CA Tarragona' not in prev:
                continue
            skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                           'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                           'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                           'Gestion', 'Pagina', 'SUMARIO', 'Rank']
            if any(label in prev for label in skip_labels):
                continue
            if is_club_line(prev):
                continue
            if re.match(r'^[\d\.\-\s]+$', prev):
                continue
            if is_name_line(prev):
                name_line_idx = j
                name_line = prev
                break
        
        # Collect data lines
        data_lines = []
        anchor_pos = all_anchors.index((anchor_idx, is_club_name, is_conersys))
        next_anchor_idx = all_anchors[anchor_pos + 1][0] if anchor_pos + 1 < len(all_anchors) else sec_end
        
        for j in range(anchor_idx + 1, min(next_anchor_idx, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                continue
            # Stop at next anchor (handle both Conersys and old format patterns)
            if re.match(r'^\s*\d+\s+\d+\s+(?:CATT|CA\s+Tarragona)', fwd):
                break
            if conersys_pattern.match(fwd):
                break
            if any(label in fwd for label in skip_labels):
                continue
            data_lines.append((j, lines[j]))
        
        # Skip athletes found in SUMARIO sub-sections
        if is_in_sumario and is_in_sumario(anchor_idx):
            continue
        
        athletes.append({
            'position_line_idx': anchor_idx,
            'position_line': anchor_line,
            'position': pos,
            'name_line_idx': name_line_idx,
            'name_line': name_line,
            'data_lines': data_lines,
            'is_conersys': is_conersys,
        })
    
    return athletes


def _find_catt_new_format(lines, sec_start, sec_end, is_in_sumario=None):
    """Find CATT athletes in new multi-line format.
    
    New format athlete block (track events):
      Line N:   NAME DOB
      Line N+1: pos  dorsal
      Line N+2: CA Tarragona / AA Catalunya / etc.
      Line N+3: CATT / AACB / etc. (club code)
      Line N+4: license (CT438 / CAT-3930878-… / etc.)
      Line N+5: results
    
    We must verify the club name is specifically "CA Tarragona" or "CATT".
    """
    athletes = []
    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                   'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                   'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
    
    # Find all name lines
    name_line_indices = []
    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i].strip()
        if is_name_line(line):
            # Make sure it's not a header line
            if not any(label in line for label in skip_labels):
                name_line_indices.append(i)
    
    for name_idx in name_line_indices:
        # Look for the multi-line block starting from this name line
        # Pattern: name -> pos+dorsal -> club_name -> club_code -> license -> results
        # OR: name -> pos+dorsal+CA+Tarragona+CATT+results -> license line
        
        # Find pos+dorsal line (next non-empty line)
        pos_line_idx = None
        for j in range(name_idx + 1, min(name_idx + 5, sec_end)):
            fwd = lines[j].strip()
            if fwd:
                pos_line_idx = j
                break
        
        if pos_line_idx is None:
            continue
        
        # Check if the pos line itself contains CA Tarragona + CATT (PDF 1 format)
        pos_line = lines[pos_line_idx]
        pos_line_stripped = pos_line.strip()
        
        # Check if this line has both pos+dorsal and CA Tarragona/CATT
        has_pos_dorsal = bool(re.match(r'^\s*\d+\s+\d+', pos_line_stripped))
        has_catt_on_pos = 'CATT' in pos_line_stripped or 'CA Tarragona' in pos_line_stripped
        
        # Check for height events format: "pos  CA Tarragona" (no dorsal)
        has_pos_club = bool(re.match(r'^\s*\d+\s+CA\s+Tarragona\s*$', pos_line_stripped))
        
        # Check for DNS format: just "CA Tarragona" (no position number)
        has_club_only = pos_line_stripped == 'CA Tarragona'
        
        # Check for Longitud format: "pos  CATT" (club code only, no CA Tarragona)
        has_catt_only = 'CATT' in pos_line_stripped and 'CA Tarragona' not in pos_line_stripped
        
        if not has_pos_dorsal and not has_pos_club and not has_club_only and not has_catt_only:
            continue
        
        # Extract position from pos line
        # DNS athletes may have only dorsal (no position), e.g. "             383"
        pos_match = re.match(r'^\s*(\d+)\s+\d+', pos_line_stripped)
        if not pos_match:
            # Try height events format: "pos  CA Tarragona"
            pos_club_match = re.match(r'^\s*(\d+)\s+CA\s+Tarragona\s*$', pos_line_stripped)
            if pos_club_match:
                pos = int(pos_club_match.group(1))
            # Try Longitud format: "pos  CATT"
            elif has_catt_only:
                catt_pos_match = re.match(r'^\s*(\d+)\s+CATT\s*$', pos_line_stripped)
                if catt_pos_match:
                    pos = int(catt_pos_match.group(1))
                else:
                    pos = 0
            else:
                # Try single number (dorsal only, DNS case)
                single_match = re.match(r'^\s*(\d+)\s*$', pos_line_stripped)
                if not single_match:
                    pos = 0  # No number at all (shouldn't happen for has_pos_club)
                else:
                    pos = 0  # DNS athletes have no position
        else:
            pos = int(pos_match.group(1))
        
        # If CATT is on the pos line, use it as the anchor directly
        # Initialize these variables for all paths through has_catt_on_pos
        license_line_idx = None
        license_line = None
        result_line_idx = None
        result_line = None
        if has_catt_on_pos:
            # Check if this is the Longitud format: "pos  CATT" without "CA Tarragona"
            # In this format, CA Tarragona is on a separate line after a blank
            has_catt_only = 'CATT' in pos_line_stripped and 'CA Tarragona' not in pos_line_stripped
            
            if has_catt_only:
                # Check if results are embedded in the pos line itself (marathon format variant)
                # Format: "pos  dorsal  CATT  ordinal  time  MMP"
                pos_time_match = re.search(r'(\d{1,2}:\d{2}(?:\.\d+)?)', pos_line_stripped)
                pos_ordinal = None
                if pos_time_match:
                    # Extract ordinal (number before the time)
                    time_start = pos_time_match.start()
                    before_time = pos_line_stripped[:time_start]
                    ordinal_match = re.findall(r'\b(\d+)\b', before_time)
                    if ordinal_match:
                        pos_ordinal = ordinal_match[-1]
                
                # Check if this is the marathon format: "pos  dorsal  CATT" followed by license, then results, then CA Tarragona
                # Format:
                #   43  249  CATT
                #   CL3135
                #   41  2:47:53  MMP
                #   CA Tarragona
                next_non_empty = None
                for j in range(pos_line_idx + 1, min(pos_line_idx + 4, sec_end)):
                    fwd = lines[j].strip()
                    if fwd:
                        next_non_empty = (j, fwd)
                        break
                
                if next_non_empty and re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', next_non_empty[1]):
                    # Marathon format: license is right after CATT line
                    license_line_idx = next_non_empty[0]
                    license_line = next_non_empty[1]
                    
                    # Find results line (after license, before CA Tarragona)
                    result_line_idx = None
                    result_line = None
                    for j in range(license_line_idx + 1, min(license_line_idx + 5, sec_end)):
                        fwd = lines[j].strip()
                        if not fwd:
                            continue
                        # Look for time pattern (HH:MM:SS or HH:MM.ss)
                        if re.search(r'\d{1,2}:\d{2}', fwd):
                            result_line_idx = j
                            result_line = fwd
                            break
                        if re.search(r'\bCA\s+Tarragona\b', fwd, re.IGNORECASE):
                            break
                    
                    # Find CA Tarragona line after results
                    club_name_line_idx = None
                    club_name_line = None
                    start_search = result_line_idx + 1 if result_line_idx else license_line_idx + 1
                    for j in range(start_search, min(start_search + 15, sec_end)):
                        fwd = lines[j].strip()
                        if not fwd:
                            continue
                        if re.search(r'\bCA\s+Tarragona\b', fwd, re.IGNORECASE):
                            club_name_line_idx = j
                            club_name_line = fwd
                            break
                        if re.match(r'^[A-Z\-]{2,8}\s*$', fwd):
                            continue  # Skip other club codes
                        if re.search(r'\b\d{2}/\d{2}/\d{4}\b', fwd):
                            break  # Hit next athlete's DOB
                    
                    # If CA Tarragona was on the license line itself (DNS case), use it
                    if club_name_line_idx is None and re.search(r'\bCA\s+Tarragona\b', license_line, re.IGNORECASE):
                        club_name_line_idx = license_line_idx
                        club_name_line = license_line
                    
                    if club_name_line_idx is None:
                        # Use result line as club name line fallback
                        club_name_line_idx = result_line_idx if result_line_idx else license_line_idx
                        club_name_line = result_line if result_line else license_line
                    
                    # Collect data lines: license + results
                    block_lines = []
                    if license_line_idx is not None:
                        block_lines.append((license_line_idx, lines[license_line_idx]))
                    if result_line_idx is not None:
                        block_lines.append((result_line_idx, lines[result_line_idx]))
                    # If results are embedded in the pos line itself
                    if pos_time_match:
                        block_lines.append((pos_line_idx, lines[pos_line_idx]))
                else:
                    # Longitud format: pos line has "pos  CATT", CA Tarragona on next non-empty line
                    club_name_line_idx = None
                    club_name_line = None
                    for j in range(pos_line_idx + 1, min(pos_line_idx + 6, sec_end)):
                        fwd = lines[j].strip()
                        if not fwd:
                            continue
                        # Skip wind values like "0.4" that appear between CATT and CA Tarragona
                        if re.match(r'^[+-]?\d+\.\d+$', fwd):
                            continue
                        if re.search(r'\bCA\s+Tarragona\b', fwd, re.IGNORECASE):
                            club_name_line_idx = j
                            club_name_line = fwd
                            break
                
                if club_name_line_idx is None:
                    continue
                
                # Find the license line (on the CA Tarragona line or next line)
                # Only re-search if license wasn't already found in marathon format path
                if license_line_idx is None:
                    license_line = None
                    for j in range(club_name_line_idx, min(club_name_line_idx + 3, sec_end)):
                        fwd = lines[j].strip()
                        if not fwd:
                            continue
                        if re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', fwd):
                            license_line_idx = j
                            license_line = fwd
                            break
                        if re.match(r'^[A-Z\-]{2,8}\s*$', fwd) and 'CATT' in fwd:
                            license_line_idx = j
                            license_line = fwd
                            break
            else:
                # This is the PDF 1 format: pos line has CA Tarragona + CATT + results inline
                # License is on the next non-empty line(s)
                club_name_line_idx = pos_line_idx
                club_name_line = pos_line_stripped
                
                # Find the license line (next non-empty line after pos line)
                license_line_idx = None
                license_line = None
                for j in range(pos_line_idx + 1, min(pos_line_idx + 5, sec_end)):
                    fwd = lines[j].strip()
                    if not fwd:
                        continue
                    if re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', fwd):
                        license_line_idx = j
                        license_line = fwd
                        break
                    # Also accept standalone club code lines
                    if re.match(r'^[A-Z\-]{2,8}\s*$', fwd) and 'CATT' in fwd:
                        license_line_idx = j
                        license_line = fwd
                        break
        else:
            # Standard new format: look for club name line after pos line
            club_name_line_idx = None
            club_name_line = None
            for j in range(pos_line_idx + 1, min(pos_line_idx + 4, sec_end)):
                fwd = lines[j].strip()
                if not fwd:
                    continue
                if re.search(r'\bCA\s+Tarragona\b|\bAA\s+Catalunya\b|\bFACVAC\s+Valls\b|\bCN\s+Reus\b|\bUA\s+Montsi[àa]\b', fwd, re.IGNORECASE):
                    club_name_line_idx = j
                    club_name_line = fwd
                    break
            
            if club_name_line_idx is None:
                continue
            
            if 'CA Tarragona' not in club_name_line and 'CATT' not in club_name_line:
                continue
            
            # Find the club code line (CATT, AACB, etc.) - next non-empty line after club name
            club_code_line_idx = None
            club_code_line = None
            for j in range(club_name_line_idx + 1, min(club_name_line_idx + 3, sec_end)):
                fwd = lines[j].strip()
                if not fwd:
                    continue
                if re.match(r'^[A-Z]{2,8}$', fwd):
                    club_code_line_idx = j
                    club_code_line = fwd
                    break
            
            if club_code_line_idx is None:
                continue
            
            if 'CATT' not in club_code_line:
                continue
            
            # Find the license line (next non-empty line after club code)
            license_line_idx = None
            license_line = None
            for j in range(club_code_line_idx + 1, min(club_code_line_idx + 5, sec_end)):
                fwd = lines[j].strip()
                if not fwd:
                    continue
                if re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', fwd):
                    license_line_idx = j
                    license_line = fwd
                    break
                if re.match(r'^[A-Z\-]{2,8}\s*$', fwd) and 'CATT' in fwd:
                    license_line_idx = j
                    license_line = fwd
                    break
        
        # Collect all lines from name to results (up to 10 lines after name)
        block_lines = []
        for j in range(name_idx, min(name_idx + 10, sec_end)):
            block_lines.append((j, lines[j]))
        
        # Check if we've hit the next athlete block
        next_name_idx = None
        for ni in name_line_indices:
            if ni > name_idx:
                next_name_idx = ni
                break
        
        # Collect data lines (after license_line_idx until next athlete or blank+next pos)
        data_lines = []
        if license_line_idx is None:
            continue
        end_idx = next_name_idx if next_name_idx else sec_end
        consecutive_blanks = 0
        for j in range(license_line_idx + 1, min(end_idx, sec_end)):
            fwd = lines[j].strip()
            if not fwd:
                consecutive_blanks += 1
                # Stop at two consecutive blank lines (end of athlete block)
                if consecutive_blanks >= 2:
                    break
                continue
            consecutive_blanks = 0
            # Stop at header lines
            if any(label in fwd for label in skip_labels):
                continue
            # Stop at next athlete's pos line
            if re.match(r'^\s*\d+\s+\d+\s*$', fwd):
                break
            data_lines.append((j, lines[j]))
        
        # If data_lines is empty, the results may be embedded in the position line itself
        # (common in field events where results are on the same line as pos/club/CATT)
        if not data_lines and has_catt_on_pos:
            # Include the position line which may contain results
            data_lines = [(pos_line_idx, pos_line)]
        
        # Skip athletes found in SUMARIO sub-sections
        if is_in_sumario and is_in_sumario(name_idx):
            continue
        
        athletes.append({
            'position_line_idx': club_name_line_idx,
            'position_line': club_name_line,
            'position': pos,
            'name_line_idx': name_idx,
            'name_line': lines[name_idx].strip(),
            'data_lines': data_lines,
            'new_format': True,
            'pos_line_idx': pos_line_idx,
            'block_lines': block_lines,
        })
    
    return athletes


def find_name_line(lines, result_line_idx, sec_start):
    """Find the name+birthdate line for an athlete, looking backwards from the CATT result line."""
    for j in range(result_line_idx - 1, max(result_line_idx - 30, sec_start - 1), -1):
        prev_line = lines[j].strip()
        if not prev_line or len(prev_line) < 4:
            continue
        if re.match(r'^\d+\s+\d+', prev_line):
            continue
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                       'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                       'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in prev_line for label in skip_labels):
            continue
        if is_club_line(prev_line):
            continue
        if re.match(r'^[\d\.\-\s]+$', prev_line):
            continue
        if is_name_line(prev_line):
            return j, prev_line
    return None, None


def extract_track_result_new(lines, athlete_block, sec_end):
    """Extract track result for new multi-line format.
    
    New format: name, pos+dorsal, club name, CATT, license+result lines.
    The result is on the line(s) after the CATT line, in the Resultado column.
    """
    catt_idx = athlete_block['position_line_idx']
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all lines in the athlete's block
    all_block_texts = []
    for idx, line in block_lines:
        all_block_texts.append(line.strip())
    # Also include data lines
    for idx, line in athlete_block['data_lines']:
        all_block_texts.append(line.strip())
    
    combined = ' '.join(all_block_texts)
    
    # Check for DNS/DNF markers first
    dns_match = re.search(r'\b(DNS|DNF|DNP|Abandona|No presentado|No comenzado|Retirado)\b', combined, re.IGNORECASE)
    if dns_match:
        return dns_match.group(1)
    
    # Try HH:MM:SS format first (e.g., 2:47:53 for marathon)
    time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})(?!\d)', combined)
    if time_match:
        return time_match.group(1)
    
    # Try time format (e.g., 1:11.69)
    time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', combined)
    if time_match:
        return time_match.group(1)
    
    # Try short time format (e.g., 11.59, 17.52)
    for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{2})(?![\d.])', combined):
        val = float(num_match.group(1))
        if val > 5.0 and val < 60.0:
            return num_match.group(1)
    
    # Try 3-decimal format
    for num_match in re.finditer(r'(?<![\d.:])(\d+\.\d{3})(?![\d.])', combined):
        val = float(num_match.group(1))
        if val > 5.0 and val < 60.0:
            return num_match.group(1)[:5]
    
    return ""


def extract_height_result_new(lines, athlete_block, sec_end):
    """Extract height result for new multi-line format.
    
    New format: name+markers, pos+dorsal, club name, CATT+license+markers, then result.
    The result is found on the line after the markers, or in the block.
    """
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all text in the block
    all_texts = []
    for idx, line in block_lines:
        all_texts.append(line.strip())
    for idx, line in athlete_block['data_lines']:
        all_texts.append(line.strip())
    
    combined = ' '.join(all_texts)
    
    # Look for height value with MMP/MMT marker
    # Pattern: "1.15 MMP" or "1.06"
    height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', combined)
    if height_match:
        val = height_match.group(1)
        num_val = float(val)
        if num_val >= 1.0 and num_val <= 7.0:
            return val
    
    # Also try to find O/XXO/XXX pattern and extract the last cleared height
    # The heights are in the section header, and we need to match them with O/XXO/XXX
    # But for simplicity, let's look for the result value at the end of the block
    
    # Find the result line - it has the final height with MMP/MMT or just a number
    for text in all_texts:
        # Skip lines with O/XXO/XXX markers
        if re.search(r'\b(O|XXO|XO|XXX)\b', text) and not re.search(r'\d+\.\d{2}', text):
            continue
        # Look for height values
        nums = re.findall(r'(\d+\.\d{2})', text)
        for num in nums:
            val = float(num)
            if 1.0 <= val <= 7.0:
                return num
    
    return ""


def extract_marcha_result_new(lines, athlete_block, sec_end):
    """Extract march result for new multi-line format.
    
    New format: name, pos+dorsal, club name, CATT, license+result lines.
    The result is on the line(s) after the CATT line.
    Times can be HH:MM, HH:MM:SS, or HH:MM.ss.
    """
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all lines in the athlete's block
    all_block_texts = []
    for idx, line in block_lines:
        all_block_texts.append(line.strip())
    # Also include data lines
    for idx, line in athlete_block['data_lines']:
        all_block_texts.append(line.strip())
    
    combined = ' '.join(all_block_texts)
    
    # Try HH:MM:SS format first (e.g., 4:12:44)
    time_match = re.search(r'(\d{1,2}:\d{2}:\d{2})(?!\d)', combined)
    if time_match:
        return time_match.group(1)
    
    # Try HH:MM.ss format (e.g., 23:09.2)
    time_match = re.search(r'(\d{1,2}:\d{2}\.\d{2})', combined)
    if time_match:
        return time_match.group(1)
    
    # Try HH:MM format (e.g., 26:29) - only if not followed by more digits
    time_match = re.search(r'(\d{1,2}:\d{2})(?!\d|:\d)', combined)
    if time_match:
        return time_match.group(1)
    
    return ""


def extract_field_result_new(lines, athlete_block, sec_end):
    """Extract field result for new multi-line format.
    
    New format for field events (Peso, Disco, etc.):
      Line 1: NAME DOB  attempt1 attempt2 attempt3 ...
      Line 2: pos  dorsal  CA Tarragona  CATT  remaining attempts
      Line 3: license
    
    The result is the best (last) valid mark.
    """
    block_lines = athlete_block.get('block_lines', [])
    
    # Collect all text in the block
    all_texts = []
    for idx, line in block_lines:
        all_texts.append(line.strip())
    for idx, line in athlete_block['data_lines']:
        all_texts.append(line.strip())
    
    combined = ' '.join(all_texts)
    
    # Find all numeric values in range 3.0-80.0
    nums = re.findall(r'(\d+\.\d{2})', combined)
    if nums:
        for num in reversed(nums):
            val = float(num)
            if val >= 3.0 and val <= 80.0:
                return num
    
    return ""


def parse_catt_athlete(lines, athlete_block, sec_start, sec_end, event_name, wind, event_type, competicio, data_comp):
    """Parse a single CATT athlete from a block found by find_catt_athletes_in_section."""
    name_line = athlete_block['name_line']
    anchor_line = athlete_block['position_line']
    data_lines = athlete_block['data_lines']
    new_format = athlete_block.get('new_format', False)
    block_lines = athlete_block.get('block_lines', [])

    if not name_line:
        return []

    name = extract_name_from_line(name_line)
    bd_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', name_line)
    birth_date = bd_match.group(1) if bd_match else ""

    # Find license from block lines and data lines
    licencia = ""
    # Search in block lines first (new format)
    for idx, line in block_lines:
        lic = extract_license(lines, idx, min(idx + 5, sec_end))
        if lic:
            licencia = lic
            break
    # Also search in data lines
    if not licencia:
        for idx, line in data_lines:
            lic = extract_license(lines, idx, min(idx + 5, sec_end))
            if lic:
                licencia = lic
                break

    # Find position
    lloc = athlete_block['position']

    # Find result
    marca = ""
    if event_type == "track" or event_type == "road":
        if new_format:
            marca = extract_track_result_new(lines, athlete_block, sec_end)
        else:
            marca = extract_track_result(lines, athlete_block['position_line_idx'], sec_end)
    elif event_type == "marcha":
        if new_format:
            marca = extract_marcha_result_new(lines, athlete_block, sec_end)
        else:
            marca = extract_marcha_result(lines, athlete_block['position_line_idx'], sec_end)
    elif event_type == "jump":
        if new_format:
            # Result is on the name line (horizontal format with attempts)
            marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "jump")
            if not marca:
                # Try block lines
                for idx, line in block_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 3.0 and val <= 20.0:
                                marca = num
                                break
                    if marca:
                        break
            # Extract wind for the best mark
            vent = extract_jump_wind(lines, athlete_block['name_line_idx'], sec_end)
            if vent:
                wind = vent
        else:
            # Old format
            marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "jump")
            if not marca:
                for idx, line in data_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 3.0 and val <= 20.0:
                                marca = num
                                break
                    if marca:
                        break
            vent = extract_jump_wind(lines, athlete_block['name_line_idx'], sec_end)
            if vent:
                wind = vent
    elif event_type == "height":
        if new_format:
            marca = extract_height_result_new(lines, athlete_block, sec_end)
        else:
            # Limit search to first 8 data_lines to avoid picking up other athletes' results
            for idx, line in data_lines[:8]:
                fwd = line.strip()
                if not fwd:
                    continue
                skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                               'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                               'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                if any(label in fwd for label in skip_labels):
                    continue
                # Try MMT/MMP marker format first
                height_match = re.search(r'([\d]+\.[\d]{2})\s+(?:MMT|MMP)?\s*(?:\d+\.\d)?', fwd)
                if height_match:
                    val = height_match.group(1)
                    num_val = float(val)
                    if num_val >= 1.0 and num_val <= 7.0:
                        marca = val
                        break
                # Conersys format: height result at end of line, before percentage
                # Pattern: "1.60       10 78,90%" - find the last height value before percentage
                pct_match = re.search(r'(\d+[,\.]\d+)%', fwd)
                if pct_match:
                    before_pct = fwd[:pct_match.start()]
                    nums = re.findall(r'(\d+\.\d{2})', before_pct)
                    for num in reversed(nums):
                        val = float(num)
                        if val >= 1.0 and val <= 7.0:
                            marca = num
                            break
                if marca:
                    break
            # Fallback: look for height values on lines that are just numbers (the result line)
            if not marca:
                for idx, line in data_lines[:8]:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    # Look for a line that is just a height value (e.g., "1.34")
                    if re.match(r'^[\d]+\.[\d]{2}$', fwd):
                        val = float(fwd)
                        if 1.0 <= val <= 7.0:
                            marca = fwd
                            break
    elif event_type == "field":
        if new_format:
            marca = extract_field_result_new(lines, athlete_block, sec_end)
        else:
            # First check the anchor line (position + club + CATT + results)
            # In old format, field results are on the anchor line itself
            anchor_text = athlete_block['position_line']
            if anchor_text:
                nums = re.findall(r'(\d+\.\d{2})', anchor_text)
                if nums:
                    for num in reversed(nums):
                        val = float(num)
                        if val >= 3.0 and val <= 80.0:
                            marca = num
                            break
            
            # Then check the name line
            if not marca:
                marca = extract_result_from_name_line(lines, athlete_block['name_line_idx'], sec_end, "field")
            
            # Also check data_lines
            if not marca:
                for idx, line in data_lines:
                    fwd = line.strip()
                    if not fwd:
                        continue
                    skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                                   'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                                   'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                    if any(label in fwd for label in skip_labels):
                        continue
                    nums = re.findall(r'(\d+\.\d{2})', fwd)
                    if nums:
                        for num in reversed(nums):
                            val = float(num)
                            if val >= 3.0 and val <= 80.0:
                                marca = num
                                break
                    if marca:
                        break
    elif event_type == "unknown":
        # Fallback: try to extract field results (covers unclassified throw/jump events)
        anchor_text = athlete_block['position_line']
        if anchor_text:
            nums = re.findall(r'(\d+\.\d{2})', anchor_text)
            if nums:
                for num in reversed(nums):
                    val = float(num)
                    if val >= 3.0 and val <= 80.0:
                        marca = num
                        break
        if not marca:
            for idx, line in data_lines:
                fwd = line.strip()
                if not fwd:
                    continue
                skip_labels = ['Puesto', 'Dorsal', 'Club', 'Nombre', 'Fecha', 'Licencia',
                               'RESULT', 'Calle', 'Hora', 'Leyenda', 'Resultado', 'Serie',
                               'Gestion', 'Pagina', 'SUMARIO', 'Rank']
                if any(label in fwd for label in skip_labels):
                    continue
                nums = re.findall(r'(\d+\.\d{2})', fwd)
                if nums:
                    for num in reversed(nums):
                        val = float(num)
                        if val >= 3.0 and val <= 80.0:
                            marca = num
                            break
                if marca:
                    break

    marca = re.sub(r'\s+(MMT|MMP|DNS|DQ|RT.*)$', '', marca).strip()

    # For jump and field events, extract all valid attempts and create one entry per attempt
    if event_type in ("jump", "field"):
        # Determine min/max range based on sub-type
        if event_type == "jump":
            min_v, max_v = 3.0, 20.0
        else:
            min_v, max_v = 3.0, 80.0
        
        best_mark, attempts = extract_all_attempts_from_name_line(
            lines, athlete_block.get('name_line_idx', sec_start), sec_end, event_type, min_v, max_v
        )
        
        # For field events, attempts might be on the anchor line (not name line)
        if not attempts and event_type == "field" and not new_format:
            anchor_text = athlete_block.get('position_line', '')
            # Find text after CATT/CA Tarragona
            club_match = re.search(r'(?:CATT|CA\s+Tarragona)\s*', anchor_text)
            if club_match:
                after_club = anchor_text[club_match.end():]
                tokens = after_club.split()
                field_attempts = []
                for token in tokens:
                    token = token.strip()
                    if token in ('X', 'x', 'r', '-', 'MMT', 'MMP', '=MMT', '=MMP'):
                        continue
                    if re.match(r'^\d+\.\d{2}$', token):
                        val = float(token)
                        if min_v <= val <= max_v:
                            field_attempts.append(token)
                if field_attempts:
                    # Last value is usually the Resultado (best mark) - skip it
                    best_val = max(field_attempts, key=float)
                    if field_attempts[-1] == best_val and len(field_attempts) > 1:
                        field_attempts = field_attempts[:-1]
                    if field_attempts:
                        attempts = []
                        for i, val in enumerate(field_attempts):
                            attempts.append({
                                "attempt": i + 1,
                                "value": val,
                                "wind": None,
                            })
                        best_mark = best_val
        
        if attempts:
            result_list = []
            for att in attempts:
                result_list.append({
                    "lloc": lloc,
                    "prova": event_name,
                    "competicio": competicio,
                    "data": data_comp,
                    "atleta_nom": name,
                    "atleta_naixement": birth_date,
                    "atleta_licencia": licencia,
                    "marca": att["value"],
                    "vent": att["wind"],
                })
            return result_list
        # Fallback: if no attempts extracted, return single entry with best mark
        return [{
            "lloc": lloc,
            "prova": event_name,
            "competicio": competicio,
            "data": data_comp,
            "atleta_nom": name,
            "atleta_naixement": birth_date,
            "atleta_licencia": licencia,
            "marca": best_mark if best_mark else marca,
            "vent": wind,
        }]
    
    return [{
        "lloc": lloc,
        "prova": event_name,
        "competicio": competicio,
        "data": data_comp,
        "atleta_nom": name,
        "atleta_naixement": birth_date,
        "atleta_licencia": licencia,
        "marca": marca,
        "vent": wind,
    }]


def parse_combined_section(lines, sec_start, sec_end, event_name, competicio, data_comp):
    """Parse a combined events section (pentathlon/heptathlon).
    
    Format:
      Puesto Dorsal Nombre  Club   60m va... 1.000m... Altura...  Puntos  P.Líder
    
      1   479   ANTONI CREUS MELGOSA        9.94   3:41.07   1.45   10.54   4.48   3458
              20/11/1964      JASB
              JA Sabadell                  818,0... 650,0(1) 696,0(1) 662,0(1) 632,0(1)
    
    The name line contains: position, dorsal, name, individual event results, total points
    The DOB line contains: DOB, club code (CATT, JASB, etc.)
    The club line contains: club name, points per event
    
    We extract: name, birth_date, position, total points as performance, event name
    """
    results = []
    
    i = sec_start
    while i < min(sec_end, len(lines)):
        line = lines[i].strip()
        
        # Skip empty lines and headers
        if not line:
            i += 1
            continue
        
        # Skip header table labels
        if 'Puesto' in line and 'Dorsal' in line and 'Nombre' in line:
            i += 1
            continue
        
        # Skip "Resultados" or similar
        if line in ('RESULTADOS', 'Resultados'):
            i += 1
            continue
        
        # Look for athlete name lines with results + points
        # Two formats:
        #   With puesto: "  1   479   NAME  results  points" (small puesto + large dorsal)
        #   Without puesto: "      392   NAME  results  points" (only large dorsal)
        # Also handle DNS lines: "      371   ADA TELLO HIDALGO            10.09       DNS        DNS        DNS        DNS"
        
        # First try to match with puesto: small number (1-2 digits) + dorsal (2+ digits) + name
        pos_match = re.match(r'^\s*(\d{1,2})\s+(\d{2,})\s+(.+)$', line)
        if pos_match:
            pos = int(pos_match.group(1))
            rest = pos_match.group(3).strip()
        else:
            # No puesto, just dorsal + name
            no_pos_match = re.match(r'^\s+(\d{2,})\s+(.+)$', line)
            if not no_pos_match:
                i += 1
                continue
            pos = 0
            rest = no_pos_match.group(2).strip()
        
        # Check if this is a DNS-only line (no actual results, all DNS/0)
        # DNS lines have repeated DNS or all zeros
        if re.search(r'\bDNS\b', rest, re.IGNORECASE):
            # Check if there are any actual numeric results (not just DNS)
            # If the line only has DNS and no real results, skip
            non_dns = re.sub(r'\bDNS\b', '', rest, flags=re.IGNORECASE)
            non_dns = re.sub(r'\s+', '', non_dns)
            if not non_dns or non_dns == '':
                i += 1
                continue
        
        # The name must contain letters (not just numbers - skip cumulative points lines)
        if not re.search(r'[A-ZÀ-ÖØ-öø-ÿ]', rest, re.IGNORECASE):
            i += 1
            continue
        
        # Check if CATT/CA Tarragona is on this line or the immediately next non-empty line
        is_catt = 'CATT' in line or 'CA Tarragona' in line
        if not is_catt:
            for j in range(i + 1, min(i + 2, sec_end)):
                next_line = lines[j].strip()
                if next_line and ('CATT' in next_line or 'CA Tarragona' in next_line):
                    is_catt = True
                    break
        
        if not is_catt:
            i += 1
            continue
        
        # Extract name from rest - remove any numeric results
        # The name line format: NAME result1 result2 ... total_points
        # Results can be: 11.96, 3:46.17, 1.33, 7.96, 4.18
        
        # Try to extract total points from end of line (3-4 digit number)
        points_match = re.search(r'\s+(\d{3,4})\s*$', rest)
        total_points = ""
        if points_match:
            total_points = points_match.group(1)
            rest = rest[:points_match.start()].strip()
        
        # Remove time format results (e.g., 3:46.17)
        rest = re.sub(r'\s+\d{1,2}:\d{2}\.\d{2}', '', rest).strip()
        # Remove truncated time results (e.g., 3:07.… with ellipsis)
        rest = re.sub(r'\s+\d{1,2}:\d{2}[.\u2026]+\s*', ' ', rest).strip()
        # Remove decimal number results (e.g., 11.96, 1.33, 7.96, 4.18)
        rest = re.sub(r'\s+\d+\.\d{2,3}', '', rest).strip()
        # Remove percentage values (e.g., 70,41%)
        rest = re.sub(r'\s+\d+[,\.]\d+%\s*', ' ', rest).strip()
        # Remove any remaining numbers
        rest = re.sub(r'\s+\d+\s*$', '', rest).strip()
        
        name = ' '.join(rest.split())
        
        if not name or len(name) < 3:
            i += 1
            continue
        
        # Extract birth date and license from DOB line
        birth_date = ""
        license = ""
        
        for j in range(i + 1, min(i + 3, sec_end)):
            next_line = lines[j].strip()
            if not next_line:
                continue
            bd_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', next_line)
            if bd_match:
                birth_date = bd_match.group(1)
                # Try to extract license from this line
                lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', next_line)
                if lic_match:
                    license = lic_match.group(1).strip()
                    license = re.sub(r'[\.\-]+\s*$', '', license)
                break
        
        # Try to extract license from club line and subsequent lines
        if not license:
            for j in range(i + 2, min(i + 6, sec_end)):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                if re.search(r'\d{1,2}/\d{1,2}/\d{4}', next_line):
                    continue
                lic_match = re.search(r'\b(CL\d+|CT[\d\-]+|CAT\-\d+[A\-\.]*|IB\-\d+[A\-\.]*)\b', next_line)
                if lic_match:
                    license = lic_match.group(1).strip()
                    license = re.sub(r'[\.\-]+\s*$', '', license)
                    break
        
        results.append({
            "lloc": pos,
            "prova": event_name,
            "competicio": competicio,
            "data": data_comp,
            "atleta_nom": name,
            "atleta_naixement": birth_date,
            "atleta_licencia": license,
            "marca": total_points,
            "vent": None,
        })
        
        i += 1
    
    return results


def parse_relay_section(lines, sec_start, sec_end, event_name, competicio, data_comp):
    """Parse relay section. Returns one result per athlete in the CATT team."""
    results = []

    # Find the CATT team block
    # Format:
    #   5  19  CA Tarragona  CATT  3  43.85  8
    #   20  Hugo Jules SAIZ SANTOLARIA  Hombre
    #   19  Ismael VALLES FERNANDEZ  Hombre
    #   19  Jan SANS RIOLA  Hombre
    #        Unai ORTIZ DE LANDAZURI ONTOSO  Hombre

    catt_team_start = None
    catt_team_result = None

    for i in range(sec_start, min(sec_end, len(lines))):
        line = lines[i]
        # Check for CATT team line: has position + CATT or CA Tarragona + result
        if (re.search(r'\bCATT\b', line) or re.search(r'\bCA\s+Tarragona\b', line)):
            pos = extract_position(line)
            if pos is not None:
                catt_team_start = i
                # Extract team result from this line
                result_match = re.search(r'(\d{1,2}:\d{2}\.\d{2}|\d+\.\d{2}|DNF|DNS|DQ)', line)
                if result_match:
                    catt_team_result = result_match.group(1).strip()
                break

    if catt_team_start is None:
        return results

    # Find all athlete names after the CATT team line
    # Athletes are listed with format: "dorsal NAME Gender" or "NAME Gender"
    # A new team block starts with: "pos  dorsal  CLUB_NAME  CLUB_CODE"
    # Match any team block line: position + dorsal + any text + short uppercase club code (2-4 chars)
    athletes = []
    team_line_pattern = re.compile(r'^\s*\d+\s+\d+\s+.+?\s+[A-Z]{2,4}\b')
    
    for i in range(catt_team_start + 1, min(sec_end, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # Check if we've hit the next team (new team block line)
        if team_line_pattern.match(line):
            break

        # Skip header-like lines
        skip_labels = ['Puesto', 'Dorsal', 'Club', 'Calle', 'Ord', 'Serie',
                       'Result', 'Viento', 'Leyenda', 'Hora', 'RESULT',
                       'Nombre', 'Fecha', 'Licencia', 'RESULTADOS',
                       'Gestion', 'Pagina', 'SUMARIO', 'Rank']
        if any(label in line for label in skip_labels):
            continue

        # Match athlete name lines: "dorsal NAME Gender" or "NAME Gender"
        # Gender is "Hombre" or "Mujer"
        athlete_match = re.search(r'(?:\d+\s+)?(.+?)\s+(?:Hombre|Mujer)\s*$', line)
        if athlete_match:
            athlete_name = athlete_match.group(1).strip()
            # Clean up the name
            athlete_name = ' '.join(athlete_name.split())
            if athlete_name and len(athlete_name) > 3:
                athletes.append(athlete_name)

    # Find license for the team
    licencia = ""
    for i in range(catt_team_start, min(catt_team_start + 10, sec_end)):
        lic = extract_license(lines, i, min(i + 5, sec_end))
        if lic:
            licencia = lic
            break

    # Get position
    team_line = lines[catt_team_start]
    lloc = extract_position(team_line)

    # Create one result per athlete
    for athlete_name in athletes:
        results.append({
            "lloc": lloc,
            "prova": event_name,
            "competicio": competicio,
            "data": data_comp,
            "atleta_nom": athlete_name,
            "atleta_naixement": "",
            "atleta_licencia": licencia,
            "marca": catt_team_result or "",
            "vent": None,
        })

    return results


def parse_with_section_aware(text, competicio, data_comp):
    results = []
    lines = text.split('\n')

    sections = find_section_boundaries(lines)

    for sec_idx in range(len(sections) - 1):
        sec_start, sec_name = sections[sec_idx]
        sec_end = sections[sec_idx + 1][0]

        if not sec_name.strip():
            continue

        event_type = classify_event(sec_name)

        # Handle relay events differently
        if event_type == "relay":
            relay_results = parse_relay_section(lines, sec_start, sec_end, sec_name.strip(), competicio, data_comp)
            results.extend(relay_results)
            continue

        # Handle combined events differently
        if event_type == "combined":
            combined_results = parse_combined_section(lines, sec_start, sec_end, sec_name.strip(), competicio, data_comp)
            results.extend(combined_results)
            continue

        # Check if this section starts with SUMARIO - if so, skip regular parsing
        # (SUMARIO sections are handled separately by parse_sumario_section)
        is_sumario = False
        for j in range(sec_start, min(sec_start + 20, sec_end)):
            if 'SUMARIO' in lines[j].upper():
                is_sumario = True
                break
        if is_sumario:
            continue

        # Find CATT athletes in this section
        catt_athletes = find_catt_athletes_in_section(lines, sec_start, sec_end)
        if not catt_athletes:
            continue

        for athlete_block in catt_athletes:
            # Extract wind closest to this athlete's position line
            # (handles multiple heats with different wind values)
            athlete_wind = None
            pos_line_idx = athlete_block.get('position_line_idx', athlete_block.get('name_line_idx', sec_start))
            for j in range(pos_line_idx - 1, max(sec_start - 1, 0), -1):
                wind_match = re.search(r'Viento:\s*([+-]?\d+\.\d)', lines[j])
                if wind_match:
                    athlete_wind = wind_match.group(1)
                    break

            athletes = parse_catt_athlete(
                lines, athlete_block, sec_start, sec_end, sec_name.strip(), athlete_wind,
                event_type, competicio, data_comp
            )
            if athletes:
                results.extend(athletes)

    # Also process SUMARIO sections (track events with series)
    sumarios = find_sumario_sections(lines)
    for sumario_idx, event_name in sumarios:
        # Find the end of this sumario section - stop at next event section header
        # or next SUMARIO, whichever comes first
        sec_end = len(lines)
        for j in range(sumario_idx + 1, min(sumario_idx + 500, len(lines))):
            stripped = lines[j].strip()
            # Stop at next SUMARIO
            if 'SUMARIO' in stripped:
                sec_end = j
                break
            # Stop at page boundary
            if 'Página' in stripped:
                # Look ahead for next event
                for k in range(j + 1, min(j + 10, len(lines))):
                    if lines[k].strip() and 'Página' not in lines[k] and 'Gestión' not in lines[k] and 'Leyenda' not in lines[k]:
                        next_line = lines[k].strip()
                        if re.search(r'\d+m\s*(\.\d+)?\s*(vallas)?\s*(Marcha)?\s*(Hombres|Mujeres|Mixto)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'4x\d+m\s+(Hombres|Mujeres|Mixto)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'(Altura|Pértiga)\s+(Hombres|Mujeres)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'(Triple\s+Salto|Disco|Martillo|Peso|Jabalina|Longitud)\s+(Hombres|Mujeres)', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        if re.search(r'5\.?000m\s+Marcha', next_line, re.IGNORECASE):
                            sec_end = k
                            break
                        break
                continue
            # Stop at next event section header
            # Pattern 1: "HH:MM   EventName" format (schedule lines)
            if re.search(r'^\d{2}:\d{2}\s+', stripped):
                # Check if this is an event name
                for pattern in EVENT_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        sec_end = j
                        break
                if sec_end != len(lines):
                    break
                continue
            # Pattern 2: Event name after page header (date line)
            # Check if this line matches an event pattern AND is preceded by a date
            for pattern in EVENT_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    # Check if previous lines contain a date (page header)
                    is_page_header = False
                    for k in range(j - 1, max(j - 6, 0), -1):
                        if re.search(r'\d{2}/\d{2}/\d{4}', lines[k]):
                            is_page_header = True
                            break
                        if lines[k].strip() and 'Página' in lines[k]:
                            break
                    if is_page_header:
                        sec_end = j
                        break
            if sec_end != len(lines):
                break
        
        sumario_results = parse_sumario_section(lines, sumario_idx + 1, event_name, sec_end, competicio, data_comp)
        results.extend(sumario_results)

    return results


def deduplicate_results(results):
    """Remove duplicates, keeping the best entry (final over series, result over DQ/DNS).
    
    If the same athlete has multiple entries for the same event with DIFFERENT valid marks,
    keep them all (they represent different series: Eliminatoria, Semifinal, Final, etc.).
    Only deduplicate when entries have the same mark.
    """
    groups = {}
    for r in results:
        key = (r["atleta_nom"].lower(), r["prova"].lower())
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    unique = []
    for key, entries in groups.items():
        if len(entries) == 1:
            entry = entries[0]
            entry["atleta_nom"] = re.sub(r'\s+RT\s*$', '', entry["atleta_nom"]).strip()
            unique.append(entry)
            continue

        with_result = [e for e in entries if e["marca"] and e["marca"] not in ("DQ", "DNS", "")]
        without_result = [e for e in entries if not e["marca"] or e["marca"] in ("DQ", "DNS")]

        if with_result:
            # Check if there are multiple different marks (different series)
            unique_marks = list(set(e["marca"] for e in with_result))
            
            if len(unique_marks) > 1:
                # Multiple different marks = different series, keep all unique marks
                # For duplicate marks, keep the best position
                seen_marks = {}
                for e in with_result:
                    mark = e["marca"]
                    if mark not in seen_marks:
                        seen_marks[mark] = e
                    else:
                        # Keep the one with better position
                        existing_pos = seen_marks[mark]["lloc"] if seen_marks[mark]["lloc"] is not None else 999
                        new_pos = e["lloc"] if e["lloc"] is not None else 999
                        if new_pos < existing_pos:
                            seen_marks[mark] = e
                for e in seen_marks.values():
                    e["atleta_nom"] = re.sub(r'\s+RT\s*$', '', e["atleta_nom"]).strip()
                    unique.append(e)
            else:
                # Same mark, deduplicate to best entry
                with_wind = [e for e in with_result if e["vent"] is not None]
                if with_wind:
                    best = min(with_wind, key=lambda e: e["lloc"] if e["lloc"] is not None else 999)
                else:
                    with_pos = [e for e in with_result if e["lloc"] is not None]
                    if with_pos:
                        best = min(with_pos, key=lambda e: e["lloc"])
                    else:
                        best = with_result[0]
                best["atleta_nom"] = re.sub(r'\s+RT\s*$', '', best["atleta_nom"]).strip()
                unique.append(best)
            
            # Don't add DNS/DQ entries when we already have a valid result
        # Skip DNS/DQ entries entirely - they don't represent actual results

    return unique


def _reconstruct_url(pdf_path: str) -> str:
    """Try to reconstruct a known URL from the local PDF filename."""
    filename = os.path.basename(pdf_path)
    filename_lower = filename.lower()
    # Known RFEA URL patterns
    rfea_patterns = [
        ("2d_hombres", "https://www.rfeacontent.es/resultados/2026/airelibre/clubes/{}"),
        ("2d_mujeres", "https://www.rfeacontent.es/resultados/2026/airelibre/clubes/{}"),
        ("2d_hombre", "https://www.rfeacontent.es/resultados/2026/airelibre/clubes/{}"),
        ("2d_mujer", "https://www.rfeacontent.es/resultados/2026/airelibre/clubes/{}"),
    ]
    for pattern_key, url_template in rfea_patterns:
        if pattern_key in filename_lower:
            url = url_template.format(filename)
            # Ensure exactly one .pdf extension
            if not url.endswith(".pdf"):
                url += ".pdf"
            return url
    return ""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_catt.py <pdf_file> [source_url]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    source_url = sys.argv[2] if len(sys.argv) > 2 else ""
    quiet = '--quiet' in sys.argv

    # If no explicit URL provided, try to reconstruct from known patterns
    if not source_url:
        source_url = _reconstruct_url(pdf_path)

    base = os.path.splitext(pdf_path)[0]
    output_path = base + ".json"

    if not quiet:
        print(f"Extracting text from: {pdf_path}")
    text = extract_text(pdf_path)

    if not quiet:
        print("Parsing competition header...")
    competicio, ubicacio, localitat, data = parse_header(text)
    full_competicio = f"{competicio} - {ubicacio}" if ubicacio else competicio
    if not quiet:
        print(f"  Competicio: {competicio or '(no trobat)'}")
        print(f"  Ubicacio: {ubicacio or '(no trobat)'}")
        print(f"  Localitat: {localitat or '(no trobat)'}")
        print(f"  Data: {data or '(no trobat)'}")

    if not quiet:
        print("\nExtracting CATT athlete results...")
    results = parse_with_section_aware(text, full_competicio, data)

    if not quiet:
        print(f"Found {len(results)} result entries for CATT athletes")

    if not quiet:
        for r in results:
            status = "OK" if r["atleta_nom"] and r["marca"] else ("DQ/DNS" if r["atleta_nom"] and not r["marca"] else "INCOMPLETE")
            print(f"  [{status}] {r['atleta_nom'] or '???':35s} | {r['prova'] or '???':25s} | {r['marca'] or '???':12s} | Lloc: {r['lloc']} | Vent: {r['vent']} | Lic: {r['atleta_licencia']}")

    results = deduplicate_results(results)
    if not quiet:
        print(f"\nAfter deduplication: {len(results)} unique results")

    # Validate and filter results - must have athlete_name, performance, and discipline
    valid_results = []
    for r in results:
        name = r.get("atleta_nom", "").strip()
        performance = r.get("marca", "").strip()
        discipline = r.get("prova", "").strip()
        
        if not name or not performance or not discipline:
            missing = []
            if not name:
                missing.append("athlete_name")
            if not performance:
                missing.append("performance")
            if not discipline:
                missing.append("discipline")
            warning = f"WARNING: Skipping entry missing {', '.join(missing)}: prova='{r.get('prova', '???')}', atleta_nom='{r.get('atleta_nom', '???')}', marca='{r.get('marca', '???')}'"
            print(warning, file=sys.stderr)
            continue
        
        valid_results.append(r)

    results = valid_results
    if not quiet:
        print(f"\nAfter validation: {len(results)} valid results")

    # Validate results against event type - filter impossible times/marks
    valid_results = []
    for r in results:
        event_type = classify_event(r.get("prova", ""))
        marca = r.get("marca", "")
        if not marca or marca in ("DQ", "DNS", "DNF"):
            # Skip DNS/DQ/DNF entries - they don't represent actual results
            if not quiet:
                print(f"  Skipping DNS/DQ/DNF: {r.get('atleta_nom', '???')} - {r.get('prova', '???')} ({marca or 'empty'})", file=sys.stderr)
            continue
        
        # Parse the mark value for validation
        try:
            if ':' in marca:
                # HH:MM.ss or MM:SS.ss format
                parts = marca.split(':')
                if len(parts) == 2:
                    seconds = float(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                else:
                    seconds = None
            else:
                seconds = float(marca)
        except (ValueError, IndexError):
            seconds = None
        
        # Validate based on event type
        invalid = False
        if event_type == "track" and seconds is not None:
            # 60m sprints should be under 15 seconds, middle distance under 300 seconds
            # If time > 60 seconds, it's likely a wrong event assignment for a sprint
            event_lower = r.get("prova", "").lower()
            if '60m' in event_lower and seconds > 15:
                if not quiet:
                    print(f"  WARNING: Discarding {r['atleta_nom']} {marca} for {r['prova']} - impossible time for 60m", file=sys.stderr)
                invalid = True
            elif '100m' in event_lower and seconds > 20:
                if not quiet:
                    print(f"  WARNING: Discarding {r['atleta_nom']} {marca} for {r['prova']} - impossible time for 100m", file=sys.stderr)
                invalid = True
            elif '200m' in event_lower and seconds > 40:
                if not quiet:
                    print(f"  WARNING: Discarding {r['atleta_nom']} {marca} for {r['prova']} - impossible time for 200m", file=sys.stderr)
                invalid = True
            elif '400m' in event_lower and seconds > 120:
                if not quiet:
                    print(f"  WARNING: Discarding {r['atleta_nom']} {marca} for {r['prova']} - impossible time for 400m", file=sys.stderr)
                invalid = True
            elif '800m' in event_lower and seconds > 250:
                invalid = True
            elif '1500m' in event_lower or '1.500m' in event_lower and seconds > 500:
                invalid = True
        elif event_type == "jump" and seconds is not None:
            # Jump distances should be reasonable (young athletes can jump very short distances)
            if seconds < 1.5 or seconds > 20:
                invalid = True
        elif event_type == "height" and seconds is not None:
            # Heights should be 1-7m
            if seconds < 1 or seconds > 7:
                invalid = True
        elif event_type == "field" and seconds is not None:
            # Field distances should be 3-80m
            if seconds < 3 or seconds > 80:
                invalid = True
        
        if not invalid:
            valid_results.append(r)
    
    results = valid_results
    if not quiet:
        print(f"After event-type validation: {len(results)} valid results")

    if not results:
        if not quiet:
            print("No results found for CATT athletes. Skipping JSON export.")
        return

    output = {
        "event_name": full_competicio,
        "event_date": data,
        "event_location": localitat,
        "total_results": len(results),
        "event_src": source_url if source_url else os.path.abspath(pdf_path),
        "results": []
    }

    for r in results:
        entry = {
            "athlete_name": r["atleta_nom"],
            "athlete_dob": r["atleta_naixement"],
            "athlete_id": r["atleta_licencia"],
            "performance": r["marca"],
            "discipline": r["prova"],
            "wind": r["vent"],
        }
        output["results"].append(entry)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if not quiet:
        print(f"\nResults written to: {output_path}")

        events = {}
        for r in results:
            if r["prova"] not in events:
                events[r["prova"]] = []
            events[r["prova"]].append(r["atleta_nom"])

        print("\nResum per prova:")
        for prova, atletes in sorted(events.items()):
            print(f"  {prova}: {len(atletes)} atletes")


if __name__ == "__main__":
    main()
