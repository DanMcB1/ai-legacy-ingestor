"""Normalize messy CSV and Excel exports with inconsistent headers and dates."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from .models import ExtractedRecord, FieldIssue
from .normalize import (
    format_currency,
    format_date,
    normalize_currency,
    normalize_date,
    normalize_name,
    normalize_vin,
)

# Map messy header labels onto a small set of canonical field names.
_HEADER_ALIASES = {
    "customer_name": {
        "customer",
        "customer name",
        "cust name",
        "cust. name",
        "cust_name",
        "customer_name",
        "name",
        "client",
        "client name",
    },
    "vin": {"vin", "vin #", "vin#", "vin_no", "vin no", "vehicle id", "vehicle_id", "veh id"},
    "date": {
        "date",
        "deal date",
        "deal_date",
        "ro date",
        "ro_date",
        "trans date",
        "service date",
        "svc date",
        "closed",
        "close date",
    },
    "amount": {
        "amount",
        "amt",
        "ro amt",
        "ro amount",
        "total",
        "gross",
        "front gross",
        "front_gross",
        "ro_amt",
        "total amt",
    },
    "store": {"store", "rooftop", "dealer", "store id", "store_id", "branch"},
    "advisor": {"advisor", "service advisor", "sa", "writer", "tech advisor"},
    "ro_number": {"ro", "ro #", "ro#", "ro number", "ro_number", "repair order", "ticket"},
    "deal_number": {"deal", "deal #", "deal#", "deal number", "deal_number", "deal no"},
    "status": {"status", "st", "state", "ro status"},
    "make": {"make", "veh make", "vehicle make"},
    "model": {"model", "veh model", "vehicle model"},
    "year": {"year", "yr", "veh year", "model year"},
    "mileage": {"miles", "mileage", "odo", "odometer"},
}


def _canonical_header(raw: Any) -> str:
    text = " ".join(str(raw or "").strip().lower().split())
    text = text.replace("_", " ").replace(".", " ").replace("$", " ").replace("#", " ")
    text = " ".join(text.split())
    for canonical, aliases in _HEADER_ALIASES.items():
        if text in aliases:
            return canonical
    # Fallback: snake_case whatever is left.
    cleaned = "".join(ch if ch.isalnum() or ch == " " else " " for ch in text)
    snake = "_".join(cleaned.split())
    return snake or "column"


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return text


def _looks_like_header(values: list[Any]) -> bool:
    texts = [_cell_text(v) for v in values]
    texts = [t for t in texts if t]
    if len(texts) < 3:
        return False
    # Prefer a row that maps onto known aliases (customer, VIN, date, amount…).
    known = {key for key in _HEADER_ALIASES}
    alias_hits = sum(1 for t in texts if _canonical_header(t) in known)
    if alias_hits >= 2:
        return True
    # A header row is mostly words, not dates or dollar amounts.
    numericish = 0
    for text in texts:
        if any(ch.isdigit() for ch in text) and any(tok in text for tok in ("$", "/", "-", "20", "19")):
            numericish += 1
    return numericish <= max(1, len(texts) // 3) and len(texts) >= 4


def _find_header_row(raw: pd.DataFrame, max_scan: int = 8) -> int:
    limit = min(max_scan, len(raw))
    for index in range(limit):
        values = raw.iloc[index].tolist()
        if _looks_like_header(values):
            return index
    return 0


def _clean_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    header_at = _find_header_row(raw)
    header = raw.iloc[header_at].tolist()
    body = raw.iloc[header_at + 1 :].copy()
    names: list[str] = []
    seen: dict[str, int] = {}
    for cell in header:
        name = _canonical_header(cell)
        count = seen.get(name, 0)
        seen[name] = count + 1
        names.append(name if count == 0 else f"{name}_{count + 1}")
    body.columns = names
    body = body.dropna(how="all")
    body = body.reset_index(drop=True)
    return body


def _normalize_row(row: dict[str, Any], source_file: str, source_type: str, number: int) -> ExtractedRecord:
    raw_fields = {k: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip() for k, v in row.items()}
    fields: dict[str, Any] = {}
    issues: list[FieldIssue] = []
    flags: list[str] = []

    if "customer_name" in row:
        fields["customer_name"] = normalize_name(row["customer_name"])
        if raw_fields.get("customer_name") and not fields["customer_name"]:
            issues.append(FieldIssue("customer_name", raw_fields["customer_name"], "could not parse name"))

    if "vin" in row:
        vin, vin_issues = normalize_vin(row["vin"]) if raw_fields.get("vin") else (None, [])
        fields["vin"] = vin
        for reason in vin_issues:
            if reason != "empty":
                issues.append(FieldIssue("vin", raw_fields.get("vin", ""), reason))
                flags.append(f"vin: {reason}")

    if "date" in row:
        parsed = normalize_date(row["date"])
        fields["date"] = format_date(parsed)
        if raw_fields.get("date") and parsed is None:
            issues.append(FieldIssue("date", raw_fields["date"], "unparseable date"))
            flags.append("unparseable date")

    if "amount" in row:
        amount = normalize_currency(row["amount"])
        fields["amount"] = format_currency(amount)
        fields["amount_value"] = amount
        if raw_fields.get("amount") and amount is None:
            issues.append(FieldIssue("amount", raw_fields["amount"], "unparseable amount"))
            flags.append("unparseable amount")

    for key in ("store", "advisor", "ro_number", "deal_number", "status", "make", "model"):
        if key in row and raw_fields.get(key):
            text = raw_fields[key]
            fields[key] = normalize_name(text) if key in {"advisor"} else text

    if "year" in row and raw_fields.get("year"):
        try:
            fields["year"] = int(float(str(row["year"]).strip()))
        except (TypeError, ValueError):
            fields["year"] = raw_fields["year"]
            issues.append(FieldIssue("year", raw_fields["year"], "unparseable year"))

    if "mileage" in row and raw_fields.get("mileage"):
        digits = "".join(ch for ch in raw_fields["mileage"] if ch.isdigit())
        fields["mileage"] = int(digits) if digits else raw_fields["mileage"]

    # Keep any other columns so we do not drop surprise fields from a customer export.
    for key, value in raw_fields.items():
        if key not in fields and value:
            fields[key] = value

    raw_text = " | ".join(f"{k}={v}" for k, v in raw_fields.items() if v)
    cleaned_parts = []
    for key, value in fields.items():
        if key == "amount_value" or value in (None, ""):
            continue
        cleaned_parts.append(f"{key.replace('_', ' ')}: {value}")
    cleaned_text = "; ".join(cleaned_parts)

    status = "ok"
    reject_reason = None
    # A row with no identifying field at all is rejected.
    has_identity = any(fields.get(k) for k in ("customer_name", "vin", "ro_number", "deal_number"))
    if not has_identity:
        status = "rejected"
        reject_reason = "No customer, VIN, or ticket number on this row"
    elif any(i.reason.startswith("unparseable amount") for i in issues) and not fields.get("amount"):
        status = "rejected"
        reject_reason = "Amount could not be parsed"
    elif flags:
        status = "review"

    return ExtractedRecord(
        record_id=f"{source_file}::r{number}",
        source_file=source_file,
        source_type=source_type,
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        fields=fields,
        raw_fields=raw_fields,
        record_number=number,
        line_start=number,
        line_end=number,
        status=status,
        reject_reason=reject_reason,
        flags=flags,
        issues=issues,
    )


def _read_csv_table(path: Path | None = None, data: bytes | None = None) -> pd.DataFrame:
    """Load a messy CSV, including title rows that do not share a column count."""
    import csv
    from io import StringIO

    if data is not None:
        handle = StringIO(data.decode("utf-8-sig", errors="replace"))
    else:
        handle = Path(path).open("r", encoding="utf-8-sig", errors="replace", newline="")
    try:
        rows = list(csv.reader(handle))
    finally:
        handle.close()
    if not rows:
        return pd.DataFrame()
    width = max(len(row) for row in rows)
    padded = [row + [None] * (width - len(row)) for row in rows]
    return pd.DataFrame(padded, dtype=object)


def extract_csv(path: str | Path, data: bytes | None = None) -> list[ExtractedRecord]:
    path = Path(path)
    frame = _read_csv_table(path=path, data=data)
    body = _clean_frame(frame)
    records = []
    for i, row in body.iterrows():
        records.append(_normalize_row(row.to_dict(), path.name, "csv", int(i) + 1))
    return records


def extract_excel(path: str | Path, data: bytes | None = None) -> list[ExtractedRecord]:
    path = Path(path)
    source = BytesIO(data) if data is not None else path
    # Read the first sheet, no assumed header, so we can find it ourselves.
    frame = pd.read_excel(source, header=None, dtype=object, engine="openpyxl")
    body = _clean_frame(frame)
    records = []
    for i, row in body.iterrows():
        records.append(_normalize_row(row.to_dict(), path.name, "excel", int(i) + 1))
    return records
