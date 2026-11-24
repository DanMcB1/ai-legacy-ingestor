"""Detect, extract, clean, chunk, and index a set of legacy source files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .chunking import chunk_records
from .copybook import load_copybook
from .detect import decode_preview, detect_type
from .extract_mainframe import extract_mainframe, find_companion_copybook
from .extract_ocr import (
    LOW_PAGE_CONFIDENCE,
    OcrUnavailable,
    low_confidence_words,
    ocr_file,
    tesseract_available,
)
from .extract_tabular import extract_csv, extract_excel
from .extract_text import extract_text
from .models import ExtractedRecord, FieldIssue, QualityReport
from .paths import INDEX_DB, SAMPLES_DIR
from .quality import build_report
from .store import VectorStore


@dataclass
class FilePreview:
    path: str
    name: str
    source_type: str
    raw_preview: str
    image_path: str | None = None


@dataclass
class PipelineResult:
    records: list[ExtractedRecord]
    chunks: list
    report: QualityReport
    previews: list[FilePreview] = field(default_factory=list)
    store: VectorStore | None = None
    notes: list[str] = field(default_factory=list)


def _ocr_records(path: Path) -> list[ExtractedRecord]:
    from .normalize import (
        format_currency,
        format_date,
        normalize_currency,
        normalize_date,
        normalize_name,
        normalize_vin,
    )
    import re

    pages = ocr_file(path)
    records: list[ExtractedRecord] = []
    vin_re = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
    for page in pages:
        fields: dict[str, Any] = {}
        issues: list[FieldIssue] = []
        flags: list[str] = []
        low = low_confidence_words(page)
        if page.confidence and page.confidence < LOW_PAGE_CONFIDENCE:
            flags.append(f"low OCR confidence ({page.confidence:.0f}%)")
        if low:
            flags.append(f"{len(low)} low-confidence word(s)")
            fields["low_confidence_words"] = [f"{w.text} ({w.conf:.0f}%)" for w in low[:12]]
        fields["deskew_degrees"] = round(page.deskew_degrees, 2)

        for match in vin_re.finditer(page.text.upper().replace(" ", "")):
            vin, vin_issues = normalize_vin(match.group(0))
            if vin:
                fields.setdefault("vins", []).append(vin)
                fields.setdefault("vin", vin)
            for reason in vin_issues:
                if reason != "empty":
                    issues.append(FieldIssue("vin", match.group(0), reason))
        # Also try the raw text (VINs may have already been contiguous).
        if "vin" not in fields:
            for token in re.findall(r"[A-HJ-NPR-Z0-9]{17}", page.text.upper()):
                vin, vin_issues = normalize_vin(token)
                if vin and not vin_issues:
                    fields["vin"] = vin
                    fields.setdefault("vins", []).append(vin)
                    break

        # Pull a few labeled form fields if OCR kept the label.
        labeled = {
            "customer": r"(?:customer|cust(?:omer)?\.?\s*name)\s*[:#]?\s*(.+)",
            "ro_number": r"(?:repair\s*order|r\.?o\.?)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9\-]+)",
            "claim_number": r"(?:claim)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9\-]+)",
            "deal_number": r"(?:deal)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9\-]+)",
        }
        for key, pattern in labeled.items():
            match = re.search(pattern, page.text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                fields[key] = normalize_name(value) if key == "customer" else value.split("\n")[0].strip()

        for match in re.finditer(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})", page.text):
            amount = normalize_currency(match.group(0))
            if amount is not None:
                fields.setdefault("amounts", []).append(format_currency(amount))

        for match in re.finditer(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", page.text):
            parsed = normalize_date(match.group(0))
            if parsed:
                fields.setdefault("dates", []).append(format_date(parsed))

        status = "review" if flags else "ok"
        if not page.text.strip():
            status = "rejected"
        records.append(
            ExtractedRecord(
                record_id=f"{path.name}::p{page.page}",
                source_file=path.name,
                source_type="scan",
                raw_text=page.text,
                cleaned_text=page.text,
                fields=fields,
                page=page.page,
                line_start=1,
                line_end=page.text.count("\n") + 1 if page.text else 1,
                ocr_confidence=page.confidence,
                status=status if status != "rejected" else "rejected",
                reject_reason="OCR returned no text" if status == "rejected" else None,
                flags=flags,
                issues=issues,
            )
        )
    return records


def _ingest_one(
    path: Path,
    data: bytes | None = None,
    copybook_path: Path | None = None,
) -> tuple[list[ExtractedRecord], FilePreview, list[str]]:
    notes: list[str] = []
    source_type = detect_type(path, data)
    blob = data if data is not None else (path.read_bytes() if path.is_file() else b"")
    preview = FilePreview(
        path=str(path),
        name=path.name,
        source_type=source_type,
        raw_preview=decode_preview(blob, source_type),
        image_path=str(path) if source_type == "scan" and path.suffix.lower() != ".pdf" else None,
    )
    records: list[ExtractedRecord] = []

    if source_type == "copybook":
        notes.append(f"{path.name} is a copybook (layout only) and was not ingested as data.")
        return records, preview, notes

    if source_type == "scan":
        if not tesseract_available():
            notes.append(
                f"Skipped {path.name}: Tesseract OCR is not installed. "
                "Other source types were still ingested."
            )
            return records, preview, notes
        try:
            records = _ocr_records(path)
        except OcrUnavailable as exc:
            notes.append(str(exc))
        return records, preview, notes

    if source_type == "csv":
        records = extract_csv(path, data=blob)
        return records, preview, notes

    if source_type == "excel":
        records = extract_excel(path, data=blob)
        return records, preview, notes

    if source_type == "mainframe":
        companion = copybook_path or find_companion_copybook(path)
        if companion is None:
            notes.append(
                f"Skipped {path.name}: no companion copybook (.cpy) was found. "
                "Upload the .CPY next to the data file."
            )
            return records, preview, notes
        accepted, rejected = extract_mainframe(path, companion, data=blob)
        records = accepted + rejected
        preview.raw_preview = (
            f"Copybook: {companion.name} (record length "
            f"{load_copybook(companion).record_length} bytes)\n\n" + preview.raw_preview
        )
        return records, preview, notes

    records = extract_text(path, data=blob)
    return records, preview, notes


def ingest_paths(
    paths: list[str | Path],
    copybook_path: str | Path | None = None,
    persist: bool = True,
    db_path: str | Path | None = None,
) -> PipelineResult:
    """Run the full pipeline over the given files and build a searchable index."""
    records: list[ExtractedRecord] = []
    previews: list[FilePreview] = []
    notes: list[str] = []
    files: list[str] = []
    companion = Path(copybook_path) if copybook_path else None

    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            notes.append(f"Missing file: {path}")
            continue
        files.append(path.name)
        found, preview, file_notes = _ingest_one(path, copybook_path=companion)
        records.extend(found)
        previews.append(preview)
        notes.extend(file_notes)

    chunks = chunk_records(records)
    report = build_report(records, chunk_count=len(chunks), files=files, notes=notes)
    store = VectorStore(db_path=db_path or INDEX_DB)
    store.clear()
    store.add_chunks(chunks)
    store.build()
    if persist:
        store.save(report)
    return PipelineResult(
        records=records,
        chunks=chunks,
        report=report,
        previews=previews,
        store=store,
        notes=notes,
    )


def default_sample_paths() -> list[Path]:
    """The bundled sample files, in a stable demo order."""
    prefer = [
        SAMPLES_DIR / "forms" / "repair-order-lakeside-honda.jpg",
        SAMPLES_DIR / "forms" / "deal-recap-lakeside-toyota.jpg",
        SAMPLES_DIR / "forms" / "warranty-claim-lakeside-honda.jpg",
        SAMPLES_DIR / "mainframe" / "CUSTDEAL.DAT",
        SAMPLES_DIR / "exports" / "service-history-export.csv",
        SAMPLES_DIR / "exports" / "deal-register-export.xlsx",
        SAMPLES_DIR / "memos" / "gm-recall-memo.txt",
    ]
    existing = [p for p in prefer if p.is_file()]
    if existing:
        return existing
    # If generate hasn't been run with the preferred names, take whatever is there.
    found: list[Path] = []
    for pattern in (
        "forms/*.{png,jpg,jpeg,pdf}",
        "mainframe/*.DAT",
        "mainframe/*.dat",
        "exports/*.{csv,xlsx}",
        "memos/*.{txt,md}",
    ):
        found.extend(sorted(SAMPLES_DIR.glob(pattern)))
    # Path.glob doesn't expand {png,jpg} brace-style; do it simply:
    if not found:
        for sub, suffixes in (
            ("forms", (".png", ".jpg", ".jpeg", ".pdf")),
            ("mainframe", (".DAT", ".dat")),
            ("exports", (".csv", ".xlsx")),
            ("memos", (".txt", ".md")),
        ):
            folder = SAMPLES_DIR / sub
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.suffix in suffixes or path.suffix.lower() in {s.lower() for s in suffixes}:
                    found.append(path)
    return found


def ingest_samples(persist: bool = True, db_path: str | Path | None = None) -> PipelineResult:
    paths = default_sample_paths()
    copybook = SAMPLES_DIR / "mainframe" / "CUSTDEAL.CPY"
    return ingest_paths(
        paths,
        copybook_path=copybook if copybook.is_file() else None,
        persist=persist,
        db_path=db_path,
    )


def load_store(db_path: str | Path | None = None) -> VectorStore:
    store = VectorStore(db_path=db_path or INDEX_DB)
    store.load()
    return store
