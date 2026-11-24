"""OCR preprocessing and a realistic scan from the bundled sample forms."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ingestor.extract_ocr import deskew, ocr_image, tesseract_available
from ingestor.pipeline import ingest_paths
from ingestor.samples import VIN_ANITA_ACCORD, generate_all

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
WARRANTY = SAMPLES / "forms" / "warranty-claim-lakeside-honda.jpg"

HAS_TESSERACT = tesseract_available()


@unittest.skipUnless(HAS_TESSERACT, "Tesseract OCR is not installed")
class OcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WARRANTY.is_file():
            generate_all()

    def test_deskew_reduces_a_known_skew(self):
        image = Image.new("RGB", (800, 400), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        for i in range(8):
            draw.text((40, 30 + i * 40), "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 12345", fill=(0, 0, 0), font=font)
        skewed = image.rotate(3.0, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(255, 255, 255))
        _, angle = deskew(skewed, max_angle=5.0, step=0.25)
        # Deskew should rotate back toward level (a negative of the applied skew).
        self.assertGreater(abs(angle), 1.0)
        self.assertLess(abs(angle + 3.0), 1.5)

    def test_generated_line_is_readable_after_skew(self):
        image = Image.new("RGB", (1600, 900), (236, 226, 198))
        draw = ImageDraw.Draw(image)
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
        font = ImageFont.truetype(str(font_path), 36) if font_path.is_file() else ImageFont.load_default()
        lines = [
            "LAKESIDE AUTO GROUP  WARRANTY CLAIM",
            "CUSTOMER ANITA ROSALES",
            f"VIN {VIN_ANITA_ACCORD}",
            "CLAIM WTY-26-04418",
            "TRANSMISSION COOLER LINE",
        ]
        y = 80
        for line in lines:
            draw.text((60, y), line, fill=(20, 20, 20), font=font)
            y += 70
        skewed = image.rotate(1.5, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(236, 226, 198))
        page = ocr_image(skewed, page=1)
        compact = page.text.upper().replace(" ", "")
        self.assertTrue(page.text.strip(), "OCR returned no text")
        self.assertIn(VIN_ANITA_ACCORD, compact)
        self.assertIn("WTY-26-04418", compact)

    def test_warranty_scan_ocr_and_search_cite_the_source_page(self):
        if not WARRANTY.is_file():
            self.skipTest("sample warranty form is missing")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ingestor-ocr-") as tmp:
            result = ingest_paths(
                [WARRANTY],
                persist=True,
                db_path=Path(tmp) / "ingestor.sqlite",
            )
        self.assertTrue(result.records)
        record = result.records[0]
        self.assertEqual(record.source_type, "scan")
        self.assertEqual(record.page, 1)
        compact = (record.raw_text or "").upper().replace(" ", "")
        self.assertIn(VIN_ANITA_ACCORD, compact)
        self.assertIn("WTY-26-04418", compact)
        self.assertIn("COOLER", record.raw_text.upper())
        self.assertIsNotNone(record.ocr_confidence)
        self.assertGreater(record.ocr_confidence, 60)
        hits = result.store.search("warranty claim transmission cooler line Anita Rosales", k=5)
        self.assertTrue(hits)
        top = hits[0].chunk
        self.assertEqual(top.source_file, WARRANTY.name)
        self.assertEqual(top.page, 1)
        self.assertIn("page 1", top.citation())
        self.assertIn("OCR", top.citation())


if __name__ == "__main__":
    unittest.main()
