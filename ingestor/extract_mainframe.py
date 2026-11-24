"""Turn a COBOL copybook + EBCDIC file into cleaned structured records."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from .copybook import Copybook, CopybookError, decode_file, load_copybook
from .models import ExtractedRecord, FieldIssue
from .normalize import (
    format_currency,
    format_date,
    normalize_currency,
    normalize_date,
    normalize_name,
    normalize_vin,
)


def _format_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format_currency(value)
    if isinstance(value, list):
        return [_format_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _format_value(v) for k, v in value.items() if k != "_record_number"}
    return value


def _clean_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[FieldIssue], list[str], str]:
    fields: dict[str, Any] = {}
    issues: list[FieldIssue] = []
    flags: list[str] = []
    parts: list[str] = []

    def take(name: str, value: Any) -> None:
        fields[name] = value
        if value not in (None, "", []):
            label = name.replace("_", " ").lower()
            if isinstance(value, list):
                parts.append(f"{label}: {value}")
            else:
                parts.append(f"{label}: {value}")

    for key, value in row.items():
        if key == "_record_number":
            continue
        upper = key.upper()
        if upper in {"CUST_NAME", "CUSTOMER_NAME", "NAME"}:
            cleaned = normalize_name(value)
            take("customer_name", cleaned)
            if value and not cleaned:
                issues.append(FieldIssue("customer_name", str(value), "could not parse name"))
        elif upper in {"VIN"}:
            vin, vin_issues = normalize_vin(value)
            take("vin", vin)
            for reason in vin_issues:
                if reason != "empty":
                    issues.append(FieldIssue("vin", str(value), reason))
                    flags.append(f"vin: {reason}")
        elif "DATE" in upper:
            parsed = normalize_date(value)
            take(key.lower(), format_date(parsed) or value)
            if value not in (None, "") and parsed is None:
                issues.append(FieldIssue(key.lower(), str(value), "unparseable date"))
                flags.append("unparseable date")
        elif any(token in upper for token in ("AMT", "AMOUNT", "GROSS", "NET")):
            amount = value if isinstance(value, Decimal) else normalize_currency(value)
            take(key.lower(), format_currency(amount) if amount is not None else value)
            if isinstance(amount, Decimal):
                fields[f"{key.lower()}_value"] = amount
        elif upper in {"CUST_ID", "CUSTOMER_ID"}:
            take("customer_id", str(value).zfill(8) if str(value).isdigit() else value)
        elif upper in {"STORE_ID", "STORE"}:
            take("store_id", str(value).strip())
        elif upper in {"VEHICLE_INFO"}:
            cleaned_vehicles = []
            for item in value or []:
                entry = {}
                if "VEH_YEAR" in item:
                    entry["year"] = int(item["VEH_YEAR"])
                if "VEH_MAKE" in item:
                    entry["make"] = str(item["VEH_MAKE"]).strip().title()
                if any(entry.values()):
                    cleaned_vehicles.append(entry)
            take("vehicles", cleaned_vehicles)
        elif upper in {"VEHICLE_COUNT"}:
            take("vehicle_count", int(value) if value not in (None, "") else 0)
        elif upper in {"CUST_STATUS", "CUST_TYPE"}:
            take(key.lower(), str(value).strip() if value is not None else "")
        else:
            take(key.lower(), _format_value(value))

    return fields, issues, flags, "; ".join(parts)


def extract_mainframe(
    data_path: str | Path,
    copybook: Copybook | str | Path,
    data: bytes | None = None,
) -> tuple[list[ExtractedRecord], list[ExtractedRecord]]:
    """Return ``(accepted_or_review, rejected)`` records for a mainframe file."""
    data_path = Path(data_path)
    if isinstance(copybook, (str, Path)):
        book = load_copybook(copybook)
    else:
        book = copybook
    blob = data if data is not None else data_path.read_bytes()
    rows, rejects = decode_file(book, blob)
    accepted: list[ExtractedRecord] = []
    rejected: list[ExtractedRecord] = []

    for row in rows:
        number = int(row["_record_number"])
        fields, issues, flags, cleaned = _clean_row(row)
        raw_bits = []
        for key, value in row.items():
            if key == "_record_number":
                continue
            raw_bits.append(f"{key}={value}")
        status = "review" if flags else "ok"
        accepted.append(
            ExtractedRecord(
                record_id=f"{data_path.name}::r{number}",
                source_file=data_path.name,
                source_type="mainframe",
                raw_text=" | ".join(raw_bits),
                cleaned_text=cleaned,
                fields=fields,
                raw_fields={k: str(v) for k, v in row.items() if k != "_record_number"},
                record_number=number,
                line_start=number,
                line_end=number,
                status=status,
                flags=flags,
                issues=issues,
            )
        )

    for item in rejects:
        number = int(item["record_number"])
        rejected.append(
            ExtractedRecord(
                record_id=f"{data_path.name}::r{number}",
                source_file=data_path.name,
                source_type="mainframe",
                raw_text=str(item.get("reason", "")),
                cleaned_text="",
                record_number=number,
                line_start=number,
                line_end=number,
                status="rejected",
                reject_reason=item.get("reason"),
                flags=["rejected"],
            )
        )
    return accepted, rejected


def find_companion_copybook(data_path: str | Path) -> Path | None:
    """Look next to a .DAT file (and in the usual sample folder) for a .CPY."""
    data_path = Path(data_path)
    candidates = [
        data_path.with_suffix(".CPY"),
        data_path.with_suffix(".cpy"),
        data_path.parent / f"{data_path.stem}.CPY",
        data_path.parent / f"{data_path.stem}.cpy",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
