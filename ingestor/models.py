"""Shared data types for the legacy ingestor demo."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal
from typing import Any


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    return str(value)


@dataclass
class FieldIssue:
    field: str
    raw: str
    reason: str


@dataclass
class ExtractedRecord:
    """One logical record or page pulled from a source file."""

    record_id: str
    source_file: str
    source_type: str
    raw_text: str
    cleaned_text: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw_fields: dict[str, str] = field(default_factory=dict)
    page: int | None = None
    record_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    ocr_confidence: float | None = None
    status: str = "ok"  # ok, rejected, review
    reject_reason: str | None = None
    flags: list[str] = field(default_factory=list)
    issues: list[FieldIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass
class Chunk:
    """A searchable passage with provenance back to the source file."""

    id: str
    text: str
    source_file: str
    source_type: str
    chunk_index: int
    page: int | None = None
    record_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    ocr_confidence: float | None = None
    record_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation(self) -> str:
        parts = [self.source_file]
        if self.page is not None:
            parts.append(f"page {self.page}")
        if self.record_number is not None:
            parts.append(f"record {self.record_number}")
        # Structured rows already cite a record number; don't repeat it as a line.
        duplicate_record = (
            self.record_number is not None
            and self.line_start == self.record_number
            and (self.line_end is None or self.line_end == self.line_start)
        )
        if self.line_start is not None and not duplicate_record:
            if self.line_end is not None and self.line_end != self.line_start:
                parts.append(f"lines {self.line_start}–{self.line_end}")
            else:
                parts.append(f"line {self.line_start}")
        if self.ocr_confidence is not None:
            parts.append(f"OCR {self.ocr_confidence:.0f}%")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["citation"] = self.citation()
        return _jsonable(payload)


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


@dataclass
class QualityReport:
    files_processed: int = 0
    records_parsed: int = 0
    records_rejected: int = 0
    records_for_review: int = 0
    chunks_indexed: int = 0
    by_source_type: dict[str, int] = field(default_factory=dict)
    rejects: list[dict[str, Any]] = field(default_factory=list)
    review_items: list[dict[str, Any]] = field(default_factory=list)
    field_issues: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))
