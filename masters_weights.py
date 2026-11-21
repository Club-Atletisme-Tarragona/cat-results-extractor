"""Masters implement weights from the RFEA 2026 general master regulations.

Source (issue #30, supplied by the owner):
<https://atletismorfea.es/sites/default/files/2025-12/NormasGeneralesMaster2026.pdf>

The page titled "Categoría / Peso / Disco / Jabalina / Martillo / Martillo
Pesado" is quoted verbatim in `odd/tasks/masters-implement-weights.md` (S1) and
is the only authority for the numbers below; do not re-derive them from the web:

    HOMBRES   35-49   peso 7,26  disco 2,00  jabalina 800g  martillo 7,26  pesado 15,88
              50-59        6,00       1,50           700g          6,00        11,34
              60-69        5,00       1,00           600g          5,00         9,08
              70-79        4,00       1,00           500g          4,00         7,26
              80+          3,00       1,00           400g          3,00         5,45
    MUJERES   35-49        4,00       1,00           600g          4,00         9,08
              50-59        3,00       1,00           500g          3,00         7,26
              60-74        3,00       1,00           500g          3,00         5,45
              75+          2,00      750g            400g          2,00         4,00

Weights are stored in kilograms (javelina/disc grams converted) so a single
comparison works for every implement. `HEAVY_HAMMER_LABELS` pins the
DISCIPLINES.md spellings for the heavy hammer ("Martell pesat (… Kg)") — that
file stays the vocabulary (task S3); no new spelling may be invented here.

**Precedence (S8-S10, owner rule L5):** the table is only the FALLBACK. When a
sheet prints the implement weight, that printed weight is stored even when it
contradicts the regulation; `resolve_implement_weight()` returns both the
weight and the authority that decided it, and `decide_implement_label()` is the
one place that turns a raw section header into a label. The discriminator is
the header text (`raw_discipline_name`), never the stored `discipline`.

This module is pure data + pure helpers (stdlib only, no I/O).
"""

import re

# ---------------------------------------------------------------------------
# S1 — the regulation table, encoded once.
# ---------------------------------------------------------------------------

#: (sex, band, implement) -> weight in kg.
RFEA_2026_WEIGHTS = {
    ("m", "35-49"): {"pes": 7.26, "disc": 2.00, "javelina": 0.800,
                     "martell": 7.26, "martell_pesat": 15.88},
    ("m", "50-59"): {"pes": 6.00, "disc": 1.50, "javelina": 0.700,
                     "martell": 6.00, "martell_pesat": 11.34},
    ("m", "60-69"): {"pes": 5.00, "disc": 1.00, "javelina": 0.600,
                     "martell": 5.00, "martell_pesat": 9.08},
    ("m", "70-79"): {"pes": 4.00, "disc": 1.00, "javelina": 0.500,
                     "martell": 4.00, "martell_pesat": 7.26},
    ("m", "80+"): {"pes": 3.00, "disc": 1.00, "javelina": 0.400,
                   "martell": 3.00, "martell_pesat": 5.45},
    ("f", "35-49"): {"pes": 4.00, "disc": 1.00, "javelina": 0.600,
                     "martell": 4.00, "martell_pesat": 9.08},
    ("f", "50-59"): {"pes": 3.00, "disc": 1.00, "javelina": 0.500,
                     "martell": 3.00, "martell_pesat": 7.26},
    ("f", "60-74"): {"pes": 3.00, "disc": 1.00, "javelina": 0.500,
                     "martell": 3.00, "martell_pesat": 5.45},
    ("f", "75+"): {"pes": 2.00, "disc": 0.75, "javelina": 0.400,
                   "martell": 2.00, "martell_pesat": 4.00},
}

#: Age bands per sex, in the regulation's own wording: (min, max|None, label).
MASTERS_BANDS = {
    "m": ((35, 49, "35-49"), (50, 59, "50-59"), (60, 69, "60-69"),
          (70, 79, "70-79"), (80, None, "80+")),
    "f": ((35, 49, "35-49"), (50, 59, "50-59"), (60, 74, "60-74"),
          (75, None, "75+")),
}

#: DISCIPLINES.md spellings for the heavy hammer, keyed by weight in kg.
#: Never invent a spelling: these six labels are the whole vocabulary.
HEAVY_HAMMER_LABELS = {
    4.00: "Martell pesat (4 Kg)",
    5.45: "Martell pesat (5.45 Kg)",
    7.26: "Martell pesat (7.26 Kg)",
    9.08: "Martell pesat (9.08 Kg)",
    11.34: "Martell pesat (11.34 Kg)",
    15.88: "Martell pesat (15.88 Kg)",
}

#: Implement keys, as used in RFEA_2026_WEIGHTS.
IMPLEMENTS = ("pes", "disc", "javelina", "martell", "martell_pesat")


# ---------------------------------------------------------------------------
# Age / category resolution (S1: "derive category bands from the meet-relative
# age — category label when the sheet prints one, otherwise DOB + event_date").
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def parse_date(text):
    """'D/M/YYYY' / 'DD/MM/YYYY' -> (year, month, day) or None."""
    m = _DATE_RE.search(str(text or ""))
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return year, month, day


def age_on(dob, event_date):
    """Whole-year age on the day of the meet, or None if a date is missing."""
    birth = parse_date(dob)
    meet = parse_date(event_date)
    if not birth or not meet:
        return None
    years = meet[0] - birth[0]
    if (meet[1], meet[2]) < (birth[1], birth[2]):
        years -= 1
    return years if years >= 0 else None


def band_for_age(sex, age):
    """Band label ('35-49', '80+', …) for a sex/age, or None below masters."""
    if sex not in MASTERS_BANDS or age is None or age < 35:
        return None
    for low, high, label in MASTERS_BANDS[sex]:
        if age >= low and (high is None or age <= high):
            return label
    return None


def expected_weight(sex, age, implement):
    """Regulation weight (kg) for a sex/age/implement, or None."""
    band = band_for_age(sex, age)
    if band is None or implement not in IMPLEMENTS:
        return None
    return RFEA_2026_WEIGHTS[(sex, band)][implement]


def _label_key(weight):
    """Float key for HEAVY_HAMMER_LABELS (2-decimal regulation values)."""
    return round(float(weight) + 0.0, 2)


def heavy_hammer_label_for(sex, age):
    """DISCIPLINES.md heavy-hammer label for a sex/age, or None."""
    weight = expected_weight(sex, age, "martell_pesat")
    if weight is None:
        return None
    return HEAVY_HAMMER_LABELS.get(_label_key(weight))


# ---------------------------------------------------------------------------
# Sex / category evidence printed in a section header.
# ---------------------------------------------------------------------------

_MALE_WORD_RE = re.compile(r"\b(?:mascul\w*|masc|homes|hombres)\b", re.IGNORECASE)
#: 'MASC.' / 'MAS.' are the sheets' own uppercase sex abbreviations; restricted
#: to uppercase so the Catalan word 'mas' can never be read as a sex.
_MALE_ABBREV_RE = re.compile(r"\bMAS\b|\bMASC\b")
_FEMALE_WORD_RE = re.compile(r"\b(?:femen\w*|fem|dones|mujeres)\b", re.IGNORECASE)
# 'M75', 'M-35', 'W-75', 'F 55', 'M.70' — the letter is the sex marker.
_LETTER_CATEGORY_RE = re.compile(r"\b([MWF])\s*[-–—.]?\s*(\d{2})(?!\d)",
                                 re.IGNORECASE)
# '40-44', '60-74' — sex must come from a word or a letter category.
_AGE_RANGE_RE = re.compile(r"\b(\d{2})\s*[-–—]\s*(\d{2})\b")


def parse_sex_and_category(text):
    """(sex, age) evidence printed in a header; unknowns are None.

    The age is the lower bound of the printed category. A header whose word
    sex and letter sex disagree is reported as unknown — never guess.
    """
    t = str(text or "")
    sex_word = None
    if _MALE_WORD_RE.search(t) or _MALE_ABBREV_RE.search(t):
        sex_word = "m"
    elif _FEMALE_WORD_RE.search(t):
        sex_word = "f"

    sex_letter = None
    age = None
    m = _LETTER_CATEGORY_RE.search(t)
    if m:
        sex_letter = "m" if m.group(1).upper() == "M" else "f"
        age = int(m.group(2))
    else:
        r = _AGE_RANGE_RE.search(t)
        if r:
            age = int(r.group(1))

    if sex_word and sex_letter and sex_word != sex_letter:
        return None, None
    return (sex_word or sex_letter), age


_HEAVY_HAMMER_RE = re.compile(r"martell|martillo|martello", re.IGNORECASE)
_HEAVY_MARKER_RE = re.compile(r"\bpesat\b|\bpesado\b", re.IGNORECASE)
_MASTERS_WORD_RE = re.compile(r"\b(?:master\w*|m[àa]ster\w*|veter\w*|vet)\b",
                              re.IGNORECASE)


def heavy_hammer_label_from_header(text):
    """Weighted heavy-hammer label when a section header names sex + category.

    Returns None when the header is not a heavy-hammer section, or when it
    carries no category (S4: keep today's unweighted output in that case).

    This is the narrow heavy-hammer-only helper (S2/S4). The general resolver
    below — `decide_implement_label()` — is what the extractor and the
    precedence rule use: it covers every implement, prefers the printed weight
    and falls back to DOB + meet date. Both agree on a heavy-hammer header
    that prints no weight.
    """
    t = str(text or "")
    if not _HEAVY_HAMMER_RE.search(t) or not _HEAVY_MARKER_RE.search(t):
        return None
    sex, age = parse_sex_and_category(t)
    return heavy_hammer_label_for(sex, age)


# ---------------------------------------------------------------------------
# Stored discipline labels ("Martell (7.260 Kg)", "Disc (1,750)", …).
# ---------------------------------------------------------------------------

_LABEL_RE = re.compile(
    r"^\s*(?P<implement>Martell pesat|Martell|Pes|Disc|Javelina)\s*"
    r"\((?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>Kg|g)?\)\s*$",
    re.IGNORECASE)

_IMPLEMENT_BY_LABEL = {
    "martell pesat": "martell_pesat",
    "martell": "martell",
    "pes": "pes",
    "disc": "disc",
    "javelina": "javelina",
}


def _number_to_kg(number, unit):
    """Label number + unit -> kg. '7.260' is 7.26 (thousands separator)."""
    text = str(number or "").replace(" ", "")
    # '7.260' / '1,750' — a one/two-digit head plus exactly three digits is a
    # thousands separator in this dataset's spellings, not a third decimal.
    if re.fullmatch(r"\d{1,2}[.,]\d{3}", text):
        head, tail = re.split(r"[.,]", text)
        value = float(head) + int(tail) / 1000.0
    else:
        value = float(text.replace(",", "."))
    if unit and unit.lower() == "g":
        return value / 1000.0
    return value


def parse_implement_label(discipline):
    """('martell_pesat', 9.08) for a stored label, or None when it states none."""
    m = _LABEL_RE.match(str(discipline or ""))
    if not m:
        return None
    implement = _IMPLEMENT_BY_LABEL[m.group("implement").lower()]
    return implement, _number_to_kg(m.group("number"), m.group("unit"))


# ---------------------------------------------------------------------------
# S8-S10 — precedence: the printed weight wins, the table is the fallback.
#
# "si el resultat original indica el pes, mana el resultat original, quan no
# quedi clar, fem fallback al document" (owner rule, L5). A sheet that prints
# the implement weight is the record of what was actually thrown, so that
# number is stored even when it contradicts the regulation table. Only a sheet
# that prints no weight is decided by RFEA_2026_WEIGHTS.
#
# The discriminator is `raw_discipline_name` — the section header, verbatim. A
# stored `discipline` label is NEVER evidence that the PDF printed a weight
# (S10): it may be a derived label, so it cannot decide its own correctness.
# ---------------------------------------------------------------------------

AUTHORITY_PRINTED = "printed"        # the sheet printed the weight (S8)
AUTHORITY_TABLE = "table"            # nothing printed, regulation decides (S9)
AUTHORITY_UNPARSEABLE = "unparseable"  # printed, but no weight could be read
AUTHORITY_UNRESOLVED = "unresolved"  # no print, and no sex/category to look up
AUTHORITY_NO_SPELLING = "no-spelling"  # weight known, DISCIPLINES.md has no label

#: DISCIPLINES.md spellings, keyed by (implement, weight in kg). Only these
#: six/seven spellings per implement exist — never invent one (S3).
IMPLEMENT_WEIGHT_LABELS = {
    "pes": {
        7.26: "Pes (7.260 Kg)", 6.0: "Pes (6 Kg)", 5.0: "Pes (5 Kg)",
        4.0: "Pes (4 Kg)", 3.0: "Pes (3 Kg)", 2.0: "Pes (2 Kg)",
    },
    "disc": {
        2.0: "Disc (2 Kg)", 1.75: "Disc (1,750)", 1.5: "Disc (1,5 Kg)",
        1.0: "Disc (1 Kg)", 0.8: "Disc (800 g)", 0.75: "Disc (750 g)",
        0.6: "Disc (600 g)",
    },
    "javelina": {
        0.8: "Javelina (800 g)", 0.7: "Javelina (700 g)",
        0.6: "Javelina (600 g)", 0.5: "Javelina (500 g)",
        0.4: "Javelina (400 g)", 0.3: "Javelina (300 g)",
    },
    "martell": {
        7.26: "Martell (7.260 Kg)", 6.0: "Martell (6 Kg)",
        5.0: "Martell (5 Kg)", 4.0: "Martell (4 Kg)",
        3.0: "Martell (3 Kg)", 2.0: "Martell (2 Kg)",
    },
    "martell_pesat": HEAVY_HAMMER_LABELS,
}

#: Implement words, Catalan and Spanish. The heavy hammer is tested first, or
#: "Martell Pesat" would be read as a plain hammer.
_IMPLEMENT_PATTERNS = (
    ("martell_pesat", re.compile(r"martell\s+pesat|martillo\s+pesad", re.IGNORECASE)),
    ("martell", re.compile(r"\bmartell|\bmartillo|\bmartelo", re.IGNORECASE)),
    ("pes", re.compile(r"\bpes\b|\bpeso\b", re.IGNORECASE)),
    ("disc", re.compile(r"\bdisc\b|\bdisco\b|\bdiscus\b", re.IGNORECASE)),
    ("javelina", re.compile(r"\bjavelina|\bjabalina|\bjavelot\b|\bdard\b",
                            re.IGNORECASE)),
)

#: Metric weight units a sheet may print, with their factor to kg. A bare "k"
#: is kilograms here because this parser only runs inside a throw header
#: ("Pes (3k) Fem. PC 50-54"); a road race never names an implement.
_WEIGHT_UNITS = {
    "kg": 1.0, "kgs": 1.0, "k": 1.0, "kilo": 1.0, "kilos": 1.0,
    "quilogram": 1.0, "quilograms": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "kilogramo": 1.0, "kilogramos": 1.0,
    "g": 0.001, "gr": 0.001, "grs": 0.001, "gram": 0.001, "grams": 0.001,
    "gramo": 0.001, "gramos": 0.001,
}

_NUMBER = r"\d{1,3}(?:[.,]\d{1,3})?"
_WEIGHT_TOKEN_RE = re.compile(
    r"(?<![\d,.])(" + _NUMBER + r")\s*(kgs|kg|k|kilos|kilo|kilogramos|kilogramo|"
    r"kilograms|kilogram|quilograms|quilogram|grs|gr|g|gramos|gramo|grams|gram)\b",
    re.IGNORECASE)
#: A bare number in brackets is this dataset's weight spelling: "DISC (1,750)".
_PAREN_NUMBER_RE = re.compile(r"\(\s*(" + _NUMBER + r")\s*\)")
#: A number followed by a non-metric weight unit ("16 lb", "600 onzas"):
#: printed, but not convertible without guessing. Such rows are reported
#: instead of silently re-decided from the regulation table.
_NON_METRIC_WEIGHT_RE = re.compile(
    r"(?<![\d,.])(" + _NUMBER + r")\s*"
    r"(lbs?|libras?|oz|onzas?|pounds?|stones?)\b", re.IGNORECASE)


def implement_from_text(text):
    """Implement key named in a section header, or None."""
    t = str(text or "")
    for implement, pattern in _IMPLEMENT_PATTERNS:
        if pattern.search(t):
            return implement
    return None


def parse_printed_weight(text):
    """Weight printed in a header/row -> (kg, status).

    status is 'ok' (a weight was read), 'none' (the text prints no weight) or
    'unparseable' (it prints something weight-like that is not metric). An
    unreadable weight is never silently dropped: S10 requires it reported.
    """
    t = str(text or "")
    if not t.strip():
        return None, "none"
    m = _WEIGHT_TOKEN_RE.search(t)
    if m:
        kg = _number_to_kg(m.group(1), None) * _WEIGHT_UNITS[m.group(2).lower()]
        return round(kg, 3), "ok"
    m = _PAREN_NUMBER_RE.search(t)
    if m:
        return _number_to_kg(m.group(1), None), "ok"
    if _NON_METRIC_WEIGHT_RE.search(t):
        return None, "unparseable"
    return None, "none"


def _weight_key(weight):
    """Float key for IMPLEMENT_WEIGHT_LABELS (3 decimals keeps grams exact)."""
    return round(float(weight) + 0.0, 3)


def label_for_weight(implement, weight):
    """DISCIPLINES.md spelling for an (implement, kg), or None when absent."""
    if weight is None:
        return None
    return IMPLEMENT_WEIGHT_LABELS.get(implement, {}).get(_weight_key(weight))


def _as_printed_weight(value):
    """Normalize the printed_weight argument -> (kg|None, status)."""
    if value is None:
        return None, "none"
    if isinstance(value, bool):
        return None, "unparseable"
    if isinstance(value, (int, float)):
        return (round(float(value), 3), "ok") if value > 0 else (None, "unparseable")
    text = str(value).strip()
    if not text:
        return None, "none"
    if re.fullmatch(_NUMBER, text):
        return _number_to_kg(text, None), "ok"
    return parse_printed_weight(text)


def resolve_implement_weight(implement, sex, category_band, printed_weight):
    """Weight in kg + the authority that decided it (S8/S9).

    ``printed_weight`` is what the sheet printed: None/'' when it printed
    nothing, a number in kg, or the printed text ('500 g', '4 kg', '(3k)').
    A printed weight always wins, even when the table disagrees. Without one,
    the RFEA 2026 table decides from the printed sex and category band (a band
    label such as '50-59', or a raw age that is banded here).

    Returns (weight_kg, authority); authority is one of AUTHORITY_PRINTED,
    AUTHORITY_TABLE, AUTHORITY_UNPARSEABLE, AUTHORITY_UNRESOLVED. An
    unparseable printed weight does NOT fall back to the table — it is
    reported, because silently substituting the regulation weight would
    overwrite what the sheet said it threw.
    """
    weight, status = _as_printed_weight(printed_weight)
    if status == "ok":
        return weight, AUTHORITY_PRINTED
    if status == "unparseable":
        return None, AUTHORITY_UNPARSEABLE

    band = category_band
    if isinstance(band, int) and not isinstance(band, bool):
        band = band_for_age(sex, band)
    if sex is None or band is None or implement not in IMPLEMENTS:
        return None, AUTHORITY_UNRESOLVED
    weights = RFEA_2026_WEIGHTS.get((sex, band))
    if weights is None or implement not in weights:
        return None, AUTHORITY_UNRESOLVED
    return weights[implement], AUTHORITY_TABLE


def is_masters_section(text):
    """True when a section header belongs to a masters/veterans section.

    Either the header says so ("Master", "Màster", "Vet.") or it prints a
    category that only exists from 35 up ("M50", "F-55", "50-54"). Used to
    keep every non-masters discipline string exactly as it is today: the
    regulation table only describes masters implements.
    """
    t = str(text or "")
    if _MASTERS_WORD_RE.search(t):
        return True
    sex, age = parse_sex_and_category(t)
    return band_for_age(sex, age) is not None


def decide_implement_label(raw_discipline_name, dob=None, event_date=None):
    """Decide one row's discipline label from what the sheet printed.

    ``raw_discipline_name`` is the section header, verbatim (S10). Returns
    (label|None, authority, weight_kg|None):

      * label is a DISCIPLINES.md spelling when the weight is known and one
        exists; None otherwise (the caller keeps the row's current label).
      * authority says who decided: AUTHORITY_PRINTED, AUTHORITY_TABLE,
        AUTHORITY_UNPARSEABLE, AUTHORITY_UNRESOLVED, AUTHORITY_NO_SPELLING, or
        None when the header is not an implement event at all.

    Category evidence order follows S1: the category printed in the header
    first, then DOB + event_date. Sex always comes from the header — no sheet
    prints a sex only per row, and guessing one would be fabrication.
    """
    implement = implement_from_text(raw_discipline_name)
    if implement is None:
        return None, None, None

    sex, age = parse_sex_and_category(raw_discipline_name)
    band = band_for_age(sex, age) if age is not None else None

    printed, status = parse_printed_weight(raw_discipline_name)
    if status == "unparseable":
        return None, AUTHORITY_UNPARSEABLE, None
    if status == "none" and band is None:
        # S1 fallback: the row's own DOB against the meet date.
        band = band_for_age(sex, age_on(dob, event_date))

    weight, authority = resolve_implement_weight(
        implement, sex, band, printed if status == "ok" else None)
    if weight is None:
        return None, authority, None
    label = label_for_weight(implement, weight)
    if label is None:
        return None, AUTHORITY_NO_SPELLING, weight
    return label, authority, weight
