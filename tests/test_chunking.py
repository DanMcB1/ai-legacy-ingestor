"""Structure-aware chunking with overlap and provenance."""

from __future__ import annotations

import unittest

from ingestor.chunking import OVERLAP_CHARS, TARGET_CHARS, chunk_record, chunk_records
from ingestor.models import ExtractedRecord


def _record(**kwargs) -> ExtractedRecord:
    base = dict(
        record_id="memo::1",
        source_file="gm-recall-memo.txt",
        source_type="text",
        raw_text="",
        cleaned_text="",
        record_number=1,
        line_start=1,
    )
    base.update(kwargs)
    return ExtractedRecord(**base)


class ChunkingTests(unittest.TestCase):
    def test_structured_row_stays_one_chunk(self):
        record = _record(
            record_id="CUSTDEAL.DAT::r1",
            source_file="CUSTDEAL.DAT",
            source_type="mainframe",
            raw_text="CUST_NAME=ROSALES, ANITA M",
            cleaned_text="customer name: Anita M Rosales; vin: 1HGCV2F36KA123456",
            record_number=1,
            line_start=1,
            line_end=1,
        )
        chunks = chunk_record(record)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].source_file, "CUSTDEAL.DAT")
        self.assertEqual(chunks[0].source_type, "mainframe")
        self.assertEqual(chunks[0].record_number, 1)
        self.assertIn("1HGCV2F36KA123456", chunks[0].text)
        self.assertEqual(chunks[0].citation(), "CUSTDEAL.DAT, record 1")

    def test_rejected_records_are_not_chunked(self):
        record = _record(status="rejected", reject_reason="Truncated", cleaned_text="nope")
        self.assertEqual(chunk_record(record), [])

    def test_long_text_is_split_with_overlap(self):
        paragraphs = [f"Paragraph {i:02d} " + ("lakeside service history. " * 20) for i in range(8)]
        text = "\n\n".join(paragraphs)
        record = _record(cleaned_text=text, raw_text=text, line_end=text.count("\n") + 1)
        chunks = chunk_record(record)
        self.assertGreaterEqual(len(chunks), 2)
        # Each window should stay in a readable size band.
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), TARGET_CHARS + OVERLAP_CHARS + 80)
            self.assertEqual(chunk.source_file, "gm-recall-memo.txt")
            self.assertIsNotNone(chunk.line_start)
        # Overlap: some text from the end of chunk 0 should appear at the start of chunk 1.
        first_tail = chunks[0].text[-OVERLAP_CHARS:]
        overlap_token = first_tail.strip().split()[-4:]
        self.assertTrue(
            any(token and token in chunks[1].text for token in overlap_token),
            f"expected overlap between {chunks[0].text[-80]!r} and {chunks[1].text[:80]!r}",
        )

    def test_chunk_records_preserves_source_order(self):
        records = [
            _record(
                record_id=f"file.csv::r{i}",
                source_file="file.csv",
                source_type="csv",
                cleaned_text=f"row {i} vin ABC",
                record_number=i,
                line_start=i,
                line_end=i,
            )
            for i in (1, 2, 3)
        ]
        chunks = chunk_records(records)
        self.assertEqual([c.record_number for c in chunks], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
