"""Copybook layout, EBCDIC, and packed-decimal (COMP-3) decoding."""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from ingestor.copybook import (
    CopybookError,
    decode_comp3,
    decode_file,
    decode_record,
    encode_comp3,
    encode_file,
    encode_record,
    parse_copybook,
    parse_pic,
)
from ingestor.samples import COPYBOOK_SOURCE, MAINFRAME_ROWS, VIN_ANITA_ACCORD, generate_all

ROOT = Path(__file__).resolve().parents[1]


class PicAndPackedDecimalTests(unittest.TestCase):
    def test_comp3_byte_lengths(self):
        self.assertEqual(parse_pic("S9(9)V99", comp3=True).byte_length, 6)
        self.assertEqual(parse_pic("S9(7)V99", comp3=True).byte_length, 5)
        self.assertEqual(parse_pic("9(8)").byte_length, 8)
        self.assertEqual(parse_pic("X(30)").byte_length, 30)

    def test_comp3_roundtrip_positive_negative_and_zero(self):
        pic = parse_pic("S9(7)V99", comp3=True)
        for value in (
            Decimal("12345.67"),
            Decimal("-88.50"),
            Decimal("0.00"),
            Decimal("12.00"),
        ):
            encoded = encode_comp3(value, pic)
            self.assertEqual(len(encoded), 5)
            self.assertEqual(decode_comp3(encoded, pic), value)

    def test_comp3_sign_nibbles(self):
        pic = parse_pic("S9(7)V99", comp3=True)
        # 12345.67 -> 00 12 34 56 7C
        self.assertEqual(encode_comp3(Decimal("12345.67"), pic).hex(), "001234567c")
        self.assertEqual(encode_comp3(Decimal("-88.50"), pic).hex(), "000008850d")
        # Unsigned F sign
        unsigned = parse_pic("9(7)V99", comp3=True)
        self.assertTrue(encode_comp3(Decimal("12.00"), unsigned).hex().endswith("f"))

    def test_comp3_rejects_invalid_digit(self):
        pic = parse_pic("S9(7)V99", comp3=True)
        with self.assertRaises(CopybookError):
            decode_comp3(bytes.fromhex("0012aa7c00"), pic)


class CopybookLayoutTests(unittest.TestCase):
    def setUp(self):
        self.book = parse_copybook(COPYBOOK_SOURCE)

    def test_redefines_does_not_grow_the_record(self):
        self.assertEqual(self.book.record_length, 118)
        status = next(f for f in self.book.fields() if f.name == "CUST_STATUS")
        ctype = next(f for f in self.book.fields() if f.name == "CUST_TYPE")
        store = next(f for f in self.book.fields() if f.name == "STORE_ID")
        self.assertEqual(status.offset, ctype.offset)
        self.assertEqual(store.offset, status.offset + status.length)

    def test_occurs_expands_repeating_group(self):
        group = next(f for f in self.book.fields() if f.name == "VEHICLE_INFO")
        self.assertEqual(group.occurs, 2)
        self.assertEqual(group.length, 32)

    def test_ebcdic_and_comp3_record_roundtrip(self):
        row = MAINFRAME_ROWS[0]
        encoded = encode_record(self.book, row)
        self.assertEqual(len(encoded), 118)
        # Leading bytes are EBCDIC digits for CUST-ID 00018401 (0xF0...).
        self.assertEqual(encoded[:8], "00018401".encode("cp037"))
        decoded = decode_record(self.book, encoded)
        self.assertEqual(int(decoded["CUST_ID"]), 18401)
        self.assertEqual(decoded["CUST_NAME"], "ROSALES, ANITA M")
        self.assertEqual(decoded["CUST_STATUS"], "A")
        self.assertEqual(decoded["CUST_TYPE"], "A")
        self.assertEqual(decoded["VIN"], VIN_ANITA_ACCORD)
        self.assertEqual(decoded["GROSS_AMT"], Decimal("28450.00"))
        self.assertEqual(decoded["NET_AMT"], Decimal("26100.00"))
        self.assertEqual(int(decoded["VEHICLE_INFO"][0]["VEH_YEAR"]), 2019)
        self.assertEqual(decoded["VEHICLE_INFO"][0]["VEH_MAKE"], "HONDA")
        self.assertEqual(int(decoded["VEHICLE_INFO"][1]["VEH_YEAR"]), 2014)

    def test_negative_packed_amount_on_chargeback_row(self):
        row = MAINFRAME_ROWS[-1]
        decoded = decode_record(self.book, encode_record(self.book, row))
        self.assertEqual(decoded["NET_AMT"], Decimal("-125.00"))
        self.assertEqual(decoded["CUST_NAME"], "RUIZ, DAVID")

    def test_file_rejects_bad_pack_and_truncated_record(self):
        rows = encode_file(self.book, MAINFRAME_ROWS[:2])
        smashed = bytearray(encode_record(self.book, MAINFRAME_ROWS[0]))
        gross = next(f for f in self.book.fields() if f.name == "GROSS_AMT")
        smashed[gross.offset + 2] = 0xAA
        blob = rows + bytes(smashed) + b"\x00\x01\x02"
        ok, rejects = decode_file(self.book, blob)
        self.assertEqual(len(ok), 2)
        self.assertEqual(len(rejects), 2)
        reasons = " ".join(r["reason"] for r in rejects)
        self.assertIn("packed-decimal", reasons.lower())
        self.assertIn("Truncated", reasons)

    def test_bundled_dat_file_matches_the_copybook(self):
        dat = ROOT / "data" / "samples" / "mainframe" / "CUSTDEAL.DAT"
        if not dat.is_file():
            generate_all()
        ok, rejects = decode_file(self.book, dat.read_bytes())
        self.assertEqual(len(ok), 8)
        self.assertEqual(len(rejects), 2)
        anita = next(r for r in ok if r["VIN"] == VIN_ANITA_ACCORD)
        self.assertEqual(anita["GROSS_AMT"], Decimal("28450.00"))
        david = next(r for r in ok if "RUIZ" in r["CUST_NAME"])
        self.assertEqual(david["NET_AMT"], Decimal("-125.00"))


if __name__ == "__main__":
    unittest.main()
