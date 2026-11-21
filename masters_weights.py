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
    if _MALE_WORD_RE.search(t):
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


def heavy_hammer_label_from_header(text):
    """Weighted heavy-hammer label when a section header names sex + category.

    Returns None when the header is not a heavy-hammer section, or when it
    carries no category (S4: keep today's unweighted output in that case).
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
