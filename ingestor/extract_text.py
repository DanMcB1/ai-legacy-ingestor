"""Extract a plain-text memo, then normalize dates, currency, VINs, and names."""

from __future__ import annotations

import re
from pathlib import Path

from .models import ExtractedRecord, FieldIssue
from .normalize import (
    format_currency,
    format_date,
    normalize_currency,
    normalize_date,
    normalize_name,
    normalize_vin,
)

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{2,4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{2,4})\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$\s?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\(\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)")


def extract_text(path: str | Path, data: bytes | None = None) -> list[ExtractedRecord]:
    path = Path(path)
    if data is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        text = data.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.split("\n")

    fields: dict[str, object] = {}
    issues: list[FieldIssue] = []
    flags: list[str] = []

    vins = []
    for match in _VIN_RE.finditer(text):
        vin, vin_issues = normalize_vin(match.group(0))
        if vin:
            vins.append(vin)
        for reason in vin_issues:
            if reason != "empty":
                issues.append(FieldIssue("vin", match.group(0), reason))
                flags.append(f"vin: {reason}")
    if vins:
        fields["vins"] = vins
        fields["vin"] = vins[0]

    dates = []
    for match in _DATE_RE.finditer(text):
        parsed = normalize_date(match.group(0))
        if parsed:
            dates.append(format_date(parsed))
    if dates:
        fields["dates"] = dates
        fields["date"] = dates[0]

    amounts = []
    for match in _MONEY_RE.finditer(text):
        amount = normalize_currency(match.group(0))
        if amount is not None:
            amounts.append(format_currency(amount))
    if amounts:
        fields["amounts"] = amounts

    # A "From:" / "MEMO FROM" line often holds a name.
    for line in lines[:12]:
        lowered = line.lower()
        if lowered.startswith("from:") or lowered.startswith("memo from"):
            name = line.split(":", 1)[-1].strip()
            # Drop a trailing title after an em dash or hyphen.
            name = re.split(r"\s+[—\-–]\s+", name)[0].strip()
            fields["author"] = normalize_name(name) or name
        if lowered.startswith("to:"):
            fields["addressee"] = line.split(":", 1)[-1].strip()
        if lowered.startswith("subject:") or lowered.startswith("re:"):
            fields["subject"] = line.split(":", 1)[-1].strip()

    cleaned_lines = [ln.rstrip() for ln in lines]
    return [
        ExtractedRecord(
            record_id=f"{path.name}::memo",
            source_file=path.name,
            source_type="text",
            raw_text=text,
            cleaned_text="\n".join(cleaned_lines),
            fields=fields,
            raw_fields={},
            record_number=1,
            line_start=1,
            line_end=len(lines),
            status="review" if flags else "ok",
            flags=flags,
            issues=issues,
        )
    ]
