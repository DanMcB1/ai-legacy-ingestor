"""Normalize dates, currency, VINs, and person names from messy legacy text."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

# ISO 3779 VIN transliteration and check-digit weights.
_VIN_MAP = {
    **{str(i): i for i in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_EMPTY = {"", "-", "--", "n/a", "na", "none", "null", "?", ".", "unknown"}

# Two-digit years 00-29 belong to 2000-2029; 30-99 belong to 1930-1999.
# The demo is set in 2026, so "26" means 2026.
_YEAR_PIVOT = 29


def _blank(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
        return True
    return str(raw).strip().lower() in _EMPTY


def _year(year: int) -> int:
    if year < 0:
        raise ValueError("invalid year")
    if year < 100:
        return 2000 + year if year <= _YEAR_PIVOT else 1900 + year
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(_year(year), month, day)
    except ValueError:
        return None


def _excel_serial(value: float | int) -> date | None:
    # Excel's Date/1900 system (the Lotus 1900 leap-year bug) is emulated
    # by using 1899-12-30 as day zero. Serials below 1 are not dates here.
    serial = int(value)
    if serial < 1 or serial > 80000:
        return None
    return date(1899, 12, 30) + timedelta(days=serial)


def normalize_date(raw: Any) -> date | None:
    """Parse a messy US-centric date into a ``datetime.date``, or None."""
    if _blank(raw):
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        # Bare numbers: 8-digit YYYYMMDD, or an Excel serial in range.
        if isinstance(raw, float) and not raw.is_integer():
            return None
        as_int = int(raw)
        as_text = str(as_int)
        if len(as_text) == 8 and as_text.startswith(("19", "20")):
            return _safe_date(int(as_text[:4]), int(as_text[4:6]), int(as_text[6:8]))
        return _excel_serial(raw)

    text = str(raw).strip()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    text = re.sub(r"[,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # YYYY-MM-DD or YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # YYYYMMDD
    m = re.fullmatch(r"(19\d{2}|20\d{2})(\d{2})(\d{2})", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # MM/DD/YY, MM-DD-YYYY, MM.DD.YY (US dealer-group default)
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})", text)
    if m:
        return _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))

    # 24-NOV-2026, 24/Nov/26, 24 NOV 2026
    m = re.fullmatch(r"(\d{1,2})[/\- ]([A-Za-z]{3,9})[/\- ](\d{2}|\d{4})", text)
    if m:
        month = _MONTHS.get(m.group(2).lower())
        if month:
            return _safe_date(int(m.group(3)), month, int(m.group(1)))

    # Nov 24 2026, November 24, 2026, Nov-24-26
    m = re.fullmatch(r"([A-Za-z]{3,9})[/\- ](\d{1,2})[/\- ](\d{2}|\d{4})", text)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            return _safe_date(int(m.group(3)), month, int(m.group(2)))

    return None


def format_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def normalize_currency(raw: Any) -> Decimal | None:
    """Parse a messy dollar amount into a 2-decimal Decimal, or None.

    Understands ``$1,234.56``, parentheses or a trailing minus for
    negatives, and a bare integer or float.
    """
    if _blank(raw):
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
            return None
        return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    text = str(raw).strip()
    text = re.sub(r"(?i)\bUSD\b", "", text).strip()
    text = text.replace("$", "").strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.endswith("-"):
        negative = True
        text = text[:-1].strip()
    if text.startswith("-"):
        negative = True
        text = text[1:].strip()
    text = text.replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_currency(value: Decimal | None) -> str | None:
    if value is None:
        return None
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def vin_check_digit(vin: str) -> str | None:
    """Return the ISO 3779 check digit for a 17-character VIN body."""
    if len(vin) != 17:
        return None
    total = 0
    for i, char in enumerate(vin):
        if i == 8:
            continue
        if char not in _VIN_MAP:
            return None
        total += _VIN_MAP[char] * _VIN_WEIGHTS[i]
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def vin_ok(vin: str) -> bool:
    """True when ``vin`` is 17 characters with no I/O/Q and a valid check digit."""
    if len(vin) != 17:
        return False
    if any(char in vin for char in "IOQ"):
        return False
    if any(char not in _VIN_MAP for char in vin):
        return False
    expected = vin_check_digit(vin)
    return expected is not None and vin[8] == expected


def normalize_vin(raw: Any) -> tuple[str | None, list[str]]:
    """Strip separators, uppercase, and flag length or check-digit problems."""
    if _blank(raw):
        return None, ["empty"]
    text = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    if not text:
        return None, ["empty"]
    issues: list[str] = []
    if any(char in text for char in "IOQ"):
        issues.append("contains I, O, or Q (not used in a VIN)")
    if len(text) != 17:
        issues.append(f"length {len(text)}, expected 17")
        return text, issues
    if not vin_ok(text):
        issues.append("invalid check digit")
    return text, issues


def make_vin(body: str) -> str:
    """Fill in the check digit at position 9 of a 17-character VIN template."""
    if len(body) != 17:
        raise ValueError("VIN template must be 17 characters")
    chars = list(body.upper())
    chars[8] = "0"
    digit = vin_check_digit("".join(chars))
    if digit is None:
        raise ValueError("VIN template has illegal characters")
    chars[8] = digit
    return "".join(chars)


_PARTICLE = {"jr": "Jr", "sr": "Sr", "ii": "II", "iii": "III", "iv": "IV"}


def _title_name_part(part: str) -> str:
    lower = part.lower().strip(".")
    if lower in _PARTICLE:
        return _PARTICLE[lower]
    if len(part.rstrip(".")) == 1 and part[0].isalpha():
        return part[0].upper() + ("." if part.endswith(".") else "")
    if part.lower().startswith("mc") and len(part) > 3:
        return "Mc" + part[2:].title()
    if part.lower().startswith("mac") and len(part) > 4:
        return "Mac" + part[3:].title()
    if re.match(r"^[Oo]'[A-Za-z]", part):
        return "O'" + part[2:].title()
    return part.title()


def normalize_name(raw: Any) -> str | None:
    """Collapse whitespace, flip ``LAST, FIRST`` order, and title-case a name."""
    if _blank(raw):
        return None
    text = re.sub(r"\s+", " ", str(raw)).strip(" .,")
    if not text:
        return None
    if "," in text:
        last, first = text.split(",", 1)
        text = f"{first.strip()} {last.strip()}".strip()
    parts = [_title_name_part(p) for p in text.split() if p]
    return " ".join(parts) or None
