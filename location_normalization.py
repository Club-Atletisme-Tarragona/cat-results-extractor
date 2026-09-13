#!/usr/bin/env python3
"""Canonical venue/location normalization shared by all extractors and scripts.

Two Barcelona venues keep showing up under several spellings in the FCAT
result PDFs, and the same venue was being written to JSON under different
strings (which splits an athlete's results across locations downstream):

  * Estadi Joan Serrahima (outdoor, Barcelona)  -> "Barcelona-SE"
  * Palau Sant Jordi (indoor track, Barcelona)  -> "Barcelona - Palau Sant Jordi"

These are two DIFFERENT venues and must never be merged: a plain
"Barcelona" location is ambiguous between them and is only resolved when the
PDF header names the venue.

Usage:
    python3 location_normalization.py   # runs the self-test
"""

import re

# ---------------------------------------------------------------------------
# Canonical strings
# ---------------------------------------------------------------------------

CANONICAL_SERRAHIMA = "Barcelona-SE"
CANONICAL_PALAU = "Barcelona - Palau Sant Jordi"

# Serrahima variants seen in the data:
#   location : "Serrahima", "Joan Serrahima", "BCN-SE"
#   venue    : "Estadi Joan Serrahima de Barcelona, ...",
#              "Estadio Joan Serrahima, ..."  (Spanish spelling too),
#              "Barcelona (Estadi Joan Serrahima), ...",
#              "Barcelona-Estadi Joan Serrahima, ..."
# The bare "serrahima" substring covers all of them; the BCN..SE token covers
# the short form used in some PDF filenames/headers (BCN-SE / BCN_SE / "BCN SE").
_SERRAHIMA_RE = re.compile(r"serrahima|\bBCN[\s\-_]?SE\b", re.IGNORECASE)

# Palau Sant Jordi is matched on the venue name only, never on "Barcelona".
_PALAU_RE = re.compile(r"palau sant jordi", re.IGNORECASE)

# Newer FCAT result sheets print the venue as its location code instead of the
# stadium name: "Barcelona-SE, 27 febrero 2021". "SE" is the Serrahima venue
# code, so the canonical string appearing in a PDF header is first-party venue
# evidence. Applied by classify_pdf_header() ONLY: normalize_location() keeps
# its documented behaviour ("Barcelona-SE" is already canonical there, so
# returning it unchanged is a no-op either way). PDF layout pads header fields,
# so a mix of spaces and dashes is allowed between the city and the code -- but at
# least one separator is required: FCAT sheets always pad the two fields, and a
# zero-separator match would let unrelated concatenations claim to be the code.
_SERRAHIMA_CODE_RE = re.compile(r"\bBarcelona[\s\-_]+SE\b", re.IGNORECASE)

# Record lines in the results block name where a RECORD was set, not where the
# current meeting is held:
#   "   RCAM   8.23   JEREMIAH OBRO IYAMU   CGTT   Serrahima-BCN   18/06/2022"
# appears inside a Gavà sheet. RCAT/RCAM lines are therefore never venue evidence.
_RECORD_LINE_RE = re.compile(r"^\s*RCA[TM]\b")


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------

def matches_serrahima(text):
    """True if text names the Joan Serrahima stadium in any known variant."""
    if not text:
        return False
    return _SERRAHIMA_RE.search(text) is not None


def matches_palau(text):
    """True if text names the Palau Sant Jordi indoor venue."""
    if not text:
        return False
    return _PALAU_RE.search(text) is not None


def _names_serrahima_in_header(text):
    """Serrahima variant, or the "Barcelona-SE" venue code (header evidence)."""
    if not text:
        return False
    return matches_serrahima(text) or _SERRAHIMA_CODE_RE.search(text) is not None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_location(location):
    """Normalize a standalone location string to its canonical form.

    Serrahima variant -> CANONICAL_SERRAHIMA
    Palau variant     -> CANONICAL_PALAU
    anything else     -> unchanged (stripped); None/empty returned as-is.
    """
    if not location:
        return location
    text = location.strip()
    if matches_serrahima(text):
        return CANONICAL_SERRAHIMA
    if matches_palau(text):
        return CANONICAL_PALAU
    return text


def location_from_header(localitat, ubicacio=""):
    """Extraction-time rule: build the canonical location from the PDF header.

    `ubicacio` is the venue line of the header ("Estadi ...", "Pista ..."),
    `localitat` is the guessed city. The venue line names the stadium
    explicitly, so it wins over the city when it matches a known venue:
    "Estadi Joan Serrahima de Barcelona" is Barcelona-SE even when the city
    guess came out as "Sabadell" or as header garbage.

    A Palau venue only resolves when the city is Barcelona (or unknown),
    otherwise the header is self-contradictory and the city is kept.
    """
    city = (localitat or "").strip()
    venue = (ubicacio or "").strip()

    # 1. Venue line names Serrahima -> always Barcelona-SE.
    if matches_serrahima(venue):
        return CANONICAL_SERRAHIMA
    # 2. Venue line names Palau Sant Jordi, city is Barcelona or unknown.
    if matches_palau(venue) and (not city or city.lower().startswith("barcelona")):
        return CANONICAL_PALAU
    # 3. City itself is a Serrahima variant.
    if matches_serrahima(city):
        return CANONICAL_SERRAHIMA
    # 4/5. Anything else (incl. an already-canonical Palau string) is handled
    # by the plain variant normalizer.
    return normalize_location(localitat)


def classify_pdf_header(text, max_lines=30):
    """Classify a raw pdftotext header into a canonical venue, or None.

    Scans the first `max_lines` lines. Serrahima takes priority over Palau
    (a two-venue championship header mentions both; the outdoor stadium is the
    one this rule is about). Returns None when neither venue is named, so the
    caller can fall back to its city guess.

    RCAT/RCAM record lines are skipped before any venue test: they name the venue
    where a record was set (frequently "Serrahima-BCN", since most records are set
    at Serrahima), which says nothing about where this meeting is held. Without the
    skip, an Igualada/Lleida/Gavà/Can Dragó sheet carrying a Serrahima record line
    is misclassified as Barcelona-SE.
    """
    if not text:
        return None
    lines = text.splitlines()[:max_lines]
    found_palau = False
    for line in lines:
        if _RECORD_LINE_RE.match(line):
            continue
        if _names_serrahima_in_header(line):
            return CANONICAL_SERRAHIMA
        if matches_palau(line):
            found_palau = True
    return CANONICAL_PALAU if found_palau else None


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- normalize_location: Serrahima location variants -------------------
    for variant in ("Serrahima", "Joan Serrahima", "  Joan Serrahima  ",
                    "Estadi Joan Serrahima", "Estadio Joan Serrahima",
                    "BCN-SE", "BCN_SE", "BCN SE", "bcn-se", "bcn_se",
                    "Barcelona (Estadi Joan Serrahima)",
                    "Barcelona-Estadi Joan Serrahima",
                    "Estadi Joan Serrahima de Barcelona"):
        assert normalize_location(variant) == CANONICAL_SERRAHIMA, variant

    # --- normalize_location: Palau variants --------------------------------
    for variant in ("Palau Sant Jordi", "Barcelona - Palau Sant Jordi",
                    "PALAU SANT JORDI", " Barcelona - Palau Sant Jordi "):
        assert normalize_location(variant) == CANONICAL_PALAU, variant

    # --- normalize_location: negatives (must stay untouched) ---------------
    for other in ("Barcelona", "Sabadell", "Tarragona", "Lleida", "Reus",
                  "Pista Mpal. de Atmo. Les Basses", "Sant Joan Despí",
                  "BCN", "SETGAS", "IbSE"):
        assert normalize_location(other) == other.strip(), other

    # --- normalize_location: empty/None-safe -------------------------------
    assert normalize_location("") == ""
    assert normalize_location(None) is None
    assert normalize_location("   ") == ""

    # --- idempotency -------------------------------------------------------
    for sample in ("Joan Serrahima", "Barcelona", CANONICAL_SERRAHIMA,
                   CANONICAL_PALAU, "Palau Sant Jordi", "Sabadell"):
        once = normalize_location(sample)
        assert normalize_location(once) == once, sample

    # --- location_from_header: venue line names Serrahima ------------------
    assert location_from_header("Barcelona",
        "Estadi Joan Serrahima de Barcelona, 5 y 6 de mayo de 2012") == CANONICAL_SERRAHIMA
    assert location_from_header("Sabadell",
        "Estadi Joan Serrahima de Barcelona, 18 marzo 2023") == CANONICAL_SERRAHIMA
    assert location_from_header("Club     Lic    Acum.",
        "Estadio Joan Serrahima, 19 febrero 2023") == CANONICAL_SERRAHIMA
    assert location_from_header("",
        "Barcelona (Estadi Joan Serrahima), 10 junio 2015") == CANONICAL_SERRAHIMA
    assert location_from_header("Barcelona",
        "Barcelona (Estadi Joan Serrahima), 27-28 abril 2019") == CANONICAL_SERRAHIMA
    assert location_from_header("Barcelona",
        "Barcelona-Estadi Joan Serrahima, 27-28 mayo 2017") == CANONICAL_SERRAHIMA
    assert location_from_header("Terrassa",
        "Estadio Joan Serrahima") == CANONICAL_SERRAHIMA
    assert location_from_header("Tarragona", "Controls BCN-SE") == CANONICAL_SERRAHIMA

    # --- location_from_header: city is the Serrahima variant ---------------
    assert location_from_header("Serrahima", "") == CANONICAL_SERRAHIMA
    assert location_from_header("Joan Serrahima", "Pista Municipal") == CANONICAL_SERRAHIMA
    assert location_from_header("BCN-SE", "Estadi") == CANONICAL_SERRAHIMA

    # --- location_from_header: Palau --------------------------------------
    assert location_from_header("Barcelona", "Palau Sant Jordi") == CANONICAL_PALAU
    assert location_from_header("", "Pavelló Palau Sant Jordi") == CANONICAL_PALAU
    assert location_from_header("Barcelona",
        "Palau Sant Jordi, Barcelona") == CANONICAL_PALAU
    # city is not Barcelona -> the venue line alone must not hijack it
    assert location_from_header("Girona", "Palau Sant Jordi") == "Girona"
    # already-canonical city form is preserved exactly
    assert location_from_header("Barcelona - Palau Sant Jordi", "") == CANONICAL_PALAU
    assert location_from_header("Barcelona - Palau Sant Jordi",
        "Pista Coberta") == CANONICAL_PALAU

    # --- location_from_header: fall-through --------------------------------
    assert location_from_header("Sabadell", "Estadi Olímpica Mil·leniari") == "Sabadell"
    assert location_from_header("Barcelona", "") == "Barcelona"
    assert location_from_header("  Tarragona ", "") == "Tarragona"
    assert location_from_header("", "") == ""
    assert location_from_header(None, None) is None

    # --- classify_pdf_header ----------------------------------------------
    serrahima_pdf = "\n".join([
        "CRITÈRIUM CAMPMANY (2a. Jornada)",
        "Barcelona (Estadi Joan Serrahima), 10 junio 2015",
        "10/06/2015",
        "RESULTATS",
    ])
    assert classify_pdf_header(serrahima_pdf) == CANONICAL_SERRAHIMA

    palau_pdf = "\n".join([
        "Control Absolut en pista coberta",
        "Palau Sant Jordi - Barcelona",
        "30/01/2021",
    ])
    assert classify_pdf_header(palau_pdf) == CANONICAL_PALAU

    both_pdf = "\n".join([
        "Campionat de Catalunya",
        "Palau Sant Jordi / Estadi Joan Serrahima",
    ])
    assert classify_pdf_header(both_pdf) == CANONICAL_SERRAHIMA

    token_pdf = "\n".join(["Control de controls", "BCN_SE", "22/05/2014"])
    assert classify_pdf_header(token_pdf) == CANONICAL_SERRAHIMA

    # venue printed as the canonical location code (newer FCAT sheets)
    code_pdf = "\n".join(["Control Nacional Preparació Temporada Indoor 2021",
                          "Barcelona-SE, 27 febrero 2021",
                          "60m MASC. AL abs"])
    assert classify_pdf_header(code_pdf) == CANONICAL_SERRAHIMA
    # a city line without a venue code is not venue evidence
    assert classify_pdf_header("Troballes\nTarragona, 12 de maig") is None
    # the venue code is header evidence only: normalize_location leaves the
    # canonical string untouched (idempotency) ...
    assert normalize_location(CANONICAL_SERRAHIMA) == CANONICAL_SERRAHIMA
    # ... and a bare "Barcelona" is never upgraded by the code rule
    assert normalize_location("Barcelona") == "Barcelona"
    assert location_from_header("Barcelona", "Pista Municipal") == "Barcelona"
    assert classify_pdf_header("Campionat\nBarcelona - Segunda Division") is None
    assert classify_pdf_header("Campionat\n     Barcelona - SE, 9 de febrer") == CANONICAL_SERRAHIMA
    # the venue code needs a separator between the city and the code ...
    for padded in ("Campionat\nBarcelona-SE, 9 de febrer",
                   "Campionat\nBarcelona - SE, 9 de febrer",
                   "Campionat\nBarcelona_SE, 9 de febrer"):
        assert classify_pdf_header(padded) == CANONICAL_SERRAHIMA, padded
    # ... the zero-separator concatenations are not venue evidence
    for glued in ("Campionat\nBarcelonaSE, 9 de febrer",
                  "Campionat\nBarcelonase, 9 de febrer"):
        assert classify_pdf_header(glued) is None, glued

    # --- classify_pdf_header: RCAT/RCAM record lines are never venue evidence ---
    # The real false positives: a meet in Gavà whose results block quotes the
    # catalan/spanish records, one of them set at Serrahima.
    gava_records_pdf = "\n".join([
        "Jornada Prèvia Campionat de Catalunya Sub12",
        "Gavà - Estadi Municipal La Bóbila, 1 junio 2024",
        "60m SUB12 MASC. AL",
        "   RCAM                                     8.23    JEREMIAH OBRO IYAMU"
        "                          CGTT     Serrahima-BCN   18/06/2022",
        "   RCAT                                     8.13    VICTOR BARRADO OMENAT"
        "                          CDUB     Gavà          16/06/2018",
    ])
    assert classify_pdf_header(gava_records_pdf) is None
    assert classify_pdf_header("\n".join([
        "Campionat de Catalunya Sub18 i Sub20",
        "Igualada, 26 de septiembre de 2020",
        "   RCAT     10.45     ARNAU MONNE CANAL       FCBB   Borås (SWE)      18/07/2019",
        "   RCAM     10.54     JOAN MARTINEZ PEÑALVER  NNAB   Serrahima-BCN    02/06/2018",
    ])) is None
    # a record line mentioning Serrahima is not evidence even with no city header
    assert classify_pdf_header("Campionat\n   RCAM   8.23   NOM APELLIDO   CGTT   "
                               "Serrahima-BCN   18/06/2022") is None
    assert classify_pdf_header("Campionat\n   RCAT   10.16   NOM APELLIDO   CAICS   "
                               "Serrahima-BCN   21/07/2018") is None
    # real venue evidence still wins when the sheet also carries record lines
    assert classify_pdf_header("\n".join([
        "Campionat de Catalunya absolut",
        "Estadi Joan Serrahima, Barcelona, 12 de julio de 2025",
        "   RCAT     10.16     PATRICK CHINEDU IKE ORIGA   CAICS   Getafe         21/07/2018",
        "   RCAM     10.46     JOSE ILLAN BLANCO           NIKE    Serrahima-BCN  04/07/1999",
    ])) == CANONICAL_SERRAHIMA
    # and record lines must not hijack a Palau sheet towards Serrahima either
    assert classify_pdf_header("\n".join([
        "Control Pista Coberta",
        "Palau Sant Jordi - Barcelona",
        "   RCAM      6.60     ALGUN NOM               QQ    Serrahima-BCN   01/02/2020",
    ])) == CANONICAL_PALAU

    other_pdf = "\n".join([
        "Campionat de Catalunya absolut",
        "Pista Mpal. de Atmo. Les Basses",
        "Lleida, 12 de julio de 2025",
    ])
    assert classify_pdf_header(other_pdf) is None
    assert classify_pdf_header("") is None
    assert classify_pdf_header(None) is None

    # deep Serrahima mention below the header window is ignored
    deep_pdf = "\n".join(["Lleida, 12 de julio"] + ["noise"] * 30
                          + ["Estadi Joan Serrahima"])
    assert classify_pdf_header(deep_pdf) is None

    print("OK")
