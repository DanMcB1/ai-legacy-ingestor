"""Build the data-quality report: parsed, rejected, and low-confidence items."""

from __future__ import annotations

from collections import Counter

from .models import ExtractedRecord, QualityReport


def build_report(
    records: list[ExtractedRecord],
    chunk_count: int = 0,
    files: list[str] | None = None,
    notes: list[str] | None = None,
) -> QualityReport:
    parsed = [r for r in records if r.status != "rejected"]
    rejected = [r for r in records if r.status == "rejected"]
    review = [r for r in records if r.status == "review"]
    by_type = Counter(r.source_type for r in parsed)

    field_issues = []
    for record in records:
        for issue in record.issues:
            field_issues.append(
                {
                    "source_file": record.source_file,
                    "record_number": record.record_number,
                    "page": record.page,
                    "field": issue.field,
                    "raw": issue.raw,
                    "reason": issue.reason,
                }
            )

    return QualityReport(
        files_processed=len(files or {r.source_file for r in records}),
        records_parsed=len(parsed),
        records_rejected=len(rejected),
        records_for_review=len(review),
        chunks_indexed=chunk_count,
        by_source_type=dict(by_type),
        rejects=[
            {
                "source_file": r.source_file,
                "record_number": r.record_number,
                "page": r.page,
                "reason": r.reject_reason or "rejected",
                "raw": (r.raw_text or "")[:240],
            }
            for r in rejected
        ],
        review_items=[
            {
                "source_file": r.source_file,
                "record_number": r.record_number,
                "page": r.page,
                "ocr_confidence": r.ocr_confidence,
                "flags": list(r.flags),
                "preview": (r.cleaned_text or r.raw_text or "")[:240],
            }
            for r in review
        ],
        field_issues=field_issues,
        notes=list(notes or []),
    )
