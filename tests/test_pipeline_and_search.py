"""Provenance, tabular cleaning, and search hits that point at the right source."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ingestor.extract_tabular import extract_csv, extract_excel
from ingestor.pipeline import ingest_paths
from ingestor.samples import (
    CLAIM_ANITA,
    VIN_ANITA_ACCORD,
    VIN_DENISE_RAV4,
    VIN_MARCUS_CIVIC,
    generate_all,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


def _ensure_samples() -> None:
    if not (SAMPLES / "mainframe" / "CUSTDEAL.DAT").is_file():
        generate_all()


class TabularTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_samples()

    def test_csv_normalizes_messy_dates_vins_and_amounts(self):
        records = extract_csv(SAMPLES / "exports" / "service-history-export.csv")
        ok = [r for r in records if r.status != "rejected"]
        anita = next(r for r in ok if r.fields.get("vin") == VIN_ANITA_ACCORD)
        self.assertEqual(anita.fields["customer_name"], "Anita M Rosales")
        self.assertEqual(anita.fields["date"], "2026-03-18")
        self.assertIn("1,847.22", anita.fields["amount"])
        marcus = next(r for r in ok if r.fields.get("ro_number") == "RO-184422")
        self.assertEqual(marcus.fields["date"], "2026-11-03")
        self.assertEqual(marcus.fields["vin"], VIN_MARCUS_CIVIC)
        rejected = [r for r in records if r.status == "rejected"]
        self.assertGreaterEqual(len(rejected), 1)
        reasons = " ".join((r.reject_reason or "") + " ".join(r.flags) for r in rejected + records)
        self.assertTrue(
            any("amount" in (r.reject_reason or "").lower() or "vin" in " ".join(r.flags).lower() for r in records),
            reasons,
        )

    def test_excel_reads_serial_dates_and_messy_headers(self):
        records = extract_excel(SAMPLES / "exports" / "deal-register-export.xlsx")
        denise = next(
            r for r in records if r.status != "rejected" and r.fields.get("vin") == VIN_DENISE_RAV4
        )
        self.assertEqual(denise.fields["customer_name"], "Denise Patel")
        self.assertEqual(denise.fields["date"], "2026-10-16")
        self.assertIn("2,150.00", denise.fields["amount"])
        rejected = [r for r in records if r.status == "rejected"]
        self.assertGreaterEqual(len(rejected), 1)


class SearchProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_samples()
        cls.tmp = tempfile.TemporaryDirectory(prefix="ingestor-index-")
        paths = [
            SAMPLES / "mainframe" / "CUSTDEAL.DAT",
            SAMPLES / "exports" / "service-history-export.csv",
            SAMPLES / "exports" / "deal-register-export.xlsx",
            SAMPLES / "memos" / "gm-recall-memo.txt",
        ]
        cls.result = ingest_paths(
            paths,
            copybook_path=SAMPLES / "mainframe" / "CUSTDEAL.CPY",
            persist=True,
            db_path=Path(cls.tmp.name) / "ingestor.sqlite",
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_quality_report_counts_rejects(self):
        report = self.result.report
        self.assertGreaterEqual(report.records_parsed, 8)
        self.assertGreaterEqual(report.records_rejected, 2)
        self.assertGreaterEqual(report.chunks_indexed, 8)
        reasons = " ".join(item["reason"] for item in report.rejects)
        self.assertTrue(
            "packed" in reasons.lower() or "Truncated" in reasons,
            reasons,
        )

    def test_search_for_anita_vin_cites_mainframe_and_memo(self):
        hits = self.result.store.search(f"warranty claim Anita Rosales VIN {VIN_ANITA_ACCORD}", k=8)
        self.assertTrue(hits, "expected at least one hit for Anita's VIN")
        sources = {hit.chunk.source_file for hit in hits}
        self.assertTrue(
            any("CUSTDEAL.DAT" in s for s in sources),
            f"mainframe missing from {sources}",
        )
        self.assertTrue(
            any("gm-recall-memo.txt" in s or "service-history" in s for s in sources),
            f"memo or csv missing from {sources}",
        )
        # A hit that mentions the VIN must carry provenance back to a record or line.
        vin_hits = [h for h in hits if VIN_ANITA_ACCORD in h.chunk.text]
        self.assertTrue(vin_hits)
        cited = vin_hits[0].chunk
        self.assertTrue(cited.citation())
        self.assertTrue(cited.source_file)
        self.assertTrue(cited.record_number is not None or cited.line_start is not None)

    def test_search_for_denise_front_gross_cites_the_spreadsheet(self):
        hits = self.result.store.search(
            "Denise Patel front gross RAV4 deal recap D-44821", k=6
        )
        self.assertTrue(hits)
        sources = {h.chunk.source_file for h in hits}
        self.assertTrue(
            any("deal-register-export.xlsx" in s or "CUSTDEAL.DAT" in s for s in sources),
            sources,
        )
        # The exact VIN should appear in at least one cited chunk.
        self.assertTrue(any(VIN_DENISE_RAV4 in h.chunk.text for h in hits))

    def test_search_for_marcus_ro_cites_the_csv(self):
        hits = self.result.store.search("repair order RO-184422 Marcus Webb oil leak Civic", k=6)
        self.assertTrue(hits)
        self.assertTrue(any("service-history-export.csv" in h.chunk.source_file for h in hits))
        self.assertTrue(any(VIN_MARCUS_CIVIC in h.chunk.text or "RO-184422" in h.chunk.text for h in hits))

    def test_sqlite_store_roundtrip_keeps_provenance(self):
        from ingestor.store import VectorStore

        reloaded = VectorStore(db_path=Path(self.tmp.name) / "ingestor.sqlite")
        reloaded.load()
        self.assertEqual(len(reloaded.chunks), len(self.result.chunks))
        hits = reloaded.search(CLAIM_ANITA, k=5)
        self.assertTrue(hits)
        self.assertTrue(any(CLAIM_ANITA in h.chunk.text for h in hits))


if __name__ == "__main__":
    unittest.main()
