"""Date, currency, VIN, and name normalization."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from ingestor.normalize import (
    make_vin,
    normalize_currency,
    normalize_date,
    normalize_name,
    normalize_vin,
    vin_ok,
)
from ingestor.samples import VIN_ANITA_ACCORD


class DateTests(unittest.TestCase):
    def test_common_us_and_iso_formats(self):
        expected = date(2026, 11, 24)
        for raw in (
            "11/24/26",
            "11/24/2026",
            "2026-11-24",
            "20261124",
            "24-NOV-2026",
            "Nov 24 2026",
            "November 24, 2026",
        ):
            self.assertEqual(normalize_date(raw), expected, raw)

    def test_two_digit_year_pivot(self):
        self.assertEqual(normalize_date("12/31/99"), date(1999, 12, 31))
        self.assertEqual(normalize_date("01/02/00"), date(2000, 1, 2))
        self.assertEqual(normalize_date("3/8/26"), date(2026, 3, 8))

    def test_excel_serial_and_integer_yyyymmdd(self):
        serial = (date(2026, 11, 24) - date(1899, 12, 30)).days
        self.assertEqual(normalize_date(serial), date(2026, 11, 24))
        self.assertEqual(normalize_date(20261124), date(2026, 11, 24))

    def test_unparseable_returns_none(self):
        self.assertIsNone(normalize_date("not-a-date"))
        self.assertIsNone(normalize_date(""))
        self.assertIsNone(normalize_date(None))


class CurrencyTests(unittest.TestCase):
    def test_dollars_commas_and_parentheses(self):
        self.assertEqual(normalize_currency("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(normalize_currency("(124.50)"), Decimal("-124.50"))
        self.assertEqual(normalize_currency("124.50-"), Decimal("-124.50"))
        self.assertEqual(normalize_currency("-$124.50"), Decimal("-124.50"))
        self.assertEqual(normalize_currency("USD 2150"), Decimal("2150.00"))
        self.assertEqual(normalize_currency("1234.5600"), Decimal("1234.56"))
        self.assertEqual(normalize_currency(2150), Decimal("2150.00"))

    def test_unparseable_returns_none(self):
        self.assertIsNone(normalize_currency("see jacket"))
        self.assertIsNone(normalize_currency("TBD"))


class VinAndNameTests(unittest.TestCase):
    def test_known_sample_vin_is_valid(self):
        self.assertTrue(vin_ok(VIN_ANITA_ACCORD))
        self.assertEqual(normalize_vin("1HG CV2F36 KA123456")[0], VIN_ANITA_ACCORD)
        self.assertEqual(normalize_vin(VIN_ANITA_ACCORD)[1], [])

    def test_length_and_check_digit_issues(self):
        vin, issues = normalize_vin("1HGCV2F36KA12345")
        self.assertTrue(any("length" in item for item in issues))
        # Flip the check digit on a known-good VIN.
        bad = VIN_ANITA_ACCORD[:8] + ("0" if VIN_ANITA_ACCORD[8] != "0" else "1") + VIN_ANITA_ACCORD[9:]
        _, issues = normalize_vin(bad)
        self.assertTrue(any("check digit" in item for item in issues))

    def test_make_vin_roundtrip(self):
        template = "1HGCV2F3XKA123456"
        vin = make_vin(template)
        self.assertTrue(vin_ok(vin))

    def test_names_flip_last_first_and_title_case(self):
        self.assertEqual(normalize_name("ROSALES, ANITA M"), "Anita M Rosales")
        self.assertEqual(normalize_name("anita   rosales"), "Anita Rosales")
        self.assertEqual(normalize_name("MCDONALD, JAMES"), "James McDonald")
        self.assertEqual(normalize_name("O'NEIL, MARY"), "Mary O'Neil")


if __name__ == "__main__":
    unittest.main()
