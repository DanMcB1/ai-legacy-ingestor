"""Guess a source type from a file name and a sniff of its contents."""

from __future__ import annotations

from pathlib import Path

from .copybook import EBCDIC

SCAN_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".webp"}
CSV_SUFFIXES = {".csv", ".tsv"}
EXCEL_SUFFIXES = {".xlsx", ".xls"}
TEXT_SUFFIXES = {".txt", ".md", ".log"}
COPYBOOK_SUFFIXES = {".cpy", ".cob", ".cobol", ".cbl"}
BINARY_SUFFIXES = {".dat", ".ebc", ".bin", ".mf"}


def _ebcdic_score(data: bytes) -> float:
    """Fraction of bytes that look like EBCDIC letters, digits, or space."""
    if not data:
        return 0.0
    hits = 0
    for byte in data:
        if byte == 0x40:  # space
            hits += 1
        elif 0xF0 <= byte <= 0xF9:  # digits
            hits += 1
        elif 0xC1 <= byte <= 0xC9 or 0xD1 <= byte <= 0xD9 or 0xE2 <= byte <= 0xE9:
            hits += 1
        elif byte in {0x4B, 0x6B, 0x5E, 0x60, 0x50}:  # ., $ + - &
            hits += 1
    return hits / len(data)


def detect_type(path: str | Path, data: bytes | None = None) -> str:
    """Return one of: scan, copybook, csv, excel, text, mainframe.

    ``copybook`` is the ``.cpy`` layout. ``mainframe`` is the fixed-width
    EBCDIC data file that the layout describes.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in SCAN_SUFFIXES:
        return "scan"
    if suffix in COPYBOOK_SUFFIXES:
        return "copybook"
    if suffix in CSV_SUFFIXES:
        return "csv"
    if suffix in EXCEL_SUFFIXES:
        return "excel"
    if suffix in TEXT_SUFFIXES:
        return "text"
    sniffed: bytes
    if data is not None:
        sniffed = data[:4096]
    elif path.is_file():
        sniffed = path.read_bytes()[:4096]
    else:
        sniffed = b""

    # A UTF-8 / ASCII text-looking file with PIC clauses is a copybook.
    try:
        as_text = sniffed.decode("utf-8")
    except UnicodeDecodeError:
        as_text = ""
    if as_text and "PIC" in as_text.upper() and any(
        token in as_text.upper() for token in ("  01 ", " 01 ", "PIC X", "PIC 9", "COMP-3")
    ):
        return "copybook"
    if suffix in BINARY_SUFFIXES or (sniffed and _ebcdic_score(sniffed) >= 0.55):
        # Don't call ASCII-heavy files mainframe just because of a .dat suffix
        # if they decode cleanly as text and do not look like EBCDIC.
        if sniffed and _ebcdic_score(sniffed) < 0.35:
            return "text"
        return "mainframe"
    if as_text and ("\x00" not in as_text):
        if "," in as_text or "\t" in as_text:
            first = as_text.splitlines()[0] if as_text.splitlines() else ""
            if first.count(",") >= 2 or first.count("\t") >= 2:
                return "csv"
        return "text"
    if sniffed and _ebcdic_score(sniffed) >= 0.35:
        return "mainframe"
    return "text"


def is_ebcdic(data: bytes) -> bool:
    return _ebcdic_score(data[:4096]) >= 0.55


def decode_preview(data: bytes, source_type: str, limit: int = 800) -> str:
    """A short printable preview for the UI's 'raw' pane."""
    if source_type == "mainframe":
        sample = data[: min(len(data), 240)]
        try:
            text = sample.decode(EBCDIC)
        except UnicodeDecodeError:
            text = ""
        hex_part = sample[:64].hex(" ")
        return f"EBCDIC (CP037) file, {len(data):,} bytes.\nHex: {hex_part}\nAs text: {text}"
    if source_type == "scan":
        return f"Scanned image or PDF, {len(data):,} bytes."
    try:
        return data[:limit].decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data[:limit].decode("latin-1")
        except UnicodeDecodeError:
            return data[:64].hex(" ")
