"""Structure-aware chunking with overlap, preserving source provenance."""

from __future__ import annotations

import re

from .models import Chunk, ExtractedRecord

# Narrative / OCR pages are packed to about this many characters.
TARGET_CHARS = 700
OVERLAP_CHARS = 140
MIN_CHARS = 60


def _paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))]
    return [p for p in parts if p]


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


def _pack_with_overlap(units: list[str], target: int = TARGET_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Pack units into windows of about ``target`` characters, with overlap."""
    if not units:
        return []
    packed: list[str] = []
    buf: list[str] = []
    size = 0
    for unit in units:
        extra = len(unit) + (2 if buf else 0)
        if buf and size + extra > target:
            packed.append("\n\n".join(buf) if any("\n" in u for u in buf) else " ".join(buf))
            # Keep a short tail of the previous window as overlap.
            joiner = "\n\n" if any("\n" in u for u in buf) else " "
            joined = joiner.join(buf)
            tail_text = joined[-overlap:].strip() if overlap else ""
            buf = ([tail_text] if tail_text else []) + [unit]
            size = sum(len(u) for u in buf)
        else:
            buf.append(unit)
            size += extra
    if buf:
        packed.append("\n\n".join(buf) if any("\n" in u for u in buf) else " ".join(buf))
    # Merge a trailing stub into the previous chunk, keeping overlap meaningful.
    if len(packed) >= 2 and len(packed[-1]) < MIN_CHARS:
        packed[-2] = packed[-2] + "\n\n" + packed[-1]
        packed.pop()
    return packed


def _base_chunk(record: ExtractedRecord, index: int, text: str, **overrides) -> Chunk:
    data = dict(
        id=f"{record.record_id}::c{index}",
        text=text.strip(),
        source_file=record.source_file,
        source_type=record.source_type,
        chunk_index=index,
        page=record.page,
        record_number=record.record_number,
        line_start=record.line_start,
        line_end=record.line_end,
        ocr_confidence=record.ocr_confidence,
        record_id=record.record_id,
        metadata={"status": record.status, "flags": list(record.flags)},
    )
    data.update(overrides)
    return Chunk(**data)


def chunk_record(record: ExtractedRecord) -> list[Chunk]:
    """Split one extracted record into searchable passages.

    Structured rows (mainframe, CSV, Excel) stay as one chunk each, so a
    citation points at a single record. Long OCR pages and memos are packed
    into overlapping windows so a search hit is still a readable passage.
    """
    if record.status == "rejected":
        return []
    text = (record.cleaned_text or record.raw_text or "").strip()
    if not text:
        return []

    if record.source_type in {"mainframe", "csv", "excel"}:
        return [_base_chunk(record, 0, text)]

    # Prefer paragraph windows; fall back to lines if the memo is one block.
    units = _paragraphs(text)
    if len(units) <= 1:
        units = _lines(text) or [text]
    pieces = _pack_with_overlap(units)
    if not pieces:
        pieces = [text]

    chunks: list[Chunk] = []
    # Approximate line numbers for narrative windows.
    all_lines = _lines(text)
    cursor = record.line_start or 1
    for index, piece in enumerate(pieces):
        piece_lines = _lines(piece)
        start = cursor
        end = start + max(0, len(piece_lines) - 1)
        # Overlap means the next window starts earlier than ``end``.
        if index < len(pieces) - 1 and piece_lines:
            overlap_lines = max(1, len(piece_lines) // 5)
            cursor = max(start, end - overlap_lines + 1)
        else:
            cursor = end + 1
        # Clamp to the record's known line range when we have it.
        if record.line_end is not None:
            end = min(end, record.line_end)
        chunks.append(
            _base_chunk(
                record,
                index,
                piece,
                line_start=start,
                line_end=end if all_lines else record.line_end,
            )
        )
    return chunks


def chunk_records(records: list[ExtractedRecord]) -> list[Chunk]:
    out: list[Chunk] = []
    for record in records:
        out.extend(chunk_record(record))
    return out
